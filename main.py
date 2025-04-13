import os
import discord
from discord.ext import commands
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import asyncio
from dotenv import load_dotenv
import io
import typing
import json
import copy

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_NAME = os.getenv('MODEL_NAME')

if not DISCORD_TOKEN: print("Error: DISCORD_TOKEN no configurado."); exit()
if not GEMINI_API_KEY: print("Error: GEMINI_API_KEY no configurado."); exit()
if not MODEL_NAME: print("Error: MODEL_NAME no configurado."); exit()

CONFIG_FILE = 'config.json'
bot_config = {}

DEFAULT_GUILD_CONFIG = {
    'command_prefix': '!',
    'admin_role_id': None,
    'allowed_channel_ids': [],
    'bot_enabled_for_users': True,
}

MODEL_NAME_USED = f'models/{MODEL_NAME}'
MODEL_INPUT_TOKEN_LIMIT = None

def load_config():
    global bot_config
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded_data = json.load(f)
            bot_config = {str(k): v for k, v in loaded_data.items()}
            print(f"Configuración cargada desde {CONFIG_FILE} para {len(bot_config)} servidor(es).")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Advertencia: No se pudo cargar {CONFIG_FILE} ({e}). Se iniciará vacío.")
        bot_config = {}

def save_config():
    global bot_config
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(bot_config, f, indent=4)
    except Exception as e:
        print(f"Error guardando configuración en {CONFIG_FILE}: {e}")

def get_guild_config(guild_id: int) -> dict:
    global bot_config
    guild_id_str = str(guild_id)

    if guild_id_str not in bot_config or not isinstance(bot_config.get(guild_id_str), dict):
        if guild_id_str not in bot_config:
             print(f"Creando configuración por defecto para el servidor {guild_id_str}")
        else:
             print(f"Advertencia: Configuración inválida para {guild_id_str}. Reemplazando con por defecto.")
        bot_config[guild_id_str] = copy.deepcopy(DEFAULT_GUILD_CONFIG)

    guild_cfg = bot_config[guild_id_str]

    config_updated = False
    for key, default_value in DEFAULT_GUILD_CONFIG.items():
        if key not in guild_cfg:
            guild_cfg[key] = copy.deepcopy(default_value)
            config_updated = True

    if not isinstance(guild_cfg.get('command_prefix'), str) or not guild_cfg.get('command_prefix'):
        guild_cfg['command_prefix'] = DEFAULT_GUILD_CONFIG['command_prefix']
        config_updated = True
    if not isinstance(guild_cfg.get('admin_role_id'), (int, type(None))):
        guild_cfg['admin_role_id'] = DEFAULT_GUILD_CONFIG['admin_role_id']
        config_updated = True
    if not isinstance(guild_cfg.get('allowed_channel_ids'), list):
        guild_cfg['allowed_channel_ids'] = []
        config_updated = True
    else:
        original_ids = guild_cfg.get('allowed_channel_ids', [])
        valid_ids = []
        changed = False
        for ch_id in original_ids:
            if isinstance(ch_id, str) and ch_id.isdigit():
                valid_ids.append(int(ch_id))
                changed = True
            elif isinstance(ch_id, int):
                valid_ids.append(ch_id)
            else:
                changed = True
        if changed:
            guild_cfg['allowed_channel_ids'] = valid_ids
            config_updated = True

    if not isinstance(guild_cfg.get('bot_enabled_for_users'), bool):
        guild_cfg['bot_enabled_for_users'] = DEFAULT_GUILD_CONFIG['bot_enabled_for_users']
        config_updated = True

    return guild_cfg

load_config()

async def get_prefix(client, message):
    if not message.guild:
        return DEFAULT_GUILD_CONFIG['command_prefix']
    guild_cfg = get_guild_config(message.guild.id)
    return guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

try:
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        print(f"Obteniendo información para el modelo: {MODEL_NAME_USED}...")
        model_info = genai.get_model(MODEL_NAME_USED)
        if hasattr(model_info, 'input_token_limit'):
            MODEL_INPUT_TOKEN_LIMIT = model_info.input_token_limit
            print(f"Límite de tokens de entrada detectado: {MODEL_INPUT_TOKEN_LIMIT}")
        else:
            print(f"Advertencia: El atributo 'input_token_limit' no se encontró para el modelo {MODEL_NAME_USED}.")
            MODEL_INPUT_TOKEN_LIMIT = None
    except Exception as model_info_error:
        print(f"Error crítico al obtener información del modelo {MODEL_NAME_USED}: {model_info_error}")
        print("El límite máximo de tokens no estará disponible.")
        MODEL_INPUT_TOKEN_LIMIT = None

except Exception as e:
    print(f"Error configurando Gemini: {e}")

channel_contexts = {}
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_SETTINGS = {'personalidad': 'Tono: neutral. Estilo: formal.', 'temperatura': 0.5}
DEFAULT_IS_ACTIVE = False
LANGUAGE_EXTENSIONS = { "python": ".py", "py": ".py", "javascript": ".js", "js": ".js", "typescript": ".ts", "ts": ".ts", "java": ".java", "csharp": ".cs", "cs": ".cs", "cpp": ".cpp", "c++": ".cpp", "c": ".c", "html": ".html", "css": ".css", "json": ".json", "yaml": ".yaml", "yml": ".yaml", "markdown": ".md", "md": ".md", "bash": ".sh", "sh": ".sh", "sql": ".sql", "ruby": ".rb", "php": ".php", "go": ".go", "rust": ".rs", }
DEFAULT_EXTENSION = ".txt"

