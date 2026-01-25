import httpx
from httpx import RequestError
from parsel import Selector

MAX_TEXT_CHARS = 2000
MAX_LINKS = 20
MAX_SNIPPET_LEN = 200

CLIENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
CLIENT_TIMEOUT = 7.0


import asyncio


def _clean_link(link: str) -> str:
    stripped = link.strip()
    if not stripped or stripped.endswith("/html/"):
        return ""
    if stripped.startswith("/html/?") or stripped.startswith("html/?"):
        return ""
    # Remove URL params and fragments
    if "?" in stripped:
        stripped = stripped.split("?", 1)[0]
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0]
    stripped = stripped.replace("https://", "").replace("http://", "")
    stripped = stripped.replace("//", "")
    if stripped.startswith("www."):
        stripped = stripped[4:]
    # Skip .js and other unwanted extensions
    if stripped.lower().endswith(".js"):
        return ""
    return stripped


async def search_and_scrape(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    async with httpx.AsyncClient(
        headers=CLIENT_HEADERS,
        follow_redirects=True,
        http2=True,
        timeout=CLIENT_TIMEOUT,
    ) as client:
        try:
            response = await client.get(url)
        except RequestError as err:
            return f"Error: HTTP error while fetching {url}: {err}"

    if response.status_code != 200:
        return f"Error: Received status code {response.status_code} for {url}"

    sel = Selector(text=response.text)

    # Title
    title = sel.xpath("//title/text()").get(default="(No title)").strip()

    # Meta description (if available)
    meta_desc = (
        sel.xpath('//meta[@name="description"]/@content').get(default="").strip()
    )

    # Remove unwanted elements before extracting visible text
    for bad in sel.xpath("//script|//style|//nav|//footer|//aside|//noscript"):
        parent = bad.root.getparent()
        if parent is not None:
            parent.remove(bad.root)

    # Extract visible text from main, article, p, h1-h6, li
    text_blocks = []
    total_len = 0
    for node in sel.css("main, article, p, h1, h2, h3, h4, h5, h6, li"):
        txt = node.xpath("string()").get(default="").strip()
        if not txt:
            continue
        if len(txt) > MAX_SNIPPET_LEN:
            txt = txt[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0]
        if len(txt) < 20:
            continue  # skip very short/noisy lines
        text_blocks.append(txt)
        total_len += len(txt)
        if total_len >= MAX_TEXT_CHARS:
            break

    # Fallback: if nothing found, get all visible body text
    if not text_blocks:
        for t in sel.xpath("//body//text()").getall():
            stripped = t.strip()
            if not stripped or len(stripped) < 20:
                continue
            if len(stripped) > MAX_SNIPPET_LEN:
                stripped = stripped[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0]
            text_blocks.append(stripped)
            total_len += len(stripped)
            if total_len >= MAX_TEXT_CHARS:
                break

    # Extract and clean links
    links = []
    seen = set()
    for node in sel.xpath("//a[@href]"):
        href = node.xpath(".//@href").get(default="").strip()
        cleaned = _clean_link(href)
        if cleaned and cleaned not in seen and len(cleaned) <= 80:
            links.append(cleaned)
            seen.add(cleaned)
        if len(links) >= MAX_LINKS:
            break

    # Format output
    output_parts = []
    if title:
        output_parts.append(f"*Title:* {title}")
    if meta_desc:
        output_parts.append(f"*Description:* {meta_desc}")
    if text_blocks:
        output_parts.append("\n".join(text_blocks))
    if links:
        output_parts.append("\n*Links:*\n" + "\n".join(f"- {l}" for l in links))

    return "\n\n".join(output_parts)


tool = {
    "name": "search_and_scrape",
    "function": search_and_scrape,
    "triggers": ["scrape", "get", "scraper"],
    "description": "Scrape a given URL and return title, meta description, main content, and cleaned links.",
    "parameters": {
        "url": {"type": "string", "description": "The URL to scrape"},
    },
}
