import asyncio
import logging
import json
import os
import re
import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import asyncio

from ollama import chat as _ollama_chat

from config import (
    DEBUG_HISTORY_STATE,
    DEBUG_OLLAMA,
    DEBUG_TOOL_DIRECTIVES,
    SYSTEM_PROMPT,
)
from services.ollama_shared import (
    COMMAND_TRANSLATOR_SYSTEM_PROMPT,
    MAX_HISTORY_LENGTH,
    MAX_TOOL_OUTPUT_IN_HISTORY,
    MODEL_NAME,
    QUERY_TRANSLATOR_SYSTEM_PROMPT,
)
from tools import load_tools
from services.ollama_tools import (
    evaluate_tool_usage,
    call_tool_with_tldr,
    tldr_tool_output,
    build_audio_script,
    run_tool_direct,
    resolve_tool_identifier,
)
# Export run_tool_direct and resolve_tool_identifier for external imports
__all__ = [
    "evaluate_tool_usage",
    "call_tool_with_tldr",
    "tldr_tool_output",
    "build_audio_script",
    "run_tool_direct",
    "resolve_tool_identifier",
]
from utils.command_guard import (
    detect_direct_command,
    get_last_sanitize_error,
    sanitize_command,
)
from utils.logger import logger, debug_payload

if hasattr(_ollama_chat, "chat"):
    chat = _ollama_chat.chat
else:
    chat = _ollama_chat


# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

# Shared constants imported from services.ollama_shared

available_functions = load_tools()

TOOL_MODE = False

EVENT_LOG_LIMIT = 200
MAX_EVENT_TEXT = 400

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

_event_log: deque[Dict[str, Any]] = deque(maxlen=EVENT_LOG_LIMIT)
_last_command_translation_error: Optional[str] = None


def debug(*args, **kwargs):
    if logger.isEnabledFor(logging.DEBUG):
        debug_payload(*args, **kwargs)


