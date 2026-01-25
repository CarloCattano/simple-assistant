import json
import re
import shlex
from typing import Any, Dict, List, Optional, Tuple

from config import DEBUG_OLLAMA, DEBUG_TOOL_DIRECTIVES
from services.ollama_shared import (
    CONTENT_REPORTER_SCRIPT_PROMPT,
    MAX_TOOL_OUTPUT_IN_HISTORY,
)
from tools import load_tools
from tools.cheat import fetch_cheat
from utils.logger import GREEN, RST, logger


def _debug(*args, **kwargs):
    if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES:
        logger.debug(*args, **kwargs)


available_functions = load_tools()

if DEBUG_OLLAMA:
    logger.debug(
        f"Loaded {len(available_functions)} tools for Ollama. {list(available_functions.keys())}"
    )

TOOL_MODE = True


def evaluate_tool_usage(prompt: str) -> Tuple[bool, Dict[str, dict]]:
    assert isinstance(prompt, str)
    lower_prompt = prompt.lower()

    if (
        prompt.startswith("Given this shell output:")
        or "answer this question:" in lower_prompt
    ):
        return False, {}

    if "previous command:" in lower_prompt:
        shell_agent_entry = available_functions.get("shell_agent")
        if shell_agent_entry:
            return True, {"shell_agent": shell_agent_entry}

    matched_tools = {
        name: entry
        for name, entry in available_functions.items()
        if any(
            re.match(r"^" + re.escape(trigger) + r"\b", lower_prompt)
            for trigger in entry.get("triggers", [])
        )
    }

    should_use = bool(matched_tools)
    return should_use, matched_tools


def tldr_tool_output(tool_name: str, output: str) -> str:
    from ollama import chat

    from config import SYSTEM_PROMPT

    MODEL_NAME = "llama3.2"
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

    return response.message.content or "No summary available"


def build_audio_script(summary_text: str) -> Optional[str]:
    from ollama import chat

    from config import SYSTEM_PROMPT

    MODEL_NAME = "llama3.2"
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
        from utils.logger import logger

        logger.error(f"Error generating audio script: {err}")
        return None


