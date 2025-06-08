import logging

from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from config import TELEGRAM_TOKEN
from handlers.commands import (clear_user_history, handle_prompt_decision,
                               handle_tts_request, help_command,
                               set_audio_mode, set_text_mode, start,
                               transcribe_text)
from handlers.messages import handle_message, voice_handler

logging.basicConfig(level=logging.WARNING)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_user_history))
    app.add_handler(CommandHandler("audio", set_audio_mode))
    app.add_handler(CommandHandler("text", set_text_mode))
    # TODO - /tool web best kebab in Berlin

    app.add_handler(CallbackQueryHandler(handle_tts_request, pattern="^send_audio_tts$"))
    app.add_handler(CallbackQueryHandler(handle_prompt_decision, pattern="^(send_prompt|cancel)$"))

    app.add_handler(MessageHandler(filters.TEXT & filters.FORWARDED, transcribe_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    

    app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()

