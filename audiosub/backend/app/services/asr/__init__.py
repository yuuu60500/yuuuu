from ...config import get_settings
from .base import ASRProvider, ASRSegment, TranscriptResult, Word


def get_asr_provider(name: str | None = None) -> ASRProvider:
    name = name or get_settings().asr_provider
    if name == "faster_whisper":
        from .faster_whisper_provider import FasterWhisperProvider

        return FasterWhisperProvider()
    if name == "openai":
        from .openai_provider import OpenAIWhisperProvider

        return OpenAIWhisperProvider()
    if name == "mock":
        from .mock_provider import MockASRProvider

        return MockASRProvider()
    raise ValueError(f"Unknown ASR provider: {name}")


__all__ = ["ASRProvider", "ASRSegment", "TranscriptResult", "Word", "get_asr_provider"]
