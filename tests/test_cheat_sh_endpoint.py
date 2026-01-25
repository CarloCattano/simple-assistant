
import unittest
import requests


class CheatShEndpointTests(unittest.TestCase):
    def test_cheat_sh_jq_available(self):
        resp = requests.get("http://cheat.sh/jq", timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("jq", resp.text.lower())

    def test_cheat_sh_ls_available(self):
        resp = requests.get("http://cheat.sh/ls", timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ls", resp.text.lower())

    def test_cheat_sh_returns_error_for_invalid(self):
        resp = requests.get("http://cheat.sh/thisisnotarealcommand", timeout=5)
        self.assertEqual(resp.status_code, 200)
        text = resp.text.lower()
        self.assertTrue(
            "not found" in text
            or "error" in text
            or "unknown topic" in text
            or len(text) < 200
        )
