import discord
import re
import datetime
from discord.ext import commands
from discord.ui import View, Button
from core.config import config_manager
from core.contexts import context_manager
from core.openrouter_models import model_info_manager

MODELS_PER_PAGE = 5

# --- Sorting Logic ---
SORT_KEYS = {
    'newest': {'key': 'created', 'reverse': True},
    'context': {'key': 'context_length', 'reverse': True},
}
SORT_KEY_NAMES = list(SORT_KEYS.keys())

# --- Spanish Date Formatting ---
SPANISH_MONTHS = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}

class ModelsPaginator(View):
    """A view to handle pagination for the !models command."""
    def __init__(self, models: list, prefix: str, search_query: str = None, sort_key: str = None):
        super().__init__(timeout=300)
        self.models = models
        self.prefix = prefix
        self.search_query = search_query
        self.sort_key = sort_key
        self.current_page = 0
        self.total_pages = (len(self.models) - 1) // MODELS_PER_PAGE

    async def create_embed(self) -> discord.Embed:
        """Creates the embed for the current page."""
        title = "🤖 Modelos Gratuitos Disponibles"
        if self.search_query:
            title += f" (Búsqueda: '{self.search_query}')"

        description = "Usa los comandos `!setservermodel` o `!setmodel` para seleccionar uno."
        sort_display = self.sort_key or "newest" # Show default sort if none is chosen
        description += f"\n*Ordenado por: {sort_display.capitalize()}*"

        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())

        start_index = self.current_page * MODELS_PER_PAGE
        end_index = start_index + MODELS_PER_PAGE
        page_models = self.models[start_index:end_index]

        for model in page_models:
            model_id = model.get('id', 'N/A')
            model_name = model.get('name', 'Nombre Desconocido')
            context_size = model.get('context_length', 0)
            
            created_timestamp = model.get('created', 0)
            date_str = "N/A"
            if created_timestamp and isinstance(created_timestamp, (int, float)):
                try:
                    dt_object = datetime.datetime.fromtimestamp(created_timestamp)
                    # Format date in Spanish using the dictionary
                    month_es = SPANISH_MONTHS.get(dt_object.month, '?')
                    date_str = f"{dt_object.day} {month_es}, {dt_object.year}"
                except (ValueError, TypeError):
                    date_str = "N/A"
            
            url = f"https://openrouter.ai/models/{model_id}"
            context_str = f"{context_size // 1000}K" if context_size else "N/A"
            provider = model_id.split('/')[0] if '/' in model_id else "Desconocido"
            
            embed.add_field(
                name=f"🔹 {model_name}",
                value=f"[Ver en OpenRouter]({url}) | **Contexto:** {context_str} | **Por:** `{provider}` | **Creado:** {date_str}",
                inline=False
            )

        embed.set_footer(text=f"Página {self.current_page + 1} de {self.total_pages + 1} | Modelos Encontrados: {len(self.models)}")
        return embed

    def update_buttons(self):
        """Enables or disables buttons based on the current page."""
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Siguiente ➡️", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_buttons()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

