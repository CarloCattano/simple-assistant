import asyncio
import base64
import html
import logging
import re
import wave
from typing import Optional

import requests

from config import GEMINI_KEY

logger = logging.getLogger(__name__)


TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{TTS_MODEL}:generateContent"
)

DEFAULT_TTS_OUTPUT = "tts.raw"
TTS_TIMEOUT_SECONDS = 30

VOICE_NAME = "Kore"
CHANNELS = 1  # mono
SAMPLE_WIDTH_BYTES = 2  # 16-bit samples
SAMPLE_RATE_HZ = 24000  # 24 kHz


def clean_text_for_tts(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"[^a-zA-Z0-9\s.,?!:]", "", text)
    # text = re.sub(r"\s+", " ", text)  # Remove multiple spaces

    logger.info(f"\nCleaned text for TTS: {text}\n")
    return text.strip()


def _generate_tts_file(text: str, output_filename: str = DEFAULT_TTS_OUTPUT) -> Optional[str]:
    text = clean_text_for_tts(text)

    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": VOICE_NAME}
                }
            },
        },
        "model": TTS_MODEL,
    }

    try:
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_KEY,
        }

        response = requests.post(
            TTS_URL,
            headers=headers,
            json=body,
            timeout=TTS_TIMEOUT_SECONDS,
        )
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
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH_BYTES)
            wf.setframerate(SAMPLE_RATE_HZ)
            wf.writeframes(pcm_data)

        return output_filename

    except Exception as e:
        logger.error(f"TTS request failed: {e}")
        return None


async def synthesize_speech(text: str, output_filename: str = DEFAULT_TTS_OUTPUT):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _generate_tts_file, text, output_filename)

def synthesize_speech_sync(text: str, output_filename: str = DEFAULT_TTS_OUTPUT) -> Optional[str]:
    return _generate_tts_file(text, output_filename)
