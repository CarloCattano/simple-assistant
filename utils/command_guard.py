import re
import shlex
from typing import Optional

# Commands considered safe for automated execution.
ALLOWED_COMMANDS = {
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
    "chmod",
    "chown",
    "hyprctl",
    "hypr_control.sh",
    "service",
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
}

_DISALLOWED_TOKENS = {";", "&&", "||", "|", ">", "<", "`", "$(", "${"}


def sanitize_command(command: str) -> Optional[str]:
    command = (command or "").strip()
    if not command:
        return None

    lowered = command.lower()
    if lowered.startswith("sudo"):
        return None

    if any(token in command for token in _DISALLOWED_TOKENS):
        return None

    try:
        parts = shlex.split(command)
    except ValueError:
        return None

    if not parts:
        return None

    if parts[0] not in ALLOWED_COMMANDS:
        return None

    return shlex.join(parts)


def heuristic_command(instruction: str) -> Optional[str]:
    return None


def detect_direct_command(instruction: str) -> Optional[str]:
    text = (instruction or "").strip()
    if not text:
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
