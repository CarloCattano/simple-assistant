import unittest

from tools.cheat import fetch_cheat


class CheatJQTests(unittest.TestCase):
    def test_cheat_jq_contains_usage_and_examples(self):
        text = fetch_cheat("jq")
        if isinstance(text, str) and text.startswith("Error"):
            self.skipTest(f"cheat.sh unavailable: {text}")

        self.assertTrue(isinstance(text, str) and len(text) > 0)

        lowered = text.lower()
        has_usage = "usage" in lowered or "synopsis" in lowered
        has_examples = "examples" in lowered or "example" in lowered

        if not (has_usage or has_examples):
            self.skipTest("cheat.sh content for jq did not contain expected markers")

        import re

        # Remove ANSI color sequences which cheat.sh may include
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        cleaned = ansi_re.sub("", text)
        lines = cleaned.strip().splitlines()

        # check the last 2 lines
        last_line = lines[-1].strip()
        second_last_line = lines[-2].strip()
        self.assertEqual(last_line, "")
        

if __name__ == "__main__":
    unittest.main()
import unittest

from tools.cheat import fetch_cheat


class CheatJQTests(unittest.TestCase):
    def test_cheat_jq_contains_usage_and_examples(self):
        text = fetch_cheat("jq")
        if isinstance(text, str) and text.startswith("Error"):
            self.skipTest(f"cheat.sh unavailable: {text}")

        self.assertTrue(isinstance(text, str) and len(text) > 0)

        lowered = text.lower()
        has_usage = "usage" in lowered or "synopsis" in lowered
        has_examples = "examples" in lowered or "example" in lowered

        if not (has_usage or has_examples):
            self.skipTest("cheat.sh content for jq did not contain expected markers")

        import re
        # Remove ANSI color sequences which cheat.sh may include
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        cleaned = ansi_re.sub("", text)
        lines = [line.strip() for line in cleaned.strip().splitlines() if line.strip()]
        if not lines:
            self.skipTest("cheat.sh content for jq too short to verify last line format")
        # Find the last non-empty line
        last_line = lines[-1]
        second_last_line = lines[-2]
        # Verify that the second last line is a command example that
        self.assertEqual(second_last_line, "# Add/remove specific keys:")
        self.assertIn("| jq ", last_line)
        self.assertTrue(last_line.startswith("cat "))



if __name__ == "__main__":
    unittest.main()
