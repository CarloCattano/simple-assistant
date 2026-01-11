import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import LLM_PROVIDER
from services.gemini import handle_user_message
from services.generate import generate_content
from services.stt import transcribe
from services.tts import synthesize_speech
from utils.logger import log_user_action, logger

from services.ocr import process_image, group_tokens_by_line

try:
    from services.ollama import pop_last_tool_audio
except ImportError:  # Guard against optional Ollama dependency
    pop_last_tool_audio = None


async def send_chunked_message(
    target, text: str, parse_mode="MarkdownV2", chunk_size=4096
):
    if len(text) > chunk_size:
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        for chunk in chunks:
            cleaned_chunk = _strip_markdown_escape(chunk)
            await target.reply_text(text=cleaned_chunk, parse_mode=None)
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


async def maybe_send_tool_audio(update_message, context):
    if LLM_PROVIDER != "ollama" or not pop_last_tool_audio:
        return

    payload = pop_last_tool_audio()
    if not payload:
        return

    filename = payload.get("path")
    summary = payload.get("summary", "")
    tool_name = payload.get("tool_name", "")

    caption = payload.get("caption")
    if not caption:
        if summary and tool_name:
            caption = f"{tool_name} TL;DR: {summary}"
        elif summary:
            caption = f"TL;DR: {summary}"
        elif tool_name:
            caption = f"TL;DR ({tool_name})"
        else:
            caption = "TL;DR"

    if not filename:
        logger.warning("Missing filename for tool audio payload: %s", payload)
        return

    # Clean up any previously pending audio before storing the new one.
    existing = context.user_data.pop("pending_tool_audio", None)
    if existing:
        old_path = existing.get("path")
        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError as err:
                logger.warning("Failed to remove stale TL;DR audio %s: %s", old_path, err)

    context.user_data["pending_tool_audio"] = {
        "path": filename,
        "caption": caption,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔊", callback_data="tool_tldr_audio_yes"),
                InlineKeyboardButton("Skip", callback_data="tool_tldr_audio_no"),
            ]
        ]
    )

    await update_message.reply_text(
        "Do you want the audio summary?",
        reply_markup=keyboard,
    )


async def respond_in_mode(update_message, context, user_input, ai_output):
    mode = context.user_data.get("mode", "text")

    if mode == "text":
        reply = markdownify(ai_output)
        await send_chunked_message(update_message, reply)
    elif mode == "audio":
        if len(ai_output) > 4096:
            ai_output = ai_output[:4096]
            await update_message.reply_text(
                "The generated content was too long and has been clipped to fit the limit."
            )

        filename = await synthesize_speech(ai_output)

        if filename:
            if len(user_input) > 100:
                user_input = user_input[:100] + "..."
            await send_voice_reply(update_message, filename, caption=user_input)
        else:
            await update_message.reply_text("Content generation failed.")

    await maybe_send_tool_audio(update_message, context)


def _strip_markdown_escape(text: str) -> str:
    # Remove escape characters used for Telegram MarkdownV2 when sending plain text.
    return re.sub(r"\\([_\*\[\]()~`>#+=|{}.!-])", r"\1", text)


async def handle_tool_audio_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload = context.user_data.pop("pending_tool_audio", None)

    if query.data == "tool_tldr_audio_yes" and payload:
        filename = payload.get("path")
        caption = payload.get("caption", "TLDR")

        if filename and os.path.exists(filename):
            await send_voice_reply(query.message, filename, caption)
            await query.message.edit_text("Shared the TLDR audio.")
            return

        await query.message.edit_text("Audio file missing, unable to send TLDR.")
        return

    if payload:
        filename = payload.get("path")
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError as err:
                logger.warning("Failed to remove skipped TLDR audio %s: %s", filename, err)

    await query.message.edit_text("Skipped the TLDR audio.")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    image_file = await update.message.photo[-1].get_file()

    receipImg = "receipt_image.jpg"

    await image_file.download_to_drive(receipImg)
    mess = await update.message.reply_text("Image received  ok")

    tokens = process_image(receipImg)
    ocr_text = " ".join(group_tokens_by_line(tokens))

    if os.path.exists(receipImg):
        os.remove(receipImg)

    await mess.delete()
    mess = await update.message.reply_text(f"text extracted, sending to llm")

    receipt_prompt = (
        """
        You are an AI assistant that extracts information from receipts text extracted with OCR.
        the text might be malformed or missing characters, be partially incomplete etc, so make an effort to fill in the gaps from context.
        List the items bought and look for the text "SUMME" ,"GESAMT" or TOTAL to find the total amount paid.
        Read the date and place of purchase if available.
        Here the json formated input with height information per token:
        """
        + ocr_text
    )

    if LLM_PROVIDER == "gemini":
        reply = handle_user_message(update.effective_user, receipt_prompt)
    elif LLM_PROVIDER == "ollama":
        reply = generate_content(receipt_prompt)
    await mess.delete()
    await respond_in_mode(update.message, context, "Describe the image.", reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, *args):
    user_text = update.message.text

    if user_text.startswith("/"):
        user_text = user_text.split(" ", 1)[1] if " " in user_text else ""

    if not user_text:
        await update.message.reply_text("Please send a valid text message.")
        return

    log_user_action("text_message", update, user_text)

    mode = context.user_data.get("mode", "text")
    mess = await update.message.reply_text(f" {mode} AI God's...")

    if LLM_PROVIDER == "gemini":
        generated_content = handle_user_message(update.effective_user, user_text)
        await respond_in_mode(update.message, context, user_text, generated_content)
    elif LLM_PROVIDER == "ollama":
        generated_content = generate_content(user_text)
        await respond_in_mode(update.message, context, user_text, generated_content)

    await mess.delete()


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    mess = await update.message.reply_text("Voice message received and saved.")

    transcription = await transcribe("voice_message.ogg")
    print(transcription)
    text = transcription["candidates"][0]["content"]["parts"][0]["text"].strip()
    await mess.delete()

    mess = await update.message.reply_text(f"Transcription: {text}")

    if LLM_PROVIDER == "gemini":
        reply = handle_user_message(update.effective_user, text)
    elif LLM_PROVIDER == "ollama":
        reply = generate_content(text)

    await mess.delete()
    await respond_in_mode(update.message, context, text, reply)
