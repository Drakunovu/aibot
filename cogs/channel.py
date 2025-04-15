import discord
from discord.ext import commands
import typing

from utils import (
    is_admin_check,
    perform_toggle_natural,
    perform_reset_channel_ai,
    perform_clear_history,
)
from core.contexts import context_manager, MODEL_INPUT_TOKEN_LIMIT
from core.config import DEFAULT_AI_SETTINGS

class ChannelCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _determine_target_channel_and_args(self, ctx: commands.Context, args: tuple) -> typing.Tuple[typing.Optional[discord.TextChannel], tuple]:
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
            except commands.BadArgument:
                 pass

        return target_channel, value_args

    @commands.command(name='setpersonality', aliases=['setpersona'])
    @is_admin_check()
    @commands.guild_only()
    async def set_personality_command(self, ctx: commands.Context, *args):
        target_channel, value_args = await self._determine_target_channel_and_args(ctx, args)

        if not value_args:
            await ctx.send(f"❌ Debes especificar una personalidad. Ejemplo: `{ctx.prefix}setpersonality Tono: amigable.` o `{ctx.prefix}setpersonality #{target_channel.name} Tono: formal.`"); return

        new_personality = " ".join(value_args).strip()

        if not new_personality:
             await ctx.send(f"❌ La personalidad no puede estar vacía."); return
        if len(new_personality) > 300:
            await ctx.send("❌ Descripción de personalidad demasiado larga (máx 300 caracteres)."); return

        channel_context = await context_manager.get_channel_ctx(target_channel.id)
        current_personality = channel_context.settings.get('personality', DEFAULT_AI_SETTINGS['personality'])

        if new_personality == current_personality:
            await ctx.send(f"ℹ️ La personalidad para {target_channel.mention} ya estaba establecida así.")
            return

        channel_context.settings['personality'] = new_personality

        display_personality = channel_context.settings['personality']
        if len(display_personality) > 100:
            display_personality = display_personality[:97] + "..."
        await ctx.send(f"✅ Personalidad para {target_channel.mention} actualizada a:\n```\n{display_personality}\n```")

    @commands.command(name='settemperature', aliases=['settemp'])
    @is_admin_check()
    @commands.guild_only()
    async def set_temperature_command(self, ctx: commands.Context, *args):
        target_channel, value_args = await self._determine_target_channel_and_args(ctx, args)

        if not value_args:
            await ctx.send(f"❌ Debes especificar una temperatura (0.0-1.0). Ejemplo: `{ctx.prefix}settemperature 0.7` o `{ctx.prefix}settemperature #{target_channel.name} 0.9`"); return

        try:
            temp_value = float(value_args[0])
            if not 0.0 <= temp_value <= 1.0:
                raise ValueError("Temperature out of range")
        except (ValueError, IndexError):
            await ctx.send("❌ La temperatura debe ser un número entre 0.0 y 1.0."); return

        channel_context = await context_manager.get_channel_ctx(target_channel.id)
        current_temp = channel_context.settings.get('temperature', DEFAULT_AI_SETTINGS['temperature'])

        if temp_value == current_temp:
             await ctx.send(f"ℹ️ La temperatura para {target_channel.mention} ya era `{temp_value}`.")
             return

        channel_context.settings['temperature'] = temp_value
        await ctx.send(f"✅ Temperatura de IA para {target_channel.mention} actualizada a: `{channel_context.settings['temperature']}`")

    @commands.command(name='resetai', aliases=['reset_ai'])
    @is_admin_check()
    @commands.guild_only()
    async def reset_channel_ai_command(self, ctx: commands.Context, target_channel: typing.Optional[discord.TextChannel] = None):
        if target_channel is None:
            target_channel = ctx.channel
        elif target_channel.guild != ctx.guild:
             await ctx.send("❌ No puedes modificar la configuración de un canal de otro servidor.")
             return
        await perform_reset_channel_ai(ctx, target_channel)

    @commands.command(name='clearhistory', aliases=['ch'])
    @is_admin_check()
    @commands.guild_only()
    async def clear_channel_history_command(self, ctx: commands.Context, target_channel: typing.Optional[discord.TextChannel] = None):
        if target_channel is None:
            target_channel = ctx.channel
        elif target_channel.guild != ctx.guild:
             await ctx.send("❌ No puedes modificar la configuración de un canal de otro servidor.")
             return
        await perform_clear_history(ctx, target_channel)

    @commands.command(name='togglenatural', aliases=['natural_conv'])
    @is_admin_check()
    @commands.guild_only()
    async def toggle_natural_conversation_command(self, ctx: commands.Context, target_channel: typing.Optional[discord.TextChannel] = None):
        if target_channel is None:
            target_channel = ctx.channel
        elif target_channel.guild != ctx.guild:
             await ctx.send("❌ No puedes modificar la configuración de un canal de otro servidor.")
             return
        await perform_toggle_natural(ctx, target_channel)

    @commands.command(name='tokencount', aliases=['context_size', 'tokens', 'history_tokens'])
    @is_admin_check()
    @commands.guild_only()
    async def token_count_command(self, ctx: commands.Context, target_channel: typing.Optional[discord.TextChannel] = None):
        if target_channel is None:
            target_channel = ctx.channel
        elif target_channel.guild != ctx.guild:
             await ctx.send("❌ No puedes ver la información de un canal de otro servidor.")
             return

        channel_context = await context_manager.get_channel_ctx(target_channel.id)

        if not channel_context.history:
            await ctx.send(f"ℹ️ No hay historial de conversación registrado para {target_channel.mention}.")
            return

        contents_for_api = []
        for msg in channel_context.history:
            msg_parts = msg.get('parts', [])
            if isinstance(msg_parts, dict): msg_parts = [msg_parts]
            if msg.get('role') and msg_parts:
                valid_parts = [part for part in msg_parts if part]
                if valid_parts:
                    contents_for_api.append({'role': msg.get('role'), 'parts': valid_parts})


        if not contents_for_api:
            await ctx.send(f"ℹ️ El historial de {target_channel.mention} está vacío o no contiene partes válidas para el conteo.")
            return

        model = channel_context.create_model()
        if model is None:
            await ctx.send(f"⚠️ Error crítico: No se pudo crear una instancia del modelo de IA para {target_channel.mention} para contar tokens.")
            return

        try:
            async with ctx.typing():
                if not contents_for_api:
                     await ctx.send(f"ℹ️ No hay contenido válido en el historial de {target_channel.mention} para contar.")
                     return

                response = await model.count_tokens_async(contents_for_api)
                token_count = response.total_tokens

            embed = discord.Embed(
                title=f"📊 Conteo de Tokens en {target_channel.mention}",
                description=f"Estimación del tamaño del historial de conversación actual.",
                color=discord.Color.blue()
            )
            max_str = f"{MODEL_INPUT_TOKEN_LIMIT}" if MODEL_INPUT_TOKEN_LIMIT is not None else "?"
            embed.add_field(name="Tokens Totales Estimados", value=f"`{token_count}/{max_str}`", inline=False)
            embed.add_field(name="Mensajes en Historial", value=f"`{len(channel_context.history)}` (Usuario + Modelo)", inline=False)
            embed.set_footer(text=f"Contado usando el modelo: {model.model_name}. La API puede tener límites diferentes.")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"⚠️ Error al contar los tokens para {target_channel.mention}: {e}")
            print(f"Error en comando tokencount ({target_channel.id}): {type(e).__name__} - {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelCommands(bot))
