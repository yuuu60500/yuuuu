from ..media import wav_duration
from .base import ASRProvider, ASRSegment, TranscriptResult, Word

_SAMPLE = {
    "pt": [
        "Bom dia, tudo bem?",
        "Gostaria de falar consigo sobre o IVA e a declaração periódica deste trimestre.",
        "A Autoridade Tributária enviou uma notificação na semana passada.",
        "Precisamos de rever as faturas e a retenção na fonte antes do fim do mês.",
    ],
    "en": [
        "Good morning, how are you?",
        "I would like to talk to you about the quarterly VAT return.",
    ],
    "zh": ["早上好，你好吗？", "我想和你谈谈这个季度的增值税申报。"],
}


class MockASRProvider(ASRProvider):
    """Deterministic fake transcript for development and tests (no model needed)."""

    name = "mock"

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        lang = language or "pt"
        lines = _SAMPLE.get(lang, _SAMPLE["pt"])
        duration = wav_duration(audio_path)
        slot = duration / len(lines)
        segments = []
        for i, text in enumerate(lines):
            start, end = i * slot, (i + 1) * slot - 0.05
            tokens = text.split(" ") if " " in text else list(text)
            step = (end - start) / len(tokens)
            words = [
                Word(start=start + j * step, end=start + (j + 1) * step,
                     word=(" " + t) if " " in text else t, probability=0.95)
                for j, t in enumerate(tokens)
            ]
            segments.append(ASRSegment(id=i + 1, start=start, end=end, text=text,
                                       confidence=0.95, words=words))
        return TranscriptResult(language=lang, duration=duration, segments=segments,
                                provider=self.name, model="mock")
