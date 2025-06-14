import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import ADMIN_ID, LLM_PROVIDER
from handlers.messages import send_chunked_message, handle_message
from services.gemini import clear_conversations, handle_user_message
from services.ollama import clear_history
from services.tts import synthesize_speech
from utils.logger import log_user_action

logger = __import__('logging').getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user


    if user.id == int(ADMIN_ID):
        await update.message.reply_markdown(
            f"Welcome back, sir {user.name}!",
        )
    else:
        await update.message.reply_markdown(
            f"Hi {user.name}! \n *THIS* is an _experimental_ private bot, please do not use *it*!",
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

        if len(user_message) > 4096:
            await query.message.reply_text("Message too long, please limit to 4096 characters.")
            return

        filename = await synthesize_speech(user_message)

        if filename:
            try:
                with open(filename, "rb") as f:
                    caption_text = user_message[:1024]
                    await query.message.reply_voice(voice=f, caption=caption_text)

            except Exception as e:
                logger.error(f"Error sending file: {e}")
                await query.message.reply_text("Couldn't send the audio.")
            finally:
                os.remove(filename)

        else:
            await query.message.reply_text("Audio generation failed.")


        await query.message.delete()

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
            mess = await query.edit_message_text("Sending prompt...")
            
            generated_content = markdownify(
                handle_user_message(query.from_user.id, prompt)
            )
            await mess.delete()
            await send_chunked_message(query.message, generated_content)

        else:
            await query.edit_message_text("No prompt to send.")
    
    elif query.data == 'cancel':
        if 'pending_transcript' in context.user_data:
            del context.user_data['pending_transcript']
            mess = await query.edit_message_text("Transcription cancelled.")
            await query.message.reply_text(
                "Do you want to send the transcribed text as a prompt?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Yes", callback_data='send_prompt')],
                    [InlineKeyboardButton("No", callback_data='cancel')]
                ])
            )
            await mess.delete()

        elif 'pending_prompt' in context.user_data:
            del context.user_data['pending_prompt']
            await query.edit_message_text("Prompt cancelled.")
        else:
            await query.edit_message_text("Prompt cancelled.")

async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    message_text = f"{mode} Mode activated."

    command = update.effective_message.text.split(' ', 1)
    cmd_args = command[1] if len(command) > 1 else ''

    context.user_data['mode'] = mode
    
    if not cmd_args:
        await update.message.reply_text(message_text)
        return

    mess = await update.message.reply_text(message_text)
    await handle_message(update, context, cmd_args)
    await mess.delete()

async def set_audio_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, 'audio')

async def set_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, 'text')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Help!")


async def clear_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warn(f"Clearing history for {update.effective_user}")

    if (LLM_PROVIDER == 'ollama'):
        clear_history()
    elif (LLM_PROVIDER == 'gemini'):
        clear_conversations(update.effective_user)
