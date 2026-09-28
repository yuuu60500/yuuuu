from ...config import get_settings
from .base import (
    GlossaryEntry,
    TranslationError,
    TranslationItem,
    TranslationProvider,
    TranslationRequest,
)


def get_translation_provider(name: str | None = None) -> TranslationProvider:
    name = name or get_settings().translation_provider
    if name == "claude":
        from .claude_provider import ClaudeTranslationProvider

        return ClaudeTranslationProvider()
    if name == "mock":
        from .mock_provider import MockTranslationProvider

        return MockTranslationProvider()
    raise ValueError(f"Unknown translation provider: {name}")


__all__ = [
    "GlossaryEntry",
    "TranslationError",
    "TranslationItem",
    "TranslationProvider",
    "TranslationRequest",
    "get_translation_provider",
]
