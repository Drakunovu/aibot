import json
import copy
import os

CONFIG_FILE = 'config.json'

DEFAULT_GUILD_CONFIG = {
    'command_prefix': '!',
    'admin_role_id': None,
    'allowed_channel_ids': [],
    'bot_enabled_for_users': True,
}

DEFAULT_AI_SETTINGS = {'personality': 'Tono: neutral. Estilo: formal.', 'temperature': 0.5}
DEFAULT_AI_IS_ACTIVE = False

MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024

LANGUAGE_EXTENSIONS = {
    "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts", "java": ".java", "csharp": ".cs",
    "cs": ".cs", "cpp": ".cpp", "c++": ".cpp", "c": ".c", "html": ".html",
    "css": ".css", "json": ".json", "yaml": ".yaml", "yml": ".yaml",
    "markdown": ".md", "md": ".md", "bash": ".sh", "sh": ".sh",
    "sql": ".sql", "ruby": ".rb", "php": ".php", "go": ".go", "rust": ".rs",
}
DEFAULT_FILE_EXTENSION = ".txt"

class ConfigManager:
    def __init__(self):
        self.bot_config = {}
        self.load_config()

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.bot_config = {str(k): v for k, v in loaded_data.items()}
                print(f"Configuración cargada desde {CONFIG_FILE} para {len(self.bot_config)} servidor(es).")
        except FileNotFoundError:
            print(f"Advertencia: {CONFIG_FILE} no encontrado. Iniciando con configuración vacía.")
            self.bot_config = {}
        except json.JSONDecodeError as e:
            print(f"Error: No se pudo decodificar {CONFIG_FILE}: {e}. Iniciando con configuración vacía.")
            self.bot_config = {}
        except Exception as e:
            print(f"Error inesperado cargando configuración: {type(e).__name__} - {e}")
            self.bot_config = {}


    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.bot_config, f, indent=4)
        except Exception as e:
            print(f"Error guardando configuración en {CONFIG_FILE}: {e}")

    def get_guild_config(self, guild_id: int) -> dict:
        guild_id_str = str(guild_id)

        if guild_id_str not in self.bot_config or not isinstance(self.bot_config.get(guild_id_str), dict):
            if guild_id_str not in self.bot_config:
                print(f"Creando configuración por defecto para servidor {guild_id_str}")
            else:
                print(f"Advertencia: Configuración inválida encontrada para {guild_id_str}. Reemplazando con defaults.")
            self.bot_config[guild_id_str] = copy.deepcopy(DEFAULT_GUILD_CONFIG)

        guild_cfg = self.bot_config[guild_id_str]

        config_updated = False
        for key, default_value in DEFAULT_GUILD_CONFIG.items():
            if key not in guild_cfg:
                guild_cfg[key] = copy.deepcopy(default_value)
                config_updated = True

        if not isinstance(guild_cfg.get('command_prefix'), str) or not guild_cfg.get('command_prefix'):
            guild_cfg['command_prefix'] = DEFAULT_GUILD_CONFIG['command_prefix']
            config_updated = True

        if not isinstance(guild_cfg.get('admin_role_id'), (int, type(None))):
            if isinstance(guild_cfg.get('admin_role_id'), str) and guild_cfg.get('admin_role_id').isdigit():
                 guild_cfg['admin_role_id'] = int(guild_cfg.get('admin_role_id'))
            else:
                 guild_cfg['admin_role_id'] = DEFAULT_GUILD_CONFIG['admin_role_id']
            config_updated = True


        if not isinstance(guild_cfg.get('allowed_channel_ids'), list):
            guild_cfg['allowed_channel_ids'] = []
            config_updated = True
        else:
            original_ids = guild_cfg.get('allowed_channel_ids', [])
            valid_ids = []
            list_changed = False
            for ch_id in original_ids:
                if isinstance(ch_id, str) and ch_id.isdigit():
                    valid_ids.append(int(ch_id))
                    list_changed = True
                elif isinstance(ch_id, int):
                    valid_ids.append(ch_id)
                else:
                    list_changed = True
            if list_changed:
                guild_cfg['allowed_channel_ids'] = valid_ids
                config_updated = True

        if not isinstance(guild_cfg.get('bot_enabled_for_users'), bool):
            guild_cfg['bot_enabled_for_users'] = DEFAULT_GUILD_CONFIG['bot_enabled_for_users']
            config_updated = True

        if config_updated:
            print(f"Configuración para servidor {guild_id_str} actualizada/validada.")
            self.save_config()

        return guild_cfg

config_manager = ConfigManager()

__all__ = [
    "config_manager",
    "DEFAULT_GUILD_CONFIG",
    "DEFAULT_AI_SETTINGS",
    "DEFAULT_AI_IS_ACTIVE",
    "MAX_ATTACHMENT_SIZE_BYTES",
    "LANGUAGE_EXTENSIONS",
    "DEFAULT_FILE_EXTENSION"
]
