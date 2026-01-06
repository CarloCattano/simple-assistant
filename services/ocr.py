import pytesseract

from PIL import Image

def process_image(image_path: str) -> str:
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        print(f"OCR extracted text: {text}")
        return text
    except Exception as e:
        print(f"Error processing image: {e}")
        return ""
