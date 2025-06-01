import logging
import os

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from services.gemini import generate_content
from services.tts import synthesize_speech

logger = logging.getLogger(__name__)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_text = context.user_data.get("last_message", "")
    prompt = user_text
        
    if query.data == "text":
            await query.edit_message_text(text=f"{user_text}", parse_mode='MarkdownV2')
       
    elif query.data == "ask":

        await query.edit_message_text(text=f"Asking Ai God's...")
        
        generated_content = markdownify(generate_content(prompt))

        # chunk in pieces the responses to pass telegram max size limit
        
        if len(generated_content) > 4096:
            chunks = [generated_content[i:i + 4096] for i in range(0, len(generated_content), 4096)]
            for chunk in chunks:
                await query.message.reply_text(text=chunk, parse_mode='MarkdownV2')
        else:
            await query.edit_message_text(text=f"{generated_content}",parse_mode='MarkdownV2')


    elif query.data == "audio":
        await query.edit_message_text(text=f"Asking Ai God's...")
        
        generated_content = generate_content(prompt)
        generated_content = generated_content.replace("*", "").replace("\n", " ").strip()
        # print(generated_content)

        filename = await synthesize_speech(generated_content)
        
        if filename:
            try:
                with open(filename, "rb") as f:
                    await query.message.reply_voice(voice=f, caption=f"{prompt}")
            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await query.message.reply_text("Couldn't send the audio.")
            finally:
              os.remove(filename)

        else:
            await query.edit_message_text(text="Content generation failed.")

