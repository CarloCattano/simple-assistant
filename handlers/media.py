import os
import uuid
from tempfile import NamedTemporaryFile
from textwrap import dedent
from typing import Any, Optional, Sequence

from telegram import Update
from telegram.ext import ContextTypes

from services.ocr import process_image, group_tokens_by_line
from services.stt import transcribe
from services.tts import synthesize_speech
from utils.auth import ADMIN_DENY_MESSAGE, is_admin
from utils.logger import logger

from services.conversation import conversation_manager
from handlers.messages import (
    _resolve_user_id,
    respond_in_mode,
    send_voice_reply,
    CALLBACK_TOOL_TLDR_AUDIO_YES,
)


RECEIPT_FILE_PREFIX = "receipt_"
RECEIPT_FILE_SUFFIX = ".jpg"

VOICE_FILE_PREFIX = "voice_"
VOICE_FILE_SUFFIX = ".ogg"

DEFAULT_TLDR_CAPTION = "TLDR"

MSG_FAILED_DOWNLOAD_IMAGE = "Could not download the image. Please try again."
MSG_PROCESSING_IMAGE = "Processing the image..."
MSG_NO_TEXT_IN_IMAGE = "No readable text detected in the image."

MSG_OCR_REFERENCE_HEADER = "OCR output (for reference):``` \n"
MSG_OCR_REFERENCE_FOOTER = "\n```"

MSG_AUDIO_SCRIPT_MISSING = "Audio script missing, unable to send TLDR."
MSG_GENERATING_TLDR_AUDIO = "Generating the TLDR audio..."
MSG_SHARED_TLDR_AUDIO = "Shared the TLDR audio."
MSG_FAILED_TLDR_AUDIO = "Failed to generate TLDR audio."
MSG_SKIPPED_TLDR_AUDIO = "Skipped the TLDR audio."

MSG_FAILED_DOWNLOAD_VOICE = "Could not download the voice message. Please try again."
MSG_TRANSCRIBING_VOICE = "Transcribing the voice message..."
MSG_AUDIO_NOT_UNDERSTOOD = "I couldn't understand the audio."


async def _ensure_admin_for_message(update: Update, message) -> bool:
    """Common admin gate for media handlers.

    Returns True when the caller is the configured admin. When False,
    it sends ADMIN_DENY_MESSAGE to the provided Telegram message (if any).
    """

    if is_admin(update):
        return True

    if message is not None:
        await message.reply_text(ADMIN_DENY_MESSAGE)

    return False


async def handle_tool_audio_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload = context.user_data.pop("pending_tool_audio", None)

    if query.data == CALLBACK_TOOL_TLDR_AUDIO_YES and payload:
        script = payload.get("script")
        caption = payload.get("caption", DEFAULT_TLDR_CAPTION)

        if not script:
            await query.message.edit_text(MSG_AUDIO_SCRIPT_MISSING)
            return

        await query.message.edit_text(MSG_GENERATING_TLDR_AUDIO)
        filename = None
        try:
            filename = await synthesize_speech(
                script, f"tool_tldr_{uuid.uuid4().hex}.raw"
            )
        except Exception as err:
            logger.error(f"Synthesizing TLDR audio failed: {err}")

        if filename:
            await send_voice_reply(query.message, filename, caption)
            await query.message.edit_text(MSG_SHARED_TLDR_AUDIO)
        else:
            await query.message.edit_text(MSG_FAILED_TLDR_AUDIO)
        return

    await query.message.edit_text(MSG_SKIPPED_TLDR_AUDIO)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not await _ensure_admin_for_message(update, message):
        return
    if not message or not message.photo:
        return

    telegram_file = await message.photo[-1].get_file()

    with NamedTemporaryFile(prefix=RECEIPT_FILE_PREFIX, suffix=RECEIPT_FILE_SUFFIX, delete=False) as tmp_file:
        temp_path = tmp_file.name

    try:
        await telegram_file.download_to_drive(temp_path)
    except Exception as exc:  # pragma: no cover - network failure
        logger.error(f"Failed to download image: {exc}")
        await message.reply_text(MSG_FAILED_DOWNLOAD_IMAGE)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return

    status_message = await message.reply_text(MSG_PROCESSING_IMAGE)

    try:
        tokens = process_image(temp_path)
        if not tokens:
            await status_message.edit_text(MSG_NO_TEXT_IN_IMAGE)
            return

        lines = group_tokens_by_line(tokens)
        if not lines:
            await status_message.edit_text(MSG_NO_TEXT_IN_IMAGE)
            return

        receipt_prompt = dedent(
            """
            You are an AI assistant that extracts information from OCR'd receipts.
            The text may be malformed or incomplete; use context to infer missing pieces.
            List purchased items, surface totals (keywords include SUMME, GESAMT, TOTAL, SUBTOTAL...),
            and capture price payed, purchase date and location when available.

            Respond in plain, human-readable text (paragraphs and/or bullet points).
            Do NOT return JSON, dictionaries, or function/tool call objects with
            fields like "name" and "parameters".

            Here is the OCR output:
            """
        ).strip()

        aggregated_text = "\n".join(lines)
        receipt_prompt = f"{receipt_prompt}\n\n{aggregated_text}"

        user_id = _resolve_user_id(update, message)
        try:
            # Also show the raw OCR text to help with debugging and transparency.
            await message.reply_text(
                f"{MSG_OCR_REFERENCE_HEADER}{aggregated_text}{MSG_OCR_REFERENCE_FOOTER}"
            )
            reply = await conversation_manager.generate_reply_async(user_id, receipt_prompt)
        except RuntimeError as err:
            await status_message.edit_text(str(err))
            return

        await status_message.delete()
        await respond_in_mode(message, context, "Describe the image.", reply)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _extract_transcribed_text(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    candidates = payload.get("candidates")
    if not isinstance(candidates, Sequence) or not candidates:
        return None

    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return None

    content = first_candidate.get("content")
    if not isinstance(content, dict):
        return None

    parts = content.get("parts")
    if not isinstance(parts, Sequence):
        return None

    for part in parts:
        if not isinstance(part, dict):
            continue

        text = part.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    return None


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not await _ensure_admin_for_message(update, message):
        return
    if not message or not message.voice:
        return

    voice_file = await message.voice.get_file()

    with NamedTemporaryFile(prefix=VOICE_FILE_PREFIX, suffix=VOICE_FILE_SUFFIX, delete=False) as tmp_file:
        temp_path = tmp_file.name

    try:
        await voice_file.download_to_drive(temp_path)
    except Exception as exc:  # pragma: no cover - network failure
        logger.error(f"Failed to download voice message: {exc}")
        await message.reply_text(MSG_FAILED_DOWNLOAD_VOICE)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return

    status_message = await message.reply_text(MSG_TRANSCRIBING_VOICE)

    reply = None
    text = None

    try:
        transcription = await transcribe(temp_path)
        logger.debug(f"Transcription result: {transcription}")
        text = _extract_transcribed_text(transcription)

        if not text:
            await status_message.edit_text(MSG_AUDIO_NOT_UNDERSTOOD)
            return

        await status_message.edit_text(f"Transcription: {text}")

        user_id = _resolve_user_id(update, message)
        reply = await conversation_manager.generate_reply_async(user_id, text)
    except RuntimeError as err:
        await message.reply_text(str(err))
        return
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if reply is None or text is None:
        return

    await respond_in_mode(message, context, text, reply)
