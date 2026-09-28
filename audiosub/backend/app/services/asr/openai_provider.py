import math

from ...config import get_settings
from .base import ASRProvider, ASRSegment, TranscriptResult, Word


class OpenAIWhisperProvider(ASRProvider):
    """Hosted Whisper API. Note: the API limits uploads to 25 MB per request."""

    name = "openai"

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        from openai import OpenAI  # optional dependency

        client = OpenAI()
        model = get_settings().openai_asr_model
        with open(audio_path, "rb") as f:
            kwargs = {
                "model": model,
                "file": f,
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment", "word"],
            }
            if language:
                kwargs["language"] = language
            resp = client.audio.transcriptions.create(**kwargs)
        data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        all_words = data.get("words") or []
        segments = []
        for i, seg in enumerate(data.get("segments") or [], start=1):
            words = [
                Word(start=w["start"], end=w["end"], word=" " + w["word"].strip())
                for w in all_words
                if w["start"] >= seg["start"] - 0.01 and w["end"] <= seg["end"] + 0.01
            ]
            logprob = seg.get("avg_logprob")
            segments.append(
                ASRSegment(
                    id=i,
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"].strip(),
                    confidence=round(math.exp(logprob), 4) if logprob is not None else None,
                    words=words,
                )
            )
        return TranscriptResult(
            language=data.get("language"),
            duration=data.get("duration"),
            segments=segments,
            provider=self.name,
            model=model,
        )
