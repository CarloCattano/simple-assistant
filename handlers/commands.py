import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import ADMIN_ID, LLM_PROVIDER
from handlers.messages import (
    handle_message,
    respond_in_mode,
    send_chunked_message,
    DEFAULT_MODE,
    MODE_AUDIO,
)
from services.gemini import clear_conversations, handle_user_message
from utils.tool_directives import (
    REPROCESS_CONTROL_WORDS,
    ToolDirectiveError,
    derive_followup_tool_request as _derive_followup_tool_request,
)

try:
    from services.ollama import (
        clear_history,
        get_recent_events,
        get_recent_history,
        resolve_tool_identifier,
        run_tool_direct,
        translate_instruction_to_command,
        translate_instruction_to_query,
    )
except ImportError:  # Optional dependency
    clear_history = None
    get_recent_events = None
    get_recent_history = None
    resolve_tool_identifier = None
    run_tool_direct = None
    translate_instruction_to_command = None
    translate_instruction_to_query = None
from services.tts import synthesize_speech
from utils.logger import log_user_action

logger = __import__("logging").getLogger(__name__)


MAX_MESSAGE_LENGTH = 4096
MAX_TTS_CAPTION_LENGTH = 1024

ADMIN_ONLY_MESSAGE = "available to the admins only."
HELP_TEXT = "Help!"

PROMPT_CHOOSE_MODE = (
    "Please choose your mode:\nType /audio for Audio mode or /text for Text mode."
)

PROMPT_TOO_LONG = "Message too long, please limit to 4096 characters."
PROMPT_CONVERT_TO_AUDIO = "Do you want to convert this text to audio?"
PROMPT_SEND_TEXT_AS_PROMPT = "Do you want to send this text as a prompt?"
PROMPT_SEND_TRANSCRIBED_AS_PROMPT = (
    "Do you want to send the transcribed text as a prompt?"
)

CALLBACK_SEND_AUDIO_TTS = "send_audio_tts"
CALLBACK_CANCEL = "cancel"
CALLBACK_SEND_PROMPT = "send_prompt"

HISTORY_LIMIT = 20
EVENT_LIMIT = 25

TRIM_HISTORY_CHARS = 380
TRIM_EVENT_EXTRA_CHARS = 120


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

    context.user_data["mode"] = DEFAULT_MODE

    await update.message.reply_text(PROMPT_CHOOSE_MODE)


async def transcribe_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(ADMIN_ONLY_MESSAGE)
        return

    await set_mode(update, context, DEFAULT_MODE)
    incoming_message = update.message.text

    if len(incoming_message) > MAX_MESSAGE_LENGTH:
        await update.message.reply_text(PROMPT_TOO_LONG)
        return

    context.user_data["pending_transcript"] = incoming_message
    context.user_data["pending_prompt"] = incoming_message

    await update.message.reply_text(
        PROMPT_CONVERT_TO_AUDIO,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Yes", callback_data=CALLBACK_SEND_AUDIO_TTS)],
                [InlineKeyboardButton("No", callback_data=CALLBACK_CANCEL)],
            ]
        ),
    )


async def handle_tts_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(ADMIN_ONLY_MESSAGE)
        return

    await set_mode(update, context, DEFAULT_MODE)
    query = update.callback_query
    await query.answer()

    user_message = context.user_data.get("pending_transcript")

    if query.data == CALLBACK_SEND_AUDIO_TTS and user_message:

        if len(user_message) > MAX_MESSAGE_LENGTH:
            await query.message.reply_text(PROMPT_TOO_LONG)
            return

        filename = await synthesize_speech(user_message)

        if filename:
            try:
                with open(filename, "rb") as f:
                    caption_text = user_message[:MAX_TTS_CAPTION_LENGTH]
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
            PROMPT_SEND_TEXT_AS_PROMPT,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Yes", callback_data=CALLBACK_SEND_PROMPT)],
                    [InlineKeyboardButton("No", callback_data=CALLBACK_CANCEL)],
                ]
            ),
        )


