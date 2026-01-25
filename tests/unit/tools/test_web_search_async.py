import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import tools.web_search as ws


class TestWebSearchAsync(unittest.IsolatedAsyncioTestCase):
    @patch("httpx.AsyncClient.get")
    async def test_web_search_async_duckduckgo_success(self, mock_get):
        # Mock DuckDuckGo HTML response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = """
            <html>
                <div class="result__snippet">This is a summary.</div>
                <a class="result__a" href="https://www.example.com/page">Example</a>
            </html>
        """
        mock_get.return_value = mock_response

        result = await ws.web_search_async("test query")
        self.assertIn("This is a summary.", result)
        self.assertIn("example.com/page", result)

    @patch("httpx.AsyncClient.get")
    async def test_web_search_async_duckduckgo_lite_fallback(self, mock_get):
        # First call fails, second call (lite) succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = ""
        mock_response_success = AsyncMock()
        mock_response_success.status_code = 200
        mock_response_success.text = """
            <html>
                <div class="result__snippet">Lite summary.</div>
                <a class="result-link" href="https://www.lite.com/page">Lite</a>
            </html>
        """
        # The first call (DuckDuckGo) fails, the second (lite) succeeds
        mock_get.side_effect = [mock_response_fail, mock_response_success]

        result = await ws.web_search_async("test query")
        self.assertIn("Lite summary.", result)
        self.assertIn("lite.com/page", result)

    @patch("httpx.AsyncClient.get")
    async def test_web_search_async_no_results(self, mock_get):
        # Both providers return no results
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"
        mock_get.return_value = mock_response

        result = await ws.web_search_async("test query")
        self.assertIn("No results found.", result)

    @patch("httpx.AsyncClient.get")
    async def test_web_search_async_http_error(self, mock_get):
        # Simulate HTTP error for both providers
        mock_get.side_effect = Exception("Network error")

        result = await ws.web_search_async("test query")
        self.assertTrue(
            "couldn't retrieve search results" in result.lower()
            or "no results found" in result.lower()
        )

    async def test_web_search_async_empty_query(self):
        result = await ws.web_search_async("")
        self.assertIn("non-empty search query", result)


if __name__ == "__main__":
    asyncio.run(unittest.main())
