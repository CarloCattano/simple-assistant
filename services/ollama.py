import json
import threading
import uuid
from collections import deque
from datetime import datetime
from logging import DEBUG, Logger
from typing import Any, Dict, List, Optional, Tuple

import os
import re
from ollama import chat as _ollama_chat
from tools import load_tools
from config import SYSTEM_PROMPT
from utils import logger
from utils.command_guard import (
    detect_direct_command,
    heuristic_command,
    sanitize_command,
    get_last_sanitize_error,
)

if hasattr(_ollama_chat, "chat"):
    chat = _ollama_chat.chat
else:
    chat = _ollama_chat

CONTENT_REPORTER_SCRIPT_PROMPT = (
    "Rewrite that summary into two energetic, fast-paced sentences that stay factually accurate,"
    " but sound like a sarcastic UK newscaster with playful current-event jokes."
    " Respond ONLY with the rewritten script—no prefixes, explanations, or quotes."
    "add [histerically] or [excitedly], !! exclamations or <em> tags where appropriate to enhance the tone. "
)

COMMAND_TRANSLATOR_SYSTEM_PROMPT = (
    "You convert natural language requests into a single Linux shell command. "
    "Do not replace literal shell commands that the user already wrote with similar ones. "
    "Respond ONLY with the exact command, making sure any quotes are properly closed "
    "(for example: echo \"Hello World\"). "
    "Do not add commentary, shell prompts, explanations, or additional lines. "
    "For requests about listing or inspecting files or directories, prefer safe commands such as 'ls', 'ls -lah', 'ls -lt', or 'find'. "
    "For requests about controlling music playback, prefer 'playerctl' subcommands like 'playerctl play', 'playerctl pause', 'playerctl next', or 'playerctl previous'. "
    "If the request could reasonably be mapped to a read-only command using these tools, you MUST output that command instead of NONE. "
    "Only respond with the single word NONE when it is impossible to infer any safe, non-destructive command."
)

QUERY_TRANSLATOR_SYSTEM_PROMPT = (
    "You receive a user follow-up or instruction plus optional context."
    " Rewrite it into a single concise web search query that will retrieve the requested information."
    " If the user refers to doing the same thing as before, infer the subject from the context provided."
    " Respond with only the search query text—no explanations, quotes, prefixes, or extra lines."
    " If you cannot produce a reasonable query, respond with the single word NONE."
)

# Internal global mapping of thread/session -> UUID
_thread_local = threading.local()

# Maps uuid -> conversation history
user_histories: Dict[str, List[Dict[str, str]]] = {}

MODEL_NAME = "llama3.2"

MAX_HISTORY_LENGTH = 40

available_functions = load_tools()

logger.info(
    f"Loaded {len(available_functions)} tools for Ollama. {list(available_functions.keys())}"
)

TOOL_MODE = False

EVENT_LOG_LIMIT = 200
MAX_EVENT_TEXT = 400

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

_event_log: deque[Dict[str, Any]] = deque(maxlen=EVENT_LOG_LIMIT)

_last_command_translation_error: Optional[str] = None


