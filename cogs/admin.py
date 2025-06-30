import discord
from discord.ext import commands

from core.config import config_manager
from utils import is_admin_check, is_owner_check, parse_model_id_from_input, perform_set_max_output_tokens, set_and_verify_model

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

    @commands.command(name='removechannel')
    @is_admin_check()
    @commands.guild_only()
    async def remove_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
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
        model_id = parse_model_id_from_input(model_input)
        
        success, response_data = await set_and_verify_model(ctx, model_id)
        
        if not success:
            return

        msg, embed = response_data
        
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['model'] = model_id
        config_manager.save_config()

        embed.description = f"El modelo por defecto para este servidor ahora es **`{model_id}`**."
        await msg.edit(content=None, embed=embed)

    @commands.command(name="setmaxoutput")
    @is_admin_check()
    @commands.guild_only()
    async def set_max_output_tokens_command(self, ctx: commands.Context, max_tokens: int):
        await perform_set_max_output_tokens(ctx, max_tokens)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))