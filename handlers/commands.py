import os

from telegram import (ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import LLM_PROVIDER
from handlers.messages import send_chunked_message
from services.gemini import clear_conversations, handle_user_message
from services.generate import generate_content
from services.ollama import clear_history
from services.tts import synthesize_speech
from utils.logger import log_user_action

logger = __import__('logging').getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_markdown(
        f"Hi {user.name}! \n *THIS* is an _experimental_ private bot, please do not use *it*!",
        reply_markup=ForceReply(selective=True),
    )

    log_user_action("User used /start", update, user)

    context.user_data['mode'] = 'text'

    await update.message.reply_text(
        "Please choose your mode:\nType /audio for Audio mode or /text for Text mode."
    )


async def transcribe_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    incoming_message = update.message.text

    if len(incoming_message) > 4096:
        await update.message.reply_text("Message too long, please limit to 4096 characters.")
        return

    # Store message in context for later confirmation steps
    context.user_data["pending_transcript"] = incoming_message
    context.user_data["pending_prompt"] = incoming_message

    await update.message.reply_text(
        "Do you want to convert this text to audio?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data='send_audio_tts')],
            [InlineKeyboardButton("No", callback_data='cancel')]
        ])
    )


async def handle_tts_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_message = context.user_data.get("pending_transcript")

    if query.data == 'send_audio_tts' and user_message:

        # trim message and inform user if too long
        if len(user_message) > 4096:
            await query.message.reply_text("Message too long, please limit to 4096 characters.")
            return

        filename = await synthesize_speech(user_message)

        if filename:
            try:
                with open(filename, "rb") as f:
                    caption_text = f"Transcribed text: {user_message}"
                    await query.message.reply_voice(voice=f, caption=caption_text)
            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await query.message.reply_text("Couldn't send the audio.")
            finally:
                os.remove(filename)
        else:
            await query.message.reply_text("Audio generation failed.")

        # Prompt the user to use the same text as an LLM prompt
        await query.message.reply_text(
            "Do you want to send this text as a prompt?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes", callback_data='send_prompt')],
                [InlineKeyboardButton("No", callback_data='cancel')]
            ])
        )


async def handle_prompt_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prompt = context.user_data.get("pending_prompt")

    if query.data == 'send_prompt':
        if prompt:
            await query.edit_message_text("Sending prompt...")
            
            generated_content = markdownify(
                handle_user_message(query.from_user.id, prompt)
            )

            await send_chunked_message(query.message, generated_content)

        else:
            await query.edit_message_text("No prompt to send.")
    
    elif query.data == 'cancel':
        await query.edit_message_text("Prompt cancelled.")


async def set_audio_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'audio'
    await update.message.reply_text("Audio mode activated.")

async def set_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'text'
    await update.message.reply_text("Text mode activated.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Help!")

async def clear_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warn(f"Clearing history for {update.effective_user}")

    if (LLM_PROVIDER == 'ollama'):
        clear_history()
    elif (LLM_PROVIDER == 'gemini'):
        clear_conversations(update.effective_user)
