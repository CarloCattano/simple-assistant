import asyncio
import unittest

from handlers import messages as msg


class FakeMessage:
    def __init__(self) -> None:
        self.calls = []

    async def reply_text(self, text: str, parse_mode: str | None = None):  # noqa: D401
        """Mimic telegram.Message.reply_text, recording calls for inspection."""

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


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(unittest.main())
