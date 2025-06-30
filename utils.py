import asyncio
import typing
import copy

import discord
from discord.ext import commands

from core.config import config_manager, DEFAULT_GUILD_CONFIG, DEFAULT_AI_SETTINGS, DEFAULT_MAX_OUTPUT_TOKENS
from core.contexts import ChannelContext
from core.openrouter_models import model_info_manager

MIN_ALLOWED_OUTPUT_TOKENS = 64
MAX_ALLOWED_OUTPUT_TOKENS = 8192

def parse_model_id_from_input(input_str: str) -> str:
    base_url_models = "https://openrouter.ai/models/"
    input_str = input_str.strip().strip('<>')
    
    if input_str.startswith(base_url_models):
        return input_str[len(base_url_models):]
    
    return input_str

async def set_and_verify_model(ctx: commands.Context, model_id: str) -> tuple[bool, typing.Union[discord.Embed, str]]:
    msg = await ctx.send(f"🔍 *Verificando compatibilidad para el modelo `{model_id}`...*")
    
    details = await model_info_manager.get_model_details(model_id)

    if not details:
        await msg.edit(content=f"❌ **Modelo no encontrado.** No pude encontrar un modelo con el ID `{model_id}`.")
        return False, msg

    pricing = details.get('pricing', {})
    is_free = float(pricing.get('prompt', 1)) == 0 and float(pricing.get('completion', 1)) == 0
    if not is_free:
        await msg.edit(content=f"❌ **Modelo no gratuito.** El modelo `{model_id}` tiene un costo y no puede ser seleccionado.")
        return False, msg
        
    personality_supported = await model_info_manager.test_system_prompt_support(model_id)

    embed = discord.Embed(title="✅ Modelo Actualizado", color=discord.Color.green())
    if description := details.get('description'):
        embed.add_field(name="Descripción", value=description, inline=False)
    
    embed.add_field(name="Contexto Máximo", value=f"`{details.get('context_length', 'N/A')} tokens`", inline=True)
    
    if personality_supported:
        embed.add_field(name="Soporte de Personalidad", value="✅ Soportado", inline=True)
    else:
        embed.add_field(name="Soporte de Personalidad", value="⚠️ No Soportado", inline=True)
        embed.set_footer(text="Nota: La personalidad será ignorada para este modelo.")
    
    return True, (msg, embed)

def is_admin(member: typing.Union[discord.Member, discord.User]) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild.owner_id == member.id:
        return True
    if member.guild_permissions.administrator:
        return True
    
    guild_cfg = config_manager.get_guild_config(member.guild.id)
    admin_role_id = guild_cfg.get('admin_role_id')
    if admin_role_id:
        return any(role.id == admin_role_id for role in member.roles)
    return False

def is_admin_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if not is_admin(ctx.author):
            raise commands.CheckFailure("No tienes permiso de administrador para usar este comando.")
        return True
    return commands.check(predicate)

def is_owner_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("Este comando solo funciona en servidores.")
        if ctx.guild.owner_id != ctx.author.id:
            raise commands.CheckFailure("Solo el dueño del servidor puede usar este comando.")
        return True
    return commands.check(predicate)

async def get_prefix(bot: commands.Bot, message: discord.Message) -> str:
    if not message.guild:
        return DEFAULT_GUILD_CONFIG['command_prefix']
    guild_cfg = config_manager.get_guild_config(message.guild.id)
    return guild_cfg.get('command_prefix', DEFAULT_GUILD_CONFIG['command_prefix'])

def is_channel_allowed(guild_id: int, channel_id: int) -> bool:
    guild_cfg = config_manager.get_guild_config(guild_id)
    allowed_ids = guild_cfg.get('allowed_channel_ids', [])
    return not allowed_ids or channel_id in allowed_ids

async def request_confirmation(ctx: commands.Context, action_description: str) -> bool:
    confirm_msg = await ctx.send(
        f"**Confirmación Requerida**: ¿Seguro que deseas **{action_description}**?\n"
        "Reacciona con ✅ para confirmar o ❌ para cancelar (tienes 30 segundos)."
    )
    await confirm_msg.add_reaction('✅')
    await confirm_msg.add_reaction('❌')

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ['✅', '❌']

    try:
        reaction, _ = await ctx.bot.wait_for('reaction_add', timeout=30.0, check=check)
        confirmed = str(reaction.emoji) == '✅'
    except asyncio.TimeoutError:
        confirmed = False
        await ctx.send("⏰ Tiempo agotado. Acción cancelada.", delete_after=10)
    finally:
        await confirm_msg.delete()
    
    if not confirmed:
        await ctx.send("❌ Acción cancelada.", delete_after=10)
        
    return confirmed

def reset_channel_settings(channel_context: ChannelContext):
    channel_context.settings = copy.deepcopy(DEFAULT_AI_SETTINGS)
    if 'model' in channel_context.settings:
        del channel_context.settings['model']
    channel_context.stop_requested = False
    print(f"Configuración de IA del canal {channel_context.channel_id} restablecida.")

async def perform_set_max_output_tokens(ctx: commands.Context, max_tokens: int) -> bool:
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
        return True
    except Exception as e:
        print(f"Error en perform_set_max_output_tokens para guild {ctx.guild.id}: {e}")
        await ctx.send("⚠️ Ocurrió un error inesperado al guardar la configuración.", delete_after=10)
        return False