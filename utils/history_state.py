from typing import Any, Dict, Optional, Tuple
from config import DEBUG_HISTORY_STATE
from utils.logger import logger

# NOTE: prompt_history and output_metadata were previously used for in-memory per-message prompt and tool tracking.
# The new architecture uses a centralized in-memory HistoryManager (services/history_manager.py) for all user history and events.
# These legacy structures are now only needed for reply context lookup in rare cases, and are not used for main conversation history or LLM context.

def get_output_metadata(context) -> Dict[int, Dict[str, Any]]:
    """Return (and initialize if needed) the per-user output metadata map.
    Stored under context.user_data["output_metadata"], keyed by Telegram message_id.
    """
    return context.user_data.setdefault("output_metadata", {})

def lookup_reply_context(
    context,
    reply_message: Any,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return (original_prompt, tool_metadata) for a reply target, if any, using persistent DB history."""
    if not reply_message or not getattr(reply_message, "message_id", None):
        return None, None
    output_metadata = get_output_metadata(context)
    tool_metadata = output_metadata.get(getattr(reply_message, "message_id", None))
    original_prompt = None
    if tool_metadata and isinstance(tool_metadata.get("prompt"), str):
        original_prompt = tool_metadata["prompt"].strip()
    elif getattr(reply_message, "text", None):
        original_prompt = reply_message.text.strip() or None
    if DEBUG_HISTORY_STATE:
        logger.debug(
            "[history_state] lookup_reply_context: msg_id=%r original_prompt=%r tool_metadata=%r",
            getattr(reply_message, "message_id", None), original_prompt, tool_metadata
        )
    return original_prompt, tool_metadata