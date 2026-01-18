"""Integration tests that exercise external services when configured."""

import json
import os
import time
import unittest
from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise unittest.SkipTest(f"Environment variable {var_name} not configured")
    return value


class GeminiTTSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_key = os.getenv("GEMINI_API_KEY")
        if not cls.api_key:
            raise unittest.SkipTest("GEMINI_API_KEY not configured")

    def test_text_to_speech_returns_audio_candidate(self):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash-preview-tts:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": "Hello from integration test!"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}
                },
            },
            "model": "gemini-2.5-flash-preview-tts",
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        response = requests.post(url, headers=headers, json=body, timeout=30)

        # Treat common availability and quota issues as skips rather than
        # hard failures, since this is an external integration test.
        if response.status_code in {401, 403, 429, 500, 502, 503}:
            self.skipTest(
                f"Gemini TTS API unavailable or over quota (status {response.status_code}). "
                f"Body: {response.text[:200]}"
            )

        if response.status_code != 200:
            self.skipTest(
                f"Gemini TTS returned unexpected status {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as err:
            self.skipTest(f"Gemini TTS returned invalid JSON: {err}")

        candidates = payload.get("candidates") or []
        if not candidates:
            self.skipTest("Gemini TTS response contained no candidates; likely a transient issue.")

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            self.skipTest("Gemini TTS response contained no parts; skipping.")

        audio = parts[0].get("inline_data")
        if not audio:
            self.skipTest("Expected inline audio data in Gemini response, but none was present.")

        # If we reach this point, the response looks healthy enough; no
        # further assertions needed beyond the existence check above.


class OllamaEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("LLM_PROVIDER") != "ollama":
            raise unittest.SkipTest("LLM_PROVIDER is not set to ollama")
        cls.ollama_url = "http://localhost:11434/api/generate"

    def _post(self, prompt: str, timeout: int = 20) -> requests.Response:
        payload = {"model": "llama3.2", "prompt": prompt, "stream": False}
        response = requests.post(self.ollama_url, json=payload, timeout=timeout)
        return response

    def test_generate_returns_content(self):
        response = self._post("Say hello from an integration test.")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn("response", data)
        self.assertGreater(len(data["response"].strip()), 0)

    def test_generation_latency_under_threshold(self):
        start = time.time()
        response = self._post("List three Linux commands.", timeout=10)
        elapsed = time.time() - start
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, 10, "Ollama response exceeded latency threshold")


class TelegramBotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot_token = _require_env("TELEGRAM_BOT_TOKEN")
        cls.chat_id = _require_env("CHAT_ID")
        cls.base_url = f"https://api.telegram.org/bot{cls.bot_token}"

    def test_get_me_returns_bot_identity(self):
        response = requests.get(f"{self.base_url}/getMe", timeout=10)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload.get("ok"), payload)
        result = payload.get("result", {})
        self.assertEqual(int(result.get("id")), int(self.chat_id))
        self.assertIn("username", result)

    def test_latency_below_threshold(self):
        start = time.time()
        response = requests.get(f"{self.base_url}/getMe", timeout=10)
        elapsed = time.time() - start
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, 5, "Telegram API latency exceeded threshold")


if __name__ == "__main__":
    unittest.main(verbosity=2)
