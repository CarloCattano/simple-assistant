import pytesseract

from PIL import Image


def group_tokens_by_line(tokens, y_tolerance=10):
    lines = []
    current_line = []
    current_y = None

    for t in sorted(tokens, key=lambda x: x["top"]):
        if current_y is None or abs(t["top"] - current_y) <= y_tolerance:
            current_line.append(t)
            current_y = t["top"] if current_y is None else current_y
        else:
            lines.append(current_line)
            current_line = [t]
            current_y = t["top"]

    if current_line:
        lines.append(current_line)

    joined_lines = [
        " ".join(word["text"] for word in sorted(line, key=lambda x: x["left"]))
        for line in lines
    ]

    return joined_lines


def process_image(image_path: str) -> str:
    try:
        image = Image.open(image_path)
        image = image.convert("L")  # grayscale
        image = image.point(lambda x: 0 if x < 145 else 255, "1")
        image.show()
        data = pytesseract.image_to_data(
            image, lang="deu", config="--psm 6", output_type=pytesseract.Output.DICT
        )

        tokens = []
        for i, txt in enumerate(data["text"]):
            if txt.strip():
                tokens.append(
                    {
                        "text": txt,
                        "top": data["top"][i],
                        "left": data["left"][i],
                        "height": data["height"][i],
                    }
                )
        return tokens

    except Exception as e:
        print(f"Error processing image: {e}")
        return ""
