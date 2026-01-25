Learning exercise by integrating GEMMINI and/or OLLAMA self hosted.
Tool usage integration and telegram interface

### Features:
- Chat with llm in /text or /audio assistant, also with voice notes with tts stt.
- Forward a message and transcribe the text to audio, or use it as a prompt
- Simple web scraping agentic tools (WIP)
- Context Storage ( needs encription probably, or proper db ) 


### Usage:
### Context & Reply-Based Tool Usage

This assistant supports context-aware interactions and reply-based tool flows:

- **Context History:**
    - The bot tracks conversation history and tool outputs for each user.
    - When you reply to a previous message (including tool outputs), your instruction is interpreted in the context of that message.
    - For example, replying to a `/web` or `/agent` result with a follow-up question will refine or re-run the tool using the previous context.

- **Replying to Tool Outputs:**
    - Replying to a tool output (e.g., `/web`, `/agent`, `/tool`, or scraping tools) triggers a context-aware follow-up.
    - The bot will attempt to translate your reply into a new tool request, using the previous prompt and tool metadata.
    - If the reply cannot be translated directly, the LLM will attempt to synthesize a valid command or query using the previous context.

- **History & Metadata:**
    - Each tool output is associated with its originating prompt and tool metadata.
    - This enables robust follow-up logic and accurate context for multi-step workflows.

**Tip:** For best results, always reply directly to the relevant tool output or message you want to refine or extend.
1. Copy `.env.template` to `.env` and fill in your `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `ADMIN_ID`.
2. Set `LLM_PROVIDER=gemini` or `LLM_PROVIDER=ollama` in `.env`.
3. Install dependencies and run telegram-bot:
    ```bash
    poetry install
    poetry run python app.py
    ```
4. All runtime errors and uncaught exceptions are logged to `usage.log` (in addition to tool usage, prompts, and events). This allows an agent to tail `usage.log` and extract error context from the Python interpreter.

5. run tests:
    ```bash
    poetry run python run_tests.py
    ```

### Shell Agent Tool

The shell agent translates natural language requests to safe shell commands via Telegram:

- Use `/agent <instruction>` to run a shell command (e.g., `/agent list files in home`).
- The agent sanitizes and translates instructions, using Ollama if configured.
- Results include the command, stdout, stderr, and trace details (logged to `usage.log`).
- Set `LLM_PROVIDER=ollama` for LLM-backed command translation.



#### TODO's 
    - [x] Add context with previous messages
    - [ ] pass scrape tool output to prompt
    - UX 

    
![image](https://github.com/user-attachments/assets/6bc2f7fd-0f9b-472c-8f47-03a607a7a11f)
