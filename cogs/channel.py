import discord
from discord.ext import commands
import typing

from utils import is_admin_check, request_confirmation, reset_channel_ai_settings, parse_model_id_from_input
from core.contexts import context_manager
from core.config import DEFAULT_AI_SETTINGS
from core.openrouter_models import model_info_manager

class ChannelCommands(commands.Cog):
    """Commands for channel-specific AI configuration."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _determine_target_channel_and_args(self, ctx: commands.Context, args: tuple) -> typing.Tuple[discord.TextChannel, tuple]:
        """Helper to allow commands to optionally target another channel."""
        target_channel = ctx.channel
        value_args = args

        if args:
            try:
                # Check if the first argument is a channel mention
                potential_channel = await commands.TextChannelConverter().convert(ctx, args[0])
                if potential_channel.guild == ctx.guild:
                    target_channel = potential_channel
                    value_args = args[1:]
            except commands.ChannelNotFound:
                pass # Not a channel, so treat it as part of the value
        
        return target_channel, value_args

    @commands.command(name='setmodel')
    @is_admin_check()
    @commands.guild_only()
    async def set_model_command(self, ctx: commands.Context, *, model_input: str = None):
        """Sets or resets the AI model for a specific channel from a model ID or OpenRouter URL."""
        target_channel, value_args = await self._determine_target_channel_and_args(ctx, (model_input,) if model_input else tuple())
        
        raw_input = " ".join(value_args).strip()
        if not raw_input:
            await ctx.send(f"❌ Debes especificar un ID de modelo, una URL de OpenRouter, o la palabra `default`.")
            return

        channel_context = await context_manager.get_channel_ctx(target_channel.id)

        if raw_input.lower() in ['default', 'reset']:
            if 'model' in channel_context.settings:
                del channel_context.settings['model']
            await ctx.send(f"✅ Modelo para {target_channel.mention} restablecido al por defecto del servidor.")
            return

        model_id = parse_model_id_from_input(raw_input)
        
        # Use the new, consistent progress message style
        msg = await ctx.send(f"🔍 *Verificando compatibilidad para el modelo `{model_id}`...*")

        details = await model_info_manager.get_model_details(model_id)

        if not details:
            await msg.edit(content=f"❌ **Modelo no encontrado.** No pude encontrar un modelo con el ID `{model_id}`.")
            return

        pricing = details.get('pricing', {})
        is_free = float(pricing.get('prompt', 0)) == 0 and float(pricing.get('completion', 0)) == 0
        if not is_free:
            await msg.edit(content=f"❌ **Modelo no gratuito.** El modelo `{model_id}` tiene un costo y no puede ser seleccionado.")
            return
            
        personality_supported = await model_info_manager.test_system_prompt_support(model_id)
        
        channel_context.settings['model'] = model_id
        
        embed = discord.Embed(
            title=f"✅ Modelo del Canal Actualizado",
            description=f"El modelo para el canal {target_channel.mention} ahora es **`{details.get('id')}`**.",
            color=discord.Color.green()
        )
        if description := details.get('description'):
            embed.add_field(name="Descripción", value=description, inline=False)
            
        embed.add_field(name="Contexto Máximo", value=f"`{details.get('context_length', 'N/A')} tokens`", inline=True)

        if personality_supported:
            embed.add_field(name="Soporte de Personalidad", value="✅ Soportado", inline=True)
        else:
            embed.add_field(name="Soporte de Personalidad", value="⚠️ No Soportado", inline=True)
            embed.set_footer(text="Nota: La personalidad será ignorada para este modelo en este canal.")
        
        await msg.edit(content=None, embed=embed)

    @commands.command(name='setpersonality', aliases=['setpersona'])
    @is_admin_check()
    @commands.guild_only()
    async def set_personality_command(self, ctx: commands.Context, *, personality: str):
        """Sets the AI's personality for the current channel."""
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
        """Sets the AI's temperature (0.0 to 1.0) for the current channel."""
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
        """Toggles on/off the bot's ability to reply without being mentioned."""
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
        """Clears the AI's conversation history for this channel."""
        if await request_confirmation(ctx, f"borrar **todo** el historial de la IA para {ctx.channel.mention}"):
            channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
            channel_context.history.clear()
            await ctx.send(f"🧹 Historial de IA para {ctx.channel.mention} limpiado.", delete_after=15)

    @commands.command(name='resetai', aliases=['reset'])
    @is_admin_check()
    @commands.guild_only()
    async def reset_channel_ai_command(self, ctx: commands.Context):
        """Resets all AI settings (model, personality, etc.) for this channel to their defaults."""
        if await request_confirmation(ctx, f"restablecer **toda** la configuración de la IA de {ctx.channel.mention}"):
            channel_context = await context_manager.get_channel_ctx(ctx.channel.id)
            reset_channel_ai_settings(channel_context)
            await ctx.send(f"⚙️ Configuración de IA para {ctx.channel.mention} restablecida.", delete_after=15)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelCommands(bot))