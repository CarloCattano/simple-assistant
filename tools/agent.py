import subprocess
from typing import Any, Dict

from utils.command_guard import get_last_sanitize_error, sanitize_command


class ShellAgent:
    """Thin wrapper around subprocess to execute sanitized shell commands.

    This class is intentionally dumb: it only preprocesses the prompt,
    passes it through sanitize_command, and executes the result once.
    All higher-level retry/translation logic lives in services.ollama.
    """

    def shell_agent(self, prompt: str) -> Dict[str, Any]:
        """Execute a single sanitized shell command and return its result."""

        preprocessed = self._preprocess_prompt(prompt)

        sanitized_command = sanitize_command(preprocessed)
        if not sanitized_command:
            detail = get_last_sanitize_error()
            base = "Command rejected as unsafe or invalid."
            stderr = f"{base} Reason: {detail}" if detail else base
            return {
                "command": prompt,
                "exit_code": -1,
                "stdout": "",
                "stderr": stderr,
                "command_trace": [{"stage": "prompt", "value": prompt}],
            }

        command_trace = [
            {"stage": "prompt", "value": prompt},
            {"stage": "preprocessed", "value": preprocessed},
            {"stage": "sanitized", "value": sanitized_command},
        ]

        try:
            result = subprocess.run(
                sanitized_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            return {
                "command": sanitized_command,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "command_trace": command_trace,
            }
        except subprocess.TimeoutExpired:
            return {
                "command": sanitized_command,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Command timed out after 20 seconds.",
                "command_trace": command_trace,
            }
        except Exception as e:
            return {
                "command": sanitized_command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command_trace": command_trace,
            }

    def _preprocess_prompt(self, prompt: str) -> str:
        """Trim whitespace from the incoming prompt."""

        return prompt.strip() if prompt else ""


shell_agent_instance = ShellAgent()

tool = {
    "name": "shell_agent",
    "function": shell_agent_instance.shell_agent,
    "triggers": ["cmd:", "shell", "linux", "agent"],
    "description": "Execute shell commands safely and return output",
    "parameters": {
        "prompt": {"type": "string", "description": "Shell command to execute"}
    },
}
