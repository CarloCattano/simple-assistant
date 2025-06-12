import threading
import uuid
from typing import Dict, List

from ollama import chat
from tools import load_tools

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

MODEL_NAME = "llama3.2"
#"deepseek-r1:1.5b"

available_functions = load_tools()

TOOL_MODE = False

TOOL_ENABLE_TRIGGERS = ["tool", "use tools", "tools"]

def should_use_tools(prompt: str) -> bool:
    lower_prompt = prompt.lower()


    if not any(trigger in lower_prompt for trigger in TOOL_ENABLE_TRIGGERS):
        return False

    for tool in available_functions.values():
        for trigger in tool['triggers']:
            if trigger in lower_prompt:
                return True

    if TOOL_MODE:
        return True
    
    return False

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
        use_tools = should_use_tools(prompt)

        response = chat(
            model=MODEL_NAME,
            messages=history,
            keep_alive=0,
            tools=[entry['function'] for entry in available_functions.values()] if use_tools else []
        )

        if response.message.tool_calls:
            for tool in response.message.tool_calls:
                func_entry = available_functions.get(tool.function.name)
                if func_entry:
                    output = func_entry['function'](**tool.function.arguments)
                    output = f"{tool.function.name}: \n{output}"
                    history.append({'role': 'assistant', 'content': output})
                    return output
                else:
                    print(f"Function {tool.function.name} not found")

        reply = filter_thinking_output(response.message.content)
        history.append({'role': 'assistant', 'content': reply})
        return reply

    except Exception as e:
        return f"Error calling Ollama API: {e}"


def clear_history():
    user_id = _get_or_create_user_id()
    user_histories.pop(user_id, None)

