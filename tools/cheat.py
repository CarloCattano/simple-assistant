from typing import Dict, Any
import requests
import re


def clean_cheat_output(text: str) -> str:
    """Remove ANSI escape codes and normalize whitespace in cheat.sh output."""
    if not isinstance(text, str):
        return text
    # Remove ANSI color codes
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    cleaned = ansi_re.sub("", text)
    # Collapse multiple spaces, strip trailing spaces from each line
    lines = [re.sub(r"\s+", " ", line).strip() for line in cleaned.splitlines()]
    # Remove empty lines at start/end, preserve paragraph breaks
    return "\n".join([line for line in lines if line])


def fetch_cheat(command: str) -> str:
    """Fetch raw cheat.sh page for a command and return its cleaned plain-text content.

    Returns a short error message when the fetch fails.
    """
    if not command or not isinstance(command, str):
        return "Error: no command provided"

    # Normalize command: use only the first token (primary binary)
    primary = command.strip().split()[0]
    url = f"http://cheat.sh/{primary}"
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "curl 8.18.0 (x86_64-pc-linux-gnu) libcurl/8.18.0"})
        if resp.status_code == 200 and resp.text:
            return clean_cheat_output(resp.text)
        return f"Error fetching cheat.sh for {primary}: status {resp.status_code}"
    except Exception as e:
        return f"Error fetching cheat.sh for {primary}: {e}"


tool = {
    "name": "cheat",
    "function": fetch_cheat,
    "triggers": ["cheat", "cheat.sh", "help"],
    "description": "Fetch plain-text usage/help from cheat.sh for a given command",
    "parameters": {"command": {"type": "string", "description": "Primary command to lookup on cheat.sh"}},
}
