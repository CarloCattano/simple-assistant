from typing import List, Dict

import unittest
from unittest.mock import patch

from services.ocr import (
    _merge_line_tokens,
    group_tokens_by_line,
    process_image,
)


def _make_token(text: str, top: int = 0, left: int = 0, height: int = 10) -> Dict[str, int | str]:
    return {"text": text, "top": top, "left": left, "height": height}


class MergeLineTokensTests(unittest.TestCase):
    def test_empty_tokens_returns_empty_string(self) -> None:
        self.assertEqual(_merge_line_tokens([]), "")

    def test_merges_decimal_tokens_with_comma(self) -> None:
        tokens = [
            _make_token("12", left=0),
            _make_token(",", left=10),
            _make_token("34", left=20),
        ]

        merged = _merge_line_tokens(tokens)

        self.assertEqual(merged, "12,34")

    def test_merges_decimal_tokens_with_dot(self) -> None:
        tokens = [
            _make_token("12", left=0),
            _make_token(".", left=10),
            _make_token("34", left=20),
        ]

        merged = _merge_line_tokens(tokens)

        self.assertEqual(merged, "12.34")

    def test_merges_currency_symbol_after_amount(self) -> None:
        tokens = [
            _make_token("12,34", left=0),
            _make_token("€", left=20),
        ]

        merged = _merge_line_tokens(tokens)

        self.assertEqual(merged, "12,34€")


class GroupTokensByLineTests(unittest.TestCase):
    def test_empty_tokens_returns_empty_list(self) -> None:
        self.assertEqual(group_tokens_by_line([]), [])

    def test_groups_two_visual_lines_and_merges_tokens(self) -> None:
        line1 = [
            _make_token("Item", top=5, left=0, height=10),
            _make_token("12", top=5, left=40, height=10),
            _make_token(",", top=5, left=60, height=10),
            _make_token("34", top=5, left=80, height=10),
            _make_token("€", top=5, left=100, height=10),
        ]

        line2 = [
            _make_token("Other", top=50, left=0, height=10),
            _make_token("5", top=50, left=40, height=10),
            _make_token(",", top=50, left=60, height=10),
            _make_token("99", top=50, left=80, height=10),
            _make_token("€", top=50, left=100, height=10),
        ]

        tokens: List[Dict[str, int | str]] = line1 + line2

        lines = group_tokens_by_line(tokens)

        self.assertEqual(lines, ["Item 12,34 €", "Other 5,99 €"])


class ProcessImageTests(unittest.TestCase):
    @patch("services.ocr.pytesseract.image_to_data")
    @patch("services.ocr.Image.open")
    def test_process_image_handles_tesseract_output(self, mock_open, mock_image_to_data) -> None:  # noqa: ANN001
        # Build a fake image object with the context manager protocol
        class DummyImage:
            def convert(self, mode: str) -> "DummyImage":  # noqa: ARG002
                # Returning self is enough because we only call .point on it
                return self

            def point(self, func, mode: str) -> "DummyImage":  # noqa: ARG002
                return self

            def __enter__(self) -> "DummyImage":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, ANN401, D401, D403
                return None

        mock_open.return_value = DummyImage()

        # Prepare fake tesseract data
        fake_data = {
            "text": ["  Item  ", "", "12", ",", "34", "€"],
            "top": [10, 0, 10, 10, 10, 10],
            "left": [0, 0, 40, 60, 80, 100],
            "height": [10, 0, 10, 10, 10, 10],
        }

        mock_image_to_data.return_value = fake_data

        tokens = process_image("dummy-path.png")

        # The empty/whitespace-only token should be skipped
        self.assertEqual(len(tokens), 5)
        self.assertEqual(tokens[0]["text"], "Item")
        self.assertEqual(tokens[1]["text"], "12")
        self.assertEqual(tokens[2]["text"], ",")
        self.assertEqual(tokens[3]["text"], "34")
        self.assertEqual(tokens[4]["text"], "€")

    def test_process_image_on_real_sample_image(self) -> None:
        """Smoke test process_image against the real tests/test.jpg.

        This doesn't assert exact OCR content (which is fragile across
        environments and Tesseract versions), but it does ensure we get
        some non-empty tokens back and that the basic structure matches
        what callers expect.
        """

        tokens = process_image("tests/test.jpg")

        self.assertGreater(len(tokens), 0)
        for token in tokens:
            self.assertIn("text", token)
            self.assertIn("top", token)
            self.assertIn("left", token)
            self.assertIn("height", token)


        # we expect SUMME to be in the OCR output of the sample receipt
        texts = [token["text"] for token in tokens]
        self.assertIn("SUMME", texts)
        #and we expect a price of 33,73 or 33.73  
        self.assertTrue("33,73" in texts or "33.73" in texts)



if __name__ == "__main__":  # pragma: no cover
    unittest.main()
