import asyncio
import unittest
from unittest.mock import patch

import handlers.commands as cmds


class TestRunToolAsync(unittest.IsolatedAsyncioTestCase):
    async def test_run_tool_async_delegates_to_thread(self):
        with patch(
            "handlers.commands.run_tool_direct", return_value="output"
        ) as mock_run:
            result = await cmds._run_tool_async("shell_agent", {"prompt": "ls"})
            self.assertEqual(result, "output")
            mock_run.assert_called_once_with("shell_agent", {"prompt": "ls"})


if __name__ == "__main__":
    asyncio.run(unittest.main())
