import base64

import requests

from config import GEMINI_KEY


def encode_audio(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

async def transcribe(file_path: str):
    data = encode_audio(file_path)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    
    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "audio/ogg", "data": data}},
                {"text": "Please transcribe this audio."}
            ]
        }]
    }

    response = requests.post(url, headers={"Content-Type": "application/json"}, json=body)
    return response.json()