class ChannelContext:
    def __init__(self):
        self.history = []
        self.settings = DEFAULT_SETTINGS.copy()
        self.is_active = DEFAULT_IS_ACTIVE
        self.stop_requested = False

    def create_model(self):
        model_name = MODEL_NAME
        safety_settings = [ {"category": c, "threshold": HarmBlockThreshold.BLOCK_NONE} for c in HarmCategory if c != HarmCategory.HARM_CATEGORY_UNSPECIFIED]
        try:
            instruccion_personalidad = self.settings.get('personalidad', '').strip()
            base_instruction = "Responde en español (latinoamericano venezolano)."

            mention_instruction = (
                "Importante: Estás en un chat de Discord con múltiples usuarios. "
                "Cada mensaje de un usuario en el historial que te proporciono vendrá prefijado con su nombre y su ID único de Discord, en el formato: 'NombreUsuario (ID: 123456789012345678): contenido del mensaje'. "
                "Es crucial que prestes atención a quién (qué ID) dijo cada cosa en el historial para mantener el contexto correcto de la conversación. "
                "Cuando necesites referirte a un usuario específico en tu respuesta, DEBES usar el formato de mención de Discord: `<@USER_ID>`, reemplazando USER_ID con el ID numérico correspondiente que viste en el prefijo de su mensaje en el historial. "
                "Ejemplo de Interacción Correcta: "
                "Historial:"
                "UsuarioA (ID: 111): @Bot saluda a @UsuarioB"
                "Tu Respuesta Correcta: '¡Claro <@111>! Hola @UsuarioB, te envío saludos de parte de <@111>.' (Nota cómo mencionas a UsuarioA usando su ID 111)."
                "Otro Ejemplo:"
                "Historial:"
                "UsuarioX (ID: 888): ¿Qué opinas de la idea de UsuarioY?"
                "UsuarioY (ID: 999): Creo que es buena idea."
                "UsuarioX (ID: 888): @Bot, ¿qué dijo UsuarioY?"
                "Tu Respuesta Correcta: '<@888>, <@999> dijo que cree que es buena idea.'"
                "NUNCA te refieras al usuario que te pide algo usando tu propio nombre ('Bot'). SIEMPRE usa su mención `<@USER_ID>` obtenida del historial."            )

            system_instruction_parts = [base_instruction]
            if instruccion_personalidad:
                system_instruction_parts.append(instruccion_personalidad)
            system_instruction_parts.append(mention_instruction)

            system_instruction = " ".join(system_instruction_parts)

            return genai.GenerativeModel(
                model_name,
                system_instruction=system_instruction,
                generation_config={'temperature': self.settings['temperatura'], 'max_output_tokens': 4096},
                safety_settings=safety_settings
            )
        except Exception as e:
            print(f"Error creando modelo Gemini: {e}")
            return None

def is_admin(member: typing.Union[discord.Member, discord.User]) -> bool:
    if not isinstance(member, discord.Member): return False
    if member.guild_permissions.administrator: return True
    if member.guild.owner_id == member.id: return True
    guild_cfg = get_guild_config(member.guild.id)
    admin_role_id = guild_cfg.get('admin_role_id')
    if admin_role_id:
        admin_role = member.guild.get_role(admin_role_id)
        if admin_role and admin_role in member.roles:
            return True
    return False

def is_admin_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild: raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if not is_admin(ctx.author): raise commands.CheckFailure("No tienes permiso de administrador.")
        return True
    return commands.check(predicate)

def is_owner_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild: raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if ctx.guild.owner_id != ctx.author.id: raise commands.CheckFailure("Solo el dueño del servidor puede usar esto.")
        return True
    return commands.check(predicate)

def is_channel_allowed(guild_id: int, channel_id: int) -> bool:
    guild_cfg = get_guild_config(guild_id)
    allowed_ids = guild_cfg.get('allowed_channel_ids', [])
    return not allowed_ids or channel_id in allowed_ids

def reset_channel_settings(channel_ctx: ChannelContext):
    channel_ctx.settings = DEFAULT_SETTINGS.copy()
    channel_ctx.is_active = DEFAULT_IS_ACTIVE
    channel_ctx.stop_requested = False
    print("Configuraciones de IA del canal restablecidas (excepto historial).")

async def ask_confirmation(ctx: commands.Context, action_description: str) -> bool:
    confirm_embed = discord.Embed(title="Confirmación Requerida", description=f"¿Seguro que deseas **{action_description}**?", color=discord.Color.orange())
    confirm_embed.set_footer(text="✅ Confirmar / ❌ Cancelar (30s)")
    confirm_msg = await ctx.send(embed=confirm_embed)
    await confirm_msg.add_reaction('✅')
    await confirm_msg.add_reaction('❌')

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ['✅', '❌']

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        confirmed = str(reaction.emoji) == '✅'
        if not confirmed:
            await ctx.send("❌ Acción cancelada.", delete_after=10)
    except asyncio.TimeoutError:
        confirmed = False
        await ctx.send("⏰ Tiempo agotado. Acción cancelada.", delete_after=10)
    finally:
        try: await confirm_msg.delete()
        except discord.NotFound: pass
    return confirmed

async def _get_channel_ctx(channel_id: int) -> ChannelContext:
    return channel_contexts.setdefault(channel_id, ChannelContext())

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
        original = error.original
        print(f'Error en comando {ctx.command.qualified_name}: {original}')
        await ctx.send("⚠️ Ocurrió un error inesperado al ejecutar el comando.")
    else:
        print(f'Error no manejado en comando {ctx.command.qualified_name}: {error}')
        await ctx.send("⚠️ Ocurrió un error desconocido.")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    default_prefix = DEFAULT_GUILD_CONFIG['command_prefix']
    await bot.change_presence(activity=discord.Game(name=f"Mencióname + tu mensaje para interactuar!"))
    print(f"Bot listo. Prefijo por defecto: {default_prefix}.")

