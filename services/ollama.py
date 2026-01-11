import json
import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ollama import chat
from tools import load_tools
from config import SYSTEM_PROMPT
from utils import logger

CONTENT_REPORTER_SCRIPT_PROMPT = (
    "Rewrite that summary into two energetic, fast-paced sentences that stay factually accurate,"
    " but sound like a sarcastic UK newscaster with playful current-event jokes."
    " Respond ONLY with the rewritten script—no prefixes, explanations, or quotes."
    "add [histerically] or [excitedly], !! exclamations or <em> tags where appropriate to enhance the tone. "
)

COMMAND_TRANSLATOR_SYSTEM_PROMPT = (
    "You convert natural language requests into a single Linux shell command."
    " Respond with the command only, no explanations, prompts, or markdown fences."
)

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

MODEL_NAME = "llama3.2"

available_functions = load_tools()

logger.info(
    f"Loaded {len(available_functions)} tools for Ollama. {list(available_functions.keys())}"
)

TOOL_MODE = False
TOOL_ENABLE_TRIGGERS = ["tool", "use", "tools", "run", "execute", "call"]

EVENT_LOG_LIMIT = 200
MAX_EVENT_TEXT = 400

_event_log: deque[Dict[str, Any]] = deque(maxlen=EVENT_LOG_LIMIT)


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
    _record_event("user", prompt)

    try:
        use_tools, matched_tools = evaluate_tool_usage(prompt)
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
                    logger.warn(f"Tool {tool.function.name} not found in available functions.")

        reply = response.message.content
        history.append({"role": "assistant", "content": reply})
        _record_event("assistant", reply)
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
                "content": CONTENT_REPORTER_SCRIPT_PROMPT,
            },
        ]

        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        return response.message.content.strip()
    except Exception as err:
        logger.error(f"Error generating audio script: {err}")
        return None

def call_tool_with_tldr(
    tool_name: str,
    tool_callable,
    history: List[Dict[str, str]],
    **arguments,
) -> str:
    raw_output = tool_callable(**arguments)
    raw_text = _format_tool_output(tool_name, raw_output)

    history.append({"role": "tool", "name": tool_name, "content": raw_text})
    logger.info(f"Tool {tool_name} output:\n{raw_text}")
    _record_event(
        "tool_call",
        f"{tool_name} completed",
        {
            "arguments": _stringify_data(arguments) if arguments else "{}",
            "output": raw_text,
        },
    )

    summary = None
    try:
        summary = tldr_tool_output(tool_name, raw_text)
    except Exception as err:
        logger.error(f"Error generating TLDR for tool {tool_name}: {err}")

    if summary:
        summary_text = summary
        logger.info(f"TLDR ready for {tool_name}: {summary_text}")
        _record_event("tldr", f"{tool_name}: {summary_text}")
        history.append(
            {
                "role": "assistant",
                "content": f"TLDR (from {tool_name}): {summary_text}",
            }
        )
        try:
            audio_script = build_audio_script(summary_text) or summary_text
            logger.info(
                f"Queued TLDR audio script for {tool_name}: {audio_script}"
            )
            _set_last_tool_audio(
                {
                    "summary": summary_text,
                    "tool_name": tool_name,
                    "script": audio_script,
                }
            )
            _record_event("audio_queue", f"Queued TLDR audio for {tool_name}")
        except Exception as audio_err:
            logger.error(f"Error building audio script for tool {tool_name}: {audio_err}")

        return f"{raw_text}\n\nTLDR: {summary_text}"

    return raw_text


