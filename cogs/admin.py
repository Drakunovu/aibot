import discord
from discord.ext import commands

from core.config import config_manager, DEFAULT_GUILD_CONFIG
from utils import is_admin_check, is_owner_check

class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='setprefix')
    @is_admin_check()
    @commands.guild_only()
    async def set_prefix(self, ctx: commands.Context, new_prefix: str):
        if not new_prefix:
            await ctx.send("❌ El prefijo no puede estar vacío."); return
        if len(new_prefix) > 5:
            await ctx.send("❌ Prefijo demasiado largo (máx 5 caracteres)."); return

        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        current_prefix = guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])
        if new_prefix == current_prefix:
            await ctx.send(f"ℹ️ El prefijo para este servidor ya es `{new_prefix}`."); return

        guild_cfg['command_prefix'] = new_prefix
        config_manager.save_config()
        await ctx.send(f"✅ Prefijo para este servidor cambiado a: `{new_prefix}`")

    @commands.command(name='setadminrole')
    @is_owner_check()
    @commands.guild_only()
    async def set_admin_role(self, ctx: commands.Context, role: discord.Role):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['admin_role_id'] = role.id
        config_manager.save_config()
        await ctx.send(f"✅ Rol de admin para este servidor establecido a: **{role.name}** (`{role.id}`).")

    @commands.command(name='addchannel')
    @is_admin_check()
    @commands.guild_only()
    async def add_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
        if channel.id in allowed_ids:
            await ctx.send(f"ℹ️ {channel.mention} ya estaba permitido."); return

        allowed_ids.append(channel.id)
        config_manager.save_config()
        await ctx.send(f"✅ {channel.mention} añadido a los canales permitidos.")
        if len(allowed_ids) == 1:
            await ctx.send("ℹ️ Nota: Ahora el bot SOLO funcionará para usuarios normales en los canales de esta lista en este servidor (admins pueden usarlo en cualquier canal).")

    @commands.command(name='removechannel')
    @is_admin_check()
    @commands.guild_only()
    async def remove_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.setdefault('allowed_channel_ids', [])
        if channel.id not in allowed_ids:
            await ctx.send(f"ℹ️ {channel.mention} no estaba en la lista de permitidos."); return

        try:
            allowed_ids.remove(channel.id)
            config_manager.save_config()
            await ctx.send(f"✅ {channel.mention} eliminado de los canales permitidos.")
            if not allowed_ids:
                await ctx.send("ℹ️ Nota: La lista de canales permitidos está vacía. El bot funcionará en **todos** los canales de este servidor para usuarios normales.")
        except ValueError:
             print(f"Advertencia: Se intentó remover canal {channel.id} que no estaba en la lista {allowed_ids}")
             await ctx.send(f"ℹ️ {channel.mention} no estaba en la lista de permitidos."); return


    @commands.command(name='listchannels')
    @is_admin_check()
    @commands.guild_only()
    async def list_allowed_channels(self, ctx: commands.Context):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        allowed_ids = guild_cfg.get('allowed_channel_ids', [])

        if not allowed_ids:
            await ctx.send(f"✅ Bot permitido en **todos** los canales de **{ctx.guild.name}** para usuarios normales."); return

        mentions = []
        not_found_ids = []
        for channel_id in allowed_ids:
            channel_obj = ctx.guild.get_channel(channel_id)
            if channel_obj:
                mentions.append(f"{channel_obj.mention} (`{channel_id}`)")
            else:
                not_found_ids.append(f"`{channel_id}`")

        description = "\n".join(mentions) if mentions else "Ningún canal permitido encontrado (o todos fueron borrados)."
        if not_found_ids:
            description += f"\n\n**IDs de canales no encontrados (quizás borrados):** {', '.join(not_found_ids)}"

        embed = discord.Embed(title=f"Canales Permitidos en {ctx.guild.name}", description=description, color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name='enablebot')
    @is_admin_check()
    @commands.guild_only()
    async def enable_bot_for_users(self, ctx: commands.Context):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        if guild_cfg.get('bot_enabled_for_users', True):
            await ctx.send(f"ℹ️ El bot ya está habilitado para usuarios normales en **{ctx.guild.name}**."); return

        guild_cfg['bot_enabled_for_users'] = True
        config_manager.save_config()
        await ctx.send(f"✅ Bot **habilitado** para usuarios normales en **{ctx.guild.name}**.")

    @commands.command(name='disablebot')
    @is_admin_check()
    @commands.guild_only()
    async def disable_bot_for_users(self, ctx: commands.Context):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        if not guild_cfg.get('bot_enabled_for_users', True):
            await ctx.send(f"ℹ️ El bot ya está deshabilitado para usuarios normales en **{ctx.guild.name}**."); return

        guild_cfg['bot_enabled_for_users'] = False
        config_manager.save_config()
        await ctx.send(f"☑️ Bot **deshabilitado** para usuarios normales en **{ctx.guild.name}** (admins aún pueden usarlo).")

    @commands.command(name='showconfig')
    @is_admin_check()
    @commands.guild_only()
    async def show_config_command(self, ctx: commands.Context):
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        admin_role_id = guild_cfg.get('admin_role_id')
        allowed_ids = guild_cfg.get('allowed_channel_ids', [])
        bot_enabled = guild_cfg.get('bot_enabled_for_users', True)
        current_prefix = guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])

        admin_role_str = "No establecido"
        if admin_role_id:
            role_obj = ctx.guild.get_role(admin_role_id)
            admin_role_str = f"{role_obj.name} (`{role_obj.id}`)" if role_obj else f"ID: `{admin_role_id}` (Rol no encontrado)"

        channels_str = "Todos" if not allowed_ids else f"{len(allowed_ids)} específicos (usa `{current_prefix}listchannels`)"
        enabled_str = "✅ Habilitado" if bot_enabled else "☑️ Deshabilitado (solo admins)"

        embed = discord.Embed(title=f"Configuración del Bot para {ctx.guild.name}", color=discord.Color.green())
        embed.add_field(name="Prefijo", value=f"`{current_prefix}`", inline=True)
        embed.add_field(name="Estado para Usuarios", value=enabled_str, inline=True)
        embed.add_field(name="Rol Admin", value=admin_role_str, inline=False)
        embed.add_field(name="Canales Permitidos (Usuarios)", value=channels_str, inline=False)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
