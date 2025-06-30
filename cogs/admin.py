import discord
from discord.ext import commands

from core.config import config_manager, DEFAULT_GUILD_CONFIG
from core.contexts import context_manager
from core.openrouter_models import model_info_manager
from utils import is_admin_check, is_owner_check, perform_set_max_output_tokens, parse_model_id_from_input

class AdminCommands(commands.Cog):
    """Commands for server-wide administration of the bot."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='setprefix')
    @is_admin_check()
    @commands.guild_only()
    async def set_prefix(self, ctx: commands.Context, new_prefix: str):
        """Sets the command prefix for the server."""
        if not new_prefix:
            await ctx.send("❌ El prefijo no puede estar vacío."); return
        if len(new_prefix) > 5:
            await ctx.send("❌ Prefijo demasiado largo (máx 5 caracteres)."); return

        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['command_prefix'] = new_prefix
        config_manager.save_config()
        await ctx.send(f"✅ Prefijo para este servidor cambiado a: `{new_prefix}`")

    @commands.command(name='setadminrole')
    @is_owner_check()
    @commands.guild_only()
    async def set_admin_role(self, ctx: commands.Context, role: discord.Role):
        """Sets the admin role for the server."""
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['admin_role_id'] = role.id
        config_manager.save_config()
        await ctx.send(f"✅ Rol de admin para este servidor establecido a: **{role.name}** (`{role.id}`).")

    @commands.command(name='addchannel')
    @is_admin_check()
    @commands.guild_only()
    async def add_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Adds a channel to the list of allowed channels for non-admin users."""
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
        if channel.id in allowed_ids:
            await ctx.send(f"ℹ️ {channel.mention} ya estaba permitido."); return

        allowed_ids.append(channel.id)
        config_manager.save_config()
        await ctx.send(f"✅ {channel.mention} añadido a los canales permitidos.")

    @commands.command(name='removechannel')
    @is_admin_check()
    @commands.guild_only()
    async def remove_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Removes a channel from the list of allowed channels."""
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
        if channel.id not in allowed_ids:
            await ctx.send(f"ℹ️ {channel.mention} no estaba en la lista de permitidos."); return

        allowed_ids.remove(channel.id)
        config_manager.save_config()
        await ctx.send(f"✅ {channel.mention} eliminado de los canales permitidos.")

    @commands.command(name='listchannels')
    @is_admin_check()
    @commands.guild_only()
    async def list_allowed_channels(self, ctx: commands.Context):
        """Lists all channels where non-admin users can use the bot."""
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.get('allowed_channel_ids', [])

        if not allowed_ids:
            await ctx.send(f"✅ El bot está permitido en **todos** los canales para usuarios normales."); return

        mentions = [f"<#{channel_id}> (`{channel_id}`)" for channel_id in allowed_ids]
        description = "\n".join(mentions)
        embed = discord.Embed(title=f"Canales Permitidos en {ctx.guild.name}", description=description, color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name='setservermodel')
    @is_admin_check()
    @commands.guild_only()
    async def set_server_model_command(self, ctx: commands.Context, *, model_input: str):
        """Sets the default AI model for the server from a model ID or OpenRouter URL."""
        model_id = parse_model_id_from_input(model_input)
        
        # Use the new, consistent progress message style
        msg = await ctx.send(f"🔍 *Verificando compatibilidad para el modelo `{model_id}`...*")
        
        details = await model_info_manager.get_model_details(model_id)

        if not details:
            await msg.edit(content=f"❌ **Modelo no encontrado.** No pude encontrar un modelo con el ID `{model_id}` en OpenRouter.")
            return

        pricing = details.get('pricing', {})
        is_free = float(pricing.get('prompt', 0)) == 0 and float(pricing.get('completion', 0)) == 0
        if not is_free:
            await msg.edit(content=f"❌ **Modelo no gratuito.** El modelo `{model_id}` tiene un costo y no puede ser seleccionado.")
            return

        personality_supported = await model_info_manager.test_system_prompt_support(model_id)

        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['model'] = model_id
        config_manager.save_config()

        embed = discord.Embed(
            title="✅ Modelo del Servidor Actualizado",
            description=f"El modelo por defecto para este servidor ahora es **`{details.get('id')}`**.",
            color=discord.Color.green()
        )
        if description := details.get('description'):
            embed.add_field(name="Descripción", value=description, inline=False)
        
        embed.add_field(name="Contexto Máximo", value=f"`{details.get('context_length', 'N/A')} tokens`", inline=True)
        
        if personality_supported:
            embed.add_field(name="Soporte de Personalidad", value="✅ Soportado", inline=True)
        else:
            embed.add_field(name="Soporte de Personalidad", value="⚠️ No Soportado", inline=True)
            embed.set_footer(text="Nota: La personalidad será ignorada para este modelo.")
        
        await msg.edit(content=None, embed=embed)

    @commands.command(name="setmaxoutput")
    @is_admin_check()
    @commands.guild_only()
    async def set_max_output_tokens_command(self, ctx: commands.Context, max_tokens: int):
        """Sets the maximum output tokens for the AI's responses."""
        await perform_set_max_output_tokens(ctx, max_tokens)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))