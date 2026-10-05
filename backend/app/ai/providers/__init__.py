from app.ai.providers.base import AIProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai import OpenAIProvider

REGISTRY: dict[str, type[AIProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}

__all__ = ["AIProvider", "GroqProvider", "GeminiProvider", "OpenAIProvider", "REGISTRY"]
