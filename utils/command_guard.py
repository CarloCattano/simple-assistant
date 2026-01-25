from utils.logger import RED, YELLOW, RST
import re
import shlex
from typing import Optional

from utils.logger import logger

from utils.tool_directives import ALLOWED_SHELL_CMDS as ALLOWED_COMMANDS

_last_sanitize_error: Optional[str] = None


def get_last_sanitize_error() -> Optional[str]:
    """Return a human-readable reason from the most recent sanitize_command failure, if any."""

    return _last_sanitize_error

def sanitize_command(command: str) -> Optional[str]:
    global _last_sanitize_error

    command = (command or "").strip()
    if not command:
        _last_sanitize_error = "empty command"
        logger.debug(f"{YELLOW}empty command{RST}")
        return None

    # Strip surrounding code fences or single-line backtick/quote wrappers
    # so that model outputs like `rg json | ...` are normalized to the inner command.
    if command.startswith("```") and command.endswith("```"):
        # Remove triple backtick fences and optionally a leading language tag
        inner = command[3:-3].strip()
        # If the first token looks like a language, drop it (e.g., ```bash\ncmd```) 
        parts = inner.split("\n", 1)
        if len(parts) == 2 and re.match(r"^[a-zA-Z0-9_+-]+$", parts[0].strip()):
            command = parts[1].strip()
        else:
            command = inner
    elif (command.startswith("`") and command.endswith("`")) or (
        (command.startswith('"') and command.endswith('"'))
        or (command.startswith("'") and command.endswith("'"))
    ):
        command = command[1:-1].strip()

    lowered = command.lower()
    if lowered.startswith("sudo"):
        _last_sanitize_error = "commands starting with sudo are not allowed"
        logger.debug(f"{RED}rejecting command starting with sudo: {command!r}{RST}")
        return None

    try:
        parts = shlex.split(command)
    except ValueError as e:
        _last_sanitize_error = f"command parsing error: {e}"
        logger.debug(f"{RED}command parsing error for {command!r}: {e}{RST}")
        return None

    operators = {"|", "||", "&", "&&", ";", ";;"}

    need_binary = True
    last_binary = None
    for idx, token in enumerate(parts):
        if token in operators:
            need_binary = True
            continue

        if need_binary:
            if token not in ALLOWED_COMMANDS:
                _last_sanitize_error = f"unknown binary {token!r}; only a curated safe list is allowed"
                logger.debug(f"rejecting unknown binary {token!r} in command {command!r}")
                return None
            last_binary = token
            need_binary = False
            # Guard: disallow ls /, cat /, find /, etc.
            if idx + 1 < len(parts):
                next_arg = parts[idx + 1]
                if last_binary in {"rm", "cp", "mv"} and next_arg == "/":
                    _last_sanitize_error = f"{last_binary} / is not allowed for safety"
                    logger.debug(f"rejecting dangerous {last_binary} / usage in command: {command!r}")
                    return None

    _last_sanitize_error = None
    sanitized = command
    
    logger.info(f"accepted sanitized command: {sanitized!r}")
    return sanitized


def detect_direct_command(instruction: str) -> Optional[str]:
    text = (instruction or "").strip()
    if not text:
        return None

    # Multi-line instructions (often containing explanatory context like
    # "Previous command: ...") should not be treated as literal commands.
    # Let the LLM translator handle those instead.
    # if "\n" in text:
    #     return None

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
