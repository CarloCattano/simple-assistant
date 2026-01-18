import unittest
from unittest.mock import patch, MagicMock

from tools.agent import ShellAgent


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


if __name__ == "__main__":
    unittest.main()