async def handle_prompt_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await set_mode(update, context, DEFAULT_MODE)
    query = update.callback_query
    await query.answer()

    prompt = context.user_data.get("pending_prompt")

    if query.data == CALLBACK_SEND_PROMPT:
        if prompt:
            mess = await query.edit_message_text("Sending prompt...")

            generated_content = markdownify(
                handle_user_message(query.from_user.id, prompt)
            )
            await mess.delete()
            await send_chunked_message(query.message, generated_content)

        else:
            await query.edit_message_text("No prompt to send.")

    elif query.data == CALLBACK_CANCEL:
        if "pending_transcript" in context.user_data:
            del context.user_data["pending_transcript"]
            mess = await query.edit_message_text("Transcription cancelled.")
            await query.message.reply_text(
                PROMPT_SEND_TRANSCRIBED_AS_PROMPT,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Yes", callback_data=CALLBACK_SEND_PROMPT)],
                        [InlineKeyboardButton("No", callback_data=CALLBACK_CANCEL)],
                    ]
                ),
            )
            await mess.delete()

        elif "pending_prompt" in context.user_data:
            del context.user_data["pending_prompt"]
            await query.edit_message_text("Prompt cancelled.")
        else:
            await query.edit_message_text("Prompt cancelled.")


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    if not _is_admin(update):
        await update.message.reply_text(ADMIN_ONLY_MESSAGE)
        return
    await set_mode(update, context, DEFAULT_MODE)
    message_text = f"{mode} Mode activated."

    command = update.effective_message.text.split(" ", 1)
    cmd_args = command[1] if len(command) > 1 else ""

    context.user_data["mode"] = mode

    if not cmd_args:
        await update.message.reply_text(message_text)
        return

    mess = await update.message.reply_text(message_text)
    await handle_message(update, context, cmd_args)
    await mess.delete()


async def set_audio_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, MODE_AUDIO)


async def set_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, DEFAULT_MODE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def tool_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text("Tool command is available to admins only.")
        return

    if LLM_PROVIDER != "ollama" or not run_tool_direct or not resolve_tool_identifier:
        await update.message.reply_text(
            "Tool execution is only available when the Ollama backend is active."
        )
        return

    if not context.args:
        await update.message.reply_text("Usage: /tool <name> [arguments]")
        return

    tool_identifier = context.args[0]
    instructions = " ".join(context.args[1:]).strip()

    message = update.effective_message
    prompt_history = context.user_data.setdefault("prompt_history", {})
    output_metadata = context.user_data.get("output_metadata") or {}

    derived_followup = None
    remaining = instructions

    if message and message.reply_to_message:
        reply_message = message.reply_to_message
        original_prompt = prompt_history.get(reply_message.message_id)
        if not original_prompt and reply_message.text:
            original_prompt = reply_message.text.strip()

        tool_metadata = (
            output_metadata.get(reply_message.message_id) if output_metadata else None
        )

        if tool_metadata:
            try:
                derived_followup = _derive_followup_tool_request(
                    instructions,
                    original_prompt or "",
                    tool_metadata,
                )
            except ToolDirectiveError as directive_err:
                await update.message.reply_text(str(directive_err))
                return

        if not derived_followup and original_prompt:
            remaining = _merge_instructions_with_prompt(instructions, original_prompt)

    if derived_followup:
        resolved = (
            resolve_tool_identifier(tool_identifier)
            if resolve_tool_identifier
            else None
        )
        if not resolved:
            await update.message.reply_text(f"Unknown tool '{tool_identifier}'.")
            return

        resolved_name, _ = resolved
        derived_tool_name, parameters, display_prompt = derived_followup

        if resolved_name != derived_tool_name:
            await update.message.reply_text(
                "Follow-up command must use the same tool as the original output."
            )
            return

        tool_name = derived_tool_name
    else:
        try:
            tool_name, parameters = _resolve_tool_invocation(tool_identifier, remaining)
        except ToolDirectiveError as directive_err:
            await update.message.reply_text(str(directive_err))
            return

        display_prompt = remaining
        if parameters:
            first_value = next(iter(parameters.values()))
            if isinstance(first_value, str) and first_value.strip():
                display_prompt = first_value.strip()

    if message:
        prompt_history[message.message_id] = display_prompt

    result = run_tool_direct(tool_name, parameters)
    if result is None:
        await update.message.reply_text("Unknown or unavailable tool.")
        return

    await respond_in_mode(
        update.message,
        context,
        display_prompt,
        result,
        tool_info={"tool_name": tool_name, "parameters": parameters},
    )


async def clear_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warn(f"Clearing history for {update.effective_user}")

    if LLM_PROVIDER == "ollama" and clear_history:
        clear_history()
    elif LLM_PROVIDER == "gemini":
        clear_conversations(update.effective_user)


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text("History is available to the admin only.")
        return

    if LLM_PROVIDER != "ollama" or not get_recent_history:
        await update.message.reply_text(
            "History inspection only works when Ollama is active."
        )
        return

    entries = get_recent_history(limit=HISTORY_LIMIT)
    if not entries:
        await update.message.reply_text("No conversation history recorded yet.")
        return

    formatted = "\n".join(_format_history_entry(entry) for entry in entries)
    await send_chunked_message(update.message, formatted, )


