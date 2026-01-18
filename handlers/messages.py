import os
import re
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from services.conversation import conversation_manager
from services.tts import synthesize_speech
from utils.auth import ADMIN_DENY_MESSAGE, is_admin
from utils.logger import log_user_action, logger
from utils.history_state import (
    get_prompt_history,
    get_output_metadata,
    remember_generated_output,
    remember_prompt,
    lookup_reply_context,
)

from utils.tool_directives import (
    REPROCESS_CONTROL_WORDS,
    ToolDirectiveError,
    derive_followup_tool_request as _derive_followup_tool_request,
    extract_tool_request as _extract_tool_request,
)

try:
    from services.ollama import (
        pop_last_tool_audio,
        run_tool_direct,
    )
except ImportError:  # Guard against optional Ollama dependency
    pop_last_tool_audio = None
    run_tool_direct = None


DEFAULT_PARSE_MODE = "MarkdownV2"
DEFAULT_CHUNK_SIZE = 4096
MAX_VOICE_CAPTION_LENGTH = 1024
MAX_AUDIO_TEXT_LENGTH = 4096
MAX_USER_INPUT_PREVIEW = 100

CALLBACK_TOOL_TLDR_AUDIO_YES = "tool_tldr_audio_yes"
CALLBACK_TOOL_TLDR_AUDIO_NO = "tool_tldr_audio_no"

DEFAULT_MODE = "text"
MODE_AUDIO = "audio"

PROMPT_AUDIO_SUMMARY_QUESTION = "Do you want the audio summary?"
PROMPT_INVALID_TEXT = "Please send a valid text message."
PROMPT_UNKNOWN_TOOL = "Unknown tool request."


async def _ensure_admin_for_message(update: Update, target_message) -> bool:
    """Common admin gate for message-based handlers.

    Returns True when the caller is the configured admin. When False,
    it sends ADMIN_DENY_MESSAGE to the provided Telegram message (if any).
    """

    if is_admin(update):
        return True

    if target_message is not None:
        await target_message.reply_text(ADMIN_DENY_MESSAGE)

    return False


async def send_chunked_message(
    target,
    text: str,
    parse_mode: Optional[str] = DEFAULT_PARSE_MODE,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
):
    if target is None:
        logger.warning("send_chunked_message invoked without a target message")
        return []

    messages = []

    if len(text) > chunk_size:
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        for chunk in chunks:
            cleaned_chunk = _strip_markdown_escape(chunk)
            messages.append(await target.reply_text(text=cleaned_chunk, parse_mode=None))
    else:
        messages.append(await target.reply_text(text=text, parse_mode=parse_mode))

    return messages


async def _send_code_block_chunked(
    target,
    body: str,
    language: str = "bash",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
):
    """Send a long code block as multiple Telegram messages with balanced fences.

    Each chunk is wrapped in its own ```language fenced block so that
    Markdown rendering remains correct even when the output must be split
    to satisfy Telegram's message length limits.
    """

    if target is None:
        logger.warning("_send_code_block_chunked invoked without a target message")
        return []

    messages = []
    lines = (body or "").splitlines()
    current = ""

    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        test_block = f"```{language}\n{candidate}\n```"

        if len(test_block) > chunk_size and current:
            block = f"```{language}\n{current}\n```"
            messages.append(
                await target.reply_text(text=block, parse_mode="Markdown")
            )
            current = line
        else:
            current = candidate

    if current or not lines:
        block_body = current or ""
        block = f"```{language}\n{block_body}\n```"
        messages.append(await target.reply_text(text=block, parse_mode="Markdown"))

    return messages


async def send_voice_reply(update_message, filename, caption):
    if update_message is None:
        logger.warning("send_voice_reply invoked without a target message")
        return None

    try:
        with open(filename, "rb") as f:
            # trim caption when too long
            if len(caption) > MAX_VOICE_CAPTION_LENGTH:
                caption = caption[: MAX_VOICE_CAPTION_LENGTH - 3] + "..."
            sent_message = await update_message.reply_voice(voice=f, caption=caption)

    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await update_message.reply_text("Couldn't send the audio.")
        return None

    finally:
        os.remove(filename)

    return sent_message


