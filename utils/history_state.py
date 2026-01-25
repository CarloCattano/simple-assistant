from typing import Any, Dict, Iterable, Optional, Tuple, List

from telegram.ext import ContextTypes


from config import DEBUG_HISTORY_STATE
from utils.logger import logger

try:  # Optional import for type hints only
    from telegram import Message  # type: ignore
except ImportError:  # pragma: no cover - telegram only required at runtime
    Message = Any  # type: ignore



# Deprecated: In-memory prompt history is replaced by persistent DB storage.
def get_prompt_history(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, str]:
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
    message: Any,
    prompt: str,
) -> None:
    """Persist prompt to DB for the given Telegram message."""
    if not message or not getattr(message, "message_id", None):
        return
    prompt_history = get_prompt_history(context)
    prompt_history[message.message_id] = prompt



def remember_generated_output(
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    messages: Iterable[Any],
    tool_info: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist assistant outputs to DB for each generated message."""
    if not messages:
        if DEBUG_HISTORY_STATE:
            logger.debug("[history_state] remember_generated_output: no messages to record for prompt=%r tool_info=%r", prompt, tool_info)
        return
    prompt_history = get_prompt_history(context)
    output_metadata = get_output_metadata(context)
    for msg in messages:
        msg_id = getattr(msg, "message_id", None)
        if not msg or not msg_id:
            if DEBUG_HISTORY_STATE:
                logger.debug("[history_state] remember_generated_output: skipping message with no message_id: %r", msg)
            continue
        if DEBUG_HISTORY_STATE:
            logger.debug("[history_state] remember_generated_output: recording message_id=%r prompt=%r tool_info=%r", msg_id, prompt, tool_info)
        prompt_history[msg_id] = prompt
        if tool_info:
            output_metadata[msg_id] = {
                "prompt": prompt,
                "tool_name": tool_info.get("tool_name"),
                "parameters": tool_info.get("parameters"),
            }
        else:
            output_metadata.pop(msg_id, None)



def lookup_reply_context(
    context: ContextTypes.DEFAULT_TYPE,
    reply_message: Any,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return (original_prompt, tool_metadata) for a reply target, if any, using persistent DB history."""
    if not reply_message or not getattr(reply_message, "message_id", None):
        return None, None
    prompt_history = get_prompt_history(context)
    output_metadata = get_output_metadata(context)

    tool_metadata = None
    msg_id = getattr(reply_message, "message_id", None)
    try:
        tool_metadata = output_metadata.get(msg_id)
    except Exception:
        tool_metadata = None

    # Prefer the originating prompt from tool_metadata if available
    original_prompt: Optional[str] = None
    if tool_metadata and isinstance(tool_metadata.get("prompt"), str):
        original_prompt = tool_metadata["prompt"].strip()
    elif prompt_history.get(msg_id):
        original_prompt = prompt_history[msg_id]
    elif getattr(reply_message, "text", None):
        original_prompt = reply_message.text.strip() or None

    if DEBUG_HISTORY_STATE:
        logger.debug(
            "[history_state] lookup_reply_context: msg_id=%r original_prompt=%r tool_metadata=%r", msg_id, original_prompt, tool_metadata
        )
    return original_prompt, tool_metadata