async def show_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(
            "Flow monitoring is available to the admin only."
        )
        return

    if LLM_PROVIDER != "ollama" or not get_recent_events:
        await update.message.reply_text(
            "Flow monitoring only works when Ollama is active."
        )
        return

    events = get_recent_events(limit=EVENT_LIMIT)
    if not events:
        await update.message.reply_text("No runtime events captured yet.")
        return

    formatted = "\n".join(_format_event_entry(event) for event in events)
    await send_chunked_message(update.message, formatted)


def _resolve_tool_invocation(tool_identifier: str, args_text: str):
    if not resolve_tool_identifier:
        raise ToolDirectiveError(
            "Tool execution is not available in this configuration."
        )

    resolved = resolve_tool_identifier(tool_identifier)
    if not resolved:
        raise ToolDirectiveError(f"Unknown tool '{tool_identifier}'.")

    resolved_name, entry = resolved
    parameters_def = entry.get("parameters", {}) or {}

    if not parameters_def:
        if args_text:
            raise ToolDirectiveError("This tool does not accept arguments.")
        return resolved_name, {}

    if len(parameters_def) != 1:
        raise ToolDirectiveError("Tool requires structured JSON parameters.")

    param_name = next(iter(parameters_def))

    if not args_text:
        raise ToolDirectiveError("Provide the arguments needed for this tool call.")

    value = args_text
    if param_name == "prompt" and translate_instruction_to_command:
        translated = translate_instruction_to_command(args_text)
        if not translated:
            raise ToolDirectiveError(
                "Couldn't translate request into a shell command. Please send the exact command instead."
            )

        cleaned = translated.strip().strip('"')
        if not cleaned:
            raise ToolDirectiveError("Command translation returned an empty result.")

        normalized = cleaned.lower()
        default_normalized = args_text.lower()
        common_prefixes = (
            "cat",
            "cd",
            "chmod",
            "chown",
            "cp",
            "curl",
            "df",
            "docker",
            "du",
            "find",
            "git",
            "grep",
            "head",
            "htop",
            "journalctl",
            "kill",
            "ls",
            "mkdir",
            "mv",
            "node",
            "npm",
            "ping",
            "pip",
            "ps",
            "pwd",
            "python",
            "rm",
            "service",
            "sudo",
            "systemctl",
            "tail",
            "tar",
            "top",
            "touch",
            "unzip",
            "wget",
            "whoami",
            "zip",
        )

        if not normalized or (
            normalized == default_normalized
            and not normalized.startswith(common_prefixes)
        ):
            raise ToolDirectiveError(
                f"I couldn't infer a valid shell command for {args_text}. Please send the exact command to run."
            )

        value = cleaned

    if (
        resolved_name == "web_search"
        and param_name == "query"
        and translate_instruction_to_query
    ):
        translated_query = translate_instruction_to_query(args_text)
        if not translated_query:
            raise ToolDirectiveError(
                "Couldn't infer a web search query from that request."
            )
        value = translated_query

    return resolved_name, {param_name: value}


def _merge_instructions_with_prompt(instructions: str, original_prompt: str) -> str:
    instructions = (instructions or "").strip()
    original_prompt = (original_prompt or "").strip()

    if not original_prompt:
        return instructions

    normalized = instructions.lower().strip()
    normalized = normalized.rstrip("!.?")
    if normalized in REPROCESS_CONTROL_WORDS:
        instructions = ""

    if instructions:
        return f"{instructions}\n\n{original_prompt}"

    return original_prompt


def _is_admin(update: Update) -> bool:
    try:
        return str(update.effective_user.id) == str(ADMIN_ID)
    except Exception:
        return False


def _trim(text: str, limit: int = TRIM_HISTORY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_history_entry(entry: dict) -> str:
    role = entry.get("role", "?")
    content = _trim(entry.get("content", ""))

    if role == "tool":
        tool_name = entry.get("name", "tool")
        return f"[tool:{tool_name}] {content}"

    return f"[{role}] {content}"


def _format_event_entry(event: dict) -> str:
    timestamp = event.get("time", "--:--:--")
    kind = event.get("kind", "event")
    message = _trim(event.get("message", ""))
    extras = event.get("extra") or {}

    if extras:
        extra_text = " | ".join(
            f"{key}={_trim(str(value), TRIM_EVENT_EXTRA_CHARS)}" for key, value in extras.items()
        )
        return f"{timestamp} [{kind}] {message} | {extra_text}"

    return f"{timestamp} [{kind}] {message}"
