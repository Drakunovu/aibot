import os
import typing
from dotenv import load_dotenv

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from core.config import DEFAULT_AI_SETTINGS, DEFAULT_AI_IS_ACTIVE

load_dotenv()
MODEL_NAME = os.getenv('MODEL_NAME')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not MODEL_NAME: print("Error: MODEL_NAME no configurado en .env"); exit()
if not GEMINI_API_KEY: print("Error: GEMINI_API_KEY no configurado en .env"); exit()

MODEL_NAME_USED = f'models/{MODEL_NAME}'
MODEL_INPUT_TOKEN_LIMIT = None

try:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except ValueError as ve:
        if "already configured" not in str(ve).lower():
             print(f"Advertencia: Error configurando genai en contexts.py: {ve}")
    except Exception as config_err:
         print(f"Advertencia: Error inesperado configurando genai en contexts.py: {config_err}")

    print(f"Obteniendo información para el modelo: {MODEL_NAME_USED}...")
    model_info = genai.get_model(MODEL_NAME_USED)
    if hasattr(model_info, 'input_token_limit'):
        MODEL_INPUT_TOKEN_LIMIT = model_info.input_token_limit
        print(f"Límite de tokens de entrada detectado: {MODEL_INPUT_TOKEN_LIMIT}")
    else:
        print(f"Advertencia: Atributo 'input_token_limit' no encontrado para el modelo {MODEL_NAME_USED}.")
except Exception as model_info_error:
    print(f"Error crítico: Fallo al obtener información del modelo {MODEL_NAME_USED}: {model_info_error}")
    print("El límite máximo de tokens no estará disponible.")

class ChannelContext:
    def __init__(self):
        self.history = []
        self.settings = DEFAULT_AI_SETTINGS.copy()
        self.is_active = DEFAULT_AI_IS_ACTIVE
        self.stop_requested = False

    def create_model(self) -> typing.Optional[genai.GenerativeModel]:
        safety_settings=[
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE}
        ]

        try:
            personality_instruction = self.settings.get('personality', '').strip()
            base_instruction = "Responde en español (latinoamericano venezolano)."
            mention_instruction = (
                "Importante: Estás en un chat de Discord con múltiples usuarios. "
                "Cada mensaje de un usuario en el historial que te proporciono vendrá prefijado con su nombre y su ID único de Discord, en el formato: 'NombreUsuario (ID: 123456789012345678): contenido del mensaje'. "
                "Es crucial que prestes atención a quién (qué ID) dijo cada cosa en el historial para mantener el contexto correcto de la conversación. "
                "Cuando necesites referirte a un usuario específico en tu respuesta, DEBES usar el formato de mención de Discord: `<@USER_ID>`, reemplazando USER_ID con el ID numérico correspondiente que viste en el prefijo de su mensaje en el historial. "
                "Ejemplo de Interacción Correcta: "
                "Historial:"
                "UsuarioA (ID: 111): @Bot saluda a @UsuarioB"
                "Tu Respuesta Correcta: '¡Claro <@111>! Hola @UsuarioB, te envío saludos de parte de <@111>.' (Nota cómo mencionas a UsuarioA usando su ID 111)."
                "Otro Ejemplo:"
                "Historial:"
                "UsuarioX (ID: 888): ¿Qué opinas de la idea de UsuarioY?"
                "UsuarioY (ID: 999): Creo que es buena idea."
                "UsuarioX (ID: 888): @Bot, ¿qué dijo UsuarioY?"
                "Tu Respuesta Correcta: '<@888>, <@999> dijo que cree que es buena idea.'"
                "NUNCA te refieras al usuario que te pide algo usando tu propio nombre ('Bot'). SIEMPRE usa su mención `<@USER_ID>` obtenida del historial."
            )

            system_instruction_parts = [base_instruction]
            if personality_instruction:
                system_instruction_parts.append(personality_instruction)
            system_instruction_parts.append(mention_instruction)

            system_instruction = " ".join(system_instruction_parts)

            return genai.GenerativeModel(
                MODEL_NAME_USED,
                system_instruction=system_instruction,
                generation_config={'temperature': self.settings['temperature'], 'max_output_tokens': 4096},
                safety_settings=safety_settings
            )
        except Exception as e:
            print(f"Error creando modelo Gemini: {e}")
            return None

class ContextManager:
    def __init__(self):
        self.channel_contexts: typing.Dict[int, ChannelContext] = {}

    async def get_channel_ctx(self, channel_id: int) -> ChannelContext:
        return self.channel_contexts.setdefault(channel_id, ChannelContext())

context_manager = ContextManager()

__all__ = ["context_manager", "ChannelContext", "MODEL_INPUT_TOKEN_LIMIT", "MODEL_NAME_USED"]
