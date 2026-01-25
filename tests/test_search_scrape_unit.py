import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

from tools import search_scrape as ss


class SearchScrapeStressTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_html_is_truncated_and_fast(self):
        # Build a synthetic "page" with lots of text and links to exercise
        # the truncation and link limiting logic without performing a
        # real network request.
        body_chunk = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        big_body = body_chunk * 2000  # ~100k chars
        many_links = [f"https://example.com/page/{i}" for i in range(200)]

        class FakeResponse:
            status_code = 200

            def __init__(self, text: str) -> None:
                self.text = text

        # Prepare an HTML document that roughly mimics a heavy page.
        html = ["<html><head><title>Stress Page</title></head><body>"]
        html.append(big_body)
        for link in many_links:
            html.append(f'<a href="{link}">link</a>')
        html.append("</body></html>")
        html_text = "".join(html)

        async def fake_get(*args, **kwargs):
            return FakeResponse(html_text)

        with patch("httpx.AsyncClient.get", new=fake_get):
            start = time.time()
            output = await ss.search_and_scrape("https://example.com/stress-test")
            elapsed = time.time() - start

        # The function should return promptly even for very large pages.
        self.assertLess(
            elapsed, 2.0, f"search_and_scrape took too long: {elapsed:.2f}s"
        )

        # Output should be non-empty but reasonably bounded thanks to the
        # internal truncation logic.
        self.assertIn("Stress Page", output)
        self.assertLess(len(output), 20000)

        # Link limiting should prevent hundreds of links from appearing.
        link_lines = [
            line for line in output.splitlines() if "example.com/page/" in line
        ]
        self.assertLessEqual(len(link_lines), ss.MAX_LINKS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
