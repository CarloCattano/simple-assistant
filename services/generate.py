from typing import Callable, Optional

from utils.logger import logger

LLM_PROVIDER = "ollama"
GEMINI_SOURCE = "gemini"
OLLAMA_SOURCE = "ollama"

def load_ollama_generator() -> Optional[Callable[..., str]]:
    try:
        import services.ollama
        ollama_generator = services.ollama.generate_content
    except ImportError as e:
        logger.error("Ollama service is not available: %s", e)
        return None
    return ollama_generator


def load_gemini_generator() -> Optional[Callable[..., str]]:

    import services.gemini
    try:
        gemini_generator = services.gemini.generate_content
        return gemini_generator
    except ImportError as e:
        logger.error("Gemini service is not available: %s", e)
        return None


def generate_from_gemini(prompt: str) -> str:
    gemini_generator = load_gemini_generator()
    if gemini_generator:
        return gemini_generator(prompt)
    logger.error("Failed to load Gemini generator")
    return "Failed to load Gemini generator"

def generate_content(prompt: str, source: Optional[str] = LLM_PROVIDER) -> str:
    """
    Generates content based on the provided prompt and source.
    Args:
        prompt (str): The input prompt to generate content from.
        source (Optional[str]): The source to use for generating content. Defaults to LLM_PROVIDER.
    Returns:
        str: The generated content, or an error message if generation fails.
    """
    normalized_source = (source or LLM_PROVIDER).strip()
    provider = normalized_source.lower()
    if provider == GEMINI_SOURCE:
        try:
            return generate_from_gemini(prompt)
        except Exception as e:
            logger.error("Error generating content from Gemini: %s", e)
            return f"Error from Gemini: {e}"
    elif provider == OLLAMA_SOURCE:
        try:
            ollama_generator = load_ollama_generator()
            if ollama_generator:
                return ollama_generator(prompt)
            else:
                logger.error("Failed to load Ollama generator")
                return f"Failed to load Ollama generator"
        except Exception as e:
            logger.error("Error generating content from Ollama: %s", e)
            return f"Error from Ollama: {e}"
    return f"Unknown source: {provider or 'unspecified'}"

