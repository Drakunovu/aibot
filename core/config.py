import json
import copy
import os
from dotenv import load_dotenv

load_dotenv()

# --- Main Config File ---
CONFIG_FILE = 'config.json'

# --- Bot Defaults ---
DEFAULT_COMMAND_PREFIX = '!'
DEFAULT_ADMIN_ROLE_ID = None
DEFAULT_ALLOWED_CHANNEL_IDS = []
DEFAULT_BOT_ENABLED_FOR_USERS = True
DEFAULT_MAX_OUTPUT_TOKENS = 4096
# The model from .env now acts as a global fallback default.
DEFAULT_MODEL = os.getenv('MODEL_NAME', 'deepseek/deepseek-r1-0528:free')

# --- Guild (Server) Configuration ---
# This dictionary represents the default structure for a new server's configuration.
DEFAULT_GUILD_CONFIG = {
    'command_prefix': DEFAULT_COMMAND_PREFIX,
    'admin_role_id': DEFAULT_ADMIN_ROLE_ID,
    'allowed_channel_ids': DEFAULT_ALLOWED_CHANNEL_IDS,
    'bot_enabled_for_users': DEFAULT_BOT_ENABLED_FOR_USERS,
    'max_output_tokens': DEFAULT_MAX_OUTPUT_TOKENS,
    'model': DEFAULT_MODEL,
}

# --- AI Behavior Defaults ---
# These settings control the AI's behavior in a channel.
DEFAULT_AI_SETTINGS = {
    'personality': 'Tono: neutral. Estilo: formal.',
    'temperature': 0.5,
    'natural_conversation': False
}

# --- File Handling ---
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
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
    """Handles loading and saving of the bot's configuration file (config.json)."""
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.bot_config = {}
        self.load_config()

    def load_config(self):
        """Loads the config from config.json, creating it if it doesn't exist."""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.bot_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Advertencia: {self.config_file} no encontrado o corrupto. Se creará uno nuevo.")
            self.bot_config = {}
            self.save_config()

    def save_config(self):
        """Saves the current configuration to config.json."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.bot_config, f, indent=4)
        except Exception as e:
            print(f"Error crítico guardando configuración en {self.config_file}: {e}")

    def get_guild_config(self, guild_id: int) -> dict:
        """
        Retrieves the configuration for a specific guild, creating it if it doesn't exist.
        Also validates and adds any missing default keys.
        """
        guild_id_str = str(guild_id)
        guild_cfg = self.bot_config.get(guild_id_str)

        if not guild_cfg or not isinstance(guild_cfg, dict):
            self.bot_config[guild_id_str] = copy.deepcopy(DEFAULT_GUILD_CONFIG)
            self.save_config()
            return self.bot_config[guild_id_str]

        # Ensure all default keys are present in an existing config
        config_updated = False
        for key, default_value in DEFAULT_GUILD_CONFIG.items():
            if key not in guild_cfg:
                guild_cfg[key] = copy.deepcopy(default_value)
                config_updated = True

        if config_updated:
            self.save_config()

        return guild_cfg

# --- Global Singleton Instances ---
config_manager = ConfigManager()