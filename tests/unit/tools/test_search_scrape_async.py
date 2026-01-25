import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch

import tools.search_scrape as ss


class TestSearchAndScrapeAsync(unittest.IsolatedAsyncioTestCase):
    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_success(self, mock_get):
        # Mock a simple HTML page with title, meta, content, and links
        html = """
        <html>
            <head>
                <title>Test Page</title>
                <meta name="description" content="This is a test description.">
            </head>
            <body>
                <main>
                    <h1>Welcome to the Test Page</h1>
                    <p>This is a paragraph with some content about testing.</p>
                    <a href="https://example.com/page1">Page 1</a>
                    <a href="https://example.com/page2?ref=tracker">Page 2</a>
                    <a href="https://example.com/script.js">Script</a>
                </main>
                <footer>
                    <p>Footer text should not appear.</p>
                </footer>
            </body>
        </html>
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

        result = await ss.search_and_scrape("https://example.com")
        # Title
        self.assertIn("Test Page", result)
        # Meta description
        self.assertIn("This is a test description.", result)
        # Main content
        self.assertIn("Welcome to the Test Page", result)
        self.assertIn("This is a paragraph with some content about testing.", result)
        # Cleaned links (no .js, no params)
        self.assertIn("- example.com/page1", result)
        self.assertIn("- example.com/page2", result)
        self.assertNotIn(".js", result)
        self.assertNotIn("ref=tracker", result)
        # Footer should not appear
        self.assertNotIn("Footer text should not appear.", result)

    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_handles_http_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        result = await ss.search_and_scrape("https://example.com")
        self.assertIn("HTTP error", result)

    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_handles_non_200(self, mock_get):
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = ""
        mock_get.return_value = mock_response
        result = await ss.search_and_scrape("https://example.com")
        self.assertIn("status code 404", result)

    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_fallback_to_body_text(self, mock_get):
        html = """
        <html>
            <head><title>No Main</title></head>
            <body>
                <div>This is some fallback body text that should be included because no main/article/p/li.</div>
            </body>
        </html>
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        result = await ss.search_and_scrape("https://example.com")
        self.assertIn("No Main", result)
        self.assertIn("fallback body text", result)

    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_skips_short_and_noisy_lines(self, mock_get):
        html = """
        <html>
            <head><title>Short Lines</title></head>
            <body>
                <main>
                    <p>Short</p>
                    <p>Valid content line that is long enough to be included in the output.</p>
                </main>
            </body>
        </html>
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        result = await ss.search_and_scrape("https://example.com")
        self.assertIn("Valid content line", result)
        self.assertNotIn("Short\n", result)

    @patch("httpx.AsyncClient.get")
    async def test_search_and_scrape_handles_no_title(self, mock_get):
        html = """
        <html>
            <head></head>
            <body>
                <main>
                    <p>Some content.</p>
                </main>
            </body>
        </html>
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        result = await ss.search_and_scrape("https://example.com")
        self.assertIn("(No title)", result)
        self.assertIn("Some content.", result)


if __name__ == "__main__":
    asyncio.run(unittest.main())
