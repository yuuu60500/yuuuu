"""Speech recognition interface.

Every provider returns the same TranscriptResult, so the rest of the system
never depends on which model produced it.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float | None = None


@dataclass
class ASRSegment:
    id: int
    start: float
    end: float
    text: str
    confidence: float | None = None
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscriptResult:
    language: str | None
    duration: float | None
    segments: list[ASRSegment]
    provider: str
    model: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ASRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        """Transcribe a 16 kHz mono WAV. `language` is an ASR code ("pt") or None to detect."""
