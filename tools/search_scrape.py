from urllib.parse import quote
from httpx import Client
from parsel import Selector

client = Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    follow_redirects=True,
    http2=True,
)

def search_and_scrape(url):
    response = client.get(url)

    if response.status_code != 200:
        return f"Error: Received status code {response.status_code} for {url}"

    sel = Selector(text=response.text)

    title = sel.xpath('//title/text()').get(default="(No title)")

    meta_tags = {}
    for tag in sel.xpath('//meta'):
        name = tag.xpath('.//@name').get()
        prop = tag.xpath('.//@property').get()
        content = tag.xpath('.//@content').get()

        key = name or prop
        if key and content:
            meta_tags[key] = content

    body_text_parts = sel.xpath('//body//text()').getall()
    body_text = ' \n'.join(t.strip() for t in body_text_parts if t.strip())

    links = []
    for link in sel.xpath('//a/@href').getall():
        if len(link) <= 80:
            links.append(link)

    title = title.strip()
    body_text = body_text.strip()
    urls = [link.strip() for link in links if link.strip()]

    output = str(title) + "\n" + str(body_text) + "\n\n" + "\n".join(urls)

    return output


tool = {
    'function': search_and_scrape,
    'triggers': ['scrape', 'get']
}

