import discord
from discord.ext import commands

from utils import (
    is_admin_check,
    perform_toggle_natural,
    perform_reset_channel_ai,
    perform_clear_history
)
from core.contexts import context_manager, MODEL_INPUT_TOKEN_LIMIT

class ChannelCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='setpersonality', aliases=['set_persona'])
    @is_admin_check()
    @commands.guild_only()
    async def set_personality_command(self, ctx: commands.Context, *, new_personality: str):
        if not new_personality:
            await ctx.send(f"❌ Debes especificar una personalidad. Ejemplo: `{ctx.prefix}setpersonality Tono: amigable. Estilo: informal.`"); return
        if len(new_personality) > 300:
            await ctx.send("❌ Descripción de personalidad demasiado larga (máx 300 caracteres)."); return

        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        channel_context.settings['personality'] = new_personality.strip()

        display_personality = channel_context.settings['personality']
        if len(display_personality) > 100:
            display_personality = display_personality[:97] + "..."
        await ctx.send(f"✅ Personalidad para {ctx.channel.mention} actualizada a:\n```\n{display_personality}\n```")

    @commands.command(name='settemperature', aliases=['set_temp'])
    @is_admin_check()
    @commands.guild_only()
    async def set_temperature_command(self, ctx: commands.Context, new_temperature: float):
        try:
            temp_value = float(new_temperature)
            if not 0.0 <= temp_value <= 1.0:
                raise ValueError("Temperature out of range")
        except ValueError:
            await ctx.send("❌ La temperatura debe ser un número entre 0.0 y 1.0."); return

        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
        channel_context.settings['temperature'] = temp_value
        await ctx.send(f"✅ Temperatura de IA para {ctx.channel.mention} actualizada a: `{channel_context.settings['temperature']}`")

    @commands.command(name='resetai', aliases=['reset_ai'])
    @is_admin_check()
    @commands.guild_only()
    async def reset_channel_ai_command(self, ctx: commands.Context):
        await perform_reset_channel_ai(ctx)

    @commands.command(name='clearhistory', aliases=['clear_history'])
    @is_admin_check()
    @commands.guild_only()
    async def clear_channel_history_command(self, ctx: commands.Context):
        await perform_clear_history(ctx)

    @commands.command(name='togglenatural', aliases=['natural_conv'])
    @is_admin_check()
    @commands.guild_only()
    async def toggle_natural_conversation_command(self, ctx: commands.Context):
        await perform_toggle_natural(ctx)

    @commands.command(name='tokencount', aliases=['context_size', 'tokens', 'history_tokens'])
    @is_admin_check()
    @commands.guild_only()
    async def token_count_command(self, ctx: commands.Context):
        channel_context = await context_manager.get_channel_ctx(ctx.channel.id)

        if not channel_context.history:
            await ctx.send(f"ℹ️ No hay historial de conversación registrado para {ctx.channel.mention}.")
            return

        contents_for_api = []
        for msg in channel_context.history:
            msg_parts = msg.get('parts', [])
            if isinstance(msg_parts, dict): msg_parts = [msg_parts]
            if msg.get('role') and msg_parts:
                contents_for_api.append({'role': msg.get('role'), 'parts': msg_parts})

        if not contents_for_api:
            await ctx.send(f"ℹ️ El historial de {ctx.channel.mention} está vacío o no se pudo formatear para el conteo.")
            return

        model = channel_context.create_model()
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
            embed.add_field(name="Mensajes en Historial", value=f"`{len(channel_context.history)}` (Usuario + Modelo)", inline=False)
            embed.set_footer(text=f"Contado usando el modelo: {model.model_name}. La API puede tener límites diferentes.")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"⚠️ Error al contar los tokens: {e}")
             # --- PRINT EN ESPAÑOL ---
            print(f"Error en comando tokencount: {type(e).__name__} - {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelCommands(bot))
