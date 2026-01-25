import asyncio
import unittest
from unittest.mock import MagicMock, patch

import services.ollama as ollama


class TestOllamaAsyncToolHelpers(unittest.IsolatedAsyncioTestCase):
    async def test_run_tool_direct_async_success(self):
        # Patch _resolve_tool_entry to return a fake tool and function
        with (
            patch.object(
                ollama,
                "_resolve_tool_entry",
                return_value=("fake_tool", {"function": lambda **kwargs: "ok"}),
            ),
            patch.object(
                ollama, "call_tool_with_tldr_async", return_value="tool output"
            ) as mock_call,
        ):
            result = await ollama.run_tool_direct_async("fake_tool", {"foo": "bar"})
            self.assertEqual(result, "tool output")
            mock_call.assert_awaited_once()
            args, kwargs = mock_call.call_args
            self.assertEqual(args[0], "fake_tool")
            self.assertTrue(callable(args[1]))
            self.assertIsInstance(args[2], list)
            self.assertEqual(kwargs["foo"], "bar")

    async def test_run_tool_direct_async_tool_not_found(self):
        with patch.object(ollama, "_resolve_tool_entry", return_value=None):
            result = await ollama.run_tool_direct_async("missing_tool", {})
            self.assertIsNone(result)

    async def test_call_tool_with_tldr_async_shell_agent_success(self):
        # Simulate a shell_agent tool that returns a dict with exit_code 0 and stdout
        def fake_shell_tool(**kwargs):
            return {"exit_code": 0, "stdout": "done", "stderr": "", "command": "ls"}

        with (
            patch.object(ollama, "_format_tool_output", return_value="done"),
            patch.object(ollama, "_debug"),
            patch.object(ollama, "_record_event"),
            patch.object(ollama, "_truncate_event_text", return_value="done"),
            patch.object(ollama, "tldr_tool_output", return_value="summary"),
            patch.object(ollama, "build_audio_script", return_value="audio script"),
            patch.object(ollama, "_set_last_tool_audio"),
        ):
            history = []
            result = await ollama.call_tool_with_tldr_async(
                "shell_agent", fake_shell_tool, history
            )
            self.assertIn("done", result)
            # For shell_agent, TLDR is skipped, so only raw output is returned
            self.assertNotIn("TLDR", result)
            self.assertTrue(any(entry["role"] == "tool" for entry in history))
            # For shell_agent, assistant TLDR entry should not be present
            self.assertFalse(any(entry["role"] == "assistant" for entry in history))

    async def test_call_tool_with_tldr_async_other_tool_success(self):
        # Simulate a generic tool that returns a string
        def fake_tool(**kwargs):
            return "raw output"

        with (
            patch.object(ollama, "_format_tool_output", return_value="raw output"),
            patch.object(ollama, "_debug"),
            patch.object(ollama, "_record_event"),
            patch.object(ollama, "_truncate_event_text", return_value="raw output"),
            patch.object(ollama, "tldr_tool_output", return_value="summary"),
            patch.object(ollama, "build_audio_script", return_value="audio script"),
            patch.object(ollama, "_set_last_tool_audio"),
        ):
            history = []
            result = await ollama.call_tool_with_tldr_async(
                "some_tool", fake_tool, history
            )
            self.assertIn("raw output", result)
            self.assertIn("TLDR", result)
            self.assertTrue(any(entry["role"] == "tool" for entry in history))
            self.assertTrue(any(entry["role"] == "assistant" for entry in history))

    async def test_call_tool_with_tldr_async_tldr_exception(self):
        # Simulate a tool that returns a string, but tldr_tool_output raises
        def fake_tool(**kwargs):
            return "raw output"

        with (
            patch.object(ollama, "_format_tool_output", return_value="raw output"),
            patch.object(ollama, "_debug"),
            patch.object(ollama, "_record_event"),
            patch.object(ollama, "_truncate_event_text", return_value="raw output"),
            patch.object(ollama, "tldr_tool_output", side_effect=Exception("fail")),
            patch.object(ollama, "build_audio_script", return_value="audio script"),
            patch.object(ollama, "_set_last_tool_audio"),
        ):
            history = []
            result = await ollama.call_tool_with_tldr_async(
                "some_tool", fake_tool, history
            )
            self.assertEqual(result, "raw output")
            self.assertTrue(any(entry["role"] == "tool" for entry in history))

    async def test_call_tool_with_tldr_async_shell_agent_retry(self):
        # Simulate a shell_agent tool that fails first, then succeeds
        call_count = {"count": 0}

        def fake_shell_tool(**kwargs):
            if call_count["count"] == 0:
                call_count["count"] += 1
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "command not found",
                    "command": "badcmd",
                }
            else:
                return {
                    "exit_code": 0,
                    "stdout": "success",
                    "stderr": "",
                    "command": "goodcmd",
                }

        with (
            patch.object(ollama, "_format_tool_output", return_value="success"),
            patch.object(ollama, "_debug"),
            patch.object(ollama, "_record_event"),
            patch.object(ollama, "_truncate_event_text", return_value="success"),
            patch.object(ollama, "tldr_tool_output", return_value="summary"),
            patch.object(ollama, "build_audio_script", return_value="audio script"),
            patch.object(ollama, "_set_last_tool_audio"),
            patch.object(
                ollama, "translate_instruction_to_command", return_value="goodcmd"
            ),
        ):
            history = []
            result = await ollama.call_tool_with_tldr_async(
                "shell_agent", fake_shell_tool, history
            )
            self.assertIn("success", result)
            # For shell_agent, TLDR is skipped, so only raw output is returned
            self.assertNotIn("TLDR", result)
            self.assertTrue(any(entry["role"] == "tool" for entry in history))
            # For shell_agent, assistant TLDR entry should not be present
            self.assertFalse(any(entry["role"] == "assistant" for entry in history))


if __name__ == "__main__":
    asyncio.run(unittest.main())
