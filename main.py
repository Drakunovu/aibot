import asyncio
import os
import typing

import discord
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv

from core import database_manager
from core.ai_handler import AIResponseHandler
from core.config import config_manager
from core.contexts import context_manager
from utils import get_prefix, is_admin, is_channel_allowed

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    print("Critical Error: DISCORD_TOKEN isn't set in the .env file")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    update_presence.start()
    cleanup_database_task.start()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    should_process, content = await _should_process_ai(message)
    if not should_process:
        return

    try:
        handler = AIResponseHandler(bot, message, content)
        await handler.process_request()
    except Exception as e:
        print(f"Fatal error on on_message dispatch to message: {message.id}: {type(e).__name__} - {e}")
        await message.channel.send("⚠️ Ocurrió un error inesperado al procesar tu mensaje.")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.author.send("Este comando solo se puede usar dentro de un servidor.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"🚫 {error}", delete_after=15)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❓ Faltan argumentos. Uso: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Argumento inválido: {error}")
    else:
        print(f'Error not managed in command {ctx.command.qualified_name}: {type(error).__name__} - {error}')
        await ctx.send("⚠️ Ocurrió un error desconocido al ejecutar el comando.")

@tasks.loop(minutes=1)
async def update_presence():
    try:
        tokens = database_manager.get_tokens_from_last_7_days()
        
        custom_state = f"Tokens usados (7d): {tokens:,}"
        activity = discord.Activity(
            type=discord.ActivityType.custom,
            name="Token Usage",
            state=custom_state
        )
        await bot.change_presence(activity=activity)
    except Exception as e:
        print(f"Failed to change the state: {e}")

@tasks.loop(hours=24)
async def cleanup_database_task():
    database_manager.cleanup_old_logs()

async def _should_process_ai(message: discord.Message) -> typing.Tuple[bool, typing.Optional[str]]:
    guild_cfg = config_manager.get_guild_config(message.guild.id)
    is_caller_admin = is_admin(message.author)

    if not is_caller_admin and not guild_cfg.get('bot_enabled_for_users'):
        return False, None

    if not is_caller_admin and not is_channel_allowed(message.guild.id, message.channel.id):
        return False, None

    channel_context = await context_manager.get_channel_ctx(message.channel.id)
    is_mention = bot.user.mentioned_in(message)

    stripped_content = message.content
    for mention in [f'<@!{bot.user.id}>', f'<@{bot.user.id}>']:
        stripped_content = stripped_content.replace(mention, '').strip()

    if is_mention and (stripped_content or message.attachments):
        return True, stripped_content
    if channel_context.settings.get('natural_conversation') and (stripped_content or message.attachments):
        return True, stripped_content

    return False, None

async def main():
    database_manager.initialize_database()
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f'Cog loaded: {filename[:-3]}')
                except Exception as e:
                    print(f'Error loading cog {filename[:-3]}: {e}')
        
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped manually.")