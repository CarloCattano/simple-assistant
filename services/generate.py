from config import LLM_PROVIDER
from services.gemini import generate_content as generate_from_gemini
from services.ollama import generate_content as generate_from_olama

def generate_content(prompt: str, source: str = str(LLM_PROVIDER)) -> str:
    source = source.lower()
    if source == "gemini":
        return generate_from_gemini(prompt)
    elif source == "ollama":
        return generate_from_olama(prompt)
    else:
        return f"Unknown source: {source}"