class GeneralCommands(commands.Cog):
    """General purpose commands, like the help command."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='help')
    @commands.guild_only()
    async def help_command(self, ctx: commands.Context):
        """Displays a comprehensive help message for the bot."""
        prefix = ctx.prefix
        embed = discord.Embed(title=f"🤖 Ayuda del Bot", color=discord.Color.purple())
        embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar.url)

        embed.add_field(
            name="🗣️ Interacción Principal",
            value=f"Mencióname (`@{self.bot.user.display_name}`) seguido de tu pregunta para hablar conmigo.",
            inline=False
        )

        embed.add_field(
            name=f"💬 Configuración por Canal (Admins)",
            value=f"`{prefix}setmodel <nombre_modelo/default>` - Asigna un modelo a este canal.\n"
                  f"`{prefix}setpersonality <texto>` - Define la personalidad de la IA.\n"
                  f"`{prefix}settemperature <0.0-1.0>` - Cambia la creatividad de la IA.\n"
                  f"`{prefix}togglenatural` - Activa/desactiva respuesta sin mención.\n"
                  f"`{prefix}clearhistory` - Borra el historial de conversación del canal.\n"
                  f"`{prefix}resetai` - Restablece todas las opciones de IA del canal.",
            inline=False
        )

        embed.add_field(
            name=f"⚙️ Configuración del Servidor (Admins)",
            value=f"`{prefix}setservermodel <nombre_modelo>` - Asigna el modelo por defecto del servidor.\n"
                  f"`{prefix}setprefix <prefijo>` - Cambia el prefijo de comandos.\n"
                  f"`{prefix}showconfig` - Muestra la configuración actual.",
            inline=False
        )
        
        embed.add_field(
            name=f"👑 Configuración del Dueño del Servidor",
            value=f"`{prefix}setadminrole <@Rol>` - Establece el rol con permisos de admin del bot.",
            inline=False
        )

        embed.set_footer(text="Admin = Dueño, rol de admin, o permiso 'Administrador'")
        await ctx.send(embed=embed)

    @commands.command(name='showconfig')
    @commands.guild_only() # Kept guild_only as config is guild-specific
    async def show_config_command(self, ctx: commands.Context):
        """Displays the current server and channel configuration."""
        msg = await ctx.send("🔍 *Verificando configuración y compatibilidad del modelo...*")

        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        
        # Server settings
        prefix = guild_cfg.get('command_prefix')
        server_model = guild_cfg.get('model')
        admin_role_id = guild_cfg.get('admin_role_id')
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else "No establecido"
        admin_role_str = admin_role.mention if isinstance(admin_role, discord.Role) else admin_role

        # Channel settings
        ch_settings = channel_context.settings
        ch_model_override = ch_settings.get('model')
        ch_temp = ch_settings.get('temperature')
        ch_persona = ch_settings.get('personality', 'Por defecto')
        ch_natural = ch_settings.get('natural_conversation', False)
        
        active_model_name = ch_model_override or server_model
        
        personality_supported = await model_info_manager.test_system_prompt_support(active_model_name)
        
        if personality_supported:
            personality_display_str = f"```{ch_persona[:200].strip()}...```" if len(ch_persona) > 203 else f"```{ch_persona.strip()}```"
        else:
            personality_display_str = "`Desactivada por el modelo`"
        
        ch_model_str = f"`{ch_model_override}`" if ch_model_override else f"Usa el del servidor (`{server_model}`)"
        
        embed = discord.Embed(title=f"📄 Configuración Actual", color=discord.Color.blue())
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)

        embed.add_field(
            name="⚙️ Configuración del Servidor",
            value=f"**Prefijo:** `{prefix}`\n"
                  f"**Rol Admin:** {admin_role_str}\n"
                  f"**Modelo por Defecto:** `{server_model}`",
            inline=False
        )
        embed.add_field(
            name=f"💬 Configuración de Canal ({ctx.channel.mention})",
            value=f"**Modelo Activo:** `{active_model_name}`\n"
                  f"**Temperatura:** `{ch_temp}`\n"
                  f"**Conversación Natural:** {'✅ Activada' if ch_natural else '❌ Desactivada'}\n"
                  f"**Personalidad:** {personality_display_str}",
            inline=False
        )
        
        await msg.edit(content=None, embed=embed)

    @commands.command(name='models')
    @commands.guild_only()
    async def list_models_command(self, ctx: commands.Context, *, args: str = ""):
        """Lists available free models with optional search and sorting."""
        msg = await ctx.send("🔍 *Buscando modelos gratuitos en OpenRouter...*")

        # Argument Parsing
        raw_args = args.split()
        search_query = ""
        sort_key_arg = None
        if raw_args:
            if raw_args[-1].lower() in SORT_KEY_NAMES:
                sort_key_arg = raw_args.pop().lower()
            search_query = " ".join(raw_args).strip()

        # Model Fetching and Filtering
        all_models_dict = await model_info_manager.get_all_models()
        if not all_models_dict:
            await msg.edit(content="❌ No se pudo obtener la lista de modelos de la API de OpenRouter.")
            return

        free_models = [
            model for model in all_models_dict.values() 
            if float(model.get('pricing', {}).get('prompt', 1)) == 0 and float(model.get('pricing', {}).get('completion', 1)) == 0
        ]
        
        if not free_models:
            await msg.edit(content="ℹ️ No se encontraron modelos gratuitos en este momento.")
            return

        # Apply Search Query
        if search_query:
            free_models = [
                m for m in free_models 
                if search_query.lower() in m.get('name', '').lower() or search_query.lower() in m.get('id', '').lower()
            ]

        # Apply Sorting
        if sort_key_arg:
            sort_info = SORT_KEYS[sort_key_arg]
            free_models.sort(key=lambda m: m.get(sort_info['key'], 0), reverse=sort_info['reverse'])
        else:
            # Default sort: by newest
            free_models.sort(key=lambda m: m.get('created', 0), reverse=True)

        if not free_models:
            await msg.edit(content=f"ℹ️ No se encontraron modelos que coincidan con tu búsqueda de '{search_query}'.")
            return
            
        paginator = ModelsPaginator(models=free_models, prefix=ctx.prefix, search_query=search_query, sort_key=sort_key_arg)
        paginator.update_buttons()
        initial_embed = await paginator.create_embed()
        
        await msg.edit(content=None, embed=initial_embed, view=paginator)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCommands(bot))