def _debug_dump(label: str, payload: Any) -> None:
    log_instance = getattr(logger, "logger", None)
    if isinstance(log_instance, Logger):
        if not log_instance.isEnabledFor(DEBUG):
            return
    elif isinstance(logger, Logger):
        log_instance = logger
        if not log_instance.isEnabledFor(DEBUG):
            return
    else:
        return

    try:
        serialized = json.dumps(payload, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = repr(payload)

    if log_instance is not None:
        log_instance.debug(f"[debug] {label}: {serialized}")
    elif hasattr(logger, "debug"):
        logger.debug(f"[debug] {label}: {serialized}")


def evaluate_tool_usage(prompt: str) -> Tuple[bool, Dict[str, dict]]:
    assert isinstance(prompt, str)
    lower_prompt = prompt.lower()

    matched_tools = {
        name: entry
        for name, entry in available_functions.items()
        if any(trigger in lower_prompt for trigger in entry.get("triggers", []))
    }

    should_use = bool(matched_tools) or TOOL_MODE

    return should_use, matched_tools



def generate_content(prompt: str) -> str:
    user_id = _get_or_create_user_id()
    history = user_histories.setdefault(user_id, [])

    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    # Add user message
    history.append({"role": "user", "content": prompt})
    _trim_history(history)
    _record_event("user", prompt)
    _debug_dump(
        "history_after_user",
        {
            "user_id": user_id,
            "entries": history,
        },
    )

    try:
        use_tools, matched_tools = evaluate_tool_usage(prompt)
        _debug_dump(
            "tool_evaluation",
            {
                "prompt": prompt,
                "use_tools": use_tools,
                "matched_tools": list(matched_tools.keys()),
            },
        )
        messages = history

        _debug_dump(
            "chat_request",
            {"messages": messages, "tools": list(available_functions.keys())},
        )

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
        response_payload = (
            response.dict()
            if hasattr(response, "dict")
            else getattr(response, "__dict__", response)
        )
        _debug_dump("chat_response", response_payload)

        if response.message.tool_calls:
            _debug_dump("tool_calls", [call.function.name for call in response.message.tool_calls])
            for tool in response.message.tool_calls:
                func_entry = available_functions.get(tool.function.name)
                if func_entry and (
                    not matched_tools or tool.function.name in matched_tools
                ):
                    _debug_dump(
                        "executing_tool",
                        {
                            "tool": tool.function.name,
                            "arguments": tool.function.arguments,
                        },
                    )
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
        _debug_dump(
            "assistant_reply",
            {
                "user_id": user_id,
                "reply": reply,
                "history_size": len(history),
            },
        )
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
            "content": "Summarize the key points in no more than three sentences.",
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
                "content": f"Here is the summary you produced earlier: {summary_text}",
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
    working_arguments = dict(arguments)

    from services.ollama import translate_instruction_to_query

    if (
        tool_name == "web_search"
        and translate_instruction_to_query
        and isinstance(working_arguments.get("query"), str)
    ):
        query = working_arguments["query"].strip()
        if query:
            translated = translate_instruction_to_query(query)
            if not translated:
                logger.warn("Query translation failed for web_search; aborting tool call.")
                return "I couldn't infer a web search query from that request."
            working_arguments["query"] = translated
    # For the shell_agent, we support a small number of safe retry attempts
    # where we let the LLM suggest alternative commands after failures.
    raw_output: Any
    if tool_name == "shell_agent":
        max_attempts = 3
        attempt = 0
        last_output: Any = None

        from services.ollama import translate_instruction_to_command

        while attempt < max_attempts:
            attempt += 1
            last_output = tool_callable(**working_arguments)

            # shell_agent is expected to return a dict; if it doesn't,
            # just break and use whatever we got.
            if not isinstance(last_output, dict):
                break

            exit_code = last_output.get("exit_code")
            stderr = (last_output.get("stderr") or "").strip()
            stdout = (last_output.get("stdout") or "").strip()

            # Consider it a hard failure if the exit code is non-zero.
            has_error = exit_code not in (0, None)

            # Also treat purely-stderr outputs with common error wording as failures,
            # even when the exit code is zero (many CLIs log to stderr).
            lower_err = stderr.lower()
            if not has_error and stderr and not stdout:
                for marker in ("unknown option", "unrecognized option", "invalid option", "command not found"):
                    if marker in lower_err:
                        has_error = True
                        break

            if not has_error:
                break

            # If we cannot translate instructions to a new command, or if we
            # don't have a textual prompt to refine, stop retrying.
            original_prompt = working_arguments.get("prompt")
            if not isinstance(original_prompt, str) or not translate_instruction_to_command:
                break

            # Ask the LLM for an alternative safe command, taking into account
            # the previous failure. The translator will still run the result
            # through sanitize_command.
            context_instruction = (
                f"{original_prompt}\n\n"
                f"Previous command: {last_output.get('command')!r} "
                f"returned exit_code={exit_code} with stderr: {stderr!r}. "
                "Suggest a different safe single-line shell command that might succeed."
            )

            new_command = translate_instruction_to_command(context_instruction)
            if not new_command or new_command == working_arguments.get("prompt"):
                break

            logger.info(
                f"shell_agent retry {attempt}/{max_attempts}: refining command from {working_arguments.get('prompt')!r} to {new_command!r}"
            )
            working_arguments["prompt"] = new_command

        raw_output = last_output
    else:
        raw_output = tool_callable(**working_arguments)
    raw_text = _format_tool_output(tool_name, raw_output)
    _debug_dump(
        "tool_raw_output",
        {
            "tool": tool_name,
            "arguments": working_arguments,
            "raw_output": raw_output,
        },
    )

    history.append({"role": "tool", "name": tool_name, "content": raw_text})
    logger.info(f"Tool {tool_name} output:\n{raw_text}")

    _record_event(
        "tool_call",
        f"{tool_name} completed",
        {
            "arguments": _stringify_data(working_arguments) if working_arguments else "{}",
            "output": raw_text,
        },
    )
    _debug_dump(
        "history_after_tool",
        {
            "tool": tool_name,
            "history": history,
        },
    )

    if tool_name == "shell_agent":
        logger.info("Skipping TLDR for shell_agent; returning raw tool output only.")
        return raw_text

    summary = None
    try:
        summary = tldr_tool_output(tool_name, raw_text)
    except Exception as err:
        logger.error(f"Error generating TLDR for tool {tool_name}: {err}")

    if summary:
        summary_text = summary
        logger.info(f"TLDR ready for {tool_name}: {summary_text}")
        _record_event("tldr", f"{tool_name}: {summary_text}")
        _debug_dump(
            "tldr_summary",
            {
                "tool": tool_name,
                "summary": summary_text,
            },
        )
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
            _debug_dump(
                "audio_queue_payload",
                {
                    "tool": tool_name,
                    "audio_script": audio_script,
                },
            )
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


def _trim_history(history: List[Dict[str, str]]) -> None:
    """Trim conversation history to a bounded length while preserving system prompt.

    Keeps the first entry (typically the system prompt) and the most recent
    MAX_HISTORY_LENGTH-1 messages.
    """
    if len(history) <= MAX_HISTORY_LENGTH:
        return

    system = history[0:1]
    recent = history[-(MAX_HISTORY_LENGTH - 1) :]
    history[:] = system + recent


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
    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    _record_event(
        "tool_request",
        f"Direct tool request: {tool_identifier}",
        {"parameters": _stringify_data(parameters)},
    )
    _debug_dump(
        "direct_tool_request",
        {
            "tool": tool_identifier,
            "parameters": parameters,
            "history_size": len(history),
        },
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


def _set_last_command_translation_error(reason: Optional[str]) -> None:
    global _last_command_translation_error
    _last_command_translation_error = reason


def get_last_command_translation_error() -> Optional[str]:
    """Return a human-readable reason from the most recent command translation attempt, if any."""

    return _last_command_translation_error


def translate_instruction_to_command(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        _set_last_command_translation_error("instruction was empty")
        return None

    _set_last_command_translation_error(None)
    _debug_dump("command_translation_input", {"instruction": instruction})

    direct = detect_direct_command(instruction)
    if direct:
        _debug_dump("command_translation_direct", direct)
        _set_last_command_translation_error(None)
        return direct

    heuristic = heuristic_command(instruction)
    if heuristic:
        sanitized = sanitize_command(heuristic)
        if sanitized:
            _debug_dump("command_translation_heuristic", sanitized)
            _set_last_command_translation_error(None)
            return sanitized

    messages = [
        {"role": "system", "content": COMMAND_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    _debug_dump("command_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        command = (response.message.content or "").strip()
        _debug_dump("command_translation_response", command)

        if command.lower().startswith("command:"):
            command = command.split(":", 1)[1].strip()

        for fence in ("```", "'''", '"', "'"):
            if command.startswith(fence) and command.endswith(fence):
                command = command[len(fence) : -len(fence)].strip()

        if "\n" in command:
            command = command.splitlines()[0].strip()

        if command.upper() == "NONE":
            _debug_dump(
                "command_translation_none",
                {"instruction": instruction, "reason": "model_returned_NONE"},
            )
            _set_last_command_translation_error("model explicitly replied with NONE (no safe command)")
            return None

        sanitized = sanitize_command(command)
        if sanitized:
            _debug_dump("command_translation_sanitized", sanitized)
            _set_last_command_translation_error(None)
            return sanitized

        # If the command was rejected by sanitize_command (for example due to pipes
        # or other shell operators), try to keep only the leading simple command
        # segment before any such operators and sanitize that instead.
        segments = re.split(r"[;&|]", command, maxsplit=1)
        leading = segments[0].strip() if segments else ""
        if leading and leading != command:
            fallback = sanitize_command(leading)
            if fallback:
                _debug_dump(
                    "command_translation_sanitized_fallback",
                    {
                        "instruction": instruction,
                        "raw_command": command,
                        "fallback_command": fallback,
                    },
                )
                _set_last_command_translation_error(
                    "original suggestion looked unsafe; using only the leading simple command segment"
                )
                return fallback

        sanitize_reason = get_last_sanitize_error() or "sanitize_command rejected the suggested command as unsafe"
        _debug_dump(
            "command_translation_rejected",
            {
                "instruction": instruction,
                "raw_command": command,
                "reason": sanitize_reason,
            },
        )
        _set_last_command_translation_error(sanitize_reason)
        return None
    except Exception as err:
        logger.error(f"Unable to translate instruction to command: {err}")
        _set_last_command_translation_error(f"exception during translation: {err}")
        return None


def translate_instruction_to_query(instruction: str) -> Optional[str]:
    instruction = (instruction or "").strip()
    if not instruction:
        return None

    messages = [
        {"role": "system", "content": QUERY_TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]

    _debug_dump("query_translation_request", messages)

    try:
        response = chat(model=MODEL_NAME, messages=messages, keep_alive=0)
        query = (response.message.content or "").strip()
        _debug_dump("query_translation_response", query)

        if "\n" in query:
            query = query.splitlines()[0].strip()

        for fence in ("`", '"', "'"):
            if query.startswith(fence) and query.endswith(fence):
                query = query[len(fence) : -len(fence)].strip()

        if query.upper() == "NONE":
            return None

        return query
    except Exception as err:
        logger.error(f"Unable to translate instruction to web query: {err}")
        return None


def get_recent_history(limit: int = 15) -> List[Dict[str, Any]]:
    user_id = _get_or_create_user_id()
    history = user_histories.get(user_id, [])
    _debug_dump("history_snapshot", {"user_id": user_id, "limit": limit, "history": history})
    if limit <= 0:
        return history
    return history[-limit:]


def get_recent_events(limit: int = 20) -> List[Dict[str, Any]]:
    _debug_dump("event_log_snapshot", {"limit": limit, "events": list(_event_log)})
    if limit <= 0:
        return list(_event_log)
    return list(_event_log)[-limit:]


def _record_event(kind: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    entry: Dict[str, Any] = {
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
