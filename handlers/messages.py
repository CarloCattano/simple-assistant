import asyncio
import os
import re
from typing import Optional

from utils.cheat_parser import format_cheat_output_for_telegram
from utils.tool_directives import ALLOWED_SHELL_CMDS as ALLOWED_COMMANDS

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.error import BadRequest
    from telegram.ext import ContextTypes
    from telegramify_markdown import markdownify
except ImportError:
    InlineKeyboardButton = InlineKeyboardMarkup = Update = BadRequest = object
    ContextTypes = object

    def markdownify(text):
        return text


from services.conversation import conversation_manager
from services.tts import synthesize_speech
from utils.auth import ADMIN_DENY_MESSAGE, is_admin
from utils.history_state import (
    get_output_metadata,
    get_prompt_history,
    lookup_reply_context,
    remember_generated_output,
    remember_prompt,
)
from utils.logger import log_user_action, logger
from utils.tool_directives import (
    REPROCESS_CONTROL_WORDS,
)
from utils.tool_directives import (
    derive_followup_tool_request as _derive_followup_tool_request,
)
from utils.tool_directives import (
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


def escape_markdown_v2(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters, including period and backslash."""
    # Escape backslash first
    text = text.replace("\\", r"\\")
    # List from Telegram MarkdownV2 docs (order matters: backslash first)
    to_escape = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    for char in to_escape:
        text = text.replace(char, f"\\{char}")
    return text


async def _safe_reply_text(target, text: str, parse_mode: Optional[str]):
    """Send a message with parse_mode, fallback to plain text on Markdown parsing errors."""
    try:
        return await target.reply_text(text=text, parse_mode=parse_mode)
    except BadRequest as e:
        if "Can't parse entities" in str(e):
            logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
            return await target.reply_text(text=text, parse_mode=None)
        raise


async def send_markdown_message(target, text: str, escape: bool = False):
    """
    Send a MarkdownV2 message with robust escaping and fallback to plain text.
    """
    if escape:
        text = escape_markdown_v2(text)
    try:
        return await target.reply_text(text=text, parse_mode="MarkdownV2")
    except BadRequest as e:
        logger.warning(f"MarkdownV2 parsing failed, sending as plain text: {e}")
        return await target.reply_text(text=text, parse_mode=None)


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

    # Use refactored chunking utilities from utils.message_chunks
    from utils.message_chunks import send_chunked_message as send_chunked_message_util

    return await send_chunked_message_util(
        target,
        text,
        parse_mode=parse_mode,
        chunk_size=chunk_size,
        safe_reply_text=_safe_reply_text,
        strip_markdown_escape=_strip_markdown_escape,
    )


from utils.message_chunks import (
    send_code_block_chunked as unified_send_code_block_chunked,
)


async def _send_code_block_chunked(
    target,
    body: str,
    language: str = "bash",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
):
    """
    Unified: Send a long code block as multiple Telegram messages with balanced fences.
    """
    import json
    # Ensure body is a string; if dict, convert to JSON string
    if isinstance(body, dict):
        body = json.dumps(body, indent=2, ensure_ascii=False)
    return await unified_send_code_block_chunked(
        target,
        body,
        language=language,
        chunk_size=chunk_size,
        safe_reply_text=_safe_reply_text,
    )


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
    if InlineKeyboardButton is not object and InlineKeyboardMarkup is not object:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔊", callback_data=CALLBACK_TOOL_TLDR_AUDIO_YES
                    ),
                    InlineKeyboardButton(
                        "Skip", callback_data=CALLBACK_TOOL_TLDR_AUDIO_NO
                    ),
                ]
            ]
        )
        await update_message.reply_text(
            PROMPT_AUDIO_SUMMARY_QUESTION,
            reply_markup=keyboard,
        )
    else:
        await update_message.reply_text(PROMPT_AUDIO_SUMMARY_QUESTION)


async def respond_in_mode(
    update_message, context, user_input, ai_output, *, tool_info=None
):
    if update_message is None:
        logger.warning("respond_in_mode invoked without a source message")
        return

    mode = context.user_data.get("mode", DEFAULT_MODE)
    # Skip TLDR summary and audio for cheat tool actions
    is_cheat_tool = bool(tool_info and tool_info.get("tool_name") == "cheat")
    ai_output = (
        ai_output
        if is_cheat_tool
        else conversation_manager.summarize_tool_output(mode, ai_output, tool_info)
    )
    sent_messages = []
    is_shell_agent = bool(tool_info and tool_info.get("tool_name") == "shell_agent")

    if mode == DEFAULT_MODE:
        if is_shell_agent:
            sent_messages = await _send_code_block_chunked(
                update_message,
                ai_output,
                language="bash",
            )
        elif is_cheat_tool:
            # Use the unified cheat.sh output formatter
            messages_to_send = format_cheat_output_for_telegram(
                ai_output, escape_markdown_v2
            )
            sent_messages = []
            for msg in messages_to_send:
                sent_msg = await _safe_reply_text(update_message, msg, "MarkdownV2")
                sent_messages.append(sent_msg)
        else:
            # Convert Markdown to MarkdownV2 for proper rendering
            ai_output = markdownify(ai_output)
            sent_messages = await send_chunked_message(
                update_message,
                ai_output,
                parse_mode=DEFAULT_PARSE_MODE,
            )

    elif mode == MODE_AUDIO:
        if is_cheat_tool:
            # Do not generate audio for cheat tool
            await update_message.reply_text(
                "Audio summary is not available for cheat.sh lookups."
            )
        else:
            if len(ai_output) > MAX_AUDIO_TEXT_LENGTH:
                ai_output = ai_output[:MAX_AUDIO_TEXT_LENGTH]
                await update_message.reply_text(
                    "The generated content was too long and has been clipped to fit the limit."
                )

            filename = await synthesize_speech(ai_output)

            if filename:
                if len(user_input) > MAX_USER_INPUT_PREVIEW:
                    user_input = user_input[:MAX_USER_INPUT_PREVIEW] + "..."
                voice_message = await send_voice_reply(
                    update_message, filename, caption=user_input
                )
                if voice_message:
                    sent_messages = [voice_message]
            else:
                await update_message.reply_text("Content generation failed.")

    remember_generated_output(context, user_input, sent_messages, tool_info)
    if not is_cheat_tool:
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
        followup = _derive_followup_tool_request(
            instructions, original_prompt, tool_metadata
        )
    except Exception as directive_err:
        await message.reply_text(str(directive_err), parse_mode=None)
        return True
    if not followup:
        return False
    tool_name, parameters, display_prompt = followup
    if not run_tool_direct:
        await message.reply_text(
            "Tool execution backend is not available.", parse_mode=None
        )
        return True
    generated_content = (
        run_tool_direct(tool_name, parameters) if run_tool_direct else None
    )
    if generated_content is None:
        await message.reply_text("Unknown tool request.", parse_mode=None)
        return True
    prompt_history = get_prompt_history(context)
    prompt_history[message.message_id] = display_prompt
    await respond_in_mode(
        message,
        context,
        display_prompt,
        generated_content,
        tool_info={"tool_name": tool_name, "parameters": parameters},
    )
    return True


def _looks_like_shell_command(text: str) -> bool:
    """Heuristic to detect if text looks like a shell command."""
    text = text.strip().lower()
    # Common shell commands
    shell_commands = ALLOWED_COMMANDS
    first_word = text.split()[0] if text else ""
    if first_word in shell_commands:
        return True
    # Check for pipes, redirects, etc.
    if "|" in text or ">" in text or "<" in text or "&" in text or ";" in text:
        return True
    return False


async def _run_tool_async(tool_name, parameters):
    # Offload to thread if run_tool_direct is blocking
    return await asyncio.to_thread(run_tool_direct, tool_name, parameters)


async def _handle_shell_command(message, context, user_text):
    tool_name = "shell_agent"
    parameters = {"prompt": user_text}
    generated_content = await _run_tool_async(tool_name, parameters)
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


async def _handle_tool_request(message, context, user_text, tool_name, parameters):
    generated_content = await _run_tool_async(tool_name, parameters)
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


async def maybe_handle_tool_followup_reply(message, context, user_text, reply):
    """
    Unified handler for follow-ups to tool outputs (web, agent, scrape, etc.).
    Uses the tool output as context for the LLM if detected.
    Returns True if handled, False otherwise.
    """
    # Heuristic: If reply has tool metadata, or looks like a tool/scrape/web output
    original_prompt, tool_metadata = lookup_reply_context(context, reply)
    if tool_metadata and tool_metadata.get("tool_name"):
        # For agent/web/tool outputs, use the output as context for LLM follow-up
        tool_content = reply.text
        prompt = (
            f"Given the following tool output:\n\n{tool_content}\n\n"
            f"Answer this question: {user_text}"
        )
        user_id = _resolve_user_id(message, message)
        generated_content = await conversation_manager.generate_reply_async(
            user_id, prompt
        )
        await respond_in_mode(message, context, user_text, generated_content)
        return True
    # For scrape outputs, detect by marker
    if (
        reply.text
        and "*Title:*" in reply.text
        and "*Links:*" in reply.text
        and not (tool_metadata and tool_metadata.get("tool_name"))
    ):
        scrape_content = reply.text
        prompt = (
            f"Given the following web page content scraped from a site:\n\n"
            f"{scrape_content}\n\n"
            f"Answer this question: {user_text}"
        )
        user_id = _resolve_user_id(message, message)
        generated_content = await conversation_manager.generate_reply_async(
            user_id, prompt
        )
        await respond_in_mode(message, context, user_text, generated_content)
        return True
    # For web search outputs, detect by marker
    if (
        reply.text
        and "**Links:**" in reply.text
        and not (tool_metadata and tool_metadata.get("tool_name"))
    ):
        web_content = reply.text
        prompt = (
            f"Given the following web search results:\n\n"
            f"{web_content}\n\n"
            f"Answer this question: {user_text}"
        )
        user_id = _resolve_user_id(message, message)
        generated_content = await conversation_manager.generate_reply_async(
            user_id, prompt
        )
        await respond_in_mode(message, context, user_text, generated_content)
        return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, *args):
    message = update.message
    logger.info(
        f"Message received from chat_id: {message.chat.id}, user: {message.from_user.id if message.from_user else 'unknown'}"
    )

    if not await _ensure_admin_for_message(update, message):
        return
    if not message or not message.text:
        return

    logger.info(
        f"Received message from chat_id: {message.chat.id}, text: {message.text[:50]}..."
    )


    user_text = _strip_command_prefix(message.text).strip()

    reprocess_detail = None
    reply = message.reply_to_message
    if reply:
        # Unified tool follow-up handler
        handled = await maybe_handle_tool_followup_reply(
            message, context, user_text, reply
        )
        if handled:
            return

        original_prompt, tool_metadata = lookup_reply_context(context, reply)
        if tool_metadata and tool_metadata.get("tool_name") == "shell_agent":
            if _looks_like_shell_command(user_text):
                # Treat as shell command: use context-aware follow-up
                instructions = user_text
                from utils.tool_directives import (
                    ToolDirectiveError,
                    derive_followup_tool_request,
                )

                try:
                    followup = derive_followup_tool_request(
                        instructions, original_prompt or "", tool_metadata
                    )
                except ToolDirectiveError as directive_err:
                    await message.reply_text(str(directive_err), parse_mode=None)
                    return
                if followup:
                    tool_name, parameters, display_prompt = followup
                    generated_content = await _run_tool_async(tool_name, parameters)
                    if generated_content is None:
                        await message.reply_text(PROMPT_UNKNOWN_TOOL, parse_mode=None)
                        return
                    await respond_in_mode(
                        message,
                        context,
                        display_prompt,
                        generated_content,
                        tool_info={"tool_name": tool_name, "parameters": parameters},
                    )
                    return
                # If followup fails, fall through to normal logic
            else:
                # Treat as natural-language question: summarize or answer
                shell_output = reply.text or ""
                llm_prompt = f"Given this shell output:\n{shell_output}\n\nAnswer this question: {user_text}"
                try:
                    user_id = _resolve_user_id(update, message)
                    generated_content = await conversation_manager.generate_reply_async(
                        user_id, llm_prompt
                    )
                except RuntimeError as err:
                    await message.reply_text(str(err))
                    return
                await respond_in_mode(message, context, user_text, generated_content)
                return
        elif original_prompt:
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

    prompt_history = get_prompt_history(context)
    llm_prompt = user_text

    if not user_text:
        await message.reply_text(PROMPT_INVALID_TEXT)
        return

    remember_prompt(context, message, user_text)

    if _looks_like_shell_command(user_text):
        await _handle_shell_command(message, context, user_text)
        return

    if conversation_manager.is_ollama() and run_tool_direct:
        try:
            tool_request = _extract_tool_request(user_text)
        except Exception as directive_err:
            await message.reply_text(str(directive_err), parse_mode=None)
            return

        if tool_request:
            tool_name, parameters = tool_request
            if not run_tool_direct:
                await message.reply_text(
                    "Tool execution backend is not available.", parse_mode=None
                )
                return
            await _handle_tool_request(
                message, context, user_text, tool_name, parameters
            )
            return

    action = "reply_reprocess" if reprocess_detail else "text_message"
    detail = user_text if not reprocess_detail else f"{reprocess_detail}\n{user_text}"
    log_user_action(action, update, detail)

    # Only send placeholder if not handled by tool followup
    mode = context.user_data.get("mode", DEFAULT_MODE)
    placeholder = f" {mode} AI God's..."
    if reprocess_detail:
        placeholder = f" {mode} Reprocessing previous message..."

    mess = await message.reply_text(placeholder, parse_mode=None)

    try:
        user_id = _resolve_user_id(update, message)
        generated_content = await conversation_manager.generate_reply_async(
            user_id, user_text
        )
    except RuntimeError as err:
        await mess.edit_text(str(err))
        return

    if reprocess_detail:
        try:
            await mess.delete()
        except Exception:
            pass

    tool_call_match = re.match(
        r"~\{\s*\"name\":\s*\"(\w+)\",\s*\"parameters\":\s*(\{.*?\})\s*\}~",
        generated_content,
    )
    if tool_call_match and run_tool_direct:
        tool_name = tool_call_match.group(1)
        import json

        try:
            parameters = json.loads(tool_call_match.group(2))
        except Exception:
            parameters = {}
        await _handle_tool_request(message, context, user_text, tool_name, parameters)
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
        generated_content = await conversation_manager.generate_reply_async(
            edited.from_user.id, edited.text
        )
    except RuntimeError as err:
        await edited.reply_text(str(err))
        return

    await respond_in_mode(edited, context, edited.text, generated_content)