def _resolve_user_id(update: Update, message) -> Optional[int]:
    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)
    if user_id is not None:
        return user_id
    return getattr(message, "chat_id", None)


def _build_tool_tldr_caption(summary: str, tool_name: str) -> str:
    if summary and tool_name:
        return f"{tool_name} TL;DR: {summary}"
    if summary:
        return f"TL;DR: {summary}"
    if tool_name:
        return f"TL;DR ({tool_name})"
    return "TL;DR"


async def maybe_send_tool_audio(update_message, context):
    if not conversation_manager.is_ollama() or not pop_last_tool_audio:
        return

    payload = pop_last_tool_audio()
    if not payload:
        return

    summary = payload.get("summary", "")
    tool_name = payload.get("tool_name", "")
    script = payload.get("script")

    caption = payload.get("caption") or _build_tool_tldr_caption(summary, tool_name)

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
                InlineKeyboardButton("🔊", callback_data=CALLBACK_TOOL_TLDR_AUDIO_YES),
                InlineKeyboardButton("Skip", callback_data=CALLBACK_TOOL_TLDR_AUDIO_NO),
            ]
        ]
    )

    await update_message.reply_text(
        PROMPT_AUDIO_SUMMARY_QUESTION,
        reply_markup=keyboard,
    )


async def respond_in_mode(update_message, context, user_input, ai_output, *, tool_info=None):
    if update_message is None:
        logger.warning("respond_in_mode invoked without a source message")
        return

    mode = context.user_data.get("mode", DEFAULT_MODE)
    ai_output = conversation_manager.summarize_tool_output(mode, ai_output, tool_info)
    sent_messages = []
    is_shell_agent = bool(tool_info and tool_info.get("tool_name") == "shell_agent")

    if mode == DEFAULT_MODE:
        if is_shell_agent:
            # For shell_agent, preserve Markdown code fencing even when the
            # message must be split: send as multiple balanced ```bash blocks.
            sent_messages = await _send_code_block_chunked(
                update_message,
                ai_output,
                language="bash",
            )
        else:
            reply = markdownify(ai_output)
            sent_messages = await send_chunked_message(update_message, reply)

    elif mode == MODE_AUDIO:
        if len(ai_output) > MAX_AUDIO_TEXT_LENGTH:
            ai_output = ai_output[:MAX_AUDIO_TEXT_LENGTH]
            await update_message.reply_text(
                "The generated content was too long and has been clipped to fit the limit."
            )

        filename = await synthesize_speech(ai_output)

        if filename:
            if len(user_input) > MAX_USER_INPUT_PREVIEW:
                user_input = user_input[:MAX_USER_INPUT_PREVIEW] + "..."
            voice_message = await send_voice_reply(update_message, filename, caption=user_input)
            if voice_message:
                sent_messages = [voice_message]
        else:
            await update_message.reply_text("Content generation failed.")

    remember_generated_output(context, user_input, sent_messages, tool_info)
    await maybe_send_tool_audio(update_message, context)


def _strip_markdown_escape(text: str) -> str:
    # Remove escape characters used for Telegram MarkdownV2 when sending plain text.
    return re.sub(r"\\([_\*\[\]()~`>#+=|{}.!-])", r"\1", text)


def _strip_command_prefix(text: str) -> str:
    if not text.startswith("/"):
        return text
    return text.split(" ", 1)[1] if " " in text else ""


