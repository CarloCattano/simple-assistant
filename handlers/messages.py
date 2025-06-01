import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from services.generate import generate_content
from services.tts import synthesize_speech

from services.stt import transcribe
from utils.logger import log_user_action

async def send_chunked_message(target, text: str, parse_mode='MarkdownV2', chunk_size=4096):
    """
    Sends a message in chunks if it exceeds Telegram's message length limit.

    Args:
        target: The telegram object to call `.reply_text()` on. Can be `update.message`, `query.message`, etc.
        text (str): The message text to send.
        parse_mode (str): Telegram parse mode (e.g., 'MarkdownV2', 'HTML').
        chunk_size (int): Maximum size per chunk. Default is 4096 (Telegram's hard limit).
    """
    if len(text) > chunk_size:
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        for chunk in chunks:
            await target.reply_text(text=chunk, parse_mode=parse_mode)
    else:
        await target.reply_text(text=text, parse_mode=parse_mode)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_text = update.message.text

    log_user_action("text_message", update, user_text)
    
    mode = context.user_data.get('mode', 'text')
    mess = await update.message.reply_text(text=f"Asking Ai God's...")
    if mode == "text":
        # keep track of message to delete later 
        generated_content = markdownify(generate_content(user_text))

        await mess.delete()
        await send_chunked_message(update.message, generated_content)

    elif mode == "audio":
        generated_content = generate_content(user_text)
        generated_content = generated_content.replace("*", "").replace("\n", " ").strip()

        if len(generated_content) > 4096:
            generated_content = generated_content[:4096]
        
        filename = await synthesize_speech(generated_content)
        
        await mess.delete()

        if filename:
            try:
                with open(filename, "rb") as f:
                    await update.message.reply_voice(voice=f, caption=f"{user_text}")
            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await update.message.reply_text("Couldn't send the audio.")
            finally:
              os.remove(filename)

        else:
            await update.message.reply_text(text="Content generation failed.")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    await update.message.reply_text("Voice message received and saved.")
    
    transcription = await transcribe("voice_message.ogg")
    text = transcription['candidates'][0]['content']['parts'][0]['text'].strip()
    await update.message.reply_text(f"Transcription: {text}")

    reply = generate_content(text)
    await update.message.reply_text(f"{markdownify(reply)}", parse_mode="Markdownv2")
