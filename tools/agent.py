import subprocess

from utils.command_guard import sanitize_command


def shell_agent(prompt):
    try:
        sanitized = sanitize_command(prompt)
        if not sanitized:
            return {
                "command": prompt,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Command rejected as unsafe or invalid.",
            }

        print(f"Executing shell command: {sanitized}")

        completed = subprocess.run(
            sanitized,
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
        )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        return {
            "command": sanitized,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "command": sanitized if "sanitized" in locals() else prompt,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Command timed out after 20 seconds.",
        }
        
    except Exception as e:
        return {
            "command": sanitized if "sanitized" in locals() else prompt,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
        }


tool = {
    'name': 'shell_agent',
    'function': shell_agent,
    'triggers': ['cmd:', 'shell_agent', 'linux agent', 'agent'],
    'description': 'Execute a shell command and return its output, exit code, and stderr.',
    'parameters': {
        'prompt': {'type': 'string', 'description': 'Shell command to execute'},
    },
}