def _redact_system_content_in_messages(
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Return a copy of messages with system role content redacted for logging."""
    sanitized: List[Dict[str, str]] = []
    for m in messages:
        if m.get("role") == "system":
            sanitized.append({**m, "content": "<REDACTED_SYSTEM_PROMPT>"})
        else:
            sanitized.append(m)
    return sanitized


def _sanitize_payload(payload: Any) -> Any:
    """Sanitize common payload structures (e.g., dicts with a 'messages' key) to avoid logging system prompts."""
    if isinstance(payload, dict):
        p = dict(payload)
        if "messages" in p and isinstance(p["messages"], list):
            p["messages"] = _redact_system_content_in_messages(p["messages"])
    return payload



def generate_content(prompt: str) -> str | tuple[str, str | None]:
    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])

    _ensure_system_prompt(history)

    # Add user message
    history.append({"role": "user", "content": prompt})
    _trim_history(history)
    _record_event("user", prompt, user_id=user_id)
    if DEBUG_HISTORY_STATE:
        debug(
            "history_after_user",
            {
                "user_id": user_id,
                "entries": _redact_system_content_in_messages(history),
            },
        )

    try:
        use_tools, matched_tools = evaluate_tool_usage(prompt)
        debug(
            "tool_evaluation",
            {
                "prompt": prompt,
                "use_tools": use_tools,
                "matched_tools": list(matched_tools.keys()),
            },
        )
        messages = history

        debug(
            "chat_request",
            {
                "messages": _redact_system_content_in_messages(messages),
            },
        )

        tool_pool = matched_tools if matched_tools else available_functions
        tool_callables = (
            [entry["function"] for entry in tool_pool.values()] if use_tools else []
        )

        response = chat(
            model=MODEL_NAME,
            messages=messages,
            keep_alive=0,
            tools=tool_callables,
        )
        response_message_content = None
        try:
            response_message_content = getattr(response.message, "content", None)
        except Exception:
            response_message_content = None
        log_payload: Dict[str, Any] = {}
        if response_message_content is not None:
            log_payload["message_content"] = response_message_content
        if log_payload:
            debug("chat_response", log_payload)

        if response.message.tool_calls:
            # Add the assistant's message with tool calls to history for context
            assistant_message = {
                "role": "assistant",
                "content": response.message.content or "",
                "tool_calls": [
                    call.model_dump() if hasattr(call, "model_dump") else call
                    for call in response.message.tool_calls
                ],
            }
            history.append(assistant_message)
            debug(
                "tool_calls",
                [call.function.name for call in response.message.tool_calls],
            )
            for tool in response.message.tool_calls:
                func_entry = available_functions.get(tool.function.name)
                if func_entry and (
                    not matched_tools or tool.function.name in matched_tools
                ):
                    debug(
                        "executing_tool",
                        {
                            "tool": tool.function.name,
                            "arguments": tool.function.arguments,
                        },
                    )
                    output = call_tool_with_tldr(
                        tool.function.name,
                        func_entry["function"],
                        history,
                        **tool.function.arguments,
                    )
                    return output
                else:
                    logger.warning(
                        f"Tool {tool.function.name} not found in available functions."
                    )

        reply = response.message.content or ""
        reply = escape_entities(reply)
        history.append({"role": "assistant", "content": reply})

        _record_event("assistant", reply)
        debug(
            "assistant_reply",
            {
                "user_id": user_id,
                "reply": reply,
                "history_size": len(history),
            },
        )
        return reply

    except Exception as e:
        return f"Error calling Ollama API: {e}"


def escape_entities(text: str) -> str:
    # a list of entities to escape
    entities = ["!", "="]
    for entity in entities:
        text = text.replace(entity, f" {entity}")
    return text








def call_tool_with_tldr(
    tool_name: str,
    tool_callable,
    history: List[Dict[str, str]],
    tldr_separate: bool = False,
    **arguments,
) -> str | tuple[str, str | None]:
    working_arguments = dict(arguments)

    if (
        tool_name == "web_search"
        and translate_instruction_to_query
        and isinstance(working_arguments.get("query"), str)
    ):
        query = working_arguments["query"].strip()
        if query:
            translated = translate_instruction_to_query(query)
            if not translated:
                logger.warning(
                    "Query translation failed for web_search; aborting tool call."
                )
                return "I couldn't infer a web search query from that request."
            working_arguments["query"] = translated

    # This function is now fully handled by services/ollama_tools.py
    # Remove all local/duplicate logic. Use the centralized import instead.
    raise NotImplementedError("call_tool_with_tldr is now handled by services/ollama_tools.py. Use the centralized version.")


def _format_tool_output(tool_name: str, raw_output: Any) -> str:
    if raw_output is None:
        return "Tool returned no data."

    if isinstance(raw_output, str):
        stripped = raw_output.strip()
        return stripped or "Tool returned an empty response."

    if isinstance(raw_output, dict):
        lines: List[str] = []

        command = raw_output.get("command")
        exit_code = raw_output.get("exit_code")
        stdout = raw_output.get("stdout")
        stderr = raw_output.get("stderr")

        if command:
            lines.append(f"$ {command}")
        has_error = (exit_code not in (0, None)) or (stderr and not stdout)

        if has_error:
            if exit_code is not None:
                lines.append(f"Exit code: {exit_code}")

            if stdout:
                stdout_str = stdout.strip()
                if len(stdout_str) > 16000:  # Truncate very long stdout
                    stdout_str = stdout_str[:16000] + "\n... (output truncated)"
                lines.append("Stdout:")
                lines.append(stdout_str)

            if stderr:
                lines.append("Stderr:")
                lines.append(stderr.strip())
        else:
            if stdout:
                stdout_str = stdout.strip()
                if len(stdout_str) > 16000:  # Truncate very long stdout
                    stdout_str = stdout_str[:16000] + "\n... (output truncated)"
                lines.append(stdout_str)
            elif exit_code is not None:
                lines.append(f"Exit code: {exit_code}")

        if lines:
            return "\n".join(lines).strip()

        try:
            return json.dumps(raw_output, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            return str(raw_output)

    if isinstance(raw_output, (list, tuple, set)):
        return (
            "\n".join(str(item) for item in raw_output)
            or "Tool returned an empty list."
        )

    return str(raw_output)


def _get_or_create_user_id() -> str:
    if not hasattr(_thread_local, "user_id"):
        _thread_local.user_id = str(uuid.uuid4())
    return _thread_local.user_id


def _ensure_system_prompt(history: List[Dict[str, str]]) -> None:
    """Ensure the first history entry is the system prompt.

    Both chat-driven and direct tool flows expect the same leading
    system message; centralize this check so behavior stays aligned.
    """

    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


def _trim_history(history: List[Dict[str, str]]) -> None:
    """Trim conversation history to a bounded length while preserving system prompt.

    Keeps the first entry (typically the system prompt) and the most recent
    MAX_HISTORY_LENGTH-1 messages.
    """
    if len(history) <= MAX_HISTORY_LENGTH:
        return

    system = history[0:1]
    recent = history[-(MAX_HISTORY_LENGTH - 1) :]
    history[:] = system + recent






# Import the async-compatible wrapper from the shim, so existing imports work
from services.ollama_async_shim import run_tool_direct_async








def _set_last_command_translation_error(reason: Optional[str]) -> None:
    global _last_command_translation_error
    _last_command_translation_error = reason


def get_last_command_translation_error() -> Optional[str]:
    """Return a human-readable reason from the most recent command translation attempt, if any."""

    return _last_command_translation_error


def _maybe_fix_unclosed_quotes(command: str) -> Optional[str]:
    """Best-effort fix for commands that only fail due to an unclosed quote.

    This is used only for LLM-suggested commands in translate_instruction_to_command,
    never for raw user input. If we detect an odd number of single or double quotes,
    we append the missing closing quote and let sanitize_command re-validate.
    """

    text = command or ""
    for quote in ('"', "'"):
        if text.count(quote) % 2 == 1:
            return text + quote
    return None


def translate_instruction_to_command(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        _set_last_command_translation_error("instruction was empty")
        return None

    _set_last_command_translation_error(None)
    debug("command_translation_input", {"instruction": instruction})

    direct = detect_direct_command(instruction)
    if direct:
        debug("command_translation_direct", direct)
        _set_last_command_translation_error(None)
        return direct

    messages = [
        {"role": "system", "content": COMMAND_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    debug("command_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        command = (response.message.content or "").strip()
        debug("command_translation_response", command)

        if command.lower().startswith("command:"):
            command = command.split(":", 1)[1].strip()

        if "\n" in command:
            command = command.splitlines()[0].strip()

        if command.upper() == "NONE":
            debug(
                "command_translation_none",
                {"instruction": instruction, "reason": "model_returned_NONE"},
            )
            _set_last_command_translation_error(
                "model explicitly replied with NONE (no safe command)"
            )
            return None

        sanitized = sanitize_command(command)
        if sanitized:
            debug("command_translation_sanitized", sanitized)
            _set_last_command_translation_error(None)
            return sanitized

        sanitize_reason = get_last_sanitize_error() or ""
        if "No closing quotation" in sanitize_reason:
            fixed = _maybe_fix_unclosed_quotes(command)
            if fixed and fixed != command:
                fixed_sanitized = sanitize_command(fixed)
                if fixed_sanitized:
                    debug("command_translation_quote_fix", fixed_sanitized)
                    _set_last_command_translation_error(None)
                    return fixed_sanitized

        segments = re.split(r"[;&|]", command, maxsplit=1)
        leading = segments[0].strip() if segments else ""
        if leading and leading != command:
            fallback = sanitize_command(leading)
            if fallback:
                debug(
                    "command_translation_sanitized_fallback",
                    {
                        "instruction": instruction,
                        "raw_command": command,
                        "fallback_command": fallback,
                    },
                )
                _set_last_command_translation_error(
                    "original suggestion looked unsafe; using only the leading simple command segment"
                )
                return fallback

        sanitize_reason = (
            get_last_sanitize_error()
            or "sanitize_command rejected the suggested command as unsafe"
        )
        debug(
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

    debug("query_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        query = (response.message.content or "").strip()
        debug("query_translation_response", query)

        if "\n" in query:
            query = query.splitlines()[0].strip()

        if query.upper() == "NONE":
            return None

        # Strip surrounding quotes to avoid web search issues
        if (query.startswith('"') and query.endswith('"')) or (
            query.startswith("'") and query.endswith("'")
        ):
            query = query[1:-1]

        return query
    except Exception as err:
        logger.error(f"Unable to translate instruction to web query: {err}")
        return None


def get_recent_history(limit: int = 15) -> List[Dict[str, Any]]:
    user_id = _get_or_create_user_id()
    history = user_histories.get(user_id, [])
    debug("history_snapshot", {"user_id": user_id, "limit": limit, "history": history})
    if limit <= 0:
        return history
    return history[-limit:]


def get_recent_events(limit: int = 20) -> List[Dict[str, Any]]:
    debug("event_log_snapshot", {"limit": limit, "events": list(_event_log)})
    if limit <= 0:
        return list(_event_log)
    return list(_event_log)[-limit:]


def _record_event(
    kind: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> None:
    entry: Dict[str, Any] = {
        "time": datetime.now(UTC).strftime("%H:%M:%S"),
        "kind": kind,
        "message": _truncate_event_text(message),
    }

    if extra:
        entry["extra"] = {
            key: _truncate_event_text(str(value)) for key, value in extra.items()
        }

    if user_id:
        entry["user_id"] = user_id

    _event_log.append(entry)
    if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES:
        extra_txt = (
            " " + " ".join(f"{k}={v}" for k, v in entry.get("extra", {}).items())
            if entry.get("extra")
            else ""
        )
        user_info = f" (user: {user_id})" if user_id else ""
        logger.info(
            f"[event] {entry['time']} {kind}: {entry['message']}{extra_txt}{user_info}"
        )


def _truncate_event_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_EVENT_TEXT:
        return text
    return text[: MAX_EVENT_TEXT - 3] + "..."


def _stringify_data(data: Any) -> str:
    try:
        return json.dumps(data, sort_keys=True)
    except (TypeError, ValueError):
        return str(data)


def clear_history():
    user_id = _get_or_create_user_id()
    user_histories.pop(user_id, None)
    if hasattr(_thread_local, "last_tool_audio"):
        delattr(_thread_local, "last_tool_audio")


def _set_last_tool_audio(payload: Dict[str, str]) -> None:
    _thread_local.last_tool_audio = payload


def pop_last_tool_audio() -> Optional[Dict[str, str]]:
    payload = getattr(_thread_local, "last_tool_audio", None)
    if hasattr(_thread_local, "last_tool_audio"):
        delattr(_thread_local, "last_tool_audio")
    return payload