@bot.command(name='setprefix')
@is_admin_check()
@commands.guild_only()
async def set_prefix(ctx: commands.Context, new_prefix: str):
    if not new_prefix:
        await ctx.send("❌ El prefijo no puede estar vacío."); return
    if len(new_prefix) > 5:
        await ctx.send("❌ Prefijo demasiado largo (máx 5 caracteres)."); return

    guild_cfg = get_guild_config(ctx.guild.id)
    if new_prefix == guild_cfg.get('command_prefix'):
        await ctx.send(f"ℹ️ El prefijo para este servidor ya es `{new_prefix}`."); return

    guild_cfg['command_prefix'] = new_prefix
    save_config()
    await ctx.send(f"✅ Prefijo para este servidor cambiado a: `{new_prefix}`")

@bot.command(name='setadminrole')
@is_owner_check()
@commands.guild_only()
async def set_admin_role(ctx: commands.Context, role: discord.Role):
    guild_cfg = get_guild_config(ctx.guild.id)
    guild_cfg['admin_role_id'] = role.id
    save_config()
    await ctx.send(f"✅ Rol de admin para este servidor establecido a: **{role.name}** (`{role.id}`).")

@bot.command(name='addchannel')
@is_admin_check()
@commands.guild_only()
async def add_allowed_channel(ctx: commands.Context, channel: discord.TextChannel):
    guild_cfg = get_guild_config(ctx.guild.id)
    allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
    if channel.id in allowed_ids:
        await ctx.send(f"ℹ️ {channel.mention} ya estaba permitido."); return

    allowed_ids.append(channel.id)
    save_config()
    await ctx.send(f"✅ {channel.mention} añadido a los canales permitidos.")
    if len(allowed_ids) == 1:
        await ctx.send("ℹ️ Nota: Ahora el bot SOLO funcionará para usuarios normales en los canales de esta lista en este servidor (admins pueden usarlo en cualquier canal).")

@bot.command(name='removechannel')
@is_admin_check()
@commands.guild_only()
async def remove_allowed_channel(ctx: commands.Context, channel: discord.TextChannel):
    guild_cfg = get_guild_config(ctx.guild.id)
    allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
    if channel.id not in allowed_ids:
        await ctx.send(f"ℹ️ {channel.mention} no estaba en la lista de permitidos."); return

    allowed_ids.remove(channel.id)
    save_config()
    await ctx.send(f"✅ {channel.mention} eliminado de los canales permitidos.")
    if not allowed_ids:
        await ctx.send("ℹ️ Nota: La lista de canales permitidos está vacía. El bot funcionará en **todos** los canales de este servidor para usuarios normales.")

@bot.command(name='listchannels')
@is_admin_check()
@commands.guild_only()
async def list_allowed_channels(ctx: commands.Context):
    guild_cfg = get_guild_config(ctx.guild.id)
    allowed_ids = guild_cfg.get('allowed_channel_ids', [])

    if not allowed_ids:
        await ctx.send(f"✅ Bot permitido en **todos** los canales de **{ctx.guild.name}** para usuarios normales."); return

    mentions = []
    not_found_ids = []
    for ch_id in allowed_ids:
        channel = ctx.guild.get_channel(ch_id)
        if channel:
            mentions.append(f"{channel.mention} (`{ch_id}`)")
        else:
            not_found_ids.append(f"`{ch_id}`")

    desc = "\n".join(mentions) if mentions else "Ningún canal permitido encontrado (o todos fueron borrados)."
    if not_found_ids:
        desc += f"\n\n**IDs de canales no encontrados (quizás borrados):** {', '.join(not_found_ids)}"

    embed = discord.Embed(title=f"Canales Permitidos en {ctx.guild.name}", description=desc, color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name='enablebot')
@is_admin_check()
@commands.guild_only()
async def enable_bot_globally(ctx: commands.Context):
    guild_cfg = get_guild_config(ctx.guild.id)
    if guild_cfg.get('bot_enabled_for_users', True):
        await ctx.send(f"ℹ️ El bot ya está habilitado para usuarios normales en **{ctx.guild.name}**."); return

    guild_cfg['bot_enabled_for_users'] = True
    save_config()
    await ctx.send(f"✅ Bot **habilitado** para usuarios normales en **{ctx.guild.name}**.")

@bot.command(name='disablebot')
@is_admin_check()
@commands.guild_only()
async def disable_bot_globally(ctx: commands.Context):
    guild_cfg = get_guild_config(ctx.guild.id)
    if not guild_cfg.get('bot_enabled_for_users', True):
        await ctx.send(f"ℹ️ El bot ya está deshabilitado para usuarios normales en **{ctx.guild.name}**."); return

    guild_cfg['bot_enabled_for_users'] = False
    save_config()
    await ctx.send(f"☑️ Bot **deshabilitado** para usuarios normales en **{ctx.guild.name}** (admins aún pueden usarlo).")