def _merge_instructions_with_prompt(instructions: str, original_prompt: str) -> str:
    original_prompt = (original_prompt or "").strip()
    instructions = (instructions or "").strip()
    if not original_prompt:
        return instructions

    normalized = instructions.lower().rstrip("!.? ")
    if normalized in REPROCESS_CONTROL_WORDS:
        instructions = ""

    if instructions:
        return f"{instructions}\n\n{original_prompt}"
    return original_prompt


async def _maybe_handle_tool_followup(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    instructions: str,
    original_prompt: str,
    tool_metadata: dict,
):
    if not (tool_metadata and run_tool_direct):
        return False

    try:
        followup = _derive_followup_tool_request(instructions, original_prompt, tool_metadata)
    except ToolDirectiveError as directive_err:
        await message.reply_text(str(directive_err), parse_mode=None)
        return True

    if not followup:
        return False

    tool_name, parameters, display_prompt = followup
    generated_content = run_tool_direct(tool_name, parameters)

    if generated_content is None:
        await message.reply_text("Unknown tool request.", parse_mode=None)
        return True

    prompt_history = _get_prompt_history(context)
    prompt_history[message.message_id] = display_prompt
    await respond_in_mode(
        message,
        context,
        display_prompt,
        generated_content,
        tool_info={"tool_name": tool_name, "parameters": parameters},
    )
    return True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, *args):
    message = update.message
    if not await _ensure_admin_for_message(update, message):
        return
    if not message or not message.text:
        return

    prompt_history = get_prompt_history(context)

    user_text = _strip_command_prefix(message.text).strip()

    reprocess_detail = None
    reply = message.reply_to_message
    if reply:
        original_prompt, tool_metadata = lookup_reply_context(context, reply)

        if original_prompt:
            instructions = user_text

            handled = await _maybe_handle_tool_followup(
                message,
                context,
                instructions,
                original_prompt,
                tool_metadata or {},
            )
            if handled:
                return

            user_text = _merge_instructions_with_prompt(instructions, original_prompt)
            reprocess_detail = f"reply_to_message_id={reply.message_id}"

    if not user_text:
        await message.reply_text(PROMPT_INVALID_TEXT)
        return

    remember_prompt(context, message, user_text)

    if conversation_manager.is_ollama() and run_tool_direct:
        try:
            tool_request = _extract_tool_request(user_text)
        except ToolDirectiveError as directive_err:
            await message.reply_text(str(directive_err), parse_mode=None)
            return

        if tool_request:
            tool_name, parameters = tool_request
            generated_content = run_tool_direct(tool_name, parameters)

            if generated_content is None:
                await message.reply_text(PROMPT_UNKNOWN_TOOL, parse_mode=None)
                return

            await respond_in_mode(
                message,
                context,
                user_text,
                generated_content,
                tool_info={"tool_name": tool_name, "parameters": parameters},
            )
            return

    action = "reply_reprocess" if reprocess_detail else "text_message"
    detail = user_text if not reprocess_detail else f"{reprocess_detail}\n{user_text}"
    log_user_action(action, update, detail)

    mode = context.user_data.get("mode", DEFAULT_MODE)
    placeholder = f" {mode} AI God's..."
    if reprocess_detail:
        placeholder = f" {mode} Reprocessing previous message..."

    mess = await message.reply_text(placeholder, parse_mode=None)

    try:
        user_id = _resolve_user_id(update, message)
        generated_content = await conversation_manager.generate_reply_async(user_id, user_text)
    except RuntimeError as err:
        await mess.edit_text(str(err))
        return

    await respond_in_mode(message, context, user_text, generated_content)


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    edited = update.edited_message
    if not edited or not edited.text:
        return

    if not await _ensure_admin_for_message(update, edited):
        return

    remember_prompt(context, edited, edited.text.strip())

    log_user_action("edited_text", update, edited.text)

    try:
        generated_content = await conversation_manager.generate_reply_async(edited.from_user.id, edited.text)
    except RuntimeError as err:
        await edited.reply_text(str(err))
        return

    await respond_in_mode(edited, context, edited.text, generated_content)
