"""
Centralized in-memory history and event manager for all users.
Stores prompts, tool invocations, and assistant responses per user.
"""
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

HISTORY_LIMIT = 50
EVENT_LOG_LIMIT = 200

class HistoryManager:
    def __init__(self):
        self.user_histories: Dict[str, List[Dict[str, Any]]] = {}
        self.event_log: deque = deque(maxlen=EVENT_LOG_LIMIT)

    def record_prompt(self, user_id: str, prompt: str):
        self._ensure_user(user_id)
        self.user_histories[user_id].append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat(),
        })

    def record_tool(self, user_id: str, tool_name: str, parameters: dict):
        self._ensure_user(user_id)
        self.user_histories[user_id].append({
            "role": "tool",
            "tool_name": tool_name,
            "parameters": parameters,
            "timestamp": datetime.now().isoformat(),
        })

    def record_response(self, user_id: str, content: str):
        self._ensure_user(user_id)
        self.user_histories[user_id].append({
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })

    def get_history(self, user_id: str, limit: int = HISTORY_LIMIT) -> List[Dict[str, Any]]:
        self._ensure_user(user_id)
        return self.user_histories[user_id][-limit:]

    def clear_history(self, user_id: str):
        self.user_histories[user_id] = []

    def record_event(self, user_id: str, kind: str, message: str, extra: Optional[dict] = None):
        event = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "kind": kind,
            "message": message,
        }
        if extra:
            event["extra"] = extra
        self.event_log.append(event)

    def get_events(self, limit: int = 25) -> List[Dict[str, Any]]:
        return list(self.event_log)[-limit:]

    def clear_events(self):
        self.event_log.clear()

    def _ensure_user(self, user_id: str):
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []

# Singleton instance
history_manager = HistoryManager()
