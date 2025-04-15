import os
import asyncio
import io
import typing
from dotenv import load_dotenv

import discord
from discord.ext import commands
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from utils import (
    get_prefix, is_admin, is_channel_allowed,
    perform_toggle_natural, perform_reset_channel_ai, perform_clear_history,
    request_confirmation
)
from core.config import (
    config_manager, DEFAULT_GUILD_CONFIG, DEFAULT_AI_SETTINGS,
    LANGUAGE_EXTENSIONS, MAX_ATTACHMENT_SIZE_BYTES, DEFAULT_FILE_EXTENSION
)
from core.contexts import context_manager, ChannelContext, MODEL_INPUT_TOKEN_LIMIT, MODEL_NAME_USED

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN: print("Error: DISCORD_TOKEN no configurado en .env"); exit()
if not GEMINI_API_KEY: print("Error: GEMINI_API_KEY no configurado en .env"); exit()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
bot.config = config_manager
bot.contexts = context_manager

async def _should_ignore_message(message: discord.Message, bot: commands.Bot) -> bool:
    if message.author == bot.user or message.author.bot:
        return True
    if not message.guild:
        return True
    return False

async def _check_processing_permissions(message: discord.Message, bot: commands.Bot) -> typing.Tuple[bool, str | None]:
    guild_id = message.guild.id
    guild_cfg = config_manager.get_guild_config(guild_id)
    is_caller_admin = is_admin(message.author)

    bot_enabled_for_users = guild_cfg.get('bot_enabled_for_users', True)
    if not is_caller_admin and not bot_enabled_for_users:
        return False, None

    if not is_caller_admin:
        if not is_channel_allowed(guild_id, message.channel.id):
            return False, None

    channel_id = message.channel.id
    channel_context = await context_manager.get_channel_ctx(channel_id)
    is_mention = bot.user.mentioned_in(message)
    user_text_content = message.content
    stripped_content = None

    should_process_gemini = False
    if is_mention:
        stripped_content = message.content.lstrip(f"<@!{bot.user.id}>").lstrip(f"<@{bot.user.id}>").strip()
        if stripped_content or message.attachments:
            should_process_gemini = True
    elif channel_context.settings.get('natural_conversation', False):
        should_process_gemini = True
        stripped_content = message.content

    return should_process_gemini, stripped_content

async def _handle_admin_menu_trigger(message: discord.Message, bot: commands.Bot, is_mention: bool, stripped_content: str) -> bool:
    if is_mention and not stripped_content and not message.attachments:
        if is_admin(message.author):
            await show_menu(message.channel, message.author, bot)
            return True
        else:
            await message.channel.send("ℹ️ Mencióname seguido de tu pregunta o adjunta un archivo.", delete_after=15)
            return True
    return False

async def _prepare_llm_input_parts(message: discord.Message, text_content: str | None) -> typing.List[dict]:
    parts = []
    author_name = message.author.display_name
    author_id = message.author.id

    if text_content and text_content.strip():
        text_for_llm = f"{author_name} (ID: {author_id}): {text_content.strip()}"
        parts.append({'text': text_for_llm})

    attachments_to_process = []
    processed_attachment_info = []

    if message.attachments:
        typing_task = asyncio.create_task(message.channel.trigger_typing())

        for attachment in message.attachments:
            is_text_or_code = attachment.content_type and attachment.content_type.startswith('text/') \
                              or attachment.filename.lower().endswith(tuple(LANGUAGE_EXTENSIONS.keys()))
            is_image = attachment.content_type and attachment.content_type.startswith('image/')

            if is_text_or_code or is_image:
                if attachment.size > MAX_ATTACHMENT_SIZE_BYTES:
                    await message.channel.send(f"⚠️ Archivo '{attachment.filename}' demasiado grande (máx {MAX_ATTACHMENT_SIZE_BYTES // 1024 // 1024}MB).")
                    continue
                attachments_to_process.append(attachment)
            else:
                await message.channel.send(f"ℹ️ Archivo '{attachment.filename}' ignorado (tipo no soportado: {attachment.content_type}).")

        for attachment in attachments_to_process:
            try:
                file_bytes = await attachment.read()
                mime_type = attachment.content_type
                is_image = mime_type and mime_type.startswith('image/')
                is_text_or_code = mime_type and mime_type.startswith('text/') \
                                  or attachment.filename.lower().endswith(tuple(LANGUAGE_EXTENSIONS.keys()))

                if is_image:
                    parts.append({'inline_data': {'mime_type': mime_type, 'data': file_bytes}})
                    processed_attachment_info.append(f"{attachment.filename} (imagen)")
                elif is_text_or_code:
                    file_content = file_bytes.decode('utf-8', errors='replace')
                    file_context_text = (
                        f"\n\n--- Contenido de {attachment.filename} (adjuntado por {author_name} ID: {author_id}) ---\n"
                        f"{file_content}\n"
                        f"--- Fin de {attachment.filename} ---"
                    )
                    parts.append({'text': file_context_text})
                    processed_attachment_info.append(f"{attachment.filename} (texto/código)")

            except Exception as e:
                print(f"Error procesando adjunto {attachment.filename}: {e}")
                await message.channel.send(f"⚠️ Error al leer '{attachment.filename}'.")

        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    if not parts and message.attachments and not processed_attachment_info:
         await message.channel.send("ℹ️ No se procesó ningún adjunto válido y no había texto.")
         return []

    if not parts:
        print(f"Advertencia: No se encontraron partes válidas para procesar en mensaje {message.id}. IA no llamada.")
        return []

    return parts


