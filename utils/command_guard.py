import re
import shlex
from typing import Optional

from utils.logger import logger

# Commands considered safe for automated execution.
ALLOWED_COMMANDS = {
    "awk",
    "bash",
    "bc",
    "cut",
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "du",
    "df",
    "whoami",
    "ps",
    "top",
    "htop",
    "uptime",
    "free",
    "env",
    "printenv",
    "uname",
    "date",
    "sleep",
    "echo",
    "stat",
    "hyprctl",
    "./hypr_control.sh",
    "service",
    "rg",
    "systemctl",
    "journalctl",
    "docker",
    "git",
    "npm",
    "pip",
    "python",
    "node",
    "curl",
    "wget",
    "tar",
    "zip",
    "unzip",
    "kill",
    "lsblk",
    "mount",
    "umount",
    "ip",
    "hostname",
    "ss",
    "netstat",
    "ping",
    "playerctl",
    "[",
    "test",
}

_DISALLOWED_TOKENS = {}

_last_sanitize_error: Optional[str] = None


def get_last_sanitize_error() -> Optional[str]:
    """Return a human-readable reason from the most recent sanitize_command failure, if any."""

    return _last_sanitize_error

def sanitize_command(command: str) -> Optional[str]:
    global _last_sanitize_error

    command = (command or "").strip()
    if not command:
        _last_sanitize_error = "empty command"
        logger.debug("sanitize_command: empty command")
        return None

    lowered = command.lower()
    if lowered.startswith("sudo"):
        _last_sanitize_error = "commands starting with sudo are not allowed"
        logger.info(f"sanitize_command: rejecting command starting with sudo: {command!r}")
        return None

    # Reject immediately if any subshell or backtick constructs are present
    if any(token in command for token in _DISALLOWED_TOKENS):
        _last_sanitize_error = "subshell or backtick constructs are not allowed"
        logger.info(
            f"sanitize_command: rejecting due to disallowed subshell/backtick token in command: {command!r}"
        )
        return None

    try:
        parts = shlex.split(command)
    except ValueError as exc:
        _last_sanitize_error = f"invalid quoting or syntax: {exc}"
        logger.info(f"sanitize_command: shlex.split failed for {command!r}: {exc}")
        return None

    if not parts:
        _last_sanitize_error = "no tokens after splitting command"
        logger.debug("sanitize_command: no tokens after splitting command")
        return None

    # We allow simple pipelines and command lists (|, &&, ||, ;) but require that
    # each command segment starts with a known-safe binary from ALLOWED_COMMANDS.
    operators = {"|", "||", "&&", ";"}

    # Reject suspicious operator usages that are glued to other tokens, e.g. "ls|grep".
    for token in parts:
        if any(op in token for op in ["|", "&", ";"]) and token not in operators:
            _last_sanitize_error = f"operator characters must be spaced out; got token {token!r}"
            logger.info(
                f"sanitize_command: rejecting token with embedded operator {token!r} in command {command!r}"
            )
            return None

        # Disallow explicit redirections to keep commands read-only-ish.
        # if token.startswith((">", "<", "2>", "1>")) or ">>" in token:
        #     _last_sanitize_error = f"redirections like {token!r} are not allowed"
        #     logger.info(
        #         f"sanitize_command: rejecting redirection token {token!r} in command {command!r}"
        #     )
        #     return None


    need_binary = True
    last_binary = None
    for idx, token in enumerate(parts):
        if token in operators:
            need_binary = True
            continue

        if need_binary:
            if token not in ALLOWED_COMMANDS:
                _last_sanitize_error = f"unknown binary {token!r}; only a curated safe list is allowed"
                logger.info(
                    f"sanitize_command: rejecting unknown binary {token!r} in command {command!r}"
                )
                return None
            last_binary = token
            need_binary = False
            # Guard: disallow ls /, cat /, find /, etc.
            if idx + 1 < len(parts):
                next_arg = parts[idx + 1]
                if last_binary in {"ls", "cat", "find", "du", "rm", "cp", "mv"} and next_arg == "/":
                    _last_sanitize_error = f"{last_binary} / is not allowed for safety"
                    logger.info(f"sanitize_command: rejecting dangerous {last_binary} / usage in command: {command!r}")
                    return None
            # Guard: disallow find / ...
            if last_binary == "find" and idx + 1 < len(parts):
                if parts[idx + 1] == "/":
                    _last_sanitize_error = "find / is not allowed for safety"
                    logger.info(f"sanitize_command: rejecting dangerous find / usage in command: {command!r}")
                    return None

    # Preserve the original command text to avoid introducing quotes
    # around operators like | and &&, now that we've validated it.
    _last_sanitize_error = None
    sanitized = command
    logger.debug(f"sanitize_command: accepted sanitized command: {sanitized!r}")
    return sanitized


def heuristic_command(instruction: str) -> Optional[str]:
    # Heuristics are intentionally disabled; translation is delegated
    # entirely to the LLM via translate_instruction_to_command.
    return None


def detect_direct_command(instruction: str) -> Optional[str]:
    text = (instruction or "").strip()
    if not text:
        return None

    # Multi-line instructions (often containing explanatory context like
    # "Previous command: ...") should not be treated as literal commands.
    # Let the LLM translator handle those instead.
    if "\n" in text:
        return None

    # Quick detection for literal commands.
    direct = sanitize_command(text)
    if direct:
        return direct

    # Allow commands wrapped in quotes or code fences.
    if text.startswith("`") and text.endswith("`"):
        return sanitize_command(text[1:-1])

    if text.startswith("\"") and text.endswith("\""):
        return sanitize_command(text[1:-1])

    return None
