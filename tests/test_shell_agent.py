import unittest
from unittest.mock import patch, MagicMock

from tools.agent import ShellAgent
from services.ollama import call_tool_with_tldr


class ShellAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ShellAgent()

    @patch("tools.agent.subprocess.run")
    @patch("tools.agent.sanitize_command")
    def test_shell_agent_rejects_unsafe_command(self, mock_sanitize, mock_run):
        mock_sanitize.return_value = None

        result = self.agent.shell_agent("rm -rf /")

        mock_run.assert_not_called()
        self.assertEqual(result["command"], "rm -rf /")
        self.assertEqual(result["exit_code"], -1)
        self.assertIn("rejected", result["stderr"].lower())

    @patch("tools.agent.subprocess.run")
    @patch("tools.agent.sanitize_command")
    def test_shell_agent_executes_sanitized_command(self, mock_sanitize, mock_run):
        mock_sanitize.return_value = "ls -lah"

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "ok"
        completed.stderr = ""
        mock_run.return_value = completed

        result = self.agent.shell_agent("ls -lah")

        mock_run.assert_called_once()
        called_cmd = mock_run.call_args.kwargs.get("args") or mock_run.call_args.args[0]
        self.assertEqual(called_cmd, "ls -lah")
        self.assertEqual(result["command"], "ls -lah")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok")

    @patch("tools.agent.subprocess.run")
    @patch("tools.agent.sanitize_command")
    def test_shell_agent_allows_pipeline_command(self, mock_sanitize, mock_run):
        mock_sanitize.return_value = "ls -lah | grep py"

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "filtered"
        completed.stderr = ""
        mock_run.return_value = completed

        result = self.agent.shell_agent("ls -lah | grep py")

        mock_run.assert_called_once()
        called_cmd = mock_run.call_args.kwargs.get("args") or mock_run.call_args.args[0]
        self.assertEqual(called_cmd, "ls -lah | grep py")
        self.assertEqual(result["command"], "ls -lah | grep py")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "filtered")

    @patch("tools.agent.subprocess.run")
    @patch("tools.agent.sanitize_command")
    def test_shell_agent_allows_and_sequence_command(self, mock_sanitize, mock_run):
        mock_sanitize.return_value = "ls -lah && echo done"

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "done"
        completed.stderr = ""
        mock_run.return_value = completed

        result = self.agent.shell_agent("ls -lah && echo done")

        mock_run.assert_called_once()
        called_cmd = mock_run.call_args.kwargs.get("args") or mock_run.call_args.args[0]
        self.assertEqual(called_cmd, "ls -lah && echo done")
        self.assertEqual(result["command"], "ls -lah && echo done")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "done")

    @patch("services.ollama.translate_instruction_to_command")
    def test_call_tool_with_tldr_shell_agent_retries_with_variations(self, mock_translate):
        # Simulate the translator suggesting three different commands in sequence.
        mock_translate.side_effect = [
            "cmd_variant_1",
            "cmd_variant_2",
            "cmd_variant_3",
        ]

        calls = []

        def fake_shell_tool(prompt: str):
            calls.append(prompt)
            # Fail the first three invocations, succeed on the fourth.
            if len(calls) < 4:
                return {
                    "command": prompt,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "simulated error",
                }
            return {
                "command": prompt,
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
            }

        history = []

        # Initial prompt that will be refined by the translator.
        result_text = call_tool_with_tldr(
            "shell_agent",
            fake_shell_tool,
            history,
            prompt="original_cmd",
        )

        # Ensure the fake tool was invoked multiple times with distinct prompts:
        # original command plus at least two translated variants.
        self.assertGreaterEqual(len(calls), 3)
        self.assertIn("original_cmd", calls[0])
        self.assertIn("cmd_variant_1", calls[1])
        self.assertIn("cmd_variant_2", calls[2])

        # The final textual result should reflect a successful execution.
        # For successful commands, we expect the compact format without an
        # explicit "Exit code: 0" label, but including the final command and
        # its stdout.
        self.assertIn("$ cmd_variant_3", result_text)
        self.assertIn("ok", result_text)


if __name__ == "__main__":
    unittest.main()
