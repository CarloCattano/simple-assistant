from urllib.parse import quote
from httpx import Client
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
)


def web_search(query):
    print(f"Performing web search for query: {query}")
    logger.info(f"Performing web search for query: {query}")
    base_url = "https://html.duckduckgo.com/html/?q="
    response = client.get(f"{base_url}{quote(query)}")

    if response.status_code != 200:
        return f"Error: Received status code {response.status_code} for {base_url}"

    selector = Selector(text=response.text)
    _remove_kl_dropdown(selector)

    snippets = _extract_snippets(selector)
    links = _extract_links(selector)

    summary = _truncate_text(" ".join(snippets).strip())
    output = [summary]

    if links:
        output.append("\nLinks:")
        output.extend(links[:MAX_LINKS])

    return "\n".join(output).strip()


tool = {
    'name': 'web_search',
    'function': web_search,
    'triggers': ['search', 'online', 'web search', 'web'],
    'description': 'Perform a web search and return textual results and links.',
    'parameters': {
        'query': {'type': 'string', 'description': 'Search query string'},
    },
}


def _remove_kl_dropdown(selector: Selector) -> None:
    for select_node in selector.xpath('//select[@name="kl"]'):
        parent = select_node.root.getparent()
        if parent is not None:
            parent.remove(select_node.root)


def _extract_snippets(selector: Selector) -> list[str]:
    snippets: list[str] = []
    for part in selector.xpath("//body//text()").getall():
        stripped = part.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_SNIPPET_LEN:
            stripped = stripped[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0] + "…"
        snippets.append(stripped.replace(".0000000", "\n --- \n"))
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
    return clean_links


def _clean_link(link: str) -> str:
    stripped = link.strip()
    if not stripped or stripped.endswith("/html/"):
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
