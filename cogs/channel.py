import typing

import discord
from discord.ext import commands

from core.contexts import context_manager
from utils import (
    is_admin_check,
    parse_model_id_from_input,
    request_confirmation,
    reset_channel_settings,
    set_and_verify_model,
)

class ChannelCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _determine_target_channel_and_args(self, ctx: commands.Context, args: tuple) -> typing.Tuple[discord.TextChannel, tuple]:
        target_channel = ctx.channel
        value_args = args

        if args:
            try:
                potential_channel = await commands.TextChannelConverter().convert(ctx, args[0])
                if potential_channel.guild == ctx.guild:
                    target_channel = potential_channel
                    value_args = args[1:]
            except commands.ChannelNotFound:
                pass
        
        return target_channel, value_args

    @commands.command(name='setmodel')
    @is_admin_check()
    @commands.guild_only()
    async def set_model_command(self, ctx: commands.Context, *, model_input: str = None):
        target_channel, value_args = await self._determine_target_channel_and_args(ctx, (model_input,) if model_input else tuple())
        
        raw_input = " ".join(value_args).strip()
        if not raw_input:
            await ctx.send("❌ Debes especificar un ID de modelo, una URL de OpenRouter, o la palabra `default`.")
            return

        channel_context = await context_manager.get_channel_ctx(target_channel.id)

        if raw_input.lower() in ['default', 'reset']:
            if 'model' in channel_context.settings:
                del channel_context.settings['model']
            await ctx.send(f"✅ Modelo para {target_channel.mention} restablecido al por defecto del servidor.")
            return

        model_id = parse_model_id_from_input(raw_input)
        
        success, response_data = await set_and_verify_model(ctx, model_id)

        if not success:
            return

        msg, embed = response_data

        channel_context.settings['model'] = model_id
        
        embed.title = "✅ Modelo del Canal Actualizado"
        embed.description = f"El modelo para el canal {target_channel.mention} ahora es **`{model_id}`**."
        await msg.edit(content=None, embed=embed)

    @commands.command(name='setpersonality', aliases=['setpersona'])
    @is_admin_check()
    @commands.guild_only()
    async def set_personality_command(self, ctx: commands.Context, *, personality: str):
        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        if len(personality) > 500:
            await ctx.send("❌ La personalidad es demasiado larga (máximo 500 caracteres).")
            return
        channel_context.settings['personality'] = personality
        await ctx.send(f"✅ Personalidad para {ctx.channel.mention} actualizada.")

    @commands.command(name='settemperature', aliases=['settemp'])
    @is_admin_check()
    @commands.guild_only()
    async def set_temperature_command(self, ctx: commands.Context, temp_value: float):
        if not 0.0 <= temp_value <= 1.0:
            await ctx.send("❌ La temperatura debe ser un número entre 0.0 y 1.0.")
            return
        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        channel_context.settings['temperature'] = temp_value
        await ctx.send(f"✅ Temperatura de IA para {ctx.channel.mention} actualizada a: `{temp_value}`")

    @commands.command(name='togglenatural')
    @is_admin_check()
    @commands.guild_only()
    async def toggle_natural_conversation_command(self, ctx: commands.Context):
        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        current_state = channel_context.settings.get('natural_conversation', False)
        new_state = not current_state
        channel_context.settings['natural_conversation'] = new_state
        state_text = "Activada" if new_state else "Desactivada"
        await ctx.send(f"✅ Conversación natural **{state_text}** en este canal.")

    @commands.command(name='clearhistory', aliases=['ch'])
    @is_admin_check()
    @commands.guild_only()
    async def clear_channel_history_command(self, ctx: commands.Context):
        if await request_confirmation(ctx, f"borrar **todo** el historial de la IA para {ctx.channel.mention}"):
            channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
            channel_context.history.clear()
            await ctx.send(f"🧹 Historial de IA para {ctx.channel.mention} limpiado.", delete_after=15)

    @commands.command(name='resetai', aliases=['reset'])
    @is_admin_check()
    @commands.guild_only()
    async def reset_channel_ai_command(self, ctx: commands.Context):
        if await request_confirmation(ctx, f"restablecer **toda** la configuración de la IA de {ctx.channel.mention}"):
            channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
            reset_channel_settings(channel_context)
            await ctx.send(f"⚙️ Configuración de IA para {ctx.channel.mention} restablecida.", delete_after=15)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelCommands(bot))