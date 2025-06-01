from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from services.gemini import generate_content
from services.stt import transcribe
from utils.logger import log_user_action


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_text = update.message.text

    log_user_action("text_message", update, user_text)
    
    if user_text.strip().startswith("/ask "):
        prompt = user_text[5:].strip()
        await update.message.reply_text("Asking Gemini...")

        reply = generate_content(prompt)
        await update.message.reply_text(reply)
    
    else:
        context.user_data["last_message"] = user_text

        keyboard = [[
            InlineKeyboardButton("🔈", callback_data="audio"),
            InlineKeyboardButton("📓", callback_data="text"),
            InlineKeyboardButton("?", callback_data="ask"),
        ]]

        markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🔈", reply_markup=markup)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    await update.message.reply_text("Voice message received and saved.")
    
    transcription = await transcribe("voice_message.ogg")
    text = transcription['candidates'][0]['content']['parts'][0]['text'].strip()
    await update.message.reply_text(f"Transcription: {text}")

    reply = generate_content(text)
    await update.message.reply_text(f"{markdownify(reply)}", parse_mode="Markdownv2")
