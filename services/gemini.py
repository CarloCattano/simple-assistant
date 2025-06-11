# services/gemini.py
import json
import os

import requests

from config import GEMINI_KEY
from utils.logger import RED_COL, RST

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

CONVERSATION_FILE = "user_conversations.json"

def save_conversations():
    # if logs grow bigger than 40 elements, pop the odest out
    global user_conversations
    if len(user_conversations) > 40:
        print(f"{RED_COL}Trimming logs{RST} ")
        keys_to_remove = list(user_conversations.keys())[:len(user_conversations) - 20]
        for key in keys_to_remove:
            del user_conversations[key]

    # Save the current conversations to a JSON file
    with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
        json.dump(user_conversations, f, ensure_ascii=False, indent=2)

def clear_conversations(delete_usr_id):
    global user_conversations
    key = str(delete_usr_id)  
    if key in user_conversations:
        del user_conversations[key]
        save_conversations()
        return True
    return False

def load_conversations():
    global user_conversations
    if os.path.exists(CONVERSATION_FILE):
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            user_conversations = json.load(f)
    else:
        user_conversations = {}

load_conversations()

def handle_user_message(user_id, message_text):
    key = str(user_id)  # Convert to string for JSON-safe key
    history = user_conversations.get(key, [])

    history.append({"role": "user", "parts": [{"text": message_text}]})

    reply = generate_content(message_text, history=history[:-1])

    history.append({"role": "model", "parts": [{"text": reply}]})

    user_conversations[key] = history
    save_conversations()
    return reply

def generate_content(prompt: str, history: list = None) -> str:
    """
    prompt: Current user message
    history: Optional previous messages (each with 'role' and 'parts')
    """
    # Start from history if exists, otherwise empty list
    contents = history[:] if history else []

    # Add current user message
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents
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