@bot.command(name='showconfig')
@is_admin_check()
@commands.guild_only()
async def show_config_command(ctx: commands.Context):
    guild_cfg = get_guild_config(ctx.guild.id)
    admin_role_id = guild_cfg.get('admin_role_id')
    allowed_ids = guild_cfg.get('allowed_channel_ids', [])
    bot_enabled = guild_cfg.get('bot_enabled_for_users', True)
    current_prefix = guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])

    admin_role_str = "No establecido"
    if admin_role_id:
        role = ctx.guild.get_role(admin_role_id)
        admin_role_str = f"{role.name} (`{role.id}`)" if role else f"ID: `{admin_role_id}` (Rol no encontrado)"

    channels_str = "Todos" if not allowed_ids else f"{len(allowed_ids)} específicos (usa `{current_prefix}listchannels`)"
    enabled_str = "✅ Habilitado" if bot_enabled else "☑️ Deshabilitado (solo admins)"

    embed = discord.Embed(title=f"Configuración del Bot para {ctx.guild.name}", color=discord.Color.green())
    embed.add_field(name="Prefijo", value=f"`{current_prefix}`", inline=True)
    embed.add_field(name="Estado para Usuarios", value=enabled_str, inline=True)
    embed.add_field(name="Rol Admin", value=admin_role_str, inline=False)
    embed.add_field(name="Canales Permitidos (Usuarios)", value=channels_str, inline=False)
    await ctx.send(embed=embed)

@bot.command(name='setpersonality', aliases=['setpersona'])
@is_admin_check()
@commands.guild_only()
async def set_personality_command(ctx: commands.Context, *, nueva_personalidad: str):
    if not nueva_personalidad:
        await ctx.send(f"❌ Debes especificar una personalidad. Ejemplo: `{ctx.prefix}setpersonality Tono: amigable. Estilo: informal.`"); return
    if len(nueva_personalidad) > 300:
        await ctx.send("❌ Descripción de personalidad demasiado larga (máx 300 caracteres)."); return

    channel_ctx = await _get_channel_ctx(ctx.channel.id)
    channel_ctx.settings['personalidad'] = nueva_personalidad.strip()
    display_persona = channel_ctx.settings['personalidad']
    if len(display_persona) > 100: display_persona = display_persona[:97] + "..."
    await ctx.send(f"✅ Personalidad para {ctx.channel.mention} actualizada a:\n```\n{display_persona}\n```")

@bot.command(name='settemperature', aliases=['settemp'])
@is_admin_check()
@commands.guild_only()
async def set_temperature_command(ctx: commands.Context, nueva_temperatura: float):
    if not 0.0 <= nueva_temperatura <= 1.0:
        await ctx.send("❌ La temperatura debe ser un número entre 0.0 y 1.0."); return

    channel_ctx = await _get_channel_ctx(ctx.channel.id)
    channel_ctx.settings['temperatura'] = nueva_temperatura
    await ctx.send(f"✅ Temperatura de IA para {ctx.channel.mention} actualizada a: `{channel_ctx.settings['temperatura']}`")

@bot.command(name='reset')
@is_admin_check()
@commands.guild_only()
async def reset_channel_ai_command(ctx: commands.Context):
    channel_ctx = await _get_channel_ctx(ctx.channel.id)
    if await ask_confirmation(ctx, f"restablecer **toda** la configuración de la IA (personalidad, temp, estado) de {ctx.channel.mention} a los valores por defecto"):
        reset_channel_settings(channel_ctx)
        await ctx.send(f"⚙️ Configuración de IA para {ctx.channel.mention} restablecida a los valores por defecto.", delete_after=15)

@bot.command(name='clearhistory')
@is_admin_check()
@commands.guild_only()
async def clear_channel_history_command(ctx: commands.Context):
    channel_ctx = await _get_channel_ctx(ctx.channel.id)
    if await ask_confirmation(ctx, f"borrar **todo** el historial de conversación de la IA para {ctx.channel.mention}"):
        channel_ctx.history.clear()
        await ctx.send(f"🧹 Historial de IA para {ctx.channel.mention} limpiado.", delete_after=15)

@bot.command(name='togglenatural', aliases=['naturalconv'])
@is_admin_check()
@commands.guild_only()
async def toggle_natural_conversation_command(ctx: commands.Context):
    channel_ctx = await _get_channel_ctx(ctx.channel.id)
    channel_ctx.is_active = not channel_ctx.is_active
    new_state = "Activada" if channel_ctx.is_active else "Desactivada"
    await ctx.send(f"✅ Conversación natural: **{new_state}** en {ctx.channel.mention}.", delete_after=15)

