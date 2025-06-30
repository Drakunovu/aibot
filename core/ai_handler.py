import typing

import discord
from discord.ext import commands
from openai import OpenAIError
from openai.types.chat import ChatCompletion

from . import database_manager
from .config import MAX_ATTACHMENT_SIZE_BYTES, config_manager
from .contexts import context_manager
from .openrouter_models import model_info_manager

class AIResponseHandler:
    def __init__(self, bot: commands.Bot, message: discord.Message, content: str):
        self.message = message
        self.content = content
        self.bot = bot 
        self.channel_context = None
        self.guild_cfg = None

    async def _prepare_llm_input(self) -> typing.Optional[list]:
        parts = []
        author_name = self.message.author.display_name
        author_id = self.message.author.id

        if self.content:
            text_for_llm = f"{author_name} (ID: {author_id}): {self.content}"
            parts.append({'type': 'text', 'text': text_for_llm})

        for attachment in self.message.attachments:
            if attachment.size > MAX_ATTACHMENT_SIZE_BYTES:
                await self.message.channel.send(f"⚠️ Archivo '{attachment.filename}' demasiado grande.", delete_after=15)
                continue
            try:
                file_bytes = await attachment.read()
                file_content = file_bytes.decode('utf-8', errors='replace')
                file_context = f"\n--- Contenido de {attachment.filename} ---\n{file_content}\n--- Fin de {attachment.filename} ---"
                parts.append({'type': 'text', 'text': file_context})
            except Exception as e:
                await self.message.channel.send(f"⚠️ Error al leer el adjunto '{attachment.filename}'.", delete_after=15)
                print(f"Error processing attachment: {e}")

        return parts if parts else None

    def _update_and_trim_history(self, user_message_content: list):
        MAX_HISTORY_MESSAGES = 10
        self.channel_context.history.append({'role': 'user', 'content': user_message_content})
        if len(self.channel_context.history) > MAX_HISTORY_MESSAGES * 2:
            self.channel_context.history = self.channel_context.history[-(MAX_HISTORY_MESSAGES * 2):]

    async def _call_openrouter_api(self) -> typing.Optional[ChatCompletion]:
        client = self.channel_context.create_client() 
        if not client:
            print("Critical error: The OpenRouter client is not initialized.")
            await self.message.channel.send("⚠️ El bot no está configurado para conectarse al servicio de IA.")
            return None

        model_name = self.channel_context.settings.get('model') or self.guild_cfg.get('model')
        
        messages_for_api = []
        if await model_info_manager.test_system_prompt_support(model_name):
            messages_for_api.append(self.channel_context.get_system_prompt_message())
            
        messages_for_api.extend(self.channel_context.history)

        try:
            return await client.chat.completions.create(
                model=model_name,
                messages=messages_for_api,
                temperature=self.channel_context.settings.get('temperature'),
                max_tokens=self.guild_cfg.get('max_output_tokens')
            )
        except OpenAIError as e:
            error_msg = f"⚠️ Error de API con el modelo `{model_name}`: {e.body.get('message', 'Error desconocido') if e.body else str(e)}"
            await self.bot.get_channel(self.channel_context.channel_id).send(error_msg, delete_after=20)
            print(f"Error from OpenRouter: {e}")
            return None
        except Exception as e:
            await self.bot.get_channel(self.channel_context.channel_id).send("⚠️ Ocurrió un error inesperado al contactar la API.")
            print(f"Unexpected Error in API call: {e}")
            return None

    def _extract_response_text(self, api_response: ChatCompletion) -> typing.Optional[str]:
        try:
            return api_response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            return None

    def _update_history_with_model_response(self, response_text: str):
        self.channel_context.history.append({'role': 'model', 'content': response_text})

    def _get_token_info(self, api_response: ChatCompletion) -> str:
        try:
            usage = api_response.usage
            if usage and usage.total_tokens > 0:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                total_tokens = usage.total_tokens
                return f"\n*Prompt Tokens: `{prompt_tokens}` | Completion Tokens: `{completion_tokens}` | Total Tokens: `{total_tokens}`*"
        except (AttributeError, TypeError):
            pass
        return ""

    async def _send_discord_response(self, response_text: str, token_info: str):
        MAX_MSG_LEN = 2000
        cleaned_response_text = response_text.rstrip()

        for i in range(0, len(cleaned_response_text), MAX_MSG_LEN):
            part = cleaned_response_text[i:i + MAX_MSG_LEN]

            if i + MAX_MSG_LEN >= len(cleaned_response_text):
                await self.message.channel.send(part + token_info)
            else:
                await self.message.channel.send(part)

    async def process_request(self):
        self.channel_context = await context_manager.get_channel_ctx(self.message.channel.id)
        self.guild_cfg = config_manager.get_guild_config(self.message.guild.id)
        
        async with self.message.channel.typing():
            llm_content = await self._prepare_llm_input()
            if not llm_content: return

            self._update_and_trim_history(llm_content)

            api_response = await self._call_openrouter_api()
            if not api_response:
                self.channel_context.history.pop()
                return

            response_text = self._extract_response_text(api_response)
            if response_text is None: return

            self._update_history_with_model_response(response_text)
            token_info = self._get_token_info(api_response)

            if api_response.usage:
                database_manager.log_token_usage(api_response.usage.total_tokens)

            await self._send_discord_response(response_text, token_info)