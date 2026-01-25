import os

try:  # Optional in non-bot/test environments
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is only needed when a .env file is used
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER")
ADMIN_ID = os.getenv("ADMIN_ID")
SYSTEM_PROMPT = """You are a helpful assistant. Your responses should be concise and well-formatted
                   for a Telegram chat. Use Markdown for formatting and include emojis often enough
                   to make the conversation more engaging.

                Key formatting guidelines:
                    - *bold* for emphasis
                    - _underline_ for titles or important sections
                    - ~strikethrough~ for corrections or deleted text
                    - `code` for snippets or commands
                    - [link](URL) for hyperlinks

Please ensure your responses are easy to read and visually appealing in a chat interface."""

if TELEGRAM_TOKEN is None:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")

if GEMINI_KEY is None and LLM_PROVIDER == "gemini":
    raise EnvironmentError("GEMINI_API_KEY is not set")

# Debug switches
DEBUG_HISTORY_STATE = (os.getenv("DEBUG_HISTORY_STATE") or "0").lower() in (
    "1",
    "true",
    "yes",
)
DEBUG_TOOL_DIRECTIVES = (os.getenv("DEBUG_TOOL_DIRECTIVES") or "0").lower() in (
    "1",
    "true",
    "yes",
)
DEBUG_OLLAMA = (os.getenv("DEBUG_OLLAMA") or "0").lower() in ("1", "true", "yes")
DEBUG_USER_ACTIONS = (os.getenv("DEBUG_USER_ACTIONS") or "0").lower() in (
    "1",
    "true",
    "yes",
)
