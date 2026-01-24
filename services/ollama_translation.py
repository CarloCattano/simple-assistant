import re
from typing import Optional

from ollama import chat
from config import DEBUG_OLLAMA, DEBUG_TOOL_DIRECTIVES
from services.ollama_shared import (
    COMMAND_TRANSLATOR_SYSTEM_PROMPT,
    QUERY_TRANSLATOR_SYSTEM_PROMPT,
    MODEL_NAME,
)
from utils.logger import logger
from utils.command_guard import (
    detect_direct_command,
    sanitize_command,
    get_last_sanitize_error,
)

# COMMAND_TRANSLATOR_SYSTEM_PROMPT, QUERY_TRANSLATOR_SYSTEM_PROMPT and MODEL_NAME
# are imported from services.ollama_shared

_last_command_translation_error: Optional[str] = None

from utils.logger import debug_payload

_debug = lambda *args, **kwargs: debug_payload(*args, **kwargs) if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES else None


def _set_last_command_translation_error(reason: Optional[str]) -> None:
    global _last_command_translation_error
    _last_command_translation_error = reason


def get_last_command_translation_error() -> Optional[str]:
    return _last_command_translation_error


def _maybe_fix_unclosed_quotes(command: str) -> Optional[str]:
    command = (command or "").strip()
    if not command:
        return None

    # Check for unclosed double quotes
    if command.count('"') % 2 == 1:
        return command + '"'

    # Check for unclosed single quotes
    if command.count("'") % 2 == 1:
        return command + "'"

    # Check for unclosed backticks
    if command.count("`") % 2 == 1:
        return command + "`"

    return None


def translate_instruction_to_command(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        _set_last_command_translation_error("instruction was empty")
        return None

    _set_last_command_translation_error(None)
    _debug("command_translation_input", {"instruction": instruction})

    direct = detect_direct_command(instruction)
    if direct:
        _debug("command_translation_direct", direct)
        _set_last_command_translation_error(None)
        return direct

    messages = [
        {"role": "system", "content": COMMAND_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    _debug("command_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        command = (response.message.content or "").strip()
        _debug("command_translation_response", command)

        if command.lower().startswith("command:"):
            command = command.split(":", 1)[1].strip()

        if "\n" in command:
            command = command.splitlines()[0].strip()

        if command.upper() == "NONE":
            _debug(
                "command_translation_none",
                {"instruction": instruction, "reason": "model_returned_NONE"},
            )
            _set_last_command_translation_error("model explicitly replied with NONE (no safe command)")
            return None

        sanitized = sanitize_command(command)
        if sanitized:
            _debug("command_translation_sanitized", sanitized)
            _set_last_command_translation_error(None)
            return sanitized

        sanitize_reason = get_last_sanitize_error() or ""
        if "No closing quotation" in sanitize_reason:
            fixed = _maybe_fix_unclosed_quotes(command)
            if fixed and fixed != command:
                fixed_sanitized = sanitize_command(fixed)
                if fixed_sanitized:
                    _debug("command_translation_quote_fix", fixed_sanitized)
                    _set_last_command_translation_error(None)
                    return fixed_sanitized

        segments = re.split(r"[;&|]", command, maxsplit=1)
        leading = segments[0].strip() if segments else ""
        if leading and leading != command:
            fallback = sanitize_command(leading)
            if fallback:
                _debug(
                    "command_translation_sanitized_fallback",
                    {
                        "instruction": instruction,
                        "raw_command": fallback,
                    },
                )
                _set_last_command_translation_error(
                    "original suggestion looked unsafe; using only the leading simple command segment"
                )
                return fallback

        sanitize_reason = get_last_sanitize_error() or "sanitize_command rejected the suggested command as unsafe"
        _debug(
            "command_translation_rejected",
            {
                "instruction": instruction,
                "raw_command": command,
                "reason": sanitize_reason,
            },
        )
        _set_last_command_translation_error(sanitize_reason)
        return None
    except Exception as err:
        logger.error(f"Unable to translate instruction to command: {err}")
        _set_last_command_translation_error(f"exception during translation: {err}")
        return None


def translate_instruction_to_query(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        return None

    messages = [
        {"role": "system", "content": QUERY_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]

    _debug("query_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        query = (response.message.content or "").strip()
        _debug("query_translation_response", query)

        if "\n" in query:
            query = query.splitlines()[0].strip()

        if query.upper() == "NONE":
            return None

        return query
    except Exception as err:
        logger.error(f"Unable to translate instruction to web query: {err}")
        return None