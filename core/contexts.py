import copy
import os
import typing
from dotenv import load_dotenv

from openai import AsyncOpenAI

from .config import DEFAULT_AI_SETTINGS

load_dotenv()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
SITE_URL = os.getenv('OPENROUTER_SITE_URL', '')
APP_NAME = os.getenv('OPENROUTER_APP_NAME', '')

if not OPENROUTER_API_KEY:
    print("Critical Error: OPENROUTER_API_KEY isn't set in the .env file")

class ChannelContext:
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.history: list[dict] = []
        self.settings = copy.deepcopy(DEFAULT_AI_SETTINGS)
        self.stop_requested = False
        self.system_prompt: str = ""
        self._last_personality: str | None = None

    def _build_system_prompt(self):
        current_personality = self.settings.get('personality', '')

        if current_personality == self._last_personality:
            return

        base_instruction = "Responde en el idioma que se te hable. Tu nombre en general es Iris."
        mention_instruction = (
            "Importante: Estás en un chat de Discord. Cada mensaje de usuario en el historial "
            "incluye su nombre y su ID de Discord en el formato: 'Nombre (ID: 12345)'. "
            "Para mencionar a un usuario en tu respuesta, DEBES usar el formato `<@USER_ID>`, "
            "reemplazando USER_ID con el número de su ID del historial. "
            "Ejemplo: Si el historial muestra 'Juan (ID: 111): Hola', tu respuesta para mencionarlo "
            "debe ser 'Hola <@111>!'."
        )

        prompt_parts = [base_instruction]
        if current_personality:
            prompt_parts.append(current_personality)
        prompt_parts.append(mention_instruction)

        self.system_prompt = " ".join(prompt_parts)
        self._last_personality = current_personality

    def get_system_prompt_message(self) -> dict[str, str]:
        self._build_system_prompt()
        return {'role': 'system', 'content': self.system_prompt}

    def create_client(self) -> typing.Optional[AsyncOpenAI]:
        try:
            headers = {"HTTP-Referer": SITE_URL, "X-Title": APP_NAME}
            return AsyncOpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                default_headers={k: v for k, v in headers.items() if v},
            )
        except Exception as e:
            print(f"Error creating the OpenRouter client: {e}")
            return None

class ContextManager:
    def __init__(self):
        self.channel_contexts: typing.Dict[int, ChannelContext] = {}

    async def get_channel_ctx(self, channel_id: int) -> ChannelContext:
        if channel_id not in self.channel_contexts:
            self.channel_contexts[channel_id] = ChannelContext(channel_id)
        return self.channel_contexts[channel_id]

context_manager = ContextManager()