def _update_and_trim_history(channel_context: ChannelContext, user_message_part: dict):
    MAX_HISTORY_LEN = 10
    channel_context.history.append(user_message_part)
    if len(channel_context.history) > MAX_HISTORY_LEN:
        channel_context.history = channel_context.history[-MAX_HISTORY_LEN:]


async def _call_gemini_api(channel_context: ChannelContext, message: discord.Message) -> typing.Tuple[genai.types.GenerateContentResponse | None, genai.GenerativeModel | None]:
    model = channel_context.create_model(message.guild.id)
    if model is None:
        await message.channel.send("⚠️ Error crítico: No se pudo configurar el modelo de IA.")
        return None, None

    api_response = None
    try:
        async with message.channel.typing():
            contents_for_api = []
            for msg in channel_context.history:
                msg_parts = msg.get('parts', [])
                if isinstance(msg_parts, dict): msg_parts = [msg_parts]
                if msg.get('role') and msg_parts:
                    contents_for_api.append({'role': msg.get('role'), 'parts': msg_parts})

            if not contents_for_api or contents_for_api[-1]['role'] != 'user':
                print("Advertencia: Intento de generar respuesta sin mensaje de usuario válido al final del historial.")
                return None, None

            api_response = await model.generate_content_async(contents=contents_for_api)

            if channel_context.stop_requested:
                print("Generación detenida por petición del usuario.")
                await message.channel.send("🛑 Generación detenida.")
                return None, model

            return api_response, model

    except ValueError as ve:
        feedback = getattr(api_response, 'prompt_feedback', None) if api_response else None
        reason = getattr(feedback, 'block_reason', 'Desconocida') if feedback else 'Desconocida'
        safety_ratings_str = ""
        if feedback and hasattr(feedback, 'safety_ratings'):
            ratings = [f"{r.category.name}: {r.probability.name}" for r in feedback.safety_ratings]
            safety_ratings_str = f" (Ratings: {', '.join(ratings)})" if ratings else ""
        print(f"Respuesta bloqueada. Razón: {reason}{safety_ratings_str}")
        await message.channel.send(f"⚠️ Mi respuesta fue bloqueada por seguridad (Razón: {reason}). Intenta reformular tu pregunta.{safety_ratings_str}")
        return None, None
    except genai.types.generation_types.StopCandidateException as sce:
         print(f"Generación detenida por el modelo: {sce}")
         await message.channel.send("⚠️ La generación fue detenida por el modelo (posiblemente contenido inseguro o fin inesperado).")
         return None, None
    except asyncio.CancelledError:
        print("Tarea de generación cancelada (likely due to typing timeout or external cancel).")
        return None, None
    except Exception as e:
        print(f"Error inesperado llamando a Gemini API: {type(e).__name__} - {e}")
        await message.channel.send("⚠️ Error inesperado procesando tu solicitud con la IA.")
        return None, None


def _extract_response_text(api_response: genai.types.GenerateContentResponse) -> str | None:
    try:
        return api_response.text
    except AttributeError:
         print(f"Error: Atributo 'text' no encontrado en respuesta API: {api_response}")
         return None
    except Exception as resp_err:
         print(f"Error inesperado accediendo a texto de respuesta API: {resp_err}")
         return None


def _update_history_with_model_response(channel_context: ChannelContext, response_text: str):
    if not channel_context.history or channel_context.history[-1]['role'] != 'model':
        channel_context.history.append({'role': 'model', 'parts': [{'text': response_text}]})
    else:
        print("Advertencia: Se intentó añadir respuestas de modelo consecutivas. Ignorado.")


