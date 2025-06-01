#!/usr/bin/env python
# pylint: disable=unused-argument

import logging
import base64, requests, uuid

from telegram import (
    ForceReply,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application, 
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

if TOKEN is None:
    raise Exception('TELEGRAM_BOT_TOKEN is not set')

if GEMINI_KEY is None:
    raise Exception('GEMINI_API_KEY is not set')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# TTS  
# 
async def synthesize_speech_gemini(text_to_speak: str, output_filename: str = "tts_output.mp3"):
    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={GEMINI_KEY}"

    headers = {
        "Content-Type": "application/json"
    }

    # Body for the dedicated Text-to-Speech API
    body_tts = {
        "input": {
            "text": text_to_speak
        },
        "voice": {
            "languageCode": "en-US",  
            "name": "Kore"
        },
        "audioConfig": {
            "audioEncoding": "OGG_OPUS"  # Other options: "OGG_OPUS", "LINEAR16"
        }
    }
    current_body = body_tts

    logger.info(f"Sending text to Gemini TTS: \"{text_to_speak[:50]}...\"")
    try:
        # Using synchronous requests here as the function isn't defined as async
        # For async behavior in an async bot, consider using an HTTP client like httpx or aiohttp
        response = requests.post(url, headers=headers, json=current_body, timeout=30)
        response.raise_for_status()  # Raise an exception for HTTP errors

        response_json = response.json()
        audio_content_b64 = response_json.get("audioContent")

        if not audio_content_b64:
            logger.error(f"No audioContent in Gemini TTS response: {response_json}")
            return None

        audio_bytes = base64.b64decode(audio_content_b64)

        with open(output_filename, "wb") as audio_file:
            audio_file.write(audio_bytes)
        
        logger.info(f"Audio content saved to {output_filename}")
        return output_filename
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Gemini TTS API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        return None
    
    except Exception as e:
        logger.error(f"An unexpected error occurred during TTS: {e}")
        return None
# -------------------------------------------------------------------


# Speech-to-text ----------------------------------------------------

def encode_audio_to_base64(file_path):
    """Encodes audio file to base64."""
    with open(file_path, "rb") as audio_file:
        return base64.b64encode(audio_file.read()).decode("utf-8")

async def transcribe_audio(file_path):
    """Sends audio to Gemini API for transcription."""
    audio_b64 = encode_audio_to_base64(file_path)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

    headers = {
        "Content-Type": "application/json"
    }

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/ogg",  # Adjust MIME type as needed
                            "data": audio_b64
                        }
                    },
                    {
                        "text": "Please transcribe this audio."
                    }
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=body)
    return response.json()
# ----------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echoes the user message as text and then sends it as speech."""
    user_text = update.message.text

    if not user_text:
        return

    if update.message.forward_origin:
        await update.message.reply_text("You sent a forwarded message.")

    context.user_data["last_message"] = user_text

    keyboard = [
        [
            InlineKeyboardButton("🔈", callback_data="audio"),
            InlineKeyboardButton("📓", callback_data="text"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🔈", reply_markup=reply_markup)


async def generate_tts(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str) -> None:
    user_id = update.effective_user.id
    audio_output_filename = f"tts_echo_{user_id}_{uuid.uuid4()}.mp3"
    audio_file_path = await synthesize_speech_gemini(user_text, audio_output_filename)

    if audio_file_path:
        try:
            with open(audio_file_path, "rb") as audio_to_send:
                await update.callback_query.message.reply_voice(
                    voice=audio_to_send,
                    caption="Here's what you said:"
                )
            logger.info(f"Sent TTS audio for: {user_text[:30]}")
        except FileNotFoundError:
            logger.error(f"TTS output file not found: {audio_file_path}")
            await update.callback_query.message.reply_text(
                "Sorry, I generated the audio but couldn't find the file to send."
            )
        except Exception as e:
            logger.error(f"Error sending TTS audio: {e}")
            await update.callback_query.message.reply_text(
                "Sorry, an error occurred while sending the audio."
            )
        finally:
            if os.path.exists(audio_file_path):
                try:
                    os.remove(audio_file_path)
                    logger.info(f"Cleaned up TTS audio file: {audio_file_path}")
                except Exception as e:
                    logger.error(f"Error deleting TTS audio file {audio_file_path}: {e}")
    else:
        await update.callback_query.message.reply_text(
            "Sorry, I couldn't convert your message to speech."
        )


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    voice = update.message.voice
    if voice:
        file = await voice.get_file()
        await file.download_to_drive(f"voice_message.ogg")  # Save the file locally
        await update.message.reply_text("Voice message received and saved.")
    
        # Upload to transcriber
        # transcription = await transcribe_audio("voice_message.ogg")
        # await update.message.reply_text(f"Transcription: {transcription}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    await query.edit_message_text(text=f"{query.data}")

    
    user_text = context.user_data.get("last_message", "")

    if query.data == "audio":
        await generate_tts(update, context, user_text)
    elif query.data == "text":
        await query.edit_message_text(text=f"You selected text: {user_text}")



def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(CallbackQueryHandler(button))

    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

