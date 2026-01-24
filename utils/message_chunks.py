"""
Utilities for chunking and splitting messages for Telegram, preserving code blocks and Markdown structure.
"""

import asyncio
import re
from typing import Any, Callable, List, Optional, Tuple


def split_preserve_code_blocks(s: str) -> List[Tuple[str, str]]:
    """
    Splits a string into ("text", ...) and ("code", ...) chunks, preserving code blocks.
    Returns a list of (kind, content) tuples.
    """
    parts = []
    last = 0
    for m in re.finditer(r"```(?:\w+)?\n.*?\n```", s, re.DOTALL):
        if m.start() > last:
            parts.append(("text", s[last : m.start()]))
        parts.append(("code", m.group(0)))
        last = m.end()
    if last < len(s):
        parts.append(("text", s[last:]))
    return parts


def split_paragraphs(text: str) -> List[str]:
    """
    Splits text into paragraphs, preserving Markdown structure where possible.
    """
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_by_chunk_size(text: str, chunk_size: int) -> List[str]:
    """
    Splits a string into chunks of at most chunk_size characters.
    """
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


async def send_code_block_chunked(
    target: Any,
    body: str,
    language: str = "bash",
    chunk_size: int = 4096,
    safe_reply_text: Optional[Callable] = None,
) -> List[Any]:
    """
    Sends a code block in chunks, ensuring balanced fences.
    """
    messages = []
    code = body.strip()
    code_lines = code.splitlines()
    current = []
    current_len = 0
    for line in code_lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > chunk_size - 10:  # Reserve for fences/lang
            chunk = "\n".join(current)
            msg = f"```{language}\n{chunk}\n```"
            if safe_reply_text:
                messages.append(await safe_reply_text(target, msg, "Markdown"))
            else:
                messages.append(
                    await target.reply_text(text=msg, parse_mode="Markdown")
                )
            await asyncio.sleep(1)
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunk = "\n".join(current)
        msg = f"```{language}\n{chunk}\n```"
        if safe_reply_text:
            messages.append(await safe_reply_text(target, msg, "Markdown"))
        else:
            messages.append(await target.reply_text(text=msg, parse_mode="Markdown"))
        await asyncio.sleep(1)
    return messages


async def send_chunked_message(
    target: Any,
    text: str,
    parse_mode: Optional[str] = "Markdown",
    chunk_size: int = 4096,
    safe_reply_text: Optional[Callable] = None,
    strip_markdown_escape: Optional[Callable] = None,
) -> List[Any]:
    """
    Sends a long message in chunks, preserving code blocks and Markdown structure.
    """
    messages = []

    if len(text) <= chunk_size:
        if safe_reply_text:
            messages.append(await safe_reply_text(target, text, parse_mode))
        else:
            messages.append(await target.reply_text(text=text, parse_mode=parse_mode))
        return messages

    parts = split_preserve_code_blocks(text)

    for kind, content in parts:
        if kind == "code":
            # Extract language if specified
            m = re.match(r"```(\w+)?\n(.*)\n```", content, re.DOTALL)
            if m:
                lang = m.group(1) or ""
                body = m.group(2)
            else:
                lang = ""
                body = content.strip("`")
            sent = await send_code_block_chunked(
                target,
                body,
                language=(lang or "bash"),
                chunk_size=chunk_size,
                safe_reply_text=safe_reply_text,
            )
            messages.extend(sent)
        else:
            paragraphs = split_paragraphs(content)
            current = ""
            for para in paragraphs:
                candidate = current + "\n\n" + para if current else para
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        if safe_reply_text:
                            messages.append(
                                await safe_reply_text(target, current, parse_mode)
                            )
                        else:
                            messages.append(
                                await target.reply_text(
                                    text=current, parse_mode=parse_mode
                                )
                            )
                        await asyncio.sleep(1)
                    # If single paragraph exceeds chunk_size, fallback to raw splits without parse mode to avoid malformed entities
                    if len(para) > chunk_size:
                        for segment in split_by_chunk_size(para, chunk_size):
                            cleaned = (
                                strip_markdown_escape(segment)
                                if parse_mode and strip_markdown_escape
                                else segment
                            )
                            messages.append(
                                await target.reply_text(
                                    text=cleaned,
                                    parse_mode=None if parse_mode else None,
                                )
                            )
                            await asyncio.sleep(1)
                        current = ""
                    else:
                        current = para
            if current:
                if safe_reply_text:
                    messages.append(await safe_reply_text(target, current, parse_mode))
                else:
                    messages.append(
                        await target.reply_text(text=current, parse_mode=parse_mode)
                    )
                await asyncio.sleep(1)

    return messages
