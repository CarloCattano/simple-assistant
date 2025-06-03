import threading
import uuid
from typing import Dict, List

from ollama import chat

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

MODEL_NAME = "llama3.2"
#"deepseek-r1:1.5b"  # 

# filter out the deepseek thinking output in a string
# <think>...</think>
def filter_thinking_output(text: str) -> str:
    start_tag = "<think>"
    end_tag = "</think>"
    
    start_index = text.find(start_tag)
    end_index = text.find(end_tag, start_index + len(start_tag))
    
    if start_index != -1 and end_index != -1:
        return text[:start_index] + text[end_index + len(end_tag):]
    
    return text

def _get_or_create_user_id() -> str:
    if not hasattr(_thread_local, "user_id"):
        _thread_local.user_id = str(uuid.uuid4())
    return _thread_local.user_id

def generate_content(prompt: str) -> str:
    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])

    # Add user message
    history.append({'role': 'user', 'content': prompt})

    try:
        response = chat(
            model=MODEL_NAME,
            messages=history,
            keep_alive=0,
        )

        reply = filter_thinking_output(response.message.content)

        history.append({'role': 'assistant', 'content': reply})
    
        return reply

    except Exception as e:
        return f"Error calling Olama API: {e}"

def clear_history():
    user_id = _get_or_create_user_id()
    user_histories.pop(user_id, None)

