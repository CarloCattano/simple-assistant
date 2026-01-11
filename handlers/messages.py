import json
import os
import re
import uuid

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

class ToolDirectiveError(Exception):
    pass


try:
    from services.ollama import (
        pop_last_tool_audio,
        resolve_tool_identifier,
        run_tool_direct,
        translate_instruction_to_command,
    )
except ImportError:  # Guard against optional Ollama dependency
    pop_last_tool_audio = None
    resolve_tool_identifier = None
    run_tool_direct = None
    translate_instruction_to_command = None


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

    summary = payload.get("summary", "")
    tool_name = payload.get("tool_name", "")
    script = payload.get("script")

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

    if not script:
        logger.warning("Missing audio script for tool payload: %s", payload)
        return

    context.user_data["pending_tool_audio"] = {
        "script": script,
        "caption": caption,
        "tool_name": tool_name,
        "summary": summary,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔊", callback_data="tool_tldr_audio_yes"),
                InlineKeyboardButton("Text", callback_data="tool_tldr_audio_no"),
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
        script = payload.get("script")
        caption = payload.get("caption", "TLDR")

        if not script:
            await query.message.edit_text("Audio script missing, unable to send TLDR.")
            return

        await query.message.edit_text("Generating the TLDR audio...")
        filename = None
        try:
            filename = await synthesize_speech(
                script, f"tool_tldr_{uuid.uuid4().hex}.raw"
            )
        except Exception as err:
            logger.error("Synthesizing TLDR audio failed: %s", err)

        if filename:
            await send_voice_reply(query.message, filename, caption)
            await query.message.edit_text("Shared the TLDR audio.")
        else:
            await query.message.edit_text("Failed to generate TLDR audio.")
        return


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
    message = update.message
    if not message or not message.text:
        return

    prompt_history = context.user_data.setdefault("prompt_history", {})

    raw_text = message.text
    user_text = raw_text

    if user_text.startswith("/"):
        user_text = user_text.split(" ", 1)[1] if " " in user_text else ""

    user_text = user_text.strip()

    reprocess_detail = None
    reply = message.reply_to_message
    if reply:
        original_prompt = prompt_history.get(reply.message_id)
        if not original_prompt and reply.text:
            original_prompt = reply.text.strip()

        if original_prompt:
            instructions = user_text
            control_words = {"reprocess", "retry", "again", "repeat"}
            normalized = instructions.lower().strip()
            normalized = normalized.rstrip("!.?")
            if normalized in control_words:
                instructions = ""

            if instructions:
                user_text = f"{instructions}\n\n{original_prompt}"
            else:
                user_text = original_prompt

            reprocess_detail = f"reply_to_message_id={reply.message_id}"

    if not user_text:
        await message.reply_text("Please send a valid text message.")
        return

    prompt_history[message.message_id] = user_text

    if LLM_PROVIDER == "ollama" and run_tool_direct:
        try:
            tool_request = _extract_tool_request(user_text)
        except ToolDirectiveError as directive_err:
            await message.reply_text(str(directive_err), parse_mode=None)
            return

        if tool_request:
            tool_name, parameters = tool_request
            generated_content = run_tool_direct(tool_name, parameters)

            if generated_content is None:
                await message.reply_text("Unknown tool request.", parse_mode=None)
                return

            await respond_in_mode(message, context, user_text, generated_content)
            return

    action = "reply_reprocess" if reprocess_detail else "text_message"
    detail = user_text if not reprocess_detail else f"{reprocess_detail}\n{user_text}"
    log_user_action(action, update, detail)

    mode = context.user_data.get("mode", "text")
    placeholder = f" {mode} AI God's..."
    if reprocess_detail:
        placeholder = f" {mode} Reprocessing previous message..."

    mess = await message.reply_text(placeholder, parse_mode=None)

    if LLM_PROVIDER == "gemini":
        generated_content = handle_user_message(update.effective_user, user_text)
        await respond_in_mode(message, context, user_text, generated_content)
    elif LLM_PROVIDER == "ollama":
        generated_content = generate_content(user_text)
        await respond_in_mode(message, context, user_text, generated_content)


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    edited = update.edited_message
    if not edited or not edited.text:
        return

    prompt_history = context.user_data.setdefault("prompt_history", {})
    prompt_history[edited.message_id] = edited.text.strip()

    log_user_action("edited_text", update, edited.text)

    if LLM_PROVIDER == "gemini":
        generated_content = handle_user_message(edited.from_user.id, edited.text)
        await respond_in_mode(edited, context, edited.text, generated_content)
    elif LLM_PROVIDER == "ollama":
        generated_content = generate_content(edited.text)
        await respond_in_mode(edited, context, edited.text, generated_content)


def _extract_tool_request(text: str):
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            name = payload.get("name")
            parameters = payload.get("parameters") or {}

            if isinstance(name, str) and isinstance(parameters, dict):
                return name, parameters

    return _parse_tool_directive(text)


def _parse_tool_directive(text: str):
    if not resolve_tool_identifier:
        return None

    match = re.match(r"\s*(?:run|use)\s+tool\s+(\S+)(?:\s+(.*))?$", text, re.IGNORECASE)
    if not match:
        return None

    tool_identifier = match.group(1)
    remaining = (match.group(2) or "").strip()

    resolved = resolve_tool_identifier(tool_identifier)
    if not resolved:
        raise ToolDirectiveError(f"Unknown tool '{tool_identifier}'.")

    resolved_name, entry = resolved
    parameters_def = entry.get("parameters", {}) or {}

    if not parameters_def:
        return resolved_name, {}

    if len(parameters_def) != 1:
        raise ToolDirectiveError("Tool requires structured JSON parameters.")

    param_name = next(iter(parameters_def))

    if not remaining:
        raise ToolDirectiveError("Provide the arguments needed for this tool call.")

    value = remaining
    if param_name == "prompt" and translate_instruction_to_command:
        translated = translate_instruction_to_command(remaining)

        logger.error(f"Translated instruction to command: {translated}")

        if not translated:
            raise ToolDirectiveError("Couldn't translate request into a shell command. Please send the exact command instead.")

        cleaned = translated.strip()
        cleaned = cleaned.strip('"')
        if not cleaned:
            raise ToolDirectiveError("Command translation returned an empty result.")

        normalized = cleaned.lower()
        default_normalized = remaining.lower()
        logger.error(f"Normalized command: {normalized}")
        common_prefixes = (
            "sudo",
            "ls",
            "pwd",
            "cd",
            "cat",
            "find",
            "grep",
            "tail",
            "head",
            "touch",
            "mkdir",
            "rm",
            "cp",
            "mv",
            "python",
            "pip",
            "npm",
            "node",
            "git",
            "docker",
            "curl",
            "wget",
            "top",
            "htop",
            "df",
            "du",
            "whoami",
            "ps",
            "kill",
            "chmod",
            "chown",
            "service",
            "systemctl",
            "journalctl",
            "tar",
            "zip",
            "ping",
            "unzip",
        )

        if not normalized or (
            normalized == default_normalized
            and not normalized.startswith(common_prefixes)
        ):
            raise ToolDirectiveError("I couldn't infer a valid shell command. Please send the exact command to run.")

        value = cleaned

    return resolved_name, {param_name: value}


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    await file.download_to_drive("voice_message.ogg")
    mess = await update.message.reply_text("Voice message received and saved.")

    transcription = await transcribe("voice_message.ogg")
    logger.info(f"\nTranscription result: {transcription}\n")
    text = transcription["candidates"][0]["content"]["parts"][0]["text"].strip()
    await mess.delete()

    mess = await update.message.reply_text(f"Transcription: {text}")

    if LLM_PROVIDER == "gemini":
        reply = handle_user_message(update.effective_user, text)
    elif LLM_PROVIDER == "ollama":
        reply = generate_content(text)

    await mess.delete()
    await respond_in_mode(update.message, context, text, reply)