@bot.command(name='help', aliases=['helpbot'])
@commands.guild_only()
async def help_config_command(ctx: commands.Context):
    current_prefix = ctx.prefix
    embed = discord.Embed(title=f"🤖 Ayuda del Bot Gemini ({ctx.guild.name})", color=discord.Color.purple())

    embed.add_field(name="🗣️ Interacción Principal", value=f"""
    - Mencióname (`@{bot.user.name} <mensaje>`) para chatear.
    - Si la 'Conversación Natural' está activa en un canal (ver comando `{current_prefix}togglenatural` o menú), puedes hablar sin mencionarme (si el canal está permitido).
    """, inline=False)

    embed.add_field(name="", value="\u200b")

    embed.add_field(name="✨ Menú Interactivo (mención sin texto)", value="""
    Permite a los **admins** configurar la IA **por canal** y ver comandos globales:
    - **Personalidad:** Define directamente cómo debe responder la IA.
    - **Temperatura:** Ajusta la creatividad (muestra comando).
    - **Conversación Natural:** Activar/desactivar respuesta sin mención.
    - **Restablecer IA Canal:** Volver a por defecto de IA para ese canal.
    - **Borrar Historial IA Canal:** Limpiar memoria de ese canal.
    - **Ver Comandos Globales:** Muestra info y comandos para config del servidor.
    """, inline=False)

    embed.add_field(name="", value="\u200b")

    embed.add_field(name=f"🔧 Configuración IA por Canal (Admins)", value=f"""
    *(Afectan solo al canal donde se usan)*
    `{current_prefix}setpersonality <descripción>` / `setpersona` - Define personalidad/tono/estilo.
    `{current_prefix}settemperature <0.0-1.0>` / `settemp` - Cambia la creatividad/aleatoriedad.
    `{current_prefix}togglenatural` / `naturalconv` - Activa/desactiva respuesta sin mención.
    `{current_prefix}reset` - Restablece configugración de la IA para el canal a por defecto (pide confirmación).
    `{current_prefix}clearhistory` - Borra historial de la IA para el canal (pide confirmación).
    `{current_prefix}tokencount` / `contextsize` / `tokens` - Muestra tokens estimados en el historial actual.
    """, inline=False)

    embed.add_field(name="", value="\u200b")

    embed.add_field(name=f"⚙️ Configuración del Servidor (Admins/Dueño)", value=f"""
    `{current_prefix}setprefix <prefijo>` - Cambia el prefijo (Admin).
    `{current_prefix}setadminrole <@Rol/ID>` - Establece el rol admin (Dueño).
    `{current_prefix}addchannel <#Canal/ID>` - Permite bot en canal para usuarios (Admin).
    `{current_prefix}removechannel <#Canal/ID>` - Impide bot en canal para usuarios (Admin).
    `{current_prefix}listchannels` - Muestra canales permitidos para usuarios (Admin).
    `{current_prefix}enablebot` - Habilita bot para usuarios (Admin).
    `{current_prefix}disablebot` - Deshabilita bot para usuarios (Admin).
    `{current_prefix}showconfig` - Muestra config actual del servidor (Admin).
    """, inline=False)

    embed.add_field(name="", value="\u200b")

    embed.set_footer(text=f"Admin = Dueño, rol admin configurado, o permiso 'Administrador' | Dueño = Creador del servidor")
    await ctx.send(embed=embed)

