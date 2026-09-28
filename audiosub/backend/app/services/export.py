"""Subtitle file generation. Exports are built on demand from segments."""

from dataclasses import dataclass

FORMATS = {"srt", "vtt", "txt"}
CONTENTS = {"original", "translation", "bilingual"}
ORDERS = {"original_first", "translation_first"}


@dataclass
class Cue:
    start: float
    end: float
    original: str
    translation: str | None
    speaker: str | None = None


def _timestamp(seconds: float, sep: str) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt_time(seconds: float) -> str:
    return _timestamp(seconds, ",")


def vtt_time(seconds: float) -> str:
    return _timestamp(seconds, ".")


def _body(cue: Cue, content: str, order: str) -> str:
    original = (cue.original or "").strip()
    translation = (cue.translation or "").strip()
    if content == "original":
        return original
    if content == "translation":
        return translation
    parts = [original, translation] if order == "original_first" else [translation, original]
    return "\n".join(p for p in parts if p)


def render(cues: list[Cue], fmt: str, content: str = "original", order: str = "original_first") -> str:
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format: {fmt}")
    if content not in CONTENTS:
        raise ValueError(f"Unsupported content: {content}")
    if order not in ORDERS:
        raise ValueError(f"Unsupported order: {order}")

    if fmt == "txt":
        lines = []
        for cue in cues:
            body = _body(cue, content, order)
            if not body:
                continue
            # Plain transcript: one paragraph per subtitle, internal line breaks joined.
            if content == "bilingual":
                lines.append(body + "\n")
            else:
                lines.append(body.replace("\n", " "))
        return "\n".join(lines).strip() + "\n"

    blocks = []
    n = 0
    for cue in cues:
        body = _body(cue, content, order)
        if not body:
            continue
        n += 1
        if fmt == "srt":
            blocks.append(f"{n}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{body}")
        else:
            blocks.append(f"{n}\n{vtt_time(cue.start)} --> {vtt_time(cue.end)}\n{body}")
    joined = "\n\n".join(blocks)
    if fmt == "vtt":
        return "WEBVTT\n\n" + joined + ("\n" if joined else "")
    return joined + ("\n" if joined else "")


MEDIA_TYPES = {
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}
