import base64

import requests

from config import GEMINI_KEY


STT_MODEL = "gemini-2.0-flash"
STT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{STT_MODEL}:generateContent?key={GEMINI_KEY}"
)

MIME_TYPE_OGG = "audio/ogg"
STT_PROMPT = "Please transcribe this audio."


def encode_audio(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def transcribe(file_path: str):
    data = encode_audio(file_path)
    body = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": MIME_TYPE_OGG, "data": data}},
                    {"text": STT_PROMPT},
                ]
            }
        ]
    }

    response = requests.post(
        STT_URL,
        headers={"Content-Type": "application/json"},
        json=body,
    )
    return response.json()
