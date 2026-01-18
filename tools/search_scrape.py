from httpx import Client, RequestError
from parsel import Selector

MAX_TEXT_CHARS = 2000
MAX_LINKS = 20
MAX_SNIPPET_LEN = 200

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


def search_and_scrape(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        response = client.get(url)
    except RequestError as err:
        return f"Error: HTTP error while fetching {url}: {err}"

    if response.status_code != 200:
        return f"Error: Received status code {response.status_code} for {url}"

    sel = Selector(text=response.text)

    title = sel.xpath("//title/text()").get(default="(No title)")

    meta_tags = {}
    for tag in sel.xpath("//meta"):
        name = tag.xpath(".//@name").get()
        prop = tag.xpath(".//@property").get()
        content = tag.xpath(".//@content").get()

        key = name or prop
        if key and content:
            meta_tags[key] = content

    body_text_parts = sel.xpath("//body//text()").getall()
    snippets = []
    total_len = 0
    for t in body_text_parts:
        stripped = t.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_SNIPPET_LEN:
            stripped = stripped[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0] + "…"
        snippets.append(stripped)
        total_len += len(stripped)
        if total_len >= MAX_TEXT_CHARS:
            break
    body_text = " \n".join(snippets)

    links = []
    for link in sel.xpath("//a/@href").getall():
        if len(link) <= 80:
            links.append(link)
        if len(links) >= MAX_LINKS:
            break

    title = title.strip()
    body_text = body_text.strip()
    urls = [link.strip() for link in links if link.strip()]

    output = str(title) + "\n" + str(body_text) + "\n\n" + "\n".join(urls)

    return output


tool = {
    'name': 'search_and_scrape',
    'function': search_and_scrape,
    'triggers': ['scrape', 'get', 'scraper'],
    'description': 'Scrape a given URL and return title, body text and links.',
    'parameters': {
        'url': {'type': 'string', 'description': 'The URL to scrape'},
    },
}
