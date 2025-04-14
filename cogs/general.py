import discord
from discord.ext import commands

class GeneralCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='help', aliases=['help_bot'])
    @commands.guild_only()
    async def help_command(self, ctx: commands.Context):
        current_prefix = ctx.prefix
        embed = discord.Embed(title=f"🤖 Ayuda del Bot Gemini ({ctx.guild.name})", color=discord.Color.purple())

        embed.add_field(name="🗣️ Interacción Principal", value=f"""
        - Mencióname (`@{self.bot.user.display_name}`) seguido de tu mensaje o adjunta un archivo para interactuar.
        - Si la 'Conversación Natural' está activa en un canal (ver comando `{current_prefix}togglenatural` o menú), puedes hablar sin mencionarme (si el canal está permitido para usuarios).
        """, inline=False)

        embed.add_field(name="", value="\u200b", inline=False)

        embed.add_field(name="✨ Menú Interactivo (mención sin texto)", value="""
        Menciona al bot sin texto adicional para abrir el menú (solo **admins**). Permite configurar la IA **por canal** y ver comandos globales:
        - **Personalidad:** Define directamente cómo debe responder la IA.
        - **Temperatura:** Ajusta la creatividad (muestra comando).
        - **Conversación Natural:** Activar/desactivar respuesta sin mención.
        - **Restablecer IA Canal:** Volver a por defecto de IA para ese canal.
        - **Borrar Historial IA Canal:** Limpiar memoria de ese canal.
        - **Ver Comandos Globales:** Muestra info y comandos para config del servidor.
        """, inline=False)

        embed.add_field(name="", value="\u200b", inline=False)

        embed.add_field(name=f"🔧 Configuración IA por Canal (Admins)", value=f"""
        *(Afectan solo al canal donde se usan)*
        `{current_prefix}setpersonality <descripción>` / `set_persona` - Define personalidad/tono/estilo.
        `{current_prefix}settemperature <0.0-1.0>` / `set_temp` - Cambia la creatividad/aleatoriedad.
        `{current_prefix}togglenatural` / `natural_conv` - Activa/desactiva respuesta sin mención.
        `{current_prefix}resetai` / `reset_ai` - Restablece config. de IA para el canal a por defecto (pide confirmación).
        `{current_prefix}clearhistory` / `clear_history` - Borra historial de la IA para el canal (pide confirmación).
        `{current_prefix}tokencount` / `context_size` / `tokens` / `history_tokens` - Muestra tokens estimados en el historial actual.
        """, inline=False)

        embed.add_field(name="", value="\u200b", inline=False)

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

        embed.add_field(name="", value="\u200b", inline=False)

        embed.set_footer(text=f"Admin = Dueño, rol admin configurado, o permiso 'Administrador' | Dueño = Creador del servidor")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCommands(bot))
