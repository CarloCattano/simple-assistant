import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if TELEGRAM_TOKEN is None:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")

if GEMINI_KEY is None:
    raise EnvironmentError("GEMINI_API_KEY is not set")