async def _calculate_token_info(model: genai.GenerativeModel, api_response: genai.types.GenerateContentResponse, channel_context: ChannelContext) -> str:
    prompt_tokens = None
    total_tokens = None
    token_info_str = ""

    try:
        if hasattr(api_response, 'usage_metadata') and hasattr(api_response.usage_metadata, 'prompt_token_count'):
            prompt_tokens = api_response.usage_metadata.prompt_token_count
        else:
            print("Advertencia: No se encontró prompt_token_count en usage_metadata.")

        if channel_context.history:
            contents_for_total_count = []
            for msg in channel_context.history:
                msg_parts = msg.get('parts', [])
                if isinstance(msg_parts, dict): msg_parts = [msg_parts]
                if msg.get('role') and msg_parts:
                    contents_for_total_count.append({'role': msg.get('role'), 'parts': msg_parts})

            if contents_for_total_count:
                if contents_for_total_count[-1]['role'] == 'model':
                    count_response = await asyncio.to_thread(model.count_tokens, contents_for_total_count)
                    total_tokens = count_response.total_tokens
                else:
                    print("Advertencia: Último mensaje en historial no es del modelo al contar tokens totales.")

    except Exception as e:
        print(f"Error obteniendo conteo de tokens: {e}")

    prompt_str = f"{prompt_tokens}" if prompt_tokens is not None else "N/A"
    total_str = f"{total_tokens}" if total_tokens is not None else "N/A"
    max_str = f"{MODEL_INPUT_TOKEN_LIMIT}" if MODEL_INPUT_TOKEN_LIMIT is not None else "?"
    if prompt_tokens is not None or total_tokens is not None:
        token_info_str = f"\n\n*Tokens (prompt/total): `{prompt_str} / {total_str}/{max_str}`*"

    return token_info_str


async def _send_discord_response(message: discord.Message, response_text: str, token_info_str: str):
    MAX_MSG_LEN = 2000
    MAX_INFO_LEN = len(token_info_str)
    sent_as_file = False
    stripped_response_text = response_text.strip()

    if stripped_response_text.startswith("```") and '\n' in stripped_response_text:
        try:
            first_line_end = stripped_response_text.find('\n')
            language_hint = stripped_response_text[3:first_line_end].strip().lower()
            code_start_index = first_line_end + 1
            closing_marker_pos = stripped_response_text.rfind("\n```")
            if closing_marker_pos == -1 and stripped_response_text.endswith("```"):
                 closing_marker_pos = len(stripped_response_text) - 3

            code_content = None
            if closing_marker_pos > code_start_index:
                code_content = stripped_response_text[code_start_index:closing_marker_pos].strip()
            else:
                print(f"Advertencia: Bloque de código iniciado pero sin cierre claro ('\\n```'). Enviando como texto.")

            if code_content:
                extension = LANGUAGE_EXTENSIONS.get(language_hint, DEFAULT_FILE_EXTENSION)
                filename = f"response_code{extension}"
                code_bytes = io.BytesIO(code_content.encode('utf-8'))
                discord_file = discord.File(fp=code_bytes, filename=filename)

                caption = f"Respuesta con código ({language_hint if language_hint else 'desconocido'}):{token_info_str}"
                if len(caption) > MAX_MSG_LEN:
                    caption = caption[:MAX_MSG_LEN-3] + "..."

                await message.channel.send(caption, file=discord_file)
                sent_as_file = True

        except Exception as file_error:
            print(f"Error procesando/enviando código como archivo: {file_error}. Enviando como texto.")
            sent_as_file = False

    if not sent_as_file:
        if not stripped_response_text:
            await message.channel.send("..." + token_info_str)
            return

        available_len_last_msg = MAX_MSG_LEN - MAX_INFO_LEN

        if len(response_text) <= available_len_last_msg:
            await message.channel.send(response_text + token_info_str)
        else:
            parts_to_send = []
            current_part = ""
            for line in response_text.splitlines(keepends=True):
                if len(current_part) + len(line) <= (MAX_MSG_LEN - 10):
                    current_part += line
                else:
                    parts_to_send.append(current_part)
                    current_part = line
                    while len(current_part) > (MAX_MSG_LEN - 10):
                        parts_to_send.append(current_part[:MAX_MSG_LEN - 10])
                        current_part = current_part[MAX_MSG_LEN - 10:]

            if current_part:
                parts_to_send.append(current_part)

            for i, part_text in enumerate(parts_to_send[:-1]):
                await message.channel.send(f"{part_text.strip()}...")

            last_part_text = parts_to_send[-1]
            if len(last_part_text) + MAX_INFO_LEN <= MAX_MSG_LEN:
                await message.channel.send(last_part_text.strip() + token_info_str)
            else:
                await message.channel.send(last_part_text.strip()[:MAX_MSG_LEN - 3] + "...")
                if MAX_INFO_LEN <= MAX_MSG_LEN:
                    await message.channel.send(token_info_str)
                else:
                    await message.channel.send("*(Info de tokens demasiado larga para mostrar)*")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.author.send("Este comando solo se puede usar dentro de un servidor.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"🚫 {error}", delete_after=15)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❓ Faltan argumentos. Uso: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Argumento inválido: {error}")
    elif isinstance(error, commands.CommandInvokeError):
        original_error = error.original
        print(f'Error en comando {ctx.command.qualified_name}: {type(original_error).__name__} - {original_error}')
        await ctx.send("⚠️ Ocurrió un error inesperado al ejecutar el comando.")
    else:
        print(f'Error no manejado en comando {ctx.command.qualified_name}: {type(error).__name__} - {error}')
        await ctx.send("⚠️ Ocurrió un error desconocido.")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    default_prefix = DEFAULT_GUILD_CONFIG['command_prefix']
    await bot.change_presence(activity=discord.Game(name=f"Mencióname + tu mensaje para interactuar!"))
    print(f"Bot listo. Prefijo por defecto: {default_prefix}.")

