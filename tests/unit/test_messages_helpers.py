import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import handlers.messages as msg


class FakeMessage:
    def __init__(self):
        self.calls = []
        self.text = "echo hello"
        self.chat = MagicMock()
        self.chat.id = 123
        self.from_user = MagicMock()
        self.from_user.id = 456

    async def reply_text(self, text, parse_mode=None):
        self.calls.append({"text": text, "parse_mode": parse_mode})
        return self


class FakeContext:
    def __init__(self):
        self.user_data = {}


class TestRunToolAsync(unittest.IsolatedAsyncioTestCase):
    async def test_run_tool_async_delegates_to_thread(self):
        with patch(
            "handlers.messages.run_tool_direct", return_value="output"
        ) as mock_run:
            result = await msg._run_tool_async("shell_agent", {"prompt": "ls"})
            self.assertEqual(result, "output")
            mock_run.assert_called_once_with("shell_agent", {"prompt": "ls"})


class TestHandleShellCommand(unittest.IsolatedAsyncioTestCase):
    async def test_handle_shell_command_success(self):
        fake_message = FakeMessage()
        fake_context = FakeContext()
        with patch("handlers.messages._run_tool_async", return_value="shell output"):
            with patch(
                "handlers.messages.respond_in_mode", new=AsyncMock()
            ) as mock_respond:
                await msg._handle_shell_command(fake_message, fake_context, "ls -l")
                mock_respond.assert_awaited_once()
                args, kwargs = mock_respond.call_args
                self.assertEqual(args[0], fake_message)
                self.assertEqual(args[1], fake_context)
                self.assertEqual(args[2], "ls -l")
                self.assertEqual(args[3], "shell output")
                self.assertIn("tool_info", kwargs)
                self.assertEqual(kwargs["tool_info"]["tool_name"], "shell_agent")

    async def test_handle_shell_command_tool_none(self):
        fake_message = FakeMessage()
        fake_context = FakeContext()
        with patch("handlers.messages._run_tool_async", return_value=None):
            with patch.object(
                fake_message, "reply_text", wraps=fake_message.reply_text
            ) as mock_reply:
                await msg._handle_shell_command(fake_message, fake_context, "ls -l")
                mock_reply.assert_awaited_once()
                self.assertIn("text", fake_message.calls[0])
                self.assertIn("unknown", fake_message.calls[0]["text"].lower())


class TestHandleToolRequest(unittest.IsolatedAsyncioTestCase):
    async def test_handle_tool_request_success(self):
        fake_message = FakeMessage()
        fake_context = FakeContext()
        with patch("handlers.messages._run_tool_async", return_value="tool output"):
            with patch(
                "handlers.messages.respond_in_mode", new=AsyncMock()
            ) as mock_respond:
                await msg._handle_tool_request(
                    fake_message,
                    fake_context,
                    "do something",
                    "some_tool",
                    {"foo": "bar"},
                )
                mock_respond.assert_awaited_once()
                args, kwargs = mock_respond.call_args
                self.assertEqual(args[0], fake_message)
                self.assertEqual(args[1], fake_context)
                self.assertEqual(args[2], "do something")
                self.assertEqual(args[3], "tool output")
                self.assertIn("tool_info", kwargs)
                self.assertEqual(kwargs["tool_info"]["tool_name"], "some_tool")
                self.assertEqual(kwargs["tool_info"]["parameters"], {"foo": "bar"})

    async def test_handle_tool_request_tool_none(self):
        fake_message = FakeMessage()
        fake_context = FakeContext()
        with patch("handlers.messages._run_tool_async", return_value=None):
            with patch.object(
                fake_message, "reply_text", wraps=fake_message.reply_text
            ) as mock_reply:
                await msg._handle_tool_request(
                    fake_message,
                    fake_context,
                    "do something",
                    "some_tool",
                    {"foo": "bar"},
                )
                mock_reply.assert_awaited_once()
                self.assertIn("text", fake_message.calls[0])
                self.assertIn("unknown", fake_message.calls[0]["text"].lower())


if __name__ == "__main__":
    asyncio.run(unittest.main())
