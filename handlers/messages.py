from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.logger import log_user_action

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if not user_text:
        return


    log_user_action("text_message", update, user_text)

    context.user_data["last_message"] = user_text

    keyboard = [[
        InlineKeyboardButton("🔈", callback_data="audio"),
        InlineKeyboardButton("📓", callback_data="text"),
    ]]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔈", reply_markup=markup)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    await update.message.reply_text("Voice message received and saved.")

