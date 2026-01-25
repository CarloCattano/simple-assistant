def clean_cheat_output(text: str) -> str:
    """
    Remove ANSI escape codes and normalize whitespace in cheat.sh output.

    Args:
        text (str): The raw output from cheat.sh.

    Returns:
        str: Cleaned, plain-text output.
    """
    import re

    # Remove ANSI escape codes
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    cleaned = ansi_re.sub("", text)
    # Normalize whitespace on each line
    lines = [re.sub(r"\s+", " ", line).strip() for line in cleaned.splitlines()]
    # Remove empty lines and join
    return "\n".join([line for line in lines if line])


def format_cheat_output_for_telegram(text: str, escape_markdown_v2) -> list[str]:
    """
    Format cheat.sh output for Telegram, splitting into Markdown-formatted sections.

    Args:
        text (str): Cleaned cheat.sh output.
        escape_markdown_v2 (callable): Function to escape headings for MarkdownV2.

    Returns:
        list[str]: List of formatted message chunks ready for Telegram.
    """
    DEFAULT_CHUNK_SIZE = 4096

    sections = []
    current_heading = None
    current_code = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            if current_code:
                # Trim leading/trailing blank lines from the accumulated code
                while current_code and current_code[0].strip() == "":
                    current_code.pop(0)
                while current_code and current_code[-1].strip() == "":
                    current_code.pop()
                sections.append((current_heading, "\n".join(current_code)))
                current_code = []
            current_heading = line.strip().lstrip("#").strip()
        else:
            current_code.append(line)
    if current_code:
        # Trim leading/trailing blank lines before appending final section
        while current_code and current_code[0].strip() == "":
            current_code.pop(0)
        while current_code and current_code[-1].strip() == "":
            current_code.pop()
        sections.append((current_heading, "\n".join(current_code)))

    formatted_sections = []
    for heading, code in sections:
        if heading and code.strip():
            escaped_heading = escape_markdown_v2(heading)
            formatted_sections.append(f"*{escaped_heading}*\n```bash\n{code}\n```")
        elif heading:
            escaped_heading = escape_markdown_v2(heading)
            formatted_sections.append(f"*{escaped_heading}*")
        elif code.strip():
            formatted_sections.append(f"```bash\n{code}\n```")

    messages_to_send = []
    current_message = ""
    for section in formatted_sections:
        test_message = (
            current_message + "\n\n" + section if current_message else section
        )
        if len(test_message) <= DEFAULT_CHUNK_SIZE:
            current_message = test_message
        else:
            if current_message:
                messages_to_send.append(current_message)
            current_message = section
    if current_message:
        messages_to_send.append(current_message)

    return messages_to_send
