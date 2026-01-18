import json
import re
from typing import Any, Optional, Sequence, Tuple, Dict

from utils.logger import logger

try:  # Optional Ollama dependency
    from services.ollama import (
        resolve_tool_identifier,
        translate_instruction_to_command,
        translate_instruction_to_query,
        get_last_command_translation_error,
    )
except ImportError:  # pragma: no cover - optional backend
    resolve_tool_identifier = None
    translate_instruction_to_command = None
    translate_instruction_to_query = None
    get_last_command_translation_error = None


REPROCESS_CONTROL_WORDS = {"reprocess", "retry", "again", "repeat"}


class ToolDirectiveError(Exception):
    """Error raised when a tool directive from the user cannot be honored."""


def _normalize_tool_parameters(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parameters, dict):
        return parameters

    if (
        tool_name == "web_search"
        and translate_instruction_to_query
        and isinstance(parameters.get("query"), str)
    ):
        query = parameters["query"].strip()
        if query:
            translated = translate_instruction_to_query(query)
            if not translated:
                raise ToolDirectiveError(
                    "Couldn't infer a web search query from that request."
                )
            parameters = {**parameters, "query": translated}

    return parameters


def _parse_tool_directive(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not resolve_tool_identifier:
        return None

    match = re.match(r"\s*(?:run|use)\s+tool\s+(\S+)(?:\s+(.*))?$", text, re.IGNORECASE)
    if not match:
        return None

    tool_identifier = match.group(1)
    remaining = (match.group(2) or "").strip()

    resolved = resolve_tool_identifier(tool_identifier)
    if not resolved:
        raise ToolDirectiveError(f"Unknown tool '{tool_identifier}'.")

    resolved_name, entry = resolved
    parameters_def = entry.get("parameters", {}) or {}

    if not parameters_def:
        return resolved_name, {}

    if len(parameters_def) != 1:
        raise ToolDirectiveError("Tool requires structured JSON parameters.")

    param_name = next(iter(parameters_def))

    if not remaining:
        raise ToolDirectiveError("Provide the arguments needed for this tool call.")

    value: Any = remaining
    if param_name == "prompt" and translate_instruction_to_command:
        logger.info(f"tool_directives: translating instruction to command: {remaining!r}")
        translated = translate_instruction_to_command(remaining)

        logger.info(f"tool_directives: raw translated command: {translated!r}")

        if not translated:
            logger.warning(
                "tool_directives: translation returned no command (None or rejected); raising ToolDirectiveError"
            )
            reason = None
            if get_last_command_translation_error:
                try:
                    reason = get_last_command_translation_error()
                except Exception:
                    reason = None

            base_msg = (
                "Couldn't translate your request into a *safe* shell command. "
                "This usually happens when the instruction is too ambiguous, or would require "
                "unsupported/unsafe operations such as sudo, subshells, redirections, or unknown binaries. "
                "Please send the exact shell command you want to run instead."
            )
            if reason:
                base_msg = f"{base_msg} (Reason: {reason})"

            raise ToolDirectiveError(base_msg)

        cleaned = translated.strip()
        if not cleaned:
            raise ToolDirectiveError("Command translation returned an empty result.")

        normalized = cleaned.lower()
        default_normalized = remaining.lower()
        logger.info(
            f"tool_directives: normalized command={normalized!r}, original={default_normalized!r}"
        )
        common_prefixes = (
            "sudo",
            "ls",
            "pwd",
            "cd",
            "cat",
            "find",
            "grep",
            "tail",
            "head",
            "touch",
            "mkdir",
            "rm",
            "cp",
            "mv",
            "python",
            "pip",
            "npm",
            "node",
            "git",
            "docker",
            "curl",
            "wget",
            "top",
            "htop",
            "df",
            "du",
            "whoami",
            "ps",
            "kill",
            "chmod",
            "chown",
            "service",
            "systemctl",
            "journalctl",
            "tar",
            "zip",
            "ping",
            "unzip",
        )

        if not normalized or (
            normalized == default_normalized
            and not normalized.startswith(common_prefixes)
        ):
            raise ToolDirectiveError(
                "I couldn't infer a concrete shell command from that description. "
                "It doesn't clearly look like a command I recognize (for example starting with ls, cd, git, etc.). "
                "Please send the exact command line you want me to execute."
            )

        value = cleaned

    parameters = _normalize_tool_parameters(resolved_name, {param_name: value})
    return resolved_name, parameters


def extract_tool_request(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Try to decode a tool request from raw user text.

    Supports both inline JSON payloads and the "run tool <name> ..." syntax.
    Returns (tool_name, parameters) or None when no tool directive is found.
    """
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            name = payload.get("name")
            parameters = payload.get("parameters") or {}

            if isinstance(name, str) and isinstance(parameters, dict):
                parameters = _normalize_tool_parameters(name, parameters)
                return name, parameters

    return _parse_tool_directive(text)


def derive_followup_tool_request(
    instructions: str, original_prompt: str, tool_metadata: Dict[str, Any]
):
    """Infer a follow-up tool invocation based on previous tool metadata.

    Currently only supports the web_search tool, where follow-up instructions
    are mapped into a new or refined query string.
    """

    tool_name = (tool_metadata or {}).get("tool_name")
    if not tool_name:
        return None

    parameters = (tool_metadata or {}).get("parameters") or {}

    if tool_name == "web_search":
        if not translate_instruction_to_query:
            return None

        base_query = ""
        if isinstance(parameters.get("query"), str):
            base_query = parameters["query"].strip()
        if not base_query and isinstance(original_prompt, str):
            base_query = original_prompt.strip()

        instructions = (instructions or "").strip()

        if instructions:
            query_input_parts = [instructions]
            if base_query:
                query_input_parts.append(f"Previous query: {base_query}")
            query_input = "\n\n".join(part for part in query_input_parts if part)
            translated = translate_instruction_to_query(query_input)
            if not translated:
                raise ToolDirectiveError(
                    "Couldn't infer a web search query from that follow-up request."
                )
            new_query = translated
        else:
            new_query = base_query

        if not new_query:
            raise ToolDirectiveError("No search query to reuse for this tool reply.")

        return tool_name, {"query": new_query}, new_query

    return None
