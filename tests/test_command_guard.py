import unittest

from utils.command_guard import (
    detect_direct_command,
    sanitize_command,
)


class CommandGuardTests(unittest.TestCase):
    def test_sanitize_command_blocks_sudo(self):
        self.assertIsNone(sanitize_command("sudo rm -rf /"))

    def test_sanitize_command_allows_known_command(self):
        self.assertEqual(sanitize_command("ls -lah"), "ls -lah")

    def test_sanitize_command_allows_safe_pipeline(self):
        self.assertEqual(
            sanitize_command("ls -lah | grep py"),
            "ls -lah | grep py",
        )

    def test_sanitize_command_allows_safe_and_sequence(self):
        self.assertEqual(
            sanitize_command("ls -lah && echo done"),
            "ls -lah && echo done",
        )

    def test_sanitize_command_rejects_unknown_binary(self):
        self.assertIsNone(sanitize_command("scarycmd --flag"))

    def test_sanitize_command_rejects_unclosed_quote(self):
        self.assertIsNone(sanitize_command('echo "unterminated'))

    def test_detect_direct_command_pass_through(self):
        self.assertEqual(detect_direct_command("ls -lah"), "ls -lah")

    def test_detect_direct_command_handles_quotes(self):
        self.assertEqual(detect_direct_command('"ls -lah"'), "ls -lah")

    def test_detect_direct_command_rejects_unclosed_quote(self):
        self.assertIsNone(detect_direct_command('"ls -lah'))


if __name__ == "__main__":
    unittest.main()
