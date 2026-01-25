import json
import os
import re
import threading
import uuid
from collections import deque
from datetime import datetime
from logging import DEBUG, Logger
from typing import Any, Dict, List, Optional, Tuple

from ollama import chat as _ollama_chat

from config import (
    DEBUG_HISTORY_STATE,
    DEBUG_OLLAMA,
    DEBUG_TOOL_DIRECTIVES,
    SYSTEM_PROMPT,
)
from services.ollama_shared import (
    MAX_HISTORY_LENGTH,
    MODEL_NAME,
)
from utils.logger import GREEN, RST, debug_payload, logger

# Event logging functions
EVENT_LOG_LIMIT = 200
MAX_EVENT_TEXT = 400

if hasattr(_ollama_chat, "chat"):
    chat = _ollama_chat
else:
    chat = _ollama_chat

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

# MODEL_NAME, MAX_HISTORY_LENGTH and MAX_TOOL_OUTPUT_IN_HISTORY are
# managed in services.ollama_shared

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
_debug = (
    lambda *args, **kwargs: debug_payload(*args, **kwargs)
    if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES
    else None
)


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


def generate_simple_response(prompt: str) -> str:
    """Generate a simple response without history or tools."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
    return response.message.content or ""


def _get_or_create_user_id() -> str:
    if not hasattr(_thread_local, "user_id"):
        _thread_local.user_id = str(uuid.uuid4())
    return _thread_local.user_id


def _ensure_system_prompt(history: List[Dict[str, str]]) -> None:
    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


def _trim_history(history: List[Dict[str, str]]) -> None:
    total_length = sum(len(entry.get("content", "")) for entry in history)
    while total_length > MAX_HISTORY_LENGTH and len(history) > 1:
        removed = history.pop(1)  # Keep system prompt
        total_length -= len(removed.get("content", ""))


def generate_content(prompt: str) -> str | tuple[str, str | None]:
    from services.ollama_tools import (
        available_functions,
        call_tool_with_tldr,
        evaluate_tool_usage,
    )

    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])

    _ensure_system_prompt(history)

    # Add user message
    history.append({"role": "user", "content": prompt})
    _trim_history(history)
    _record_event("user", prompt, user_id=user_id)
    if DEBUG_HISTORY_STATE:
        _debug(
            "history_after_user",
            {
                "user_id": user_id,
                "entries": _redact_system_content_in_messages(history),
            },
        )

    try:
        use_tools, matched_tools = evaluate_tool_usage(prompt)
        _debug(
            "tool_evaluation",
            {
                "prompt": prompt,
                "use_tools": use_tools,
                "matched_tools": list(matched_tools.keys()),
            },
        )
        messages = history

        _debug(
            "chat_request",
            {
                "messages": _redact_system_content_in_messages(messages),
                "tools": list(available_functions.keys()),
            },
        )

        tool_pool = matched_tools if matched_tools else available_functions
        tool_defs = (
            [
                {
                    "type": "function",
                    "function": {
                        "name": entry["name"],
                        "description": entry.get("description", ""),
                        "parameters": entry.get("parameters", {}),
                    },
                }
                for entry in tool_pool.values()
            ]
            if use_tools
            else []
        )

        response = chat(
            model=MODEL_NAME,
            messages=messages,
            keep_alive=0,
            tools=tool_defs,
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
            _debug("chat_response", log_payload)

        if response.message.tool_calls:
            assistant_message = {
                "role": "assistant",
                "content": response.message.content or "",
                "tool_calls": [
                    call.model_dump() if hasattr(call, "model_dump") else call
                    for call in response.message.tool_calls
                ],
            }
            history.append(assistant_message)
            _debug(
                "tool_calls",
                [call.function.name for call in response.message.tool_calls],
            )
            for tool in response.message.tool_calls:
                func_entry = available_functions.get(tool.function.name)
                if func_entry and (
                    not matched_tools or tool.function.name in matched_tools
                ):
                    _debug(
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
        # Try to parse tool call from content
        tool_call_in_text = re.search(
            r'"name":\s*"(\w+)",\s*"parameters":\s*({.*?})', reply, re.DOTALL
        )
        if tool_call_in_text:
            tool_name = tool_call_in_text.group(1)
            parameters_str = tool_call_in_text.group(2)
            try:
                parameters = json.loads(parameters_str)
            except Exception as e:
                _debug(
                    "json_load_failed",
                    {"error": str(e), "parameters_str": parameters_str},
                )
                parameters = {}
            from services.ollama_tools import run_tool_direct

            tool_output = run_tool_direct(tool_name, parameters)
            if tool_output is not None:
                # Add the tool output to history as assistant message
                history.append({"role": "assistant", "content": str(tool_output)})
                _record_event("assistant", str(tool_output))
                _debug(
                    "assistant_reply_from_tool",
                    {
                        "user_id": user_id,
                        "tool_output": tool_output,
                        "history_size": len(history),
                    },
                )
                return str(tool_output)
            else:
                error_msg = f"Tool {tool_name} execution failed."
                history.append({"role": "assistant", "content": error_msg})
                _record_event("assistant", error_msg)
                return error_msg
        history.append({"role": "assistant", "content": reply})
        _record_event("assistant", reply)
        _debug(
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


_event_log: deque[Dict[str, Any]] = deque(maxlen=EVENT_LOG_LIMIT)


def _record_event(
    kind: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> None:
    event = {
        "timestamp": datetime.now().isoformat(),
        "kind": kind,
        "message": _truncate_event_text(message),
        "user_id": user_id,
    }
    if extra:
        event["extra"] = extra
    _event_log.append(event)


def _truncate_event_text(text: str) -> str:
    if len(text) > MAX_EVENT_TEXT:
        return text[:MAX_EVENT_TEXT] + "..."
    return text


def get_recent_events(limit: int = 20) -> List[Dict[str, Any]]:
    return list(_event_log)[-limit:]


def get_recent_history(limit: int = 15) -> List[Dict[str, Any]]:
    user_id = _get_or_create_user_id()
    history = user_histories.get(user_id, [])
    return history[-limit:]


def clear_history() -> None:
    user_id = _get_or_create_user_id()
    if user_id in user_histories:
        del user_histories[user_id]
