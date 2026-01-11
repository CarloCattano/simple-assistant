import threading
import uuid
from typing import Dict, List, Optional, Tuple

from ollama import chat
from tools import load_tools
from config import SYSTEM_PROMPT
from services.tts import synthesize_speech_sync

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

MODEL_NAME = "llama3.2"

available_functions = load_tools()

print(
    f"Loaded {len(available_functions)} tools for Ollama. {list(available_functions.keys())}"
)

TOOL_MODE = False
TOOL_ENABLE_TRIGGERS = ["tool", "use", "tools", "run", "execute", "call"]


def evaluate_tool_usage(prompt: str) -> Tuple[bool, Dict[str, dict]]:
    assert isinstance(prompt, str)
    lower_prompt = prompt.lower()

    matched_tools = {
        name: entry
        for name, entry in available_functions.items()
        if any(trigger in lower_prompt for trigger in entry.get("triggers", []))
    }

    should_use = bool(matched_tools) or TOOL_MODE or any(
        trigger in lower_prompt for trigger in TOOL_ENABLE_TRIGGERS
    )

    return should_use, matched_tools



def generate_content(prompt: str) -> str:
    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])

    # Add user message
    history.append({"role": "user", "content": prompt})

    try:
        use_tools, matched_tools = evaluate_tool_usage(prompt)
        print(f"Using tools: {use_tools}")
        # Prepend system prompt if history is empty
        messages = history
        if len(history) == 1:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        tool_pool = matched_tools if matched_tools else available_functions
        tool_callables = (
            [entry["function"] for entry in tool_pool.values()] if use_tools else []
        )

        response = chat(
            model=MODEL_NAME,
            messages=messages,
            keep_alive=0,
            tools=tool_callables,
        )

        if response.message.tool_calls:
            for tool in response.message.tool_calls:
                func_entry = available_functions.get(tool.function.name)
                if func_entry and (
                    not matched_tools or tool.function.name in matched_tools
                ):
                    output = call_tool_with_tldr(
                        tool.function.name,
                        func_entry["function"],
                        history,
                        **tool.function.arguments,
                    )
                    return output
                else:
                    print(f"Function {tool.function.name} not found")

        reply = response.message.content
        history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        return f"Error calling Ollama API: {e}"

def tldr_tool_output(tool_name: str, output: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "assistant",
            "content": f"Tool {tool_name} returned the following data:\n{output}",
        },
        {
            "role": "user",
            "content": "Summarize the key points in no more than two sentences.",
        },
    ]
    response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
    
    return response.message.content


def build_audio_script(summary_text: str) -> Optional[str]:
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "assistant",
                "content": f"Here is the TLDR summary you produced earlier: {summary_text}",
            },
            {
                "role": "user",
                "content": (
                    "Rewrite that summary into two energetic, fast-paced sentences that stay factually accurate,"
                    " but sound like a sarcastic UK newscaster with playful current-event jokes."
                    " Respond ONLY with the rewritten script—no prefixes, explanations, or quotes."
                ),
            },
        ]

        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        return response.message.content.strip()
    except Exception as err:
        print(f"Unable to build audio script: {err}")
        return None

def call_tool_with_tldr(
    tool_name: str,
    tool_callable,
    history: List[Dict[str, str]],
    **arguments,
) -> str:
    raw_output = tool_callable(**arguments)
    raw_text = f"{raw_output}"

    history.append({"role": "tool", "name": tool_name, "content": raw_text})

    summary = None
    try:
        summary = tldr_tool_output(tool_name, raw_text)
    except Exception as err:
        print(f"Unable to summarize tool output for {tool_name}: {err}")

    if summary:
        summary_text = summary
        history.append(
            {
                "role": "assistant",
                "content": f"TLDR (from {tool_name}): {summary_text}",
            }
        )
        try:
            safe_name = "".join(
                ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in tool_name
            )
            audio_filename = f"{safe_name or 'tool'}_{uuid.uuid4().hex[:8]}.raw"
            audio_script = build_audio_script(summary_text) or summary_text
            audio_path = synthesize_speech_sync(audio_script, audio_filename)
            if audio_path:
                _set_last_tool_audio(
                    {
                        "path": audio_path,
                        "summary": summary_text,
                        "tool_name": tool_name,
                    }
                )
        except Exception as audio_err:
            print(f"Unable to generate audio for {tool_name}: {audio_err}")
        return f"{raw_text}\n\nTLDR: {summary_text}"

    return raw_text

def _get_or_create_user_id() -> str:
    if not hasattr(_thread_local, "user_id"):
        _thread_local.user_id = str(uuid.uuid4())
    return _thread_local.user_id

def clear_history():
    user_id = _get_or_create_user_id()
    user_histories.pop(user_id, None)
    if hasattr(_thread_local, "last_tool_audio"):
        delattr(_thread_local, "last_tool_audio")


def _set_last_tool_audio(payload: Dict[str, str]) -> None:
    _thread_local.last_tool_audio = payload


def pop_last_tool_audio() -> Optional[Dict[str, str]]:
    payload = getattr(_thread_local, "last_tool_audio", None)
    if hasattr(_thread_local, "last_tool_audio"):
        delattr(_thread_local, "last_tool_audio")
    return payload
