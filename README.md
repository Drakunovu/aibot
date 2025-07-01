# Iris - AI Discord Bot

Iris is a powerful and highly configurable Discord bot that connects to the [OpenRouter.ai](https://openrouter.ai/) API. It allows server administrators to bring a wide variety of free, high-quality language models into their communities, with fine-grained control over their behavior on a per-channel basis.

## ✨ Features

- **Dynamic Model Selection**: Choose from any free model available on OpenRouter.
- **Granular Configuration**:
    - **Server-wide defaults**: Set a default model, command prefix, and admin role for the entire server.
    - **Per-channel overrides**: Customize the AI's model, personality, and creativity (`temperature`) for each specific channel.
- **Natural Conversation Mode**: Toggle a mode that allows the bot to reply to messages without needing a direct @mention.
- **Usage Tracking Status**: The bot's custom status automatically updates to show the total tokens used in the last 7 days, tracked locally and reliably.
- **Built-in Help & Configuration Display**: Easy-to-use commands (`!help`, `!showconfig`) to view settings and available commands.
- **Permission System**: Clear distinction between server owner, admin, and regular user permissions.
- **Extensible Cog Architecture**: The bot is built using `discord.py` cogs, making it easy to add new commands and features.

## 🚀 Setup & Installation

Follow these steps to get your own instance of Iris running.

### 1. Prerequisites

- Python 3.9 or newer
- A Discord Bot Token
- An OpenRouter API Key

### 2. Clone the Repository

Clone this repository to your local machine or server.

```bash
git clone https://github.com/Drakunovu/aibot.git
cd aibot
```

### 3. Install Dependencies

Install all the required Python libraries using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Create the Environment File

Create a file named `.env` in the main project directory. This file will store your secret keys. Add the following lines to it, replacing the placeholder text with your actual keys:

```env
# Your Discord bot's token
DISCORD_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"

# Your API key from OpenRouter.ai
OPENROUTER_API_KEY="sk-or-v1-..."
```

### 5. Run the Bot

Once the setup is complete, you can start the bot with the following command:

```bash
python main.py
```

The bot should come online in your Discord server, a `bot_usage.db` file will be created to store token logs and a `config.json` file will be also created to store configurations from each server and their channels.

## 🤖 Command List

The default command prefix is `!`.

### General Commands

| Command | Description |
| :--- | :--- |
| `!help` | Displays the main help message with all commands. |
| `!showconfig` | Shows the current configuration for the server and the channel. |
| `!models [search] [sort]` | Lists all available free models. Sort by `newest` or `context`. |

### Channel Admin Commands

*(Requires Admin Role or server "Administrator" permission)*
| Command | Description |
| :--- | :--- |
| `!setmodel <model_id / default>` | Sets or resets the AI model for the current channel. |
| `!setpersonality <text>` | Sets a custom personality/system prompt for the AI in this channel. |
| `!settemperature <0.0-1.0>` | Sets the AI's creativity (0.0 = deterministic, 1.0 = very creative). |
| `!togglenatural` | Toggles whether the bot replies without being @mentioned. |
| `!clearhistory` | Clears the AI's conversation memory for the channel. |
| `!resetai` | Resets all AI settings for the channel back to server defaults. |

### Server Admin Commands

*(Requires Admin Role or server "Administrator" permission)*
| Command | Description |
| :--- | :--- |
| `!setservermodel <model_id>` | Sets the default AI model for the entire server. |
| `!setprefix <new_prefix>` | Changes the command prefix for the bot on this server. |
| `!setmaxoutput <tokens>` | Sets the maximum number of tokens the AI can generate in a response. |
| `!addchannel <#channel>` | Adds a channel to the list of allowed channels for non-admins. |
| `!removechannel <#channel>` | Removes a channel from the allowed list. |
| `!listchannels` | Lists all channels where non-admins can use the bot. |

### Server Owner Commands

*(Requires being the owner of the Discord server)*
| Command | Description |
| :--- | :--- |
| `!setadminrole <@Role>` | Designates a server role as the bot's "Admin Role". |

## 📂 Project Structure

  - **`main.py`**: The main entry point for the bot. Handles startup, event listening, and loading cogs.
  - **`core/`**: Contains the core logic of the bot.
      - `ai_handler.py`: Manages the entire process of generating an AI response.
      - `config.py`: Defines default settings and manages the `config.json` file.
      - `contexts.py`: Manages the conversation history and settings for each channel.
      - `database_manager.py`: Handles all interactions with the `bot_usage.db` SQLite database for token logging.
      - `openrouter_models.py`: Fetches and caches model information from the OpenRouter API.
  - **`cogs/`**: Contains command files, separated by category (admin, channel, general).
  - **`config.json`**: Stores server-specific settings (auto-generated).
  - **`bot_usage.db`**: SQLite database that logs token usage for the status display (auto-generated).
  - **`.env`**: Stores your secret API keys (you must create this).

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/Drakunovu/aibot/issues).