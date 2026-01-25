import asyncio
from posixpath import pardir
from typing import List, Tuple
from urllib.parse import quote

import httpx
from httpx import RequestError
from parsel import Selector

from utils.logger import logger

MAX_TEXT_CHARS = 1500
MAX_LINKS = 12
MAX_SNIPPET_LEN = 160
MAX_LINK_LEN = 280

CLIENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
CLIENT_TIMEOUT = 5.0


def web_search(query: str) -> str:
    """
    Legacy sync wrapper for backward compatibility.
    """
    return asyncio.run(web_search_async(query))


async def web_search_async(query: str) -> str:
    query = (query or "").strip()
    if not query:
        return "Please provide a non-empty search query."

    logger.debug(f"Performing web search for query: {query}")

    # Run both DuckDuckGo and Lite in parallel, use the first with results
    results = await asyncio.gather(
        _search_duckduckgo_async(query), _search_duckduckgo_lite_async(query)
    )
    # Prefer the first with results
    for pairs in results:
        if pairs:
            # Filter out irrelevant results
            relevant_pairs = [p for p in pairs if _is_relevant(p[0], p[1], query)]
            return _format_search_result(relevant_pairs)
    return _format_search_result([])


tool = {
    "name": "web_search",
    "function": web_search,
    "triggers": ["search", "online", "web search", "web"],
    "description": "Perform a web search and return textual results and links.",
    "parameters": {
        "query": {"type": "string", "description": "Search query string"},
    },
}


async def _search_duckduckgo_async(query: str) -> List[Tuple[str, str]]:
    base_url = "https://html.duckduckgo.com/html/?q="
    url = f"{base_url}{quote(query)}"
    async with httpx.AsyncClient(
        headers=CLIENT_HEADERS,
        follow_redirects=True,
        http2=True,
        timeout=CLIENT_TIMEOUT,
    ) as client:
        try:
            response = await client.get(url)
        except RequestError as err:
            logger.error(f"HTTP error contacting DuckDuckGo: {err}")
            return []

    if response.status_code != 200:
        logger.warning(
            f"DuckDuckGo returned status {response.status_code} for {query!r}"
        )
        return []

    selector = Selector(response.text)
    # ... rest of parsing logic ...
    _remove_kl_dropdown(selector)

    pairs = _extract_snippet_link_pairs(selector)
    return pairs


def _remove_kl_dropdown(selector: Selector) -> None:
    for select_node in selector.xpath('//select[@name="kl"]'):
        parent = select_node.root.getparent()
        if parent is not None:
            parent.remove(select_node.root)


def _extract_snippet_link_pairs(selector: Selector) -> list[tuple[str, str]]:
    # DuckDuckGo HTML: .result, Lite: .result
    pairs = []
    for node in selector.css(".result"):
        snippet = (
            node.css(".result__snippet, .result-snippet")
            .xpath("string()")
            .get(default="")
            .strip()
        )
        link = ""
        link_node = node.css(".result__a, .result-link")
        if link_node:
            href = link_node.attrib.get("href", "").strip()
            link = _clean_link(href)
        if snippet and link:
            pairs.append((snippet, link))
        elif snippet:
            pairs.append((snippet, ""))
        elif link:
            pairs.append(("", link))
        if len(pairs) >= MAX_LINKS:
            break
    return pairs


def _clean_link(link: str) -> str:
    stripped = link.strip()
    if not stripped or stripped.endswith("/html/"):
        return ""

    if stripped.startswith("/html/?") or stripped.startswith("html/?"):
        return ""

    # Remove URL params
    if "?" in stripped:
        stripped = stripped.split("?", 1)[0]

    # Remove fragments
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0]

    # Remove protocol
    stripped = stripped.replace("https://", "").replace("http://", "")
    stripped = stripped.replace("//", "")

    if stripped.startswith("www."):
        stripped = stripped[4:]

    # Skip .js links
    if stripped.lower().endswith(".js"):
        return ""

    return stripped


def _is_relevant(snippet: str, link: str, query: str) -> bool:
    keywords = query.lower().split()
    text = (snippet + " " + link).lower()
    return any(kw in text for kw in keywords)


def _format_search_result(pairs: list[tuple[str, str]]) -> str:
    parts: List[str] = []
    for snippet, link in pairs:
        snippet = snippet.strip()
        link = link.strip()
        if snippet:
            parts.append(snippet)
        if link:
            parts.append(f"- {link}")
        if snippet or link:
            parts.append("")  # blank line between pairs
    return "\n".join(parts).strip() or "No results found."


async def _search_duckduckgo_lite_async(query: str) -> List[Tuple[str, str]]:
    base_url = "https://lite.duckduckgo.com/lite/?q="
    url = f"{base_url}{quote(query)}"
    async with httpx.AsyncClient(
        headers=CLIENT_HEADERS,
        follow_redirects=True,
        http2=True,
        timeout=CLIENT_TIMEOUT,
    ) as client:
        try:
            response = await client.get(url)
        except RequestError as err:
            logger.error(f"HTTP error contacting DuckDuckGo lite: {err}")
            return []

    if response.status_code != 200:
        logger.warning(
            f"DuckDuckGo lite returned status {response.status_code} for {query!r}"
        )
        return []

    selector = Selector(response.text)
    pairs = _extract_snippet_link_pairs(selector)
    return pairs
