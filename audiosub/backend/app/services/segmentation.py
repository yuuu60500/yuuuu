"""Subtitle segmentation: turn raw ASR segments into readable subtitle cues.

Rule-based (MVP). Works on word timestamps when the ASR provides them and
falls back to interpolating times across each ASR segment otherwise.

Rules, in priority order:
  1. Always break after sentence-ending punctuation (". ? ! 。 ？ ！").
  2. Break on a long pause between words.
  3. Keep each cue within max_lines x max_line_chars and max_duration; when a
     cue overflows, split at the last clause punctuation (", ; :") if one
     leaves a reasonable remainder, else at the last word boundary.
  4. Wrap each cue into at most two balanced lines.
  5. Enforce a minimum display time without overlapping the next cue.
"""

import re
from dataclasses import dataclass, field

SENTENCE_END = tuple(".?!。？！…")
CLAUSE_END = tuple(",;:，；：、")
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")


@dataclass
class SegmentationConfig:
    max_line_chars: int = 42
    max_line_chars_cjk: int = 18
    max_lines: int = 2
    max_duration: float = 7.0
    min_duration: float = 0.8
    pause_break: float = 0.8


@dataclass
class Token:
    text: str  # includes leading space for space-delimited languages
    start: float
    end: float
    probability: float | None = None


@dataclass
class Cue:
    start: float
    end: float
    text: str
    confidence: float | None = None
    tokens: list[Token] = field(default_factory=list, repr=False)


def is_cjk(text: str) -> bool:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return False
    return sum(1 for c in chars if CJK_RE.match(c)) / len(chars) > 0.3


def _tokens_for_segment(seg: dict) -> list[Token]:
    words = seg.get("words") or []
    if words:
        return [
            Token(w["word"], float(w["start"]), float(w["end"]), w.get("probability"))
            for w in words
            if w.get("word", "").strip()
        ]
    # No word timings: split text and spread the segment's time by character count.
    text = (seg.get("text") or "").strip()
    if not text:
        return []
    if is_cjk(text):
        pieces = re.findall(r"[^\s，。？！、；：,.?!;:]+[，。？！、；：,.?!;:]*", text)
    else:
        pieces = [" " + p for p in text.split()]
    start, end = float(seg["start"]), float(seg["end"])
    total = sum(len(p.strip()) for p in pieces) or 1
    tokens, t = [], start
    for p in pieces:
        dur = (end - start) * len(p.strip()) / total
        tokens.append(Token(p, t, t + dur, seg.get("confidence")))
        t += dur
    return tokens


def _join(tokens: list[Token]) -> str:
    return re.sub(r"\s+", " ", "".join(t.text for t in tokens)).strip()


def _cue_from(tokens: list[Token]) -> Cue:
    probs = [t.probability for t in tokens if t.probability is not None]
    return Cue(
        start=tokens[0].start,
        end=tokens[-1].end,
        text=_join(tokens),
        confidence=round(sum(probs) / len(probs), 4) if probs else None,
        tokens=tokens,
    )


def _max_chars(text: str, cfg: SegmentationConfig) -> int:
    per_line = cfg.max_line_chars_cjk if is_cjk(text) else cfg.max_line_chars
    return per_line * cfg.max_lines


def _find_clause_split(tokens: list[Token]) -> int | None:
    """Index after which to split, at the last clause/sentence punctuation that
    leaves at least a third of the text on each side."""
    total = len(_join(tokens))
    best = None
    acc = 0
    for i, tok in enumerate(tokens[:-1]):
        acc += len(tok.text)
        stripped = tok.text.strip()
        if stripped.endswith(CLAUSE_END + SENTENCE_END) and total / 3 <= acc <= total * 2 / 3 + 5:
            best = i
    return best


def wrap_lines(text: str, cfg: SegmentationConfig | None = None) -> str:
    """Wrap a cue into at most two balanced lines."""
    cfg = cfg or SegmentationConfig()
    text = text.replace("\n", " ").strip()
    cjk = is_cjk(text)
    limit = cfg.max_line_chars_cjk if cjk else cfg.max_line_chars
    if len(text) <= limit:
        return text
    mid = len(text) / 2
    candidates: list[tuple[float, int]] = []
    for i, ch in enumerate(text[:-1]):
        if cjk:
            pos = i + 1
            bonus = -4 if ch in CLAUSE_END + SENTENCE_END else 0
        else:
            if ch != " ":
                continue
            pos = i
            bonus = -6 if text[i - 1] in CLAUSE_END + SENTENCE_END else 0
        candidates.append((abs(pos - mid) + bonus, pos))
    if not candidates:
        return text
    _, pos = min(candidates)
    return text[:pos].rstrip() + "\n" + text[pos:].lstrip()


def segment_transcript(
    asr_segments: list[dict], cfg: SegmentationConfig | None = None
) -> list[Cue]:
    cfg = cfg or SegmentationConfig()
    tokens: list[Token] = []
    for seg in asr_segments:
        tokens.extend(_tokens_for_segment(seg))
    if not tokens:
        return []

    cues: list[Cue] = []
    current: list[Token] = []

    def flush(upto: int | None = None):
        nonlocal current
        if not current:
            return
        if upto is None:
            cues.append(_cue_from(current))
            current = []
        else:
            cues.append(_cue_from(current[: upto + 1]))
            current = current[upto + 1 :]

    for i, tok in enumerate(tokens):
        if current:
            candidate = current + [tok]
            text = _join(candidate)
            too_long = len(text) > _max_chars(text, cfg)
            too_slow = tok.end - current[0].start > cfg.max_duration
            if too_long or too_slow:
                split = _find_clause_split(current + [tok])
                if split is not None and split < len(current):
                    flush(split)
                else:
                    flush()
        current.append(tok)

        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        stripped = tok.text.strip()
        if stripped.endswith(SENTENCE_END):
            flush()
        elif nxt is not None and nxt.start - tok.end >= cfg.pause_break:
            flush()
    flush()

    # Timing clean-up: minimum duration, no overlaps.
    for i, cue in enumerate(cues):
        next_start = cues[i + 1].start if i + 1 < len(cues) else None
        if cue.end - cue.start < cfg.min_duration:
            cue.end = cue.start + cfg.min_duration
        if next_start is not None and cue.end > next_start:
            cue.end = max(cue.start + 0.1, next_start)
        cue.start = round(cue.start, 3)
        cue.end = round(cue.end, 3)
        cue.text = wrap_lines(cue.text, cfg)
    return cues
