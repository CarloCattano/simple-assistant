import os
import requests
import unittest
from unittest import TestCase

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv('../.env')

gemmini_key = os.getenv('GEMINI_API_KEY')
import os
import unittest
import requests

class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        self.gemini_key = gemmini_key
        self.ollama_url = "http://localhost:11434/api/generate"

    def test_gemini_text_generator(self):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}"

        payload = {
            "contents": [{"parts": [{"text": "Hello from test!"}]}]
        }
        response = requests.post(url, json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn('candidates', response.json())
        # gemini text generator works
        self.assertGreater(len(response.json()['candidates']), 0)


    def test_text_to_speech(self):
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.gemini_key}"
        payload = {
            "input": {"text": "Hello from test!"},
            "voice": {"languageCode": "en-US", "ssmlGender": "FEMALE"},
            "audioConfig": {"audioEncoding": "MP3"}
        }
        response = requests.post(url, json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn('audioContent', response.json())
        # text to speech works messsage
        self.assertIsInstance(response.json()['audioContent'], str)

    def test_ollama_endpoint(self):
        data = {
            "model": "llama3.2",
            "prompt": "Hello, world!",
            "stream": False
        }
        response = requests.post(self.ollama_url, json=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("response", response.json())
        # success message for ollama test
        self.assertGreater(len(response.json()['response']), 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
