
# utils/user_prefs.py
import json
import os
from typing import Dict

PREFS_FILE = "user_preferences.json"
_user_preferences: Dict[str, Dict] = {}

def load_preferences():
    """Loads user preferences from the JSON file."""
    global _user_preferences
    if os.path.exists(PREFS_FILE):
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            _user_preferences = json.load(f)
    else:
        _user_preferences = {}

def save_preferences():
    """Saves the current user preferences to the JSON file."""
    with open(PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(_user_preferences, f, indent=2)

def set_short_mode(user_id: int, enabled: bool):
    """Sets the short mode preference for a given user."""
    user_id_str = str(user_id)
    if user_id_str not in _user_preferences:
        _user_preferences[user_id_str] = {}
    _user_preferences[user_id_str]['short_mode'] = enabled
    save_preferences()

def get_short_mode(user_id: int) -> bool:
    """Gets the short mode preference for a given user."""
    user_id_str = str(user_id)
    return _user_preferences.get(user_id_str, {}).get('short_mode', False)

# Load preferences when the module is imported
load_preferences()
