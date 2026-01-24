import asyncio
import time
import unittest

from handlers import messages as msg


class FakeMessage:
    def __init__(self) -> None:
        self.calls = []
        self.timestamps = []

    async def reply_text(self, text: str, parse_mode: str | None = None):  # noqa: D401
        """Mimic telegram.Message.reply_text, recording calls for inspection."""

        self.timestamps.append(time.time())
        self.calls.append({"text": text, "parse_mode": parse_mode})
        return self


class SendCodeBlockChunkedTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_short_block_sends_one_message(self) -> None:
        fake = FakeMessage()
        body = "$ ls /var/cache\ncolord\nfontconfig"

        messages = await msg._send_code_block_chunked(  # type: ignore[attr-defined]
            fake,
            body,
            language="bash",
            chunk_size=4096,
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(len(fake.calls), 1)
        payload = fake.calls[0]
        text = payload["text"]
        self.assertTrue(text.startswith("```bash\n"))
        self.assertTrue(text.endswith("\n```"))
        self.assertEqual(payload["parse_mode"], "Markdown")

    async def test_long_block_is_split_with_balanced_fences(self) -> None:
        fake = FakeMessage()
        # Construct a body that will exceed the tiny chunk_size when wrapped
        # in ```bash fences, forcing _send_code_block_chunked to split.
        lines = [f"line {i}" for i in range(30)]
        body = "\n".join(lines)

        messages = await msg._send_code_block_chunked(  # type: ignore[attr-defined]
            fake,
            body,
            language="bash",
            chunk_size=80,
        )

        # We expect more than one message when using a small chunk_size.
        self.assertGreater(len(messages), 1)
        self.assertEqual(len(messages), len(fake.calls))

        for call in fake.calls:
            text = call["text"]
            self.assertTrue(text.startswith("```bash\n"))
            self.assertTrue(text.endswith("\n```"))
            self.assertEqual(call["parse_mode"], "Markdown")


class SendChunkedMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_message_adds_delays(self) -> None:
        fake = FakeMessage()
        # Create text that will be split into multiple chunks
        long_text = "x" * 5000  # Exceeds DEFAULT_CHUNK_SIZE of 4096

        start_time = time.time()
        messages = await msg.send_chunked_message(  # type: ignore[attr-defined]
            fake,
            long_text,
            chunk_size=2000,  # Force splitting
        )

        # Should have multiple messages
        self.assertGreater(len(messages), 1)
        self.assertEqual(len(messages), len(fake.calls))
        
        # Check that delays were added (at least 0.5 seconds between chunks)
        for i in range(1, len(fake.timestamps)):
            delay = fake.timestamps[i] - fake.timestamps[i-1]
            self.assertGreaterEqual(delay, 0.5)  # Allow some tolerance

    async def test_code_block_chunked_adds_delays(self) -> None:
        fake = FakeMessage()
        # Create a body that will be split
        lines = [f"line {i}" for i in range(50)]
        body = "\n".join(lines)

        start_time = time.time()
        messages = await msg._send_code_block_chunked(  # type: ignore[attr-defined]
            fake,
            body,
            language="bash",
            chunk_size=100,  # Force splitting
        )

        # Should have multiple messages
        self.assertGreater(len(messages), 1)
        self.assertEqual(len(messages), len(fake.calls))
        
        # Check that delays were added
        for i in range(1, len(fake.timestamps)):
            delay = fake.timestamps[i] - fake.timestamps[i-1]
            self.assertGreaterEqual(delay, 0.5)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(unittest.main())
