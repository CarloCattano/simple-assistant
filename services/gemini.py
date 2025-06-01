# services/gemini.py
import requests

from config import GEMINI_KEY

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

def generate_content(prompt: str) -> str:
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
        if not candidates:
            return "No response from Gemini."
        return candidates[0]["content"]["parts"][0]["text"]
    except requests.RequestException as e:
        return f"Error calling Gemini API: {e}"

