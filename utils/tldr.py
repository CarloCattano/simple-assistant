"""
Unified TLDR (summary) extraction, formatting, and sending utilities for tools and handlers.
"""

from typing import Any, Callable, Optional

from handlers.messages import escape_markdown_v2, send_markdown_message

# --- TLDR Extraction ---


def extract_tldr_from_tool_result(result: Any) -> Optional[str]:
    """
    Extract TLDR summary from a tool result.
    Supports both (main_result, tldr) tuples and TLDR markers in text.
    """
    if isinstance(result, tuple) and len(result) == 2:
        _, tldr = result
        return tldr
    if isinstance(result, str):
        # Heuristic: look for TLDR marker in text
        marker = "TLDR:"
        idx = result.find(marker)
        if idx != -1:
            # Return everything after the marker
            return result[idx + len(marker) :].strip()
    return None


# --- TLDR Formatting ---


def format_tldr_text(
    tldr: str, tool_name: Optional[str] = None, markdown: bool = True
) -> str:
    """
    Format a TLDR summary for display.
    """
    if not tldr:
        return ""
    if markdown:
        if tool_name:
            return f"*{escape_markdown_v2(tool_name)} TLDR:*\n{tldr}"
        return f"*TLDR:*\n{tldr}"
    else:
        if tool_name:
            return f"{tool_name} TLDR:\n{tldr}"
        return f"TLDR:\n{tldr}"


# --- TLDR Sending ---


async def send_tldr(
    target,
    tldr: str,
    tool_name: Optional[str] = None,
    markdown: bool = True,
    escape: bool = False,
    send_func: Optional[Callable] = None,
):
    """
    Send a TLDR summary as a separate message.
    """
    if not tldr:
        return None
    text = format_tldr_text(tldr, tool_name, markdown=markdown)
    if send_func:
        return await send_func(target, text, escape=escape)
    # Default to send_markdown_message
    return await send_markdown_message(target, text, escape=escape)


# --- TLDR Audio Caption ---


def build_tldr_caption(summary: str, tool_name: Optional[str] = None) -> str:
    """
    Build a caption for TLDR audio messages.
    """
    if summary and tool_name:
        return f"{tool_name} TLDR: {summary}"
    if summary:
        return f"TLDR: {summary}"
    return "TLDR"


# --- Example Usage ---
# In a handler:
# from utils.tldr import extract_tldr_from_tool_result, send_tldr
# result = await run_tool_direct_async("web_search", parameters)
# tldr = extract_tldr_from_tool_result(result)
# if tldr:
#     await send_tldr(update.message, tldr, tool_name="Web Search")
