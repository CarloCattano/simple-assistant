import os, time
import requests
import unittest
from unittest import TestCase

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv("../.env")

gemmini_key = os.getenv("GEMINI_API_KEY")
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")

import os
import unittest
import requests


class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        self.gemini_key = gemmini_key
        self.ollama_url = "http://localhost:11434/api/generate"

    def test_text_to_speech(self):

        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"

        body = {
            "contents": [{"parts": [{"text": "Hello from test!"}]}],
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
            "x-goog-api-key": self.gemini_key,
        }

        response = requests.post(url, headers=headers, json=body, timeout=30)
        self.assertEqual(response.status_code, 200)
        self.assertIn("candidates", response.json())

    def test_ollama_endpoint(self):
        data = {"model": "llama3.2", "prompt": "Hello, world!", "stream": False}
        response = requests.post(self.ollama_url, json=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("response", response.json())
        # success message for ollama test
        self.assertGreater(len(response.json()["response"]), 0)

    def test_telegram_bot_responds(self):
        url = f"https://api.telegram.org/bot{telegram_bot_token}/getMe"
        response = requests.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ok", response.json())
        self.assertIn("result", response.json())
        self.assertIn("id", response.json()["result"])
        self.assertEqual(response.json()["result"]["id"], int(chat_id))

    def test_telegram_answer_speed(self):
        url = f"https://api.telegram.org/bot{telegram_bot_token}/getMe"
        timeStarted = time.time()
        response = requests.get(url, timeout=5)
        timeEnded = time.time()
        self.assertLess(timeEnded - timeStarted, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
