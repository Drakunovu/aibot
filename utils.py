import asyncio
import typing

import discord
from discord.ext import commands

from core.config import config_manager, DEFAULT_GUILD_CONFIG, DEFAULT_AI_SETTINGS, DEFAULT_AI_IS_ACTIVE, DEFAULT_MAX_OUTPUT_TOKENS
from core.contexts import ChannelContext, context_manager

MIN_ALLOWED_OUTPUT_TOKENS = 64
MAX_ALLOWED_OUTPUT_TOKENS = 8192

async def get_prefix(bot: commands.Bot, message: discord.Message) -> str:
    if not message.guild:
        return DEFAULT_GUILD_CONFIG['command_prefix']
    guild_cfg = config_manager.get_guild_config(message.guild.id)
    return guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])

def is_admin(member: typing.Union[discord.Member, discord.User]) -> bool:
    if not isinstance(member, discord.Member): return False
    if member.guild_permissions.administrator: return True
    if member.guild.owner_id == member.id: return True
    guild_cfg = config_manager.get_guild_config(member.guild.id)
    admin_role_id = guild_cfg.get('admin_role_id')
    if admin_role_id:
        admin_role = member.guild.get_role(admin_role_id)
        if admin_role and admin_role in member.roles:
            return True
    return False

def is_admin_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if not is_admin(ctx.author):
            raise commands.CheckFailure("No tienes permiso de administrador.")
        return True
    return commands.check(predicate)

def is_owner_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if ctx.guild.owner_id != ctx.author.id:
            raise commands.CheckFailure("Solo el dueño del servidor puede usar esto.")
        return True
    return commands.check(predicate)

def is_channel_allowed(guild_id: int, channel_id: int) -> bool:
    guild_cfg = config_manager.get_guild_config(guild_id)
    allowed_ids = guild_cfg.get('allowed_channel_ids', [])
    return not allowed_ids or channel_id in allowed_ids

def reset_channel_ai_settings(channel_context: ChannelContext):
    channel_context.settings = DEFAULT_AI_SETTINGS.copy()
    channel_context.settings['natural_conversation'] = DEFAULT_AI_SETTINGS.get('natural_conversation', False)
    channel_context.is_active = DEFAULT_AI_IS_ACTIVE # Keep for compatibility if used elsewhere, but settings is primary
    channel_context.stop_requested = False
    print(f"Configuraciones de IA del canal restablecidas para objeto {id(channel_context)} (historial no borrado).")

async def request_confirmation(ctx: commands.Context, action_description: str) -> bool:
    confirm_embed = discord.Embed(
        title="Confirmación Requerida",
        description=f"¿Seguro que deseas **{action_description}**?",
        color=discord.Color.orange()
    )
    confirm_embed.set_footer(text="✅ Confirmar / ❌ Cancelar (30s)")

    confirm_msg = None
    try:
        confirm_msg = await ctx.send(embed=confirm_embed)
        await confirm_msg.add_reaction('✅')
        await confirm_msg.add_reaction('❌')
    except discord.Forbidden:
        print(f"Error: Faltan permisos para enviar/reaccionar confirmación en {ctx.channel.id}")
        await ctx.send("⚠️ No tengo permisos para enviar o reaccionar al mensaje de confirmación.", delete_after=10)
        return False
    except Exception as e:
        print(f"Error enviando mensaje de confirmación: {e}")
        await ctx.send("⚠️ Ocurrió un error al pedir confirmación.", delete_after=10)
        return False

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ['✅', '❌']

    confirmed = False
    try:
        reaction, _ = await ctx.bot.wait_for('reaction_add', timeout=30.0, check=check)
        confirmed = str(reaction.emoji) == '✅'
        if not confirmed:
            await ctx.send("❌ Acción cancelada.", delete_after=10)
    except asyncio.TimeoutError:
        confirmed = False
        await ctx.send("⏰ Tiempo agotado. Acción cancelada.", delete_after=10)
    except Exception as e:
         print(f"Error durante espera de confirmación: {e}")
         confirmed = False
         await ctx.send("⚠️ Error durante la confirmación. Acción cancelada.", delete_after=10)
    finally:
        if confirm_msg:
            try:
                await confirm_msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
    return confirmed

