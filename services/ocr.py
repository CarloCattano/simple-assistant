import logging
from typing import Dict, List

import pytesseract

from PIL import Image

logger = logging.getLogger(__name__)


DEFAULT_Y_TOLERANCE = 12
DEFAULT_BINARY_THRESHOLD = 145
TESSERACT_LANG = "eng+deu"
TESSERACT_PSM = 6


def _merge_line_tokens(tokens: List[Dict[str, int | str]]) -> str:
    """Merge tokens on a single visual line into a readable string.

    This tries to fix common OCR artifacts on receipts, such as:
    - Splitting decimals into three tokens: "12" "," "34" -> "12,34"
    - Splitting currency symbols: "12,34" "€" -> "12,34€"
    """

    if not tokens:
        return ""

    merged: List[str] = []
    i = 0

    while i < len(tokens):
        current_text = str(tokens[i]["text"])

        # Merge patterns like: 12 , 34  ->  12,34   or  12 . 34  ->  12.34
        if i + 2 < len(tokens):
            next_text = str(tokens[i + 1]["text"])
            third_text = str(tokens[i + 2]["text"])

            if (
                next_text in {",", "."}
                and current_text.replace(",", "").replace(".", "").isdigit()
                and third_text.isdigit()
            ):
                merged.append(f"{current_text}{next_text}{third_text}")
                i += 3
                continue

        # Merge currency symbol / code directly after an amount: 12,34  € -> 12,34€
        if i + 1 < len(tokens):
            next_text = str(tokens[i + 1]["text"])
            if next_text in {"€", "EUR", "eur"} and any(ch.isdigit() for ch in current_text):
                merged.append(f"{current_text}{next_text}")
                i += 2
                continue

        merged.append(current_text)
        i += 1

    return " ".join(merged)


def group_tokens_by_line(tokens: List[Dict[str, int | str]], y_tolerance: int = DEFAULT_Y_TOLERANCE) -> List[str]:
    """Group OCR tokens into visual lines.

    We cluster tokens by the vertical centre of their bounding boxes so that
    wide receipts with right-aligned prices (e.g. "...          33,74") end
    up on a single logical line instead of being split into narrow columns.
    """

    if not tokens:
        return []

    enriched: List[Dict[str, int | str]] = []
    for token in tokens:
        top = int(token["top"])
        height = int(token.get("height", 0))
        center_y = top + (height / 2.0 if height else 0)
        # Copy token so we don't mutate the original list unexpectedly
        enriched.append({**token, "_center_y": center_y})

    # Sort by vertical centre so tokens from the same printed row stay close
    enriched.sort(key=lambda t: t["_center_y"])

    lines: List[List[Dict[str, int | str]]] = []

    for token in enriched:
        placed = False
        for line in lines:
            # Use the average centre of the existing line as its reference
            line_center = sum(t["_center_y"] for t in line) / len(line)
            if abs(token["_center_y"] - line_center) <= y_tolerance:
                line.append(token)
                placed = True
                break

        if not placed:
            lines.append([token])

    # Within each visual line, sort left-to-right and apply token merging
    result: List[str] = []
    for line in lines:
        ordered = sorted(line, key=lambda t: t["left"])
        result.append(_merge_line_tokens(ordered))

    return result

def process_image(image_path: str) -> List[Dict[str, int | str]]:
    tokens: List[Dict[str, int | str]] = []

    try:
        with Image.open(image_path) as image:
            grayscale = image.convert("L")
            binary = grayscale.point(
                lambda x: 0 if x < DEFAULT_BINARY_THRESHOLD else 255,
                "1",
            )
            data = pytesseract.image_to_data(
                binary,
                # Many receipts are mixed English/German; enable both to
                # improve recognition of store names and item descriptions.
                lang=TESSERACT_LANG,
                config=f"--psm {TESSERACT_PSM}",
                output_type=pytesseract.Output.DICT,
            )


        for index, text in enumerate(data.get("text", [])):
            cleaned = text.strip()
            if not cleaned:
                continue

            tokens.append(
                {
                    "text": cleaned,
                    "top": data["top"][index],
                    "left": data["left"][index],
                    "height": data["height"][index],
                }
            )
    except Exception as exc:  # pragma: no cover - defensive log
        logger.error("Error processing image: %s", exc)
        return []

    return tokens
