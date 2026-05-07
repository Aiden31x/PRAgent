"""Factory that instantiates the correct LLMProvider by name."""

from __future__ import annotations

from app.agent.llm.base import LLMProvider
from app.agent.llm.claude import ClaudeProvider
from app.agent.llm.gemini import GeminiProvider
from app.config import settings


def get_provider(provider: str, model: str) -> LLMProvider:
    """Return a ready-to-use LLMProvider instance.

    Raises ValueError if the provider name is unknown or the required
    API key is not configured.
    """
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured on the server")
        return GeminiProvider(model)

    if provider == "claude":
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured on the server. "
                "Add it to your .env to enable Claude reviews."
            )
        return ClaudeProvider(model)

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. Valid options: 'gemini', 'claude'."
    )