@bot.command(name='tokencount', aliases=['contextsize', 'tokens', 'historytokens'])
@is_admin_check()
@commands.guild_only()
async def token_count_command(ctx: commands.Context):
    channel_ctx = await _get_channel_ctx(ctx.channel.id)

    if not channel_ctx.history:
        await ctx.send(f"ℹ️ No hay historial de conversación registrado para {ctx.channel.mention}.")
        return

    contents_for_api = []
    for msg in channel_ctx.history:
        msg_parts = msg.get('parts', [])
        if isinstance(msg_parts, dict): msg_parts = [msg_parts]
        if msg.get('role') and msg_parts:
            contents_for_api.append({'role': msg.get('role'), 'parts': msg_parts})

    if not contents_for_api:
        await ctx.send(f"ℹ️ El historial de {ctx.channel.mention} está vacío o no se pudo formatear para el conteo.")
        return

    model = channel_ctx.create_model()
    if model is None:
        await ctx.send("⚠️ Error crítico: No se pudo crear una instancia del modelo de IA para contar tokens.")
        return

    try:
        async with ctx.typing():
            response = model.count_tokens(contents_for_api)
            token_count = response.total_tokens

        embed = discord.Embed(
            title=f"📊 Conteo de Tokens en {ctx.channel.mention}",
            description=f"Estimación del tamaño del historial de conversación actual.",
            color=discord.Color.blue()
        )
        max_str = f"{MODEL_INPUT_TOKEN_LIMIT}" if MODEL_INPUT_TOKEN_LIMIT is not None else "?"
        embed.add_field(name="Tokens Totales Estimados", value=f"`{token_count}/{max_str}`", inline=False)
        embed.add_field(name="Mensajes en Historial", value=f"`{len(channel_ctx.history)}` (Usuario + Modelo)", inline=False)
        embed.set_footer(text=f"Contado usando el modelo: {model.model_name}. La API puede tener límites diferentes.")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"⚠️ Error al contar los tokens: {e}")
        print(f"Error en tokencount command: {type(e).__name__} - {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.author.bot: return
    if not message.guild:
        return

    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    guild_id = message.guild.id
    guild_cfg = get_guild_config(guild_id)
    is_currently_admin = is_admin(message.author)

    bot_globally_enabled_for_users = guild_cfg.get('bot_enabled_for_users', True)
    if not is_currently_admin and not bot_globally_enabled_for_users:
        return

    channel_allowed_for_chat = True
    if not is_currently_admin:
        channel_allowed_for_chat = is_channel_allowed(guild_id, message.channel.id)
        if not channel_allowed_for_chat:
            return

    channel_id = message.channel.id
    ctx_gemini = await _get_channel_ctx(channel_id)
    is_mention = bot.user.mentioned_in(message)
    user_text_content = message.content

    should_process_gemini = False
    if is_mention:
        user_text_content = user_text_content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_text_content and not message.attachments:
            if is_currently_admin:
                await show_menu(message.channel, message.author)
            else:
                await message.channel.send("ℹ️ Mencióname seguido de tu pregunta o adjunta un archivo.", delete_after=15)
            return
        else:
            should_process_gemini = True
    elif ctx_gemini.is_active:
        should_process_gemini = True

    if not should_process_gemini:
        return

    ctx_gemini.stop_requested = False
    original_user_text = user_text_content
    author_name = message.author.display_name
    final_content_for_history = user_text_content

    author_id = message.author.id

    text_for_llm = original_user_text
    if original_user_text.strip():
        text_for_llm = f"{author_name} (ID: {author_id}): {original_user_text}"

    processed_attachment_info = []
    attachments_to_process = []

    if message.attachments:
        async with message.channel.typing():
            for attachment in message.attachments:
                if attachment.content_type and (
                    attachment.content_type.startswith('text/') or
                    attachment.content_type.startswith('image/') or
                    attachment.filename.lower().endswith(tuple(LANGUAGE_EXTENSIONS.values()))
                ):
                    if attachment.size > MAX_ATTACHMENT_SIZE_BYTES:
                        await message.channel.send(f"⚠️ Archivo '{attachment.filename}' demasiado grande (máx {MAX_ATTACHMENT_SIZE_BYTES // 1024 // 1024}MB)."); continue
                    attachments_to_process.append(attachment)
                else:
                    await message.channel.send(f"ℹ️ Archivo '{attachment.filename}' ignorado (tipo no soportado: {attachment.content_type}).")

    parts = []

    if text_for_llm.strip(): 
        parts.append({'text': text_for_llm})

    if attachments_to_process:
        async with message.channel.typing():
            for attachment in attachments_to_process:
                try:
                    file_bytes = await attachment.read()
                    if attachment.content_type.startswith('image/'):
                         parts.append({'inline_data': {'mime_type': attachment.content_type, 'data': file_bytes}})
                         processed_attachment_info.append(f"{attachment.filename} (imagen de {author_name})")
                    elif attachment.content_type.startswith('text/') or attachment.filename.lower().endswith(tuple(LANGUAGE_EXTENSIONS.values())):
                         file_content = file_bytes.decode('utf-8', errors='replace')
                         parts.append({'text': f"\n\n--- Contenido de {attachment.filename} (adjuntado por {author_name} ID: {author_id}) ---\n{file_content}"})
                         processed_attachment_info.append(f"{attachment.filename} (texto/código de {author_name})") 

                except Exception as e:
                    print(f"Error procesando adjunto {attachment.filename}: {e}")
                    await message.channel.send(f"⚠️ Error al leer '{attachment.filename}'.")

    if not parts:
        if message.attachments and not processed_attachment_info:
             await message.channel.send("ℹ️ No se procesó ningún adjunto válido y no había texto.")
        print(f"Advertencia: No se encontraron partes válidas para procesar en el mensaje {message.id}. No se llamará a la IA.")
        return

    user_message_part = {'role': 'user', 'parts': parts}
    ctx_gemini.history.append(user_message_part)

    MAX_HISTORY_LEN = 10
    if len(ctx_gemini.history) > MAX_HISTORY_LEN:
        ctx_gemini.history = ctx_gemini.history[-MAX_HISTORY_LEN:]

    model = None
    try:
        model = ctx_gemini.create_model()
        if model is None:
            await message.channel.send("⚠️ Error crítico: No se pudo configurar el modelo de IA."); return

        respuesta = None
        response = None
        async with message.channel.typing():
            contents_for_api = []
            for msg in ctx_gemini.history:
                 msg_parts = msg.get('parts', [])
                 if isinstance(msg_parts, dict): msg_parts = [msg_parts]
                 if msg.get('role') and msg_parts:
                     contents_for_api.append({'role': msg.get('role'), 'parts': msg_parts})

            if not contents_for_api or contents_for_api[-1]['role'] != 'user':
                 print("Advertencia: Intento de generar respuesta sin mensaje de usuario válido en el historial.")
                 if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
                 return

            response = await model.generate_content_async(contents=contents_for_api)

            if ctx_gemini.stop_requested:
                print("Generación detenida por el usuario.")
                await message.channel.send("🛑 Generación detenida.")
                if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
                return

            try:
                respuesta = response.text
            except ValueError as ve:
                feedback = getattr(response, 'prompt_feedback', None)
                reason = getattr(feedback, 'block_reason', 'Desconocida') if feedback else 'Desconocida'
                safety_ratings_str = ""
                if feedback and hasattr(feedback, 'safety_ratings'):
                    ratings = [f"{r.category.name}: {r.probability.name}" for r in feedback.safety_ratings]
                    safety_ratings_str = f" (Ratings: {', '.join(ratings)})" if ratings else ""
                print(f"Respuesta bloqueada. Razón: {reason}{safety_ratings_str}")
                await message.channel.send(f"⚠️ Mi respuesta fue bloqueada por seguridad (Razón: {reason}). Intenta reformular tu pregunta.{safety_ratings_str}")
                if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
                return
            except AttributeError:
                 print(f"Error: Atributo 'text' no encontrado en la respuesta: {response}")
                 await message.channel.send("⚠️ Hubo un problema inesperado al obtener la respuesta del modelo.")
                 if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
                 return
            except Exception as resp_err:
                 print(f"Error inesperado accediendo a la respuesta: {resp_err}")
                 await message.channel.send("⚠️ Ocurrió un error al procesar la respuesta del modelo.")
                 if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
                 return

        if respuesta is not None and response is not None:
            current_tokens = None
            total_tokens = None
            token_info_str = ""
            allowed_mentions = discord.AllowedMentions(users=True)

            try:
                if hasattr(response, 'usage_metadata'):
                    prompt_tokens = response.usage_metadata.prompt_token_count
                    candidate_tokens = response.usage_metadata.candidates_token_count
                    current_tokens = prompt_tokens
                else:
                    print("Advertencia: No se encontró usage_metadata en la respuesta.")
            except AttributeError:
                print("Advertencia: Atributo faltante en usage_metadata.")
            except Exception as e:
                print(f"Error obteniendo usage_metadata: {e}")

            if not ctx_gemini.history or ctx_gemini.history[-1]['role'] != 'model':
                 ctx_gemini.history.append({'role': 'model', 'parts': [{'text': respuesta}]})
            else:
                 print("Advertencia: Se intentó añadir una respuesta del modelo consecutiva. Ignorando.")

            if ctx_gemini.history:
                try:
                    contents_for_total_count = []
                    for msg in ctx_gemini.history:
                        msg_parts = msg.get('parts', [])
                        if isinstance(msg_parts, dict): msg_parts = [msg_parts]
                        if msg.get('role') and msg_parts:
                            contents_for_total_count.append({'role': msg.get('role'), 'parts': msg_parts})

                    if contents_for_total_count:
                        count_response = model.count_tokens(contents_for_total_count)
                        total_tokens = count_response.total_tokens
                except Exception as e:
                    print(f"Error contando tokens totales del historial: {e}")

            current_str = f"{current_tokens}" if current_tokens is not None else "N/A"
            total_str = f"{total_tokens}" if total_tokens is not None else "N/A"
            max_str = f"{MODEL_INPUT_TOKEN_LIMIT}" if MODEL_INPUT_TOKEN_LIMIT is not None else "?"
            if current_tokens is not None or total_tokens is not None:
                token_info_str = f"\n\n*Tokens del prompt: `{current_str}`, totales: `{total_str}/{max_str}`*"

            stripped_respuesta = respuesta.strip()
            sent_as_file = False
            MAX_MSG_LEN = 2000
            MAX_INFO_LEN = len(token_info_str)

            if stripped_respuesta.startswith("```") and '\n' in stripped_respuesta:
                try:
                    first_line_end = stripped_respuesta.find('\n')
                    language = stripped_respuesta[3:first_line_end].strip().lower()
                    code_start_index = first_line_end + 1
                    closing_marker_pos = stripped_respuesta.find("\n```", code_start_index)
                    code_content = None

                    if closing_marker_pos != -1:
                        code_content = stripped_respuesta[code_start_index:closing_marker_pos].strip()
                    else:
                        print(f"Advertencia: Bloque de código iniciado pero sin cierre claro ('\\n```'). Enviando como texto.")

                    if code_content:
                        extension = LANGUAGE_EXTENSIONS.get(language, DEFAULT_EXTENSION)
                        filename = f"respuesta_codigo{extension}"
                        code_bytes = io.BytesIO(code_content.encode('utf-8'))
                        discord_file = discord.File(fp=code_bytes, filename=filename)
                        caption = f"Respuesta con código ({language if language else 'desconocido'}):{token_info_str}"
                        if len(caption) > MAX_MSG_LEN:
                             caption = caption[:MAX_MSG_LEN-3] + "..."
                        await message.channel.send(caption, file=discord_file)
                        sent_as_file = True

                except Exception as file_error:
                    print(f"Error procesando/enviando código como archivo: {file_error}. Enviando como texto.")
                    sent_as_file = False

            if not sent_as_file:
                if stripped_respuesta:
                    available_len = MAX_MSG_LEN - MAX_INFO_LEN

                    if len(respuesta) <= available_len:
                        await message.channel.send(respuesta + token_info_str)
                    else:
                        parts_to_send = []
                        current_part = ""
                        for line in respuesta.splitlines(keepends=True):
                            if len(current_part) + len(line) <= (MAX_MSG_LEN - 10):
                                current_part += line
                            else:
                                parts_to_send.append(current_part)
                                current_part = line
                        if current_part:
                            parts_to_send.append(current_part)

                        for i, part in enumerate(parts_to_send[:-1]):
                            await message.channel.send(f"{part.strip()}...")

                        last_part = parts_to_send[-1]
                        if len(last_part) + MAX_INFO_LEN <= MAX_MSG_LEN:
                            await message.channel.send(last_part.strip() + token_info_str)
                        else:
                            await message.channel.send(last_part.strip()[:MAX_MSG_LEN - 3] + "...")
                            if MAX_INFO_LEN <= MAX_MSG_LEN:
                                await message.channel.send(token_info_str)
                            else:
                                await message.channel.send("*(Info de tokens demasiado larga)*")

                else:
                    await message.channel.send("..." + token_info_str)

    except asyncio.CancelledError:
        print("Tarea de generación cancelada.")
        await message.channel.send("🛑 Operación cancelada.")
        if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
    except genai.types.generation_types.StopCandidateException as sce:
         print(f"Generación detenida por el modelo: {sce}")
         await message.channel.send("⚠️ La generación fue detenida por el modelo (posiblemente contenido inseguro o fin inesperado).")
         if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
    except Exception as e:
        await message.channel.send("⚠️ Error inesperado procesando tu solicitud con la IA.")
        print(f"Error en on_message (Procesamiento Gemini): {type(e).__name__} - {str(e)}")
        if ctx_gemini.history and ctx_gemini.history[-1]['role'] == 'user': ctx_gemini.history.pop()
    finally:
        if ctx_gemini: ctx_gemini.stop_requested = False

async def show_menu(channel: discord.TextChannel, author: discord.Member):
    if not is_admin(author):
        await channel.send("🚫 No tienes permiso para usar este menú.", delete_after=10)
        return

    guild_cfg = get_guild_config(channel.guild.id)
    current_prefix = guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])
    channel_ctx = await _get_channel_ctx(channel.id)

    embed = discord.Embed(title=f"🔧 Menú de Configuración", color=0x00aaff)

    embed.add_field(name=f"Configuración de IA para el canal {channel.mention}:", value="\u200b", inline=False)
    persona_display = channel_ctx.settings['personalidad']
    if len(persona_display) > 150: persona_display = persona_display[:147] + "..."
    embed.add_field(name="🇦 Personalidad", value=f"```{persona_display if persona_display else 'Default'}```", inline=False)
    embed.add_field(name="🇧 Temperatura", value=f"`{channel_ctx.settings['temperatura']}`", inline=True)
    embed.add_field(name="🇨 Conversación Natural", value="✅ Activa" if channel_ctx.is_active else "☑️ Desactivada", inline=True)
    embed.add_field(name="🇩 Limpiar Historial", value="Iniciar una conversación como nueva", inline=True)
    embed.add_field(name="🇪 Restablecer configuración", value="Volver a los valores por defecto", inline=True)
    embed.add_field(name="", value="\u200b", inline=False)

    embed.add_field(name=f"Configuración de IA para el servidor ({channel.guild.name}):", value="\u200b", inline=False)
    bot_enabled_str = "✅ Habilitado" if guild_cfg.get('bot_enabled_for_users', True) else "☑️ Deshabilitado"
    embed.add_field(name="🇫 Disponibilidad para Usuarios", value=f"{bot_enabled_str} (`{current_prefix}(enable/disable)bot`)", inline=False)
    admin_role_id = guild_cfg.get('admin_role_id')
    admin_role_str = "No establecido"
    if admin_role_id:
        role = channel.guild.get_role(admin_role_id)
        admin_role_str = f"{role.mention}" if role else f"ID {admin_role_id} (No enc.)"
    embed.add_field(name="🇬 Rol de Administración", value=f"{admin_role_str} (`{current_prefix}setadminrole` siendo el dueño del servidor)", inline=False)
    allowed_channels_str = "Todos" if not guild_cfg.get('allowed_channel_ids') else f"{len(guild_cfg.get('allowed_channel_ids', []))} específ."
    embed.add_field(name="🇭 Canales Permitidos (Usuarios)", value=f"{allowed_channels_str} (`{current_prefix}listchannels`)", inline=False)
    embed.add_field(name="🇮 Prefijo del Servidor", value=f"El prefijo actual es: `{current_prefix}` (`{current_prefix}setprefix`)", inline=False)

    embed.add_field(name="", value="\u200b")

    embed.set_footer(text="Reacciona para ajustar IA del canal (🇦-🇪) o IA del servidor (🇫-🇮)")

    menu_msg = None
    try:
        menu_msg = await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"Error: Permiso denegado para enviar menú en {channel.id}"); return
    except Exception as e:
        print(f"Error enviando menú: {e}"); return

    menu_emojis = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '❌']
    for emoji in menu_emojis:
        try: await menu_msg.add_reaction(emoji)
        except discord.NotFound: return

    def check_menu(reaction, user):
        return user == author and reaction.message.id == menu_msg.id and str(reaction.emoji) in menu_emojis

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=120.0, check=check_menu)
        selected_emoji = str(reaction.emoji)

        try: await menu_msg.remove_reaction(selected_emoji, author)
        except (discord.Forbidden, discord.NotFound): pass

        delete_menu_after_action = True

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
                         channel_ctx.settings['personalidad'] = DEFAULT_SETTINGS['personalidad']
                         await channel.send(f"✅ Personalidad restablecida a default para {channel.mention}.", delete_after=15)
                    elif len(new_value) > 300:
                        await channel.send("⚠️ Descripción demasiado larga (máximo de 300). No se guardó.", delete_after=10)
                    else:
                        channel_ctx.settings['personalidad'] = new_value
                        display_persona = new_value if len(new_value) <= 100 else new_value[:97] + "..."
                        await channel.send(f"✅ Personalidad actualizada para {channel.mention}:\n```\n{display_persona}\n```", delete_after=15)
                    try: await user_response_msg.delete()
                    except (discord.Forbidden, discord.NotFound): pass
                else:
                    await channel.send("⚠️ No se proporcionó descripción. No se guardó.", delete_after=10)
            except asyncio.TimeoutError:
                await channel.send(f"⏰ Tiempo agotado para establecer personalidad.", delete_after=10)
            finally:
                 try: await prompt_msg.delete()
                 except (discord.Forbidden, discord.NotFound): pass

        elif selected_emoji == '🇧':
             await channel.send(f"ℹ️ Para ajustar la **temperatura** (creatividad) en {channel.mention}, usa:\n`{current_prefix}settemperature <0.0-1.0>` (ej: `{current_prefix}settemperature 0.7`)", delete_after=25)
             delete_menu_after_action = False

        elif selected_emoji == '🇨':
            await toggle_natural_conversation_command(commands.Context(message=menu_msg, bot=bot, view=None))

        elif selected_emoji == '🇪':
            await reset_channel_ai_command(commands.Context(message=menu_msg, bot=bot, view=None))

        elif selected_emoji == '🇩':
            await clear_channel_history_command(commands.Context(message=menu_msg, bot=bot, view=None))

        elif selected_emoji in ['🇫', '🇬', '🇭', '🇮']:
            await channel.send(f"ℹ️ Esta sección muestra información del servidor. Usa los comandos `{current_prefix}...` (ver `{current_prefix}helpconfig`) para gestionar la configuración global.", delete_after=20)
            delete_menu_after_action = False

    except asyncio.TimeoutError:
        await channel.send("⏰ Menú interactivo cerrado por inactividad.", delete_after=10)
        delete_menu_after_action = True
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"Error inesperado en menú interactivo: {e}")
        await channel.send("⚠️ Ocurrió un error con el menú.", delete_after=10)
        delete_menu_after_action = True
    finally:
        if delete_menu_after_action and menu_msg:
            try: await menu_msg.delete()
            except (discord.Forbidden, discord.NotFound): pass

if __name__ == '__main__':
    try:
        bot.run(DISCORD_TOKEN)
    except discord.PrivilegedIntentsRequired:
        print("\nError: Falta una o más Intents Privilegiadas (probablemente Members).")
        print("Ve al Portal de Desarrolladores de Discord -> Tu Aplicación -> Bot -> Privileged Gateway Intents y actívalas.")
    except discord.LoginFailure:
        print("\nError: Token de Discord inválido.")
    except Exception as e:
        print(f"Error fatal al iniciar el bot: {e}")
