from typing import Any, Dict, Iterable, Optional, Tuple

from telegram.ext import ContextTypes

try:  # Optional import for type hints only
    from telegram import Message  # type: ignore
except ImportError:  # pragma: no cover - telegram only required at runtime
    Message = Any  # type: ignore


def get_prompt_history(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, str]:
    """Return (and initialize if needed) the per-user prompt history map.

    Stored under context.user_data["prompt_history"], keyed by Telegram
    message_id, with the original prompt text as the value.
    """

    return context.user_data.setdefault("prompt_history", {})  # type: ignore[return-value]


def get_output_metadata(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, Dict[str, Any]]:
    """Return (and initialize if needed) the per-user output metadata map.

    Stored under context.user_data["output_metadata"], keyed by Telegram
    message_id, with a small metadata dict describing how that message
    was produced (tool name, parameters, originating prompt, etc.).
    """

    return context.user_data.setdefault("output_metadata", {})  # type: ignore[return-value]


def remember_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    message: Optional[Message],
    prompt: str,
) -> None:
    """Associate a prompt with the given Telegram message in user_data.

    Safe no-op when the message is missing or does not expose message_id.
    """

    if not message or not getattr(message, "message_id", None):
        return

    prompt_history = get_prompt_history(context)
    prompt_history[message.message_id] = prompt


def remember_generated_output(
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    messages: Iterable[Optional[Message]],
    tool_info: Optional[Dict[str, Any]] = None,
) -> None:
    """Record prompt and optional tool metadata for each generated message.

    This mirrors the previous _remember_generated_prompt implementation in
    handlers.messages and centralizes how prompt_history and
    output_metadata are maintained.
    """

    if not messages:
        return

    prompt_history = get_prompt_history(context)
    output_metadata = get_output_metadata(context)

    for msg in messages:
        if not msg or not getattr(msg, "message_id", None):
            continue

        prompt_history[msg.message_id] = prompt
        if tool_info:
            output_metadata[msg.message_id] = {
                "prompt": prompt,
                "tool_name": tool_info.get("tool_name"),
                "parameters": tool_info.get("parameters"),
            }
        else:
            output_metadata.pop(msg.message_id, None)


def lookup_reply_context(
    context: ContextTypes.DEFAULT_TYPE,
    reply_message: Optional[Message],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return (original_prompt, tool_metadata) for a reply target, if any.

    Looks up prompt_history and output_metadata using reply_message.message_id
    and falls back to reply_message.text for the original prompt when no
    explicit history entry exists.
    """

    if not reply_message or not getattr(reply_message, "message_id", None):
        return None, None

    prompt_history = get_prompt_history(context)
    output_metadata = get_output_metadata(context)

    original_prompt: Optional[str] = prompt_history.get(reply_message.message_id)
    if not original_prompt and getattr(reply_message, "text", None):
        original_prompt = reply_message.text.strip() or None

    tool_metadata = None
    try:
        tool_metadata = output_metadata.get(reply_message.message_id)
    except Exception:
        tool_metadata = None

    return original_prompt, tool_metadata
