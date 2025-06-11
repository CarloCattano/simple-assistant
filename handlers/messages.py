import os

from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import LLM_PROVIDER
from services.gemini import handle_user_message
from services.generate import generate_content
from services.stt import transcribe
from services.tts import synthesize_speech
from utils.logger import log_user_action, logger


async def send_chunked_message(target, text: str, parse_mode='MarkdownV2', chunk_size=4096):
    if len(text) > chunk_size:
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        for chunk in chunks:
            await target.reply_text(text=chunk, parse_mode=parse_mode)
    else:
        await target.reply_text(text=text, parse_mode=parse_mode)

async def send_voice_reply(update_message, filename, caption):
    try:
        with open(filename, "rb") as f:
            # trim caption when too long 
            if len(caption) > 1024:
                caption = caption[:1021] + "..."
            await update_message.reply_voice(voice=f, caption=caption)
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await update_message.reply_text("Couldn't send the audio.")
    finally:
        os.remove(filename)


async def respond_in_mode(update_message, context, user_input, ai_output):
    mode = context.user_data.get('mode', 'text')

    if mode == "text":
        reply = markdownify(ai_output)
        await send_chunked_message(update_message, reply)
    elif mode == "audio":
        if len(ai_output) > 4096:
            ai_output = ai_output[:4096]
            await update_message.reply_text("The generated content was too long and has been clipped to fit the limit.")

        filename = await synthesize_speech(ai_output)

        if filename:
            if len(user_input) > 100:
                user_input = user_input[:100] + "..."
            await send_voice_reply(update_message, filename, caption=user_input)
        else:
            await update_message.reply_text("Content generation failed.")
        

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, *args):
    user_text = update.message.text

    if user_text.startswith('/'):
        user_text = user_text.split(' ', 1)[1] if ' ' in user_text else ''

    if not user_text:
        await update.message.reply_text("Please send a valid text message.")
        return

    log_user_action("text_message", update, user_text)

    mode = context.user_data.get('mode', 'text')
    mess = await update.message.reply_text(f" {mode} Ai God's...")
    
    if (LLM_PROVIDER == 'gemini'):
        generated_content = handle_user_message(update.effective_user, user_text)
        await respond_in_mode(update.message, context, user_text, generated_content)
    elif (LLM_PROVIDER == 'ollama'):
        generated_content = generate_content(user_text)
        await respond_in_mode(update.message, context, user_text, generated_content)

    await mess.delete()

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    mess = await update.message.reply_text("Voice message received and saved.")

    transcription = await transcribe("voice_message.ogg")
    text = transcription['candidates'][0]['content']['parts'][0]['text'].strip()
    await mess.delete()

    mess = await update.message.reply_text(f"Transcription: {text}")
 
    if (LLM_PROVIDER == 'gemini'):
        reply = handle_user_message(update.effective_user, text)
    elif (LLM_PROVIDER == 'ollama'):
        reply = generate_content(text)
    
    await mess.delete()
    await respond_in_mode(update.message, context, text, reply)

