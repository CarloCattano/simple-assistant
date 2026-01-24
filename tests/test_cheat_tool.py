import unittest

from tools import load_tools


class CheatToolTests(unittest.TestCase):
    def test_fetch_cheat_real(self):
        tools = load_tools()
        func_entry = tools.get("fetch_cheat")
        self.assertIsNotNone(func_entry)
        result = func_entry["function"]("ls")
        # If network or cheat.sh is unavailable, skip rather than fail CI.
        if isinstance(result, str) and result.startswith("Error"):
            self.skipTest(f"cheat.sh unavailable: {result}")
        self.assertTrue(isinstance(result, str) and len(result) > 0)


if __name__ == "__main__":
    unittest.main()
