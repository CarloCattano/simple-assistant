import logging

from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from config import TELEGRAM_TOKEN
from handlers.callbacks import button
from handlers.commands import help_command, start
from handlers.messages import handle_message, voice_handler

logging.basicConfig(level=logging.WARNING)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()

