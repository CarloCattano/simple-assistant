import unittest
from unittest.mock import patch, MagicMock

from services.ollama_tools import call_tool_with_tldr


class CheatRetryTests(unittest.TestCase):
    @patch("services.ollama_translation.translate_instruction_to_command")
    def test_cheat_sh_used_on_final_retry(self, mock_translate):
        # Simulate initial failing command then a successful refined command
        initial = "find the first json and read it with jq"
        refined = "rg -n json | xargs -I {} jq {} | head -n1"

        # Mock translate to return None initially, refined when provided cheat context
        def translate_side_effect(arg):
            if not arg:
                return None
            # If cheat.sh or primary 'rg' appears in prompt, return refined
            if "rg" in arg or "cheat.sh" in arg:
                return refined
            return None

        mock_translate.side_effect = translate_side_effect

        call_count = {"n": 0}

        def fake_tool(prompt: str = None):
            call_count["n"] += 1
            p = prompt or ""
            # First call: fail
            if call_count["n"] == 1:
                return {
                    "command": p,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "not found",
                }
            # Second call: success with refined command
            return {
                "command": p,
                "exit_code": 0,
                "stdout": "{\"found\":true}",
                "stderr": "",
            }

        history = []

        result = call_tool_with_tldr("shell_agent", fake_tool, history, prompt=initial)

        # Ensure translator was called to produce refined command
        self.assertTrue(mock_translate.called)
        # Final result should reflect successful output
        self.assertIn("Output:", result)
        self.assertIn("found", result)


if __name__ == "__main__":
    unittest.main()