@bot.event
async def on_message(message: discord.Message):
    if await _should_ignore_message(message, bot):
        return

    ctx_check = await bot.get_context(message)
    if ctx_check.valid:
        await bot.process_commands(message)
        return

    is_mention = bot.user.mentioned_in(message)
    stripped_content = None
    if is_mention:
        stripped_content = message.content.lstrip(f"<@!{bot.user.id}>").lstrip(f"<@{bot.user.id}>").strip()
    else:
        stripped_content = message.content

    if await _handle_admin_menu_trigger(message, bot, is_mention, stripped_content):
        return

    should_process_ai, ai_content = await _check_processing_permissions(message, bot)

    if not should_process_ai:
        return

    channel_id = message.channel.id
    channel_context = await context_manager.get_channel_ctx(channel_id)
    channel_context.stop_requested = False

    try:
        llm_parts = await _prepare_llm_input_parts(message, ai_content)
        if not llm_parts:
            return

        user_message_part = {'role': 'user', 'parts': llm_parts}
        _update_and_trim_history(channel_context, user_message_part)

        api_response, model = await _call_gemini_api(channel_context, message)

        if api_response is None or model is None:
            if channel_context.history and channel_context.history[-1] is user_message_part:
                 print("Popping user message from history due to API call failure/block.")
                 channel_context.history.pop()
            return

        response_text = _extract_response_text(api_response)
        if response_text is None:
            await message.channel.send("⚠️ Ocurrió un error al procesar la respuesta del modelo.")
            return

        _update_history_with_model_response(channel_context, response_text)
        token_info_str = await _calculate_token_info(model, api_response, channel_context)

        await _send_discord_response(message, response_text, token_info_str)

    except Exception as e:
        print(f"Error general no capturado en on_message para mensaje {message.id}: {type(e).__name__} - {str(e)}")
        try:
            await message.channel.send("⚠️ Ocurrió un error inesperado al procesar tu mensaje.")
        except discord.Forbidden:
            pass
        if 'channel_context' in locals() and channel_context and channel_context.history and channel_context.history[-1]['role'] == 'user':
            print("Popping user message from history due to general exception.")
            channel_context.history.pop()
    finally:
        if 'channel_context' in locals() and channel_context:
            channel_context.stop_requested = False