def call_tool_with_tldr(
    tool_name: str,
    tool_callable,
    history: List[Dict[str, str]],
    tldr_separate: bool = False,
    **arguments,
) -> str | tuple[str, str | None]:
    from services.ollama_core import _record_event
    from services.ollama_translation import (
        translate_instruction_to_command,
        translate_instruction_to_query,
    )

    working_arguments = dict(arguments)

    if (
        tool_name == "web_search"
        and translate_instruction_to_query
        and isinstance(working_arguments.get("query"), str)
    ):
        query = working_arguments["query"].strip()
        if query:
            translated = translate_instruction_to_query(query)
            if not translated:
                logger.warn(
                    "Query translation failed for web_search; aborting tool call."
                )
                return "I couldn't infer a web search query from that request."
            working_arguments["query"] = translated

    raw_output: Any
    if tool_name == "shell_agent":
        max_attempts = 3
        attempt = 0
        last_output: Any = None

        while attempt < max_attempts:
            attempt += 1
            last_output = tool_callable(**working_arguments)

            if not isinstance(last_output, dict):
                break

            exit_code = last_output.get("exit_code")
            stderr = (last_output.get("stderr") or "").strip()
            stdout = (last_output.get("stdout") or "").strip()


            # Treat exit_code 1 as a retryable error (e.g., 'exit 1' from LLM)
            has_error = exit_code not in (0, None)
            if exit_code == 1:
                has_error = True

            lower_err = stderr.lower()
            if not has_error and stderr:
                for marker in (
                    "unknown option",
                    "unrecognized option",
                    "invalid option",
                    "command not found",
                    "permission denied",
                    "no such file or directory",
                    "cannot access",
                    "not found",
                    "no such file or directory",
                    "failed",
                    "error",
                ):
                    if marker in lower_err:
                        has_error = True
                        break

            # If command succeeded but produced no output, consider it a failure
            # Most information-gathering commands should produce at least some output
            if not has_error and exit_code == 0 and not stdout.strip():
                has_error = True

            if not has_error:
                break

            logger.info(
                f"shell_agent attempt {attempt} failed: exit_code={exit_code}, stderr={stderr!r}, stdout={stdout!r}"
            )

            original_prompt = working_arguments.get("prompt")
            if (
                not isinstance(original_prompt, str)
                or not translate_instruction_to_command
            ):
                break

            context_instruction = (
                f"The command '{last_output.get('command')}' failed. "
                f"Suggest a simple alternative command for the same task: {original_prompt}"
            )

            new_command = translate_instruction_to_command(context_instruction)
            if new_command:
                logger.info(
                    f"shell_agent retry {attempt}/{max_attempts}: refining command from {working_arguments.get('prompt')!r} to {new_command!r}"
                )
                working_arguments["prompt"] = new_command
                continue
            else:
                logger.info(
                    f"shell_agent retry {attempt}/{max_attempts}: no new command generated, aborting retry"
                )
                # As a last-ditch attempt, try to fetch cheat.sh usage for the primary binary
                try:
                    primary = None
                    if isinstance(original_prompt, str) and original_prompt.strip():
                        try:
                            primary = shlex.split(original_prompt.strip())[0]
                        except Exception:
                            primary = None
                    if primary:
                        logger.info(
                            f"shell_agent: fetching cheat.sh for '{primary}' to aid retries"
                        )
                        try:
                            cheat_text = fetch_cheat(primary)
                            if isinstance(
                                cheat_text, str
                            ) and not cheat_text.startswith("Error"):
                                context_instruction = (
                                    f"The command '{last_output.get('command')}' failed. "
                                    f"Here is a short usage reference for {primary}:\n{cheat_text}\n"
                                    f"Suggest a simple alternative command that accomplishes: {original_prompt}\n"
                                    "Respond ONLY with the new shell command."
                                )
                                new_command = translate_instruction_to_command(
                                    context_instruction
                                )
                                if new_command:
                                    logger.info(
                                        f"shell_agent retry {attempt}/{max_attempts}: obtained suggestion from cheat.sh context: {new_command}"
                                    )
                                    working_arguments["prompt"] = new_command
                                    continue
                        except Exception as e:
                            logger.debug(f"Error fetching cheat.sh for {primary}: {e}")
                except Exception:
                    pass
                break

        # After all retries, check if the final command matches the user's intent using LLM
        final_command = None
        if isinstance(last_output, dict):
            final_command = last_output.get("command")
        original_prompt = arguments.get("prompt")
        llm_compliance_fail = False
        if final_command and original_prompt and translate_instruction_to_command:
            # Ask LLM to translate the original prompt again
            llm_expected_command = translate_instruction_to_command(original_prompt)
            if llm_expected_command:
                # Check if the final command is semantically close to what LLM would generate
                # Use a simple normalization for now (strip, lower, ignore whitespace)
                def _norm(cmd):
                    return " ".join((cmd or "").strip().lower().split())
                if _norm(final_command) != _norm(llm_expected_command):
                    logger.info(f"LLM compliance check failed: final_command='{final_command}' vs expected='{llm_expected_command}'")
                    llm_compliance_fail = True
        if llm_compliance_fail:
            logger.info("shell_agent: LLM compliance check failed, treating as fail to allow /cheat fallback")
            # Simulate a hard failure so cheat fallback can be triggered
            raw_output = {"command": final_command or "", "exit_code": -2, "stdout": "", "stderr": "LLM compliance check failed: Command does not match user intent."}
        else:
            raw_output = last_output
    else:
        raw_output = tool_callable(**working_arguments)
    raw_text = _format_tool_output(tool_name, raw_output)
    _debug(
        "tool_raw_output",
        {
            "tool": tool_name,
            "arguments": working_arguments,
            "raw_output": raw_output,
        },
    )

    # Truncate tool output for history to keep it manageable
    truncated_text = raw_text[:MAX_TOOL_OUTPUT_IN_HISTORY] + (
        "..." if len(raw_text) > MAX_TOOL_OUTPUT_IN_HISTORY else ""
    )

    history.append({"role": "tool", "name": tool_name, "content": truncated_text})

    _record_event(
        "tool_call",
        f"{tool_name} completed",
        {
            "arguments": _stringify_data(working_arguments)
            if working_arguments
            else "{}",
            "output": raw_text,
        },
    )

    if tool_name in ("shell_agent", "cheat", "fetch_cheat", "cheat.sh"):
        if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES:
            logger.info(
                f"Skipping TLDR for {tool_name}; returning raw tool output only."
            )
        return raw_text if not tldr_separate else (raw_text, None)

    summary = None
    try:
        summary = tldr_tool_output(tool_name, raw_text)
    except Exception as err:
        logger.error(f"Error generating TLDR for tool {tool_name}: {err}")

    if summary:
        summary_text = summary
        if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES:
            logger.info(f"TLDR ready for {tool_name}: {summary_text}")
        _record_event("tldr", f"{tool_name}: {summary_text}")
        _debug(
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
            if DEBUG_OLLAMA or DEBUG_TOOL_DIRECTIVES:
                logger.info(f"Queued TLDR audio script for {tool_name}: {audio_script}")
            _set_last_tool_audio(
                {
                    "summary": summary_text,
                    "tool_name": tool_name,
                    "script": audio_script,
                }
            )
            _record_event("audio_queue", f"Queued TLDR audio for {tool_name}")
            _debug(
                "audio_queue_payload",
                {
                    "tool": tool_name,
                    "audio_script": audio_script,
                },
            )
        except Exception as audio_err:
            logger.error(
                f"Error building audio script for tool {tool_name}: {audio_err}"
            )

        if tldr_separate:
            return raw_text, summary_text
        else:
            return f"{raw_text}\n\nTLDR: {summary_text}"

    return raw_text if not tldr_separate else (raw_text, None)


def _format_tool_output(tool_name: str, raw_output: Any) -> str:
    if tool_name == "shell_agent":
        if isinstance(raw_output, dict):
            command = raw_output.get("command", "")
            stdout = raw_output.get("stdout", "")
            stderr = raw_output.get("stderr", "")
            if len(stdout) > 16000:
                stdout = stdout[:16000] + "\n... (output truncated)"
            return f"Command: {command}\nOutput: {stdout}\nError: {stderr}"
        return str(raw_output)

    if isinstance(raw_output, dict):
        return json.dumps(raw_output, indent=2)

    return str(raw_output)


def run_tool_direct(
    tool_identifier: str, parameters: Optional[Dict[str, Any]] = None
) -> str | tuple[str, str | None] | None:
    resolved = _resolve_tool_entry(tool_identifier)
    if not resolved:
        return None

    tool_name, entry = resolved
    tool_callable = entry.get("function")
    if not tool_callable:
        return None

    try:
        return tool_callable(**(parameters or {}))
    except Exception as e:
        return f"Error running tool {tool_name}: {e}"


def _resolve_tool_entry(tool_identifier: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    # Direct name match
    if tool_identifier in available_functions:
        return tool_identifier, available_functions[tool_identifier]

    # Alias match
    for name, entry in available_functions.items():
        if tool_identifier in entry.get("aliases", []):
            return name, entry

    return None


def resolve_tool_identifier(
    tool_identifier: str,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    return _resolve_tool_entry(tool_identifier)


def _stringify_data(data: Any) -> str:
    try:
        return json.dumps(data, sort_keys=True)
    except (TypeError, ValueError):
        return str(data)


def _set_last_tool_audio(payload: Dict[str, str]) -> None:
    from services.ollama import _set_last_tool_audio as set_audio

    set_audio(payload)
