import base64
import html
import logging
import re
import uuid
import wave
import io
import requests

from config import GEMINI_KEY

logger = logging.getLogger(__name__)


def clean_text_for_tts(text: str) -> str:
    text = html.unescape(text) 
    text = re.sub(r"[^a-zA-Z0-9\s.,?!:]", "", text) 
    # allow [ ] for google tts controls 
    # text = re.sub(r"[^a-zA-Z0-9\s.,?!:\[\]]", "", text)  # Remove unwanted characters

    text = re.sub(r"\s+", " ", text) #Remove multiple spaces

    print(text)
    return text.strip()

async def synthesize_speech(text: str, output_filename: str = 'tts.raw'):

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"

    text = clean_text_for_tts(text)

    body = {
        "contents": [
            {
                "parts": [
                    {"text": text}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": "Kore"
                    }
                }
            }
        },
        "model": "gemini-2.5-flash-preview-tts",
    }

    try:
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_KEY,
        }

        response = requests.post(url, headers=headers, json=body, timeout=30)
        response.raise_for_status()

        data = response.json()
        audio_b64 = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("inlineData", {})
            .get("data")
        )

        if not audio_b64:
          logger.error("Missing audio data in response.")
          return None

        pcm_data = base64.b64decode(audio_b64)
        output_filename = output_filename.replace(".raw", ".wav")

        with wave.open(output_filename, "wb") as wf:
            wf.setnchannels(1)        # mono
            wf.setsampwidth(2)        # 16-bit samples
            wf.setframerate(24000)    # 24 kHz
            wf.writeframes(pcm_data)

        return output_filename

    except Exception as e:
        logger.error(f"TTS request failed: {e}")
        return None

