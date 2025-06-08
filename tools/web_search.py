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

def web_search(query):
    url = f"https://html.duckduckgo.com/html/?q="
    query = quote(query)
    response = client.get(f"{url}{query}")

    if response.status_code != 200:
        return f"Error: Received status code {response.status_code} for {url}"

    sel = Selector(text=response.text)

     # Remove the entire <select name="kl"> element which contains the country/region options
    for select_node in sel.xpath('//select[@name="kl"]'):
        # Using .root to get lxml element and remove it from its parent
        parent = select_node.root.getparent()
        if parent is not None:
            parent.remove(select_node.root)

    # get all body contents    
    # body_text_parts = sel.xpath('//body//text()').getall()
    # body_text = ' '.join(t.strip() for t in body_text_parts if t.strip())

    body_text_parts = sel.xpath('//body//text()').getall()
    # for each text inside a tag separate by new line
    print(response.text)

    # print only class="result__snippet" 
    body_text = ' '.join(t.strip() for t in body_text_parts if t.strip() and 'result__snippet' or 'result__url' in t)


    links = []
    for link in sel.xpath('//a/@href').getall():
        if len(link) <= 80:
            links.append(link)

    body_text = body_text.strip()
    urls = [link.strip() for link in links if link.strip()]

    output = str(body_text) + "\n".join(urls)

    return output


tool = {
    'function': web_search,
    'triggers': ['search', 'online', 'web search'],
}


