from typing import List, Tuple
from urllib.parse import quote

from httpx import Client, RequestError
from parsel import Selector
from utils.logger import logger

MAX_TEXT_CHARS = 1500
MAX_LINKS = 12
MAX_SNIPPET_LEN = 160
MAX_LINK_LEN = 280

client = Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    follow_redirects=True,
    http2=True,
    timeout=5.0,
)

def web_search(query: str) -> str:
    query = (query or "").strip()
    if not query:
        return "Please provide a non-empty search query."

    logger.debug(f"Performing web search for query: {query}")

    # Primary provider: DuckDuckGo HTML
    try:
        summary, links = _search_duckduckgo(query)
        if summary or links:
            return _format_search_result(summary, links)
    except Exception as err:
        logger.error(f"DuckDuckGo search failed for {query!r}: {err}")

    # Fallback provider: DuckDuckGo lite HTML endpoint (no API key needed).
    try:
        summary, links = _search_duckduckgo_lite(query)
        if summary or links:
            return _format_search_result(summary, links)
    except Exception as err:
        logger.error(f"DuckDuckGo lite search failed for {query!r}: {err}")

    return "I couldn't retrieve search results at the moment. Please try again later."


tool = {
    'name': 'web_search',
    'function': web_search,
    'triggers': ['search', 'online', 'web search', 'web'],
    'description': 'Perform a web search and return textual results and links.',
    'parameters': {
        'query': {'type': 'string', 'description': 'Search query string'},
    },
}


def _search_duckduckgo(query: str) -> Tuple[str, List[str]]:
    base_url = "https://html.duckduckgo.com/html/?q="
    url = f"{base_url}{quote(query)}"
    try:
        response = client.get(url)
    except RequestError as err:
        logger.error(f"HTTP error contacting DuckDuckGo: {err}")
        return "", []

    if response.status_code != 200:
        logger.warning(
            f"DuckDuckGo returned status {response.status_code} for {url}"
        )
        return "", []

    selector = Selector(text=response.text)
    _remove_kl_dropdown(selector)

    snippets = _extract_snippets(selector)
    links = _extract_links(selector)

    summary = _truncate_text(" ".join(snippets).strip()) if snippets else ""
    return summary, links


def _remove_kl_dropdown(selector: Selector) -> None:
    for select_node in selector.xpath('//select[@name="kl"]'):
        parent = select_node.root.getparent()
        if parent is not None:
            parent.remove(select_node.root)


def _extract_snippets(selector: Selector) -> list[str]:
    snippets: list[str] = []
    total_len = 0
    for part in selector.xpath("//body//text()").getall():
        stripped = part.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_SNIPPET_LEN:
            stripped = stripped[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0] + "…"
        snippets.append(stripped.replace(".0000000", "\n --- \n"))
        total_len += len(stripped)
        if total_len >= MAX_TEXT_CHARS:
            break
    return snippets


def _extract_links(selector: Selector) -> list[str]:
    clean_links: list[str] = []
    seen = set()
    for link in selector.xpath("//a/@href").getall():
        if len(link) > MAX_LINK_LEN:
            continue
        cleaned = _clean_link(link)
        if cleaned and cleaned not in seen:
            clean_links.append(cleaned)
            seen.add(cleaned)
            if len(clean_links) >= MAX_LINKS * 2:
                break
    return clean_links


def _clean_link(link: str) -> str:
    stripped = link.strip()
    if not stripped or stripped.endswith("/html/"):
        return ""

    if stripped.startswith("/html/?") or stripped.startswith("html/?"):
        return ""

    stripped = stripped.replace("https://", "").replace("http://", "")
    stripped = stripped.replace("//", "")

    if stripped.startswith("www."):
        stripped = stripped[4:]

    return stripped


def _truncate_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return f"{truncated}\n\n[Output truncated]"


def _format_search_result(summary: str, links: List[str]) -> str:
    parts: List[str] = []
    summary = (summary or "").strip()
    if summary:
        parts.append(summary)

    if links:
        if parts:
            parts.append("")  # blank line before links section
        parts.append("**Links:**")
        for link in links[:MAX_LINKS]:
            parts.append(f"- {link}")

    return "\n".join(parts).strip() or "No results found."


def _search_duckduckgo_lite(query: str) -> Tuple[str, List[str]]:
    base_url = "https://lite.duckduckgo.com/lite/?q="
    url = f"{base_url}{quote(query)}"
    try:
        response = client.get(url)
    except RequestError as err:
        logger.error(f"HTTP error contacting DuckDuckGo lite: {err}")
        return "", []

    if response.status_code != 200:
        logger.warning(
            f"DuckDuckGo lite returned status {response.status_code} for {url}"
        )
        return "", []

    selector = Selector(text=response.text)
    snippets = _extract_snippets(selector)
    links = _extract_links(selector)

    summary = _truncate_text(" ".join(snippets).strip()) if snippets else ""
    return summary, links
