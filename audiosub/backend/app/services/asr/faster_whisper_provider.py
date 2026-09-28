import math
import threading

from ...config import get_settings
from .base import ASRProvider, ASRSegment, TranscriptResult, Word

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            s = get_settings()
            _model = WhisperModel(
                s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type
            )
    return _model


class FasterWhisperProvider(ASRProvider):
    """Local Whisper via faster-whisper (CTranslate2). Runs offline."""

    name = "faster_whisper"

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        model = _load_model()
        segments_iter, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=True,
        )
        segments: list[ASRSegment] = []
        for i, seg in enumerate(segments_iter, start=1):
            words = [
                Word(start=w.start, end=w.end, word=w.word, probability=w.probability)
                for w in (seg.words or [])
            ]
            if words:
                confidence = sum(w.probability or 0 for w in words) / len(words)
            else:
                confidence = math.exp(seg.avg_logprob) if seg.avg_logprob is not None else None
            segments.append(
                ASRSegment(
                    id=i,
                    start=float(seg.start),
                    end=float(seg.end),
                    text=seg.text.strip(),
                    confidence=round(confidence, 4) if confidence is not None else None,
                    words=words,
                )
            )
        return TranscriptResult(
            language=info.language,
            duration=info.duration,
            segments=segments,
            provider=self.name,
            model=get_settings().whisper_model,
        )