async def show_menu(channel: discord.TextChannel, author: discord.Member, bot: commands.Bot):
    if not is_admin(author):
        await channel.send("🚫 No tienes permiso para usar este menú.", delete_after=10)
        return

    guild_cfg = config_manager.get_guild_config(channel.guild.id)
    current_prefix = guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])
    channel_context = await context_manager.get_channel_ctx(channel.id)

    embed = discord.Embed(title=f"🔧 Menú de Configuración", color=0x00aaff)

    embed.add_field(name=f"Configuración de IA para el canal {channel.mention}:", value="\u200b", inline=False)
    personality_display = channel_context.settings['personality']
    if len(personality_display) > 150: personality_display = personality_display[:147] + "..."
    embed.add_field(name="🇦 Personalidad", value=f"```{personality_display if personality_display else 'Default'}```", inline=False)
    embed.add_field(name="🇧 Temperatura", value=f"`{channel_context.settings['temperature']}`", inline=True)
    natural_conv_state = channel_context.settings.get('natural_conversation', False)
    embed.add_field(name="🇨 Conversación Natural", value="✅ Activa" if natural_conv_state else "☑️ Desactivada", inline=True)
    embed.add_field(name="🇩 Limpiar Historial", value="Iniciar una conversación como nueva", inline=True)
    embed.add_field(name="🇪 Restablecer configuración", value="Volver a los valores por defecto", inline=True)
    embed.add_field(name="", value="\u200b", inline=False)

    embed.add_field(name=f"Configuración de IA para el servidor ({channel.guild.name}):", value="\u200b", inline=False)
    bot_enabled_str = "✅ Habilitado" if guild_cfg.get('bot_enabled_for_users', True) else "☑️ Deshabilitado"
    embed.add_field(name="🇫 Disponibilidad para Usuarios", value=f"{bot_enabled_str} (`{current_prefix}(enable/disable)bot`)", inline=False)
    admin_role_id = guild_cfg.get('admin_role_id')
    admin_role_str = "No establecido"
    if admin_role_id:
        role_obj = channel.guild.get_role(admin_role_id)
        admin_role_str = f"{role_obj.mention}" if role_obj else f"ID {admin_role_id} (No enc.)"
    embed.add_field(name="🇬 Rol de Administración", value=f"{admin_role_str} (`{current_prefix}setadminrole` siendo el dueño del servidor)", inline=False)
    allowed_channels_str = "Todos" if not guild_cfg.get('allowed_channel_ids') else f"{len(guild_cfg.get('allowed_channel_ids', []))} específ."
    embed.add_field(name="🇭 Canales Permitidos (Usuarios)", value=f"{allowed_channels_str} (`{current_prefix}listchannels`)", inline=False)
    embed.add_field(name="🇮 Prefijo del Servidor", value=f"El prefijo actual es: `{current_prefix}` (`{current_prefix}setprefix`)", inline=False)

    embed.add_field(name="", value="\u200b", inline=False)
    embed.set_footer(text="Reacciona para ajustar IA del canal (🇦-🇪) o IA del servidor (🇫-🇮)")

    menu_msg = None
    try:
        menu_msg = await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"Error: Permiso denegado para enviar menú en {channel.id}"); return
    except Exception as e:
        print(f"Error enviando menú: {e}"); return

    menu_emojis = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '❌']
    try:
        for emoji in menu_emojis:
            await menu_msg.add_reaction(emoji)
    except discord.NotFound:
        print(f"Mensaje de menú {menu_msg.id} borrado mientras se añadían reacciones.")
        return
    except discord.Forbidden:
        print(f"Error: Permiso denegado para añadir reacciones en {channel.id}")
        try: await menu_msg.delete()
        except: pass
        return
    except Exception as e:
        print(f"Error añadiendo reacción {emoji}: {e}")
        return

    def check_menu(reaction, user):
        return user == author and reaction.message and reaction.message.id == menu_msg.id and str(reaction.emoji) in menu_emojis

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=120.0, check=check_menu)
        selected_emoji = str(reaction.emoji)

        try:
            if menu_msg:
                 await menu_msg.remove_reaction(selected_emoji, author)
        except (discord.Forbidden, discord.NotFound):
            pass

        delete_menu_after_action = True

        if not menu_msg:
             print("Error: menu_msg es None después de wait_for.")
             return
        ctx = await bot.get_context(menu_msg)
        ctx.author = author
        ctx.channel = channel

        if selected_emoji == '❌':
             await channel.send("Menú cerrado.", delete_after=10)

        elif selected_emoji == '🇦':
            prompt_msg = await channel.send(f"✍️ Escribe la nueva **personalidad** para la IA en este canal (máximo de 300 caracteres, 'default' para restablecer). Tienes 90 segundos.")
            def check_msg(msg): return msg.author == author and msg.channel == channel
            try:
                user_response_msg = await bot.wait_for('message', timeout=90.0, check=check_msg)
                new_value = user_response_msg.content.strip()
                if new_value:
                    if new_value.lower() == 'default':
                         channel_context.settings['personality'] = DEFAULT_AI_SETTINGS['personality']
                         await channel.send(f"✅ Personalidad restablecida a default para {channel.mention}.", delete_after=15)
                    elif len(new_value) > 300:
                        await channel.send("⚠️ Descripción demasiado larga (máximo de 300). No se guardó.", delete_after=10)
                    else:
                        channel_context.settings['personality'] = new_value
                        display_personality = new_value if len(new_value) <= 100 else new_value[:97] + "..."
                        await channel.send(f"✅ Personalidad actualizada para {channel.mention}:\n```\n{display_personality}\n```", delete_after=15)
                    try: await user_response_msg.delete()
                    except (discord.Forbidden, discord.NotFound): pass
                else:
                    await channel.send("⚠️ No se proporcionó descripción. No se guardó.", delete_after=10)
            except asyncio.TimeoutError:
                await channel.send(f"⏰ Tiempo agotado para establecer personalidad.", delete_after=10)
            finally:
                 try:
                     if prompt_msg: await prompt_msg.delete()
                 except (discord.Forbidden, discord.NotFound): pass

        elif selected_emoji == '🇧':
             await channel.send(f"ℹ️ Para ajustar la **temperatura** (creatividad) en {channel.mention}, usa:\n`{current_prefix}settemperature <0.0-1.0>` (ej: `{current_prefix}settemperature 0.7`)", delete_after=25)
             delete_menu_after_action = False

        elif selected_emoji == '🇨':
            await perform_toggle_natural(ctx)

        elif selected_emoji == '🇪':
            await perform_reset_channel_ai(ctx)

        elif selected_emoji == '🇩':
            await perform_clear_history(ctx)

        elif selected_emoji in ['🇫', '🇬', '🇭', '🇮']:
             await channel.send(f"ℹ️ Esta sección muestra información del servidor. Usa los comandos `{current_prefix}...` (ver `{current_prefix}help`) para gestionar la configuración global.", delete_after=20)
             delete_menu_after_action = False

    except asyncio.TimeoutError:
        try:
             await channel.send("⏰ Menú interactivo cerrado por inactividad.", delete_after=10)
        except discord.Forbidden: pass
        delete_menu_after_action = True
    except discord.Forbidden:
         print(f"Error de permisos durante menú interactivo en canal {channel.id}")
         delete_menu_after_action = True
    except Exception as e:
        print(f"Error inesperado en menú interactivo: {type(e).__name__} - {e}")
        try:
            await channel.send("⚠️ Ocurrió un error con el menú.", delete_after=10)
        except discord.Forbidden:
            pass
        delete_menu_after_action = True
    finally:
        if delete_menu_after_action and menu_msg:
            try:
                await menu_msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

