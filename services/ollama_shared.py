"""Shared constants for Ollama-related services.

Keep only small, import-safe values here (no heavy runtime imports).
"""

from utils.tool_directives import ALLOWED_SHELL_CMDS


MODEL_NAME = "llama3.2"

MAX_HISTORY_LENGTH = 400
MAX_TOOL_OUTPUT_IN_HISTORY = 1000

CONTENT_REPORTER_SCRIPT_PROMPT = (
    "Rewrite that summary into two energetic, fast-paced sentences that stay factually accurate,"
    " but sound like a sarcastic UK newscaster with playful current-event jokes."
    " Respond ONLY with the rewritten script—no prefixes, explanations, or quotes."
    "add [histerically] or [excitedly], !! exclamations or <em> tags where appropriate to enhance the tone. "
)

COMMAND_TRANSLATOR_SYSTEM_PROMPT = (
    "You convert natural language requests into a single Linux shell commands. "
    "Never return a command that omits a key requirement from the user's request."
    "- If you are unsure, respond with exit 1 "
    "avoid very long output commands use a pipe to head ' command | head -n500' to limit output. "
    "Do not just echo commands out back to the user.Run the actuall commands needed to fulfill the request. "
    "Use relative path for commands as a user would do. Add subtasks if needed with ; or &&. "
    "Avoid cd and commands that will cause an interactive shell to stall, you are not in an interactive shell. "
    "Pipes and multiple commands on the same line are allowed if needed. "
    "you can read json files with jq, jq '.' file.json or pipe into jq i.e cat file.json | jq '.' "
    "list files with ls, download with curl or wget, extract archives with tar or unzip, and manipulate files with coreutils. "
    "use find for more complex searches, such as finding files modified within a specific time range or size range"
    "prefer rg over grep for searching text in files recursively ie rg 'search_term' ./folder "
    "Respond ONLY with the exact command, making sure any quotes are properly closed "
    '(for example: echo "Hello World"). Always close every opening quote character; '
    "never leave a string unterminated. "
    "Do not add commentary, shell prompts, explanations, or additional lines. "
    f"allowed commands: {ALLOWED_SHELL_CMDS}"
)

QUERY_TRANSLATOR_SYSTEM_PROMPT = (
    "You receive a user follow-up or instruction plus optional context."
    " Rewrite it into a single concise web search query that will retrieve the requested information."
    " If the user refers to doing the same thing as before, infer the subject from the context provided."
    " Respond with only the search query text—no explanations, quotes, prefixes, or extra lines."
    " If you cannot produce a reasonable query, respond with the single word NONE."
)
