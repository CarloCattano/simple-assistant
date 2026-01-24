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
    @patch("services.ollama.translate_instruction_to_command")
    def test_call_tool_with_tldr_shell_agent_retries_on_empty_output(self, mock_translate):
        # Test that commands with exit_code 0 but no stdout are retried
        mock_translate.side_effect = [
            "find /nonexistent -type f",  # Same as input, will retry again
            "ls -la",  # Fallback command
        ]

        calls = []

        def fake_shell_tool(prompt: str):
            calls.append(prompt)
            if "find /nonexistent" in prompt:
                # Simulate find succeeding but finding nothing
                return {
                    "command": prompt,
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                }
            return {
                "command": prompt,
                "exit_code": 0,
                "stdout": "total 0",
                "stderr": "",
            }

        history = []

        result_text = call_tool_with_tldr(
            "shell_agent",
            fake_shell_tool,
            history,
            prompt="find /nonexistent -type f",  # Start with the command that produces no output
        )

        # Should have called at least 3 commands (original + 2 retries)
        self.assertGreaterEqual(len(calls), 3)
        self.assertIn("find /nonexistent", calls[0])
        self.assertIn("ls -la", calls[-1])  # Last call should be the successful one

        # Should contain the successful command output
        self.assertIn("$ ls -la", result_text)
        self.assertIn("total 0", result_text)

    def test_tool_output_truncated_in_history(self):
        # Test that tool outputs are truncated when added to history
        from services.ollama import _format_tool_output, MAX_TOOL_OUTPUT_IN_HISTORY
        
        # Create a long output
        long_output = "x" * 2000
        raw_output = {
            "command": "echo " + long_output,
            "exit_code": 0,
            "stdout": long_output,
            "stderr": "",
        }
        
        formatted = _format_tool_output("shell_agent", raw_output)
        
        # Should be truncated in history storage
        truncated = formatted[:MAX_TOOL_OUTPUT_IN_HISTORY] + ("..." if len(formatted) > MAX_TOOL_OUTPUT_IN_HISTORY else "")
        
        self.assertLessEqual(len(truncated), MAX_TOOL_OUTPUT_IN_HISTORY + 3)  # +3 for "..."

    def test_tool_output_truncated_in_formatting(self):
        # Test that very long stdout is truncated in formatting
        from services.ollama import _format_tool_output
        
        # Create output longer than 16000 chars
        long_stdout = "x" * 17000
        raw_output = {
            "command": "some_command",
            "exit_code": 0,
            "stdout": long_stdout,
            "stderr": "",
        }
        
        formatted = _format_tool_output("shell_agent", raw_output)
        
        # Should contain truncation message
        self.assertIn("... (output truncated)", formatted)
        # Should be shorter than original
        self.assertLess(len(formatted), len(long_stdout))

    def test_tool_history_truncation(self):
        # Test that tool outputs are truncated when stored in history
        from services.ollama import call_tool_with_tldr, MAX_TOOL_OUTPUT_IN_HISTORY
        
        long_output = "x" * 2000  # Longer than MAX_TOOL_OUTPUT_IN_HISTORY
        history = []
        
        def fake_tool(prompt: str):
            return {
                "command": prompt,
                "exit_code": 0,
                "stdout": long_output,
                "stderr": "",
            }
        
        result = call_tool_with_tldr("shell_agent", fake_tool, history, prompt="test")
        
        # History should contain truncated output
        self.assertEqual(len(history), 1)
        tool_entry = history[0]
        self.assertEqual(tool_entry["role"], "tool")
        self.assertLessEqual(len(tool_entry["content"]), MAX_TOOL_OUTPUT_IN_HISTORY + 3)  # +3 for "..."


if __name__ == "__main__":
    unittest.main()
