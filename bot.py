import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_TOKEN
from handlers.commands import (
    agent_command,
    clear_user_history,
    handle_prompt_decision,
    handle_tts_request,
    help_command,
    show_flow,
    show_history,
    set_audio_mode,
    set_text_mode,
    start,
    tool_command,
    web_command,
    transcribe_text,
)
from handlers.messages import handle_edited_message, handle_message
from handlers.media import handle_image, handle_tool_audio_choice, voice_handler


LOG_LEVEL = logging.WARNING

CMD_START = "start"
CMD_HELP =  "help"
CMD_HISTORY = "history"
CMD_FLOW =  "flow"
CMD_TOOL =  "tool"
CMD_AGENT = "agent"
CMD_WEB =   "web"
CMD_CLEAR = "clear"
CMD_AUDIO = "audio"
CMD_TEXT =  "text"

# start - Start interaction with the bot
# help - Show this help message
# text - Set to text Mode
# audio - Set to audio Mode
# web - Web search 
# agent - runs commands 
# clear - Clear conversation history
# flow - Shows history flow
# tool - Use agentic tools
# history - See  your history

PATTERN_SEND_AUDIO_TTS = "^send_audio_tts$"
PATTERN_SEND_OR_CANCEL_PROMPT = "^(send_prompt|cancel)$"
PATTERN_TOOL_TLDR_AUDIO = "^tool_tldr_audio_(yes|no)$"

ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]


logging.basicConfig(level=LOG_LEVEL)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    command_handlers = [
        (CMD_START, start),
        (CMD_HELP, help_command),
        (CMD_HISTORY, show_history),
        (CMD_FLOW, show_flow),
        (CMD_TOOL, tool_command),
        (CMD_AGENT, agent_command),
        (CMD_WEB, web_command),
        (CMD_CLEAR, clear_user_history),
        (CMD_AUDIO, set_audio_mode),
        (CMD_TEXT, set_text_mode),
    ]

    for name, handler in command_handlers:
        app.add_handler(CommandHandler(name, handler))

    callback_handlers = [
        (handle_tts_request, PATTERN_SEND_AUDIO_TTS),
        (handle_prompt_decision, PATTERN_SEND_OR_CANCEL_PROMPT),
        (handle_tool_audio_choice, PATTERN_TOOL_TLDR_AUDIO),
    ]

    for handler, pattern in callback_handlers:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    app.add_handler(MessageHandler(filters.TEXT & filters.FORWARDED, transcribe_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.UpdateType.EDITED_MESSAGE,
            handle_edited_message,
        )
    )
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))

    app.run_polling(allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    print("Bot is starting...")
    main()
    print("...Bot quiting...")
