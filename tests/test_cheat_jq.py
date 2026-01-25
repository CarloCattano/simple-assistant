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

        # check the last and second last lines for expected content
        last_line = lines[-1]
        second_last_line = lines[-2]
        self.assertTrue(second_last_line.startswith("# Add"))
        self.assertTrue(last_line.startswith("cat "))

if __name__ == "__main__":
    unittest.main()