from typing import Any, Optional

from config import LLM_PROVIDER
from services.gemini import handle_user_message
from services.generate import generate_content
from utils.logger import logger


class ConversationManager:
    """Central entry point for generating LLM replies.

    This hides provider-specific details (Gemini vs Ollama) behind a simple
    `generate_reply` API so handlers don't need to know about backends.
    Provider-specific history is still managed by the underlying services.
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        self._provider = (provider or LLM_PROVIDER or "").strip().lower()

    @property
    def provider(self) -> str:
        return self._provider

    def is_ollama(self) -> bool:
        return self.provider == "ollama"

    def generate_reply(self, user_id: Optional[int], prompt: str) -> str:
        provider = self.provider

        if provider == "gemini":
            return handle_user_message(user_id, prompt)

        if provider == "ollama":
            return generate_content(prompt)

        raise RuntimeError("LLM provider is not configured. Enable Gemini or Ollama.")

    def summarize_tool_output(self, mode: str, ai_output: str, tool_info: Any) -> str:
        """Return tool output as-is.

        Ollama already produces a TL;DR in call_tool_with_tldr; avoiding a
        second summarization call here keeps tool interactions snappier.
        """
        return ai_output


# Module-level singleton used by handlers.
conversation_manager = ConversationManager()
