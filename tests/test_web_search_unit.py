import unittest

from tools import web_search as ws


class WebSearchHelpersTests(unittest.TestCase):
    def test_clean_link_strips_protocol_and_www(self):
        self.assertEqual(
            ws._clean_link("https://www.example.com/path"),
            "example.com/path",
        )

    def test_clean_link_drops_internal_html_queries(self):
        self.assertEqual(ws._clean_link("/html/?q=foo"), "")
        self.assertEqual(ws._clean_link("html/?q=bar"), "")

    def test_clean_link_drops_empty_and_trailing_html(self):
        self.assertEqual(ws._clean_link(""), "")
        self.assertEqual(ws._clean_link("https://duckduckgo.com/html/"), "")



    def test_format_search_result_summary_only(self):
        out = ws._format_search_result([("Summary here", "")])
        self.assertEqual(out, "Summary here")

    def test_format_search_result_links_and_summary(self):
        pairs = [("Summary here", "example.com/one"), ("", "example.com/two")]
        out = ws._format_search_result(pairs)
        self.assertIn("Summary here", out)
        self.assertIn("- example.com/one", out)
        self.assertIn("- example.com/two", out)

    def test_format_search_result_empty(self):
        out = ws._format_search_result([])
        self.assertEqual(out, "No results found.")


if __name__ == "__main__":
    unittest.main()