def _format_tool_output(tool_name: str, raw_output: Any) -> str:
    if raw_output is None:
        return "Tool returned no data."

    if isinstance(raw_output, str):
        stripped = raw_output.strip()
        return stripped or "Tool returned an empty response."

    if isinstance(raw_output, dict):
        lines: List[str] = []

        command = raw_output.get("command")
        exit_code = raw_output.get("exit_code")
        stdout = raw_output.get("stdout")
        stderr = raw_output.get("stderr")

        if command:
            lines.append(f"$ {command}")

        if exit_code is not None:
            lines.append(f"Exit code: {exit_code}")

        if stdout:
            lines.append("Stdout:")
            lines.append(stdout.strip())

        if stderr:
            lines.append("Stderr:")
            lines.append(stderr.strip())

        if lines:
            return "\n".join(lines).strip()

        try:
            return json.dumps(raw_output, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            return str(raw_output)

    if isinstance(raw_output, (list, tuple, set)):
        return "\n".join(str(item) for item in raw_output) or "Tool returned an empty list."

    return str(raw_output)

def _get_or_create_user_id() -> str:
    if not hasattr(_thread_local, "user_id"):
        _thread_local.user_id = str(uuid.uuid4())
    return _thread_local.user_id


def run_tool_direct(
    tool_identifier: str, parameters: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    parameters = parameters or {}

    resolved = _resolve_tool_entry(tool_identifier)
    if not resolved:
        logger.warn(f"Direct tool request failed: {tool_identifier} not found")
        return None

    tool_identifier, entry = resolved

    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])
    _record_event(
        "tool_request",
        f"Direct tool request: {tool_identifier}",
        {"parameters": _stringify_data(parameters)},
    )
    history.append(
        {
            "role": "user",
            "content": f"[Direct tool request] {tool_identifier} with {parameters}",
        }
    )

    try:
        return call_tool_with_tldr(
            tool_identifier,
            entry["function"],
            history,
            **parameters,
        )
    except TypeError as err:
        logger.error(
            f"Error executing direct tool {tool_identifier} with {parameters}: {err}"
        )
        return f"Error executing tool {tool_identifier}: {err}"


def _resolve_tool_entry(
    tool_identifier: str,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    identifier_lower = tool_identifier.lower()

    entry = available_functions.get(tool_identifier)
    if entry:
        return tool_identifier, entry

    for key, candidate in available_functions.items():
        candidate_name = candidate.get("name", "")
        candidate_name_lower = candidate_name.lower() if candidate_name else ""
        function_name = candidate.get("function").__name__
        function_name_lower = function_name.lower()
        trigger_matches = any(
            isinstance(trigger, str) and trigger.lower() == identifier_lower
            for trigger in candidate.get("triggers", [])
        )

        if identifier_lower in (
            candidate_name_lower,
            function_name_lower,
        ) or trigger_matches:
            return key, candidate

    return None


def resolve_tool_identifier(
    tool_identifier: str,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    return _resolve_tool_entry(tool_identifier)


def translate_instruction_to_command(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        return None

    messages = [
        {"role": "system", "content": COMMAND_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        command = (response.message.content or "").strip()

        if command.lower().startswith("command:"):
            command = command.split(":", 1)[1].strip()

        for fence in ("```", "'''", '"', "'"):
            if command.startswith(fence) and command.endswith(fence):
                command = command[len(fence) : -len(fence)].strip()

        if "\n" in command:
            command = command.splitlines()[0].strip()

        command = command.strip("`\"'")

        return command or None
    except Exception as err:
        logger.error(f"Unable to translate instruction to command: {err}")
        return None


def get_recent_history(limit: int = 15) -> List[Dict[str, Any]]:
    user_id = _get_or_create_user_id()
    history = user_histories.get(user_id, [])
    if limit <= 0:
        return history
    return history[-limit:]


def get_recent_events(limit: int = 20) -> List[Dict[str, Any]]:
    if limit <= 0:
        return list(_event_log)
    return list(_event_log)[-limit:]


def _record_event(kind: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    entry = {
        "time": datetime.utcnow().strftime("%H:%M:%S"),
        "kind": kind,
        "message": _truncate_event_text(message),
    }

    if extra:
        entry["extra"] = {
            key: _truncate_event_text(str(value)) for key, value in extra.items()
        }

    _event_log.append(entry)
    extra_txt = (
        " "
        + " ".join(f"{k}={v}" for k, v in entry.get("extra", {}).items())
        if entry.get("extra")
        else ""
    )
    logger.info(f"[event] {entry['time']} {kind}: {entry['message']}{extra_txt}")


def _truncate_event_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_EVENT_TEXT:
        return text
    return text[: MAX_EVENT_TEXT - 3] + "..."


def _stringify_data(data: Any) -> str:
    try:
        return json.dumps(data, sort_keys=True)
    except (TypeError, ValueError):
        return str(data)


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
