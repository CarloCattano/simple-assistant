import base64
import html
import logging
import os
import re
import uuid

import requests

from config import GEMINI_KEY

logger = logging.getLogger(__name__)


def clean_text_for_tts(text: str) -> str:
    text = html.unescape(text) 
    text = re.sub(r"[^a-zA-Z0-9\s.,?!:]", "", text) 
    text = re.sub(r"\s+", " ", text) #Remove multiple spaces

    return text.strip()

async def synthesize_speech(text: str, output_filename: str = None):
    if output_filename is None:
        output_filename = f"tts_{uuid.uuid4()}.mp3"
    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={GEMINI_KEY}"

    text = clean_text_for_tts(text)

    body = {
        "input": {"text": text},
        "voice": {"languageCode": "en-US", "name": "Zephyr"},
        "audioConfig": {"audioEncoding": "OGG_OPUS"},

    }

    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=body, timeout=30)
        response.raise_for_status()
        audio_b64 = response.json().get("audioContent")
        if not audio_b64:
            logger.error("Missing audioContent in response.")
            return None

        with open(output_filename, "wb") as f:
            f.write(base64.b64decode(audio_b64))
        return output_filename
    
    except Exception as e:
        logger.error(f"TTS request failed: {e}")
        return None

