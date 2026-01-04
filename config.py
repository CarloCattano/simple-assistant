import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER")
ADMIN_ID = os.getenv("ADMIN_ID")
SYSTEM_PROMPT = """You are a helpful assistant. Your responses should be concise and well-formatted for a Telegram chat. Use MarkdownV2 for formatting and include emojis often enough to make the conversation more engaging.

Key formatting guidelines:
- *bold* for emphasis
- _italic_ for less emphasis
- __underline__ for titles or important sections
- ~strikethrough~ for corrections or deleted text
- `code` for snippets or commands
- [link](URL) for hyperlinks

Please ensure your responses are easy to read and visually appealing in a chat interface."""

if TELEGRAM_TOKEN is None:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")

if GEMINI_KEY is None and LLM_PROVIDER == "gemini":
    raise EnvironmentError("GEMINI_API_KEY is not set")
