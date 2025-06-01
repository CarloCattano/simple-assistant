import logging
import os

from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from services.tts import synthesize_speech

logger = logging.getLogger(__name__)


