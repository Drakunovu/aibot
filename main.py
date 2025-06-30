import os
import asyncio
import io
import typing
from dotenv import load_dotenv

import discord
from discord.ext import commands
from openai import OpenAIError
from openai.types.chat import ChatCompletion

from utils import get_prefix, is_admin, is_channel_allowed
from core.config import config_manager, DEFAULT_GUILD_CONFIG, LANGUAGE_EXTENSIONS, MAX_ATTACHMENT_SIZE_BYTES, DEFAULT_FILE_EXTENSION
from core.contexts import context_manager, ChannelContext
from core.openrouter_models import model_info_manager

# --- Initial Setup ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    print("Error Crítico: DISCORD_TOKEN no está configurado en el archivo .env")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# --- Event Handlers ---

@bot.event
async def on_ready():
    """Event handler for when the bot successfully connects to Discord."""
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Mencióname para charlar!"))

@bot.event
async def on_message(message: discord.Message):
    """Main event handler that processes every message the bot can see."""
    if message.author.bot or not message.guild:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    should_process, content = await _should_process_ai(message)
    if not should_process:
        return

    channel_context = await context_manager.get_channel_ctx(message.channel.id)

    async with message.channel.typing():
        try:
            llm_content = await _prepare_llm_input(message, content)
            if not llm_content: return

            _update_and_trim_history(channel_context, llm_content)

            api_response = await _call_openrouter_api(channel_context, message.guild.id)
            if not api_response:
                channel_context.history.pop()
                return

            response_text = _extract_response_text(api_response)
            if response_text is None: return

            _update_history_with_model_response(channel_context, response_text)
            token_info = _get_token_info(api_response)
            await _send_discord_response(message, response_text, token_info)

        except Exception as e:
            print(f"Error fatal en on_message para mensaje {message.id}: {type(e).__name__} - {e}")
            await message.channel.send("⚠️ Ocurrió un error inesperado al procesar tu mensaje.")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Handles errors that occur during command processing."""
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
    else:
        print(f'Error no manejado en comando {ctx.command.qualified_name}: {type(error).__name__} - {error}')
        await ctx.send("⚠️ Ocurrió un error desconocido al ejecutar el comando.")

# --- Helper Functions for on_message ---

async def _should_process_ai(message: discord.Message) -> typing.Tuple[bool, str | None]:
    """Determines if a message should be processed by the AI."""
    guild_cfg = config_manager.get_guild_config(message.guild.id)
    is_caller_admin = is_admin(message.author)

    if not is_caller_admin and not guild_cfg.get('bot_enabled_for_users'):
        return False, None

    if not is_caller_admin and not is_channel_allowed(message.guild.id, message.channel.id):
        return False, None

    channel_context = await context_manager.get_channel_ctx(message.channel.id)
    is_mention = bot.user.mentioned_in(message)
    stripped_content = message.content.lstrip(f"<@!{bot.user.id}>").lstrip(f"<@{bot.user.id}>").strip()

    if is_mention and (stripped_content or message.attachments):
        return True, stripped_content
    if channel_context.settings.get('natural_conversation'):
        return True, message.content

    return False, None

async def _prepare_llm_input(message: discord.Message, text_content: str | None) -> list | None:
    """Prepares the user's message and attachments for the LLM API."""
    parts = []
    author_name = message.author.display_name
    author_id = message.author.id

    if text_content:
        text_for_llm = f"{author_name} (ID: {author_id}): {text_content}"
        parts.append({'type': 'text', 'text': text_for_llm})

    for attachment in message.attachments:
        if attachment.size > MAX_ATTACHMENT_SIZE_BYTES:
            await message.channel.send(f"⚠️ Archivo '{attachment.filename}' demasiado grande.", delete_after=15)
            continue
        try:
            file_bytes = await attachment.read()
            file_content = file_bytes.decode('utf-8', errors='replace')
            file_context = f"\n--- Contenido de {attachment.filename} ---\n{file_content}\n--- Fin de {attachment.filename} ---"
            parts.append({'type': 'text', 'text': file_context})
        except Exception as e:
            await message.channel.send(f"⚠️ Error al leer el adjunto '{attachment.filename}'.", delete_after=15)
            print(f"Error procesando adjunto: {e}")

    return parts if parts else None

