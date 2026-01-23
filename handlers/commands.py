import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from config import LLM_PROVIDER
from utils.auth import ADMIN_DENY_MESSAGE, is_admin
from utils.history_state import (
    get_prompt_history,
    lookup_reply_context,
    remember_prompt,
)
from handlers.messages import (
    handle_message,
    respond_in_mode,
    send_chunked_message,
    DEFAULT_MODE,
    MODE_AUDIO,
    _merge_instructions_with_prompt,
)
from services.gemini import clear_conversations, handle_user_message
from utils.tool_directives import (
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
HELP_TEXT = (
    "Available commands:\n"
    "/start  - Start interaction with the bot\n"
    "/help   - Show this help message\n"
    "/text   - Switch to Text mode\n"
    "/audio  - Switch to Audio mode\n"
    "/web    - Web search: /web <instruction>\n"
    "/agent  - Shell agent: /agent <instruction>\n"
    "/tool   - Use tools directly: /tool <name> [args]\n"
    "/clear  - Clear conversation history\n"
    "/history- Show recent conversation history\n"
    "/flow   - Show recent tool flow events"
)

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

    if not _ensure_admin(update, update.message, context, markdown=True):
        return

    await update.message.reply_markdown(
        f"Welcome back, sir {user.name}!",
    )

    log_user_action("User used /start", update, user)

    context.user_data["mode"] = DEFAULT_MODE

    await update.message.reply_text(PROMPT_CHOOSE_MODE)


async def transcribe_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _ensure_admin(update, update.message, context):
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
    if not _ensure_admin(update, update.message, context):
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
    if not _ensure_admin(update, update.message, context):
        return

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
    if not _ensure_admin(update, update.message, context, custom_message="Tool command is available to admins only."):
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

    derived_followup = None
    remaining = instructions

    if message and message.reply_to_message:
        reply_message = message.reply_to_message
        original_prompt, tool_metadata = lookup_reply_context(context, reply_message)

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

    remember_prompt(context, message, display_prompt)

    # Ensure tool_name and parameters are set before proceeding
    if not tool_name or parameters is None:
        await update.message.reply_text("Tool name or parameters are not set. Cannot execute tool request.")
        return

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


async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut for running the shell agent via /agent <instruction>.

    Behaves like `/tool shell_agent <instruction>`: the natural-language
    instruction is translated into a safe shell command (when available)
    and executed via the existing shell_agent tool.
    """

    await _run_direct_instruction_tool(
        update,
        context,
        tool_identifier="shell_agent",
        usage_message="Usage: /agent <instruction>",
        missing_instruction_message="Please provide an instruction for the agent.",
        admin_only_message="Agent command is available to admins only.",
        backend_unavailable_message=(
            "Agent execution is only available when the Ollama backend is active."
        ),
        unavailable_message="Shell agent is unavailable.",
    )


async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut for running web_search via /web <instruction>.

    Behaves like `/tool web_search <instruction>`: the natural-language
    instruction is translated into a concise search query (when possible)
    and executed via the existing web_search tool.
    """

    await _run_direct_instruction_tool(
        update,
        context,
        tool_identifier="web_search",
        usage_message="Usage: /web <instruction>",
        missing_instruction_message="Please provide an instruction for web search.",
        admin_only_message="Web command is available to admins only.",
        backend_unavailable_message=(
            "Web search is only available when the Ollama backend is active."
        ),
        unavailable_message="Web search tool is unavailable.",
    )


async def _run_direct_instruction_tool(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    tool_identifier: str,
    usage_message: str,
    missing_instruction_message: str,
    admin_only_message: str,
    backend_unavailable_message: str,
    unavailable_message: str,
) -> None:
    """Resolve and execute a single-instruction tool and respond in mode.

    Shared helper for /agent and /web so that natural-language instructions
    are translated and routed through run_tool_direct with consistent
    prompt_history and respond_in_mode handling.
    """

    if not _ensure_admin(update, update.message, context, custom_message=admin_only_message):
        return

    if (
        LLM_PROVIDER != "ollama"
        or not run_tool_direct
        or not resolve_tool_identifier
    ):
        await update.message.reply_text(backend_unavailable_message)
        return

    if not context.args:
        await update.message.reply_text(usage_message)
        return

    instructions = " ".join(context.args).strip()
    if not instructions:
        await update.message.reply_text(missing_instruction_message)
        return

    message = update.effective_message
    derived_followup = None
    display_prompt = instructions
    tool_display_info = ""

    # When replying to a previous tool output, attempt to derive a follow-up
    # invocation using the stored prompt and tool metadata.
    if message and message.reply_to_message:
        reply_message = message.reply_to_message
        original_prompt, tool_metadata = lookup_reply_context(context, reply_message)

        if tool_metadata and resolve_tool_identifier:
            try:
                derived_followup = _derive_followup_tool_request(
                    instructions,
                    original_prompt or "",
                    tool_metadata,
                )
            except ToolDirectiveError as directive_err:
                await update.message.reply_text(str(directive_err))
                return

            if derived_followup:
                resolved = resolve_tool_identifier(tool_identifier)
                if not resolved:
                    await update.message.reply_text(unavailable_message)
                    return

                resolved_name, _ = resolved
                derived_tool_name, parameters, derived_display = derived_followup

                if derived_tool_name != resolved_name:
                    await update.message.reply_text(
                        "Follow-up command must use the same tool as the original output."
                    )
                    return

                tool_name = derived_tool_name
                display_prompt = derived_display
            else:
                tool_name = None
        else:
            tool_name = None
    else:
        tool_name = None



    # If this is a reply to a previous shell_agent message and no follow-up could be derived,
    # try to synthesize a new command using the LLM translator with previous context.
    if message and message.reply_to_message and not derived_followup:
        reply_message = message.reply_to_message
        original_prompt, tool_metadata = lookup_reply_context(context, reply_message)
        if tool_metadata and tool_metadata.get("tool_name") == "shell_agent" and translate_instruction_to_command:
            prev_command = ""
            if isinstance(tool_metadata.get("parameters", {}).get("prompt"), str):
                prev_command = tool_metadata["parameters"]["prompt"].strip()
            if not prev_command and isinstance(original_prompt, str):
                prev_command = original_prompt.strip()
            instructions_stripped = instructions.strip()
            llm_input = instructions_stripped
            if prev_command:
                llm_input = f"{instructions_stripped}\n\nPrevious command: {prev_command}"
            logger.info(f"[AGENT REPLY] LLM fallback input: {llm_input!r}")
            translated = translate_instruction_to_command(llm_input)
            logger.info(f"[AGENT REPLY] LLM fallback output: {translated!r}")
            if translated:
                tool_name = "shell_agent"
                parameters = {"prompt": translated.strip()}
                display_prompt = translated.strip()
            else:
                await update.message.reply_text(
                    "Sorry, I couldn't translate your follow-up into a valid shell command. Please rephrase."
                )
                return
        else:
            logger.info(f"[AGENT REPLY] No valid previous shell_agent context or LLM unavailable. instructions={instructions!r} tool_metadata={tool_metadata!r}")
            await update.message.reply_text(
                "Sorry, I couldn't understand your follow-up. Please rephrase or be more specific."
            )
            return

    if not derived_followup:
        try:
            tool_name, parameters = _resolve_tool_invocation(tool_identifier, instructions)
        except ToolDirectiveError as directive_err:
            await update.message.reply_text(str(directive_err))
            return

        display_prompt = instructions
        if parameters:
            first_value = next(iter(parameters.values()))
            if isinstance(first_value, str) and first_value.strip():
                display_prompt = first_value.strip()

        # Compose tool display info for user
        if tool_name == "web_search":
            tool_display_info = f"[TOOL REQUEST]\nTool: web_search\nQuery: {parameters.get('query','')}"
        elif tool_name == "shell_agent":
            tool_display_info = f"[TOOL REQUEST]\nTool: shell_agent\nPrompt: {parameters.get('prompt','')}"
        elif tool_name == "search_scrape":
            tool_display_info = f"[TOOL REQUEST]\nTool: search_scrape\nQuery: {parameters.get('query','')}"
        else:
            tool_display_info = f"[TOOL REQUEST]\nTool: {tool_name}\nParameters: {parameters}"

        if tool_display_info:
            await update.message.reply_text(tool_display_info)

    message = update.effective_message
    remember_prompt(context, message, display_prompt)

    result = run_tool_direct(tool_name, parameters)
    if result is None:
        await update.message.reply_text(unavailable_message)
        return

    await respond_in_mode(
        update.message,
        context,
        display_prompt,
        result,
        tool_info={"tool_name": tool_name, "parameters": parameters},
    )


async def clear_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _ensure_admin(update, update.message, context):
        return

    logger.warn(f"Clearing history for {update.effective_user}")

    if LLM_PROVIDER == "ollama" and clear_history:
        clear_history()
    elif LLM_PROVIDER == "gemini":
        if update.effective_user is not None:
            clear_conversations(update.effective_user.id)
    else:
        await update.message.reply_text(
            "History clearing is only supported for Ollama or Gemini backends."
        )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _ensure_admin(update, update.message, context, custom_message="History is available to the admin only."):
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
    # History entries may contain arbitrary characters that break MarkdownV2;
    # send them as plain text.
    await send_chunked_message(update.message, formatted, parse_mode=None)


async def show_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _ensure_admin(
        update,
        update.message,
        context,
        custom_message="Flow monitoring is available to the admin only.",
    ):
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
    # Event payloads often contain characters like ']' that conflict with
    # Telegram's MarkdownV2 parsing. Send as plain text.
    await send_chunked_message(update.message, formatted, parse_mode=None)


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
            "cat","cd","chmod","chown","cp","curl","df","docker","du","find","git",
            "grep","head","htop","journalctl","kill","ls","mkdir","mv","node","npm",
            "ping","pip","ps","pwd","python","rm","service","sudo","systemctl","tail","tar",             "top",             "touch",             "unzip",             "wget",             "whoami",             "zip",
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


def _ensure_admin(
    update: Update,
    message: Update | None,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    markdown: bool = False,
    custom_message: str | None = None,
) -> bool:
    """Common admin gate for command handlers.

    Returns True when the caller is the configured admin. When False,
    it sends an appropriate denial message to the provided message
    (if any) and leaves context/user_data untouched.
    """

    if is_admin(update):
        return True

    if message is None or not hasattr(message, "reply_text"):
        return False

    text = custom_message or ADMIN_DENY_MESSAGE
    if markdown and hasattr(message, "reply_markdown"):
        # Used by /start for a slightly richer welcome/deny path.
        context.application.create_task(message.reply_markdown(text))
    else:
        context.application.create_task(message.reply_text(text))

    return False
