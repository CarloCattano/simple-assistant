"""End-to-end tests for the Telegram bot."""

import os
import unittest

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TEST_CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")

if not TEST_CHAT_ID:
    raise unittest.SkipTest("CHAT_ID not set, skipping e2e tests")


class E2ETests(unittest.TestCase):
    BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    def _send_message(self, text, parse_mode=None):
        """Send a message to the test chat."""
        data = {"chat_id": TEST_CHAT_ID, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        response = requests.post(
            f"{self.BASE_URL}/sendMessage",
            json=data
        )
        response.raise_for_status()
        return response.json()

    def test_start_command(self):
        """Test sending /start command."""
        result = self._send_message("/start")
        self.assertEqual(result["ok"], True)
        print(f"Sent /start to chat {TEST_CHAT_ID}")

    def test_help_command(self):
        """Test sending /help command."""
        result = self._send_message("/help")
        self.assertEqual(result["ok"], True)
        print(f"Sent /help to chat {TEST_CHAT_ID}")

    def test_simple_message(self):
        """Test sending a simple message."""
        result = self._send_message("Hello bot")
        self.assertEqual(result["ok"], True)
        print(f"Sent 'Hello bot' to chat {TEST_CHAT_ID}")

    def test_web_command(self):
        """Test sending /web command."""
        result = self._send_message("/web")
        self.assertEqual(result["ok"], True)
        print(f"Sent /web to chat {TEST_CHAT_ID}")

    def test_agent_command(self):
        """Test sending /agent command."""
        result = self._send_message("/agent")
        self.assertEqual(result["ok"], True)
        print(f"Sent /agent to chat {TEST_CHAT_ID}")

    def test_audio_command(self):
        """Test sending /audio command."""
        result = self._send_message("/audio")
        self.assertEqual(result["ok"], True)
        print(f"Sent /audio to chat {TEST_CHAT_ID}")

    def test_markdown_message(self):
        """Test sending a message with Markdown formatting."""
        result = self._send_message("**Bold text** and `inline code` with [link](https://example.com)", parse_mode="MarkdownV2")
        self.assertEqual(result["ok"], True)
        print(f"Sent markdown text to chat {TEST_CHAT_ID}")

    def test_code_snippet(self):
        """Test sending a code snippet."""
        result = self._send_message("```python\nprint('Hello World')\nfor i in range(3):\n    print(i)\n```", parse_mode="MarkdownV2")
        self.assertEqual(result["ok"], True)
        print(f"Sent code snippet to chat {TEST_CHAT_ID}")

    def test_send_photo(self):
        """Test sending a photo."""
        with open("tests/test.jpg", "rb") as f:
            response = requests.post(
                f"{self.BASE_URL}/sendPhoto",
                data={"chat_id": TEST_CHAT_ID, "caption": "Test image for bot"},
                files={"photo": f}
            )
        response.raise_for_status()
        result = response.json()
        self.assertEqual(result["ok"], True)

        print(f"Sent photo to chat {TEST_CHAT_ID}")


if __name__ == "__main__":
    unittest.main()