def _update_and_trim_history(channel_context: ChannelContext, user_message_content: list):
    """Adds the user's message to the history and trims it to a max length."""
    MAX_HISTORY_MESSAGES = 10
    channel_context.history.append({'role': 'user', 'content': user_message_content})
    if len(channel_context.history) > MAX_HISTORY_MESSAGES * 2:
        channel_context.history = channel_context.history[-(MAX_HISTORY_MESSAGES * 2):]

async def _call_openrouter_api(channel_context: ChannelContext, guild_id: int) -> typing.Optional[ChatCompletion]:
    """
    Calls the OpenRouter API, including the system prompt only if the model
    is known to support it based on the live test.
    """
    client = channel_context.create_client()
    if not client: return None

    guild_cfg = config_manager.get_guild_config(guild_id)
    model_name = channel_context.settings.get('model') or guild_cfg.get('model')
    
    messages_for_api = []
    
    # Check the cached result of the live test to decide on sending the system prompt.
    personality_is_supported = await model_info_manager.test_system_prompt_support(model_name)
    if personality_is_supported:
        messages_for_api.append(channel_context.get_system_prompt_message())
        
    messages_for_api.extend(channel_context.history)

    try:
        # The complex retry logic is no longer needed here.
        return await client.chat.completions.create(
            model=model_name,
            messages=messages_for_api,
            temperature=channel_context.settings.get('temperature'),
            max_tokens=guild_cfg.get('max_output_tokens')
        )
    except OpenAIError as e:
        error_msg = f"⚠️ Error de API con el modelo `{model_name}`: {e.body.get('message', 'Error desconocido') if e.body else str(e)}"
        await bot.get_channel(channel_context.channel_id).send(error_msg, delete_after=20)
        print(f"Error de OpenRouter: {e}")
        return None
    except Exception as e:
        await bot.get_channel(channel_context.channel_id).send("⚠️ Ocurrió un error inesperado al contactar la API.")
        print(f"Error inesperado en API call: {e}")
        return None

def _extract_response_text(api_response: ChatCompletion) -> str | None:
    """Extracts the text content from the API response."""
    try:
        return api_response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return None

def _update_history_with_model_response(channel_context: ChannelContext, response_text: str):
    """Adds the model's response to the conversation history."""
    if channel_context.history and channel_context.history[-1]['role'] == 'model':
        print("Advertencia: Se intentó añadir respuestas de modelo consecutivas. Ignorado.")
    else:
        channel_context.history.append({'role': 'model', 'content': response_text})

def _get_token_info(api_response: ChatCompletion) -> str:
    """Extracts token usage information from the API response."""
    try:
        if api_response.usage and api_response.usage.total_tokens > 0:
            return f"\n*Tokens: `{api_response.usage.total_tokens}`*"
    except AttributeError:
        pass
    return ""

async def _send_discord_response(message: discord.Message, response_text: str, token_info: str):
    """Sends the AI's response to Discord, handling long messages and code blocks."""
    MAX_MSG_LEN = 2000
    
    cleaned_response_text = response_text.rstrip()

    for i in range(0, len(cleaned_response_text), MAX_MSG_LEN):
        part = cleaned_response_text[i:i + MAX_MSG_LEN]
        if i + MAX_MSG_LEN >= len(cleaned_response_text):
            await message.channel.send(part + token_info)
        else:
            await message.channel.send(part)

# --- Main Execution ---

async def main():
    """Main function to load extensions and start the bot."""
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f'-> Cog cargado: {filename[:-3]}')
                except Exception as e:
                    print(f'Error cargando cog {filename[:-3]}: {e}')
        
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")