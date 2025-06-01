import os, logging
from telegram import Update
from telegram.ext import ContextTypes
from services.tts import synthesize_speech

logger = logging.getLogger(__name__)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_text = context.user_data.get("last_message", "")

    if query.data == "audio":
        filename = await synthesize_speech(user_text)
        if filename:
            try:
                with open(filename, "rb") as f:
                    await query.message.reply_voice(voice=f, caption="Here's what you said:")
            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await query.message.reply_text("Couldn't send the audio.")
            finally:
                os.remove(filename)
        else:
            await query.message.reply_text("TTS failed.")
    elif query.data == "text":
        await query.edit_message_text(text=f"You selected text: {user_text}")

