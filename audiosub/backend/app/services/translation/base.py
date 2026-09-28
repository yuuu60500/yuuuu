"""Translation interface.

Translation works on already-segmented subtitles and is keyed by segment id,
so timings are never touched and translation can be re-run at any time
without re-running speech recognition.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationItem:
    id: str
    text: str


@dataclass
class GlossaryEntry:
    term: str
    translation: str
    note: str | None = None


@dataclass
class TranslationRequest:
    items: list[TranslationItem]  # the lines to translate
    source_language: str | None  # registry code, e.g. "pt-PT"; None if unknown
    target_language: str  # registry code
    domain: str = "general"
    glossary: list[GlossaryEntry] = field(default_factory=list)
    context_before: list[str] = field(default_factory=list)  # read-only context
    context_after: list[str] = field(default_factory=list)


class TranslationError(Exception):
    pass


class TranslationProvider(ABC):
    name = "base"

    @abstractmethod
    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        """Return {item_id: translated_text} for every item in the request."""