async def load_extensions():
    print("Cargando extensiones (Cogs)...")
    cogs_path = './cogs'
    if not os.path.isdir(cogs_path):
        print(f"Error: Directorio de Cogs '{cogs_path}' no encontrado.")
        return

    for filename in os.listdir(cogs_path):
        if filename.endswith('.py') and not filename.startswith('_'):
            extension_name = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(extension_name)
                print(f'-> Extensión cargada: {filename[:-3]}')
            except commands.ExtensionNotFound:
                print(f"Error: Extensión '{extension_name}' no encontrada.")
            except commands.ExtensionAlreadyLoaded:
                print(f"Advertencia: Extensión '{extension_name}' ya estaba cargada.")
            except commands.NoEntryPointError:
                print(f"Error: Extensión '{extension_name}' no tiene función 'setup'.")
            except commands.ExtensionFailed as e:
                print(f'Error cargando extensión {filename[:-3]}: {type(e.original).__name__} - {e.original}')
            except Exception as e:
                 print(f'Error inesperado cargando extensión {filename[:-3]}: {type(e).__name__} - {e}')
    print("Carga de extensiones finalizada.")

async def main():
    async with bot:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            print("Gemini configurado.")
        except Exception as e:
            print(f"Error configurando Gemini en main(): {e}")

        await load_extensions()

        try:
            print("Iniciando bot...")
            await bot.start(DISCORD_TOKEN)
        except discord.PrivilegedIntentsRequired:
             print("\nError: Falta una o más Intents Privilegiadas (probablemente Members y/o Message Content).")
             print("Ve al Portal de Desarrolladores de Discord -> Tu Aplicación -> Bot -> Privileged Gateway Intents y actívalas.")
        except discord.LoginFailure:
             print("\nError: Token de Discord inválido.")
        except Exception as e:
             print(f"Error fatal durante inicio del bot: {type(e).__name__} - {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido manualmente.")
