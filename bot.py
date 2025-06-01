import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_TOKEN
from handlers.commands import start, help_command
from handlers.messages import echo, voice_handler
from handlers.callbacks import button

logging.basicConfig(level=logging.WARNING)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()

