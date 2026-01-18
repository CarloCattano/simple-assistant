import logging
from typing import Dict, List, Any
import subprocess
from utils.command_guard import sanitize_command

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ShellAgent:
    def __init__(self):
        self._command_trace: List[Dict[str, str]] = []

    def shell_agent(self, prompt: str) -> Dict[str, Any]:
        """
        Execute a shell command safely and return output.
        Args:
            prompt (str): The shell command to execute.
        Returns:
            A dictionary containing the execution result.
        """
        preprocessed = self._preprocess_prompt(prompt)
        
        sanitized_command = sanitize_command(preprocessed)
        if not sanitized_command:
            return {
                "command": prompt,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Command rejected as unsafe or invalid.",
                "command_trace": [{"stage": "prompt", "value": prompt}],
            }

        translated_command = None
        if self._translate_instruction_to_command:
            from services.ollama import translate_instruction_to_command  # Import the optional dependency
            translated_command = translate_instruction_to_command(preprocessed)
            sanitized_translated_command = sanitize_command(translated_command)
        
        command_trace = [
            {"stage": "prompt", "value": prompt},
            {"stage": "preprocessed", "value": preprocessed},
        ]
        if sanitized_command:
            command_trace.append({"stage": "sanitized", "value": sanitized_command})
        if translated_command and sanitized_translated_command:
            command_trace.append({"stage": "translated", "value": sanitized_translated_command})

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
        """
        Preprocess the input prompt.
        Args:
            prompt (str): The input prompt.
        Returns:
            The preprocessed prompt.
        """
        return prompt.strip() if prompt else ""

    @staticmethod
    def _sanitize_command(command: str) -> str:
        """
        Sanitize a command string.
        Args:
            command (str): The command to sanitize.
        Returns:
            The sanitized command.
        """
        return sanitize_command(command)

    @staticmethod
    def _translate_instruction_to_command(command: str) -> str:
        """
        Translate an instruction to a command (optional).
        Args:
            command (str): The instruction to translate.
        Returns:
            The translated command.
        """
        if not hasattr(ShellAgent, '_translate_instruction_to_command'):
            return None
        from services.ollama import translate_instruction_to_command  
        return translate_instruction_to_command(command).strip()


from tools.agent import ShellAgent  
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

