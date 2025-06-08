import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER")
ADMIN_ID = os.getenv("ADMIN_ID")

if TELEGRAM_TOKEN is None:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")

if GEMINI_KEY is None and LLM_PROVIDER == "gemini":
    raise EnvironmentError("GEMINI_API_KEY is not set")
