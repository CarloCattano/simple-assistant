import subprocess


def shell_agent(prompt):
    try:
        print(f"Executing shell command: {prompt}")

        completed = subprocess.run(prompt, shell=True, capture_output=True, text=True)

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        return {
            "command": prompt,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    except Exception as e:
        return {
            "command": prompt,
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