async def perform_toggle_natural(ctx: commands.Context, target_channel: discord.TextChannel) -> bool:
    try:
        channel_context = await context_manager.get_channel_ctx(target_channel.id)
        current_state = channel_context.settings.get('natural_conversation', False)
        new_state = not current_state
        channel_context.settings['natural_conversation'] = new_state
        new_state_text = "Activada" if new_state else "Desactivada"
        await ctx.send(f"✅ Conversación natural: **{new_state_text}** en {target_channel.mention}.", delete_after=15)
        return True
    except Exception as e:
        print(f"Error en perform_toggle_natural para canal {target_channel.id}: {e}")
        try:
            await ctx.send("⚠️ Ocurrió un error al cambiar el estado de conversación natural.", delete_after=10)
        except discord.Forbidden:
            pass
        return False

async def perform_reset_channel_ai(ctx: commands.Context, target_channel: discord.TextChannel) -> bool:
    try:
        action_desc = f"restablecer **toda** la configuración de la IA (personalidad, temp, estado) de {target_channel.mention} a los valores por defecto"
        if await request_confirmation(ctx, action_desc):
            channel_context = await context_manager.get_channel_ctx(target_channel.id)
            reset_channel_ai_settings(channel_context)
            await ctx.send(f"⚙️ Configuración de IA para {target_channel.mention} restablecida a los valores por defecto.", delete_after=15)
            return True
        else:
            return False
    except Exception as e:
        print(f"Error en perform_reset_channel_ai para canal {target_channel.id}: {e}")
        try:
            await ctx.send("⚠️ Ocurrió un error al restablecer la configuración del canal.", delete_after=10)
        except discord.Forbidden:
            pass
        return False

async def perform_clear_history(ctx: commands.Context, target_channel: discord.TextChannel) -> bool:
    try:
        action_desc = f"borrar **todo** el historial de conversación de la IA para {target_channel.mention}"
        if await request_confirmation(ctx, action_desc):
            channel_context = await context_manager.get_channel_ctx(target_channel.id)
            channel_context.history.clear()
            await ctx.send(f"🧹 Historial de IA para {target_channel.mention} limpiado.", delete_after=15)
            return True
        else:
            return False
    except Exception as e:
        print(f"Error en perform_clear_history para canal {target_channel.id}: {e}")
        try:
            await ctx.send("⚠️ Ocurrió un error al limpiar el historial del canal.", delete_after=10)
        except discord.Forbidden:
            pass
        return False

async def perform_set_max_output_tokens(ctx: commands.Context, max_tokens: int) -> bool:
    if not ctx.guild:
        await ctx.send("Este comando/acción solo funciona en servidores.", delete_after=10)
        return False

    if not (MIN_ALLOWED_OUTPUT_TOKENS <= max_tokens <= MAX_ALLOWED_OUTPUT_TOKENS):
        await ctx.send(
            f"❌ El número de tokens debe estar entre **{MIN_ALLOWED_OUTPUT_TOKENS}** y **{MAX_ALLOWED_OUTPUT_TOKENS}**. "
            f"El valor por defecto es `{DEFAULT_MAX_OUTPUT_TOKENS}`.", delete_after=20
        )
        return False

    try:
        guild_cfg = config_manager.get_guild_config(ctx.guild.id)
        guild_cfg['max_output_tokens'] = max_tokens
        config_manager.save_config()
        await ctx.send(f"✅ Límite máximo de tokens de salida establecido en **{max_tokens}** para este servidor.", delete_after=15)
        print(f"User {ctx.author} ({ctx.author.id}) set max_output_tokens to {max_tokens} for guild {ctx.guild.id} via {'command' if ctx.command else 'menu'}")
        return True
    except Exception as e:
        print(f"Error en perform_set_max_output_tokens para guild {ctx.guild.id}: {e}")
        await ctx.send("⚠️ Ocurrió un error inesperado al guardar la configuración.", delete_after=10)
        return False
