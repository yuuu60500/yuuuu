"""Prompt construction for subtitle translation.

Priority of terminology: glossary > domain terminology > normal translation.
"""

import json

from ...domains import get_domain
from ...languages import get_language, language_name
from .base import TranslationRequest

SYSTEM_PROMPT = """You are a professional subtitle translator.

You translate subtitle lines from a transcribed recording. Each line is shown on \
screen on its own, at its own time, so:
- Translate every line you are asked to translate, and return exactly one translation \
per line id. Never merge, split, drop or reorder lines.
- Use the surrounding lines (and the read-only context) to understand meaning: a \
sentence may continue across several lines. Translate each line so that, read in \
sequence, the lines form a natural translation, while each line still carries the \
part of the meaning spoken during that line.
- Keep translations concise enough to read as subtitles. Keep a line break (\\n) \
only where it helps readability; at most two lines.
- The transcript comes from speech recognition and may contain small recognition \
errors. Translate the most plausible intended meaning; do not comment on errors.
- Keep names of people, companies and products unchanged. Keep numbers, dates and \
amounts exact.
- Output only the translations in the requested JSON format, with no notes.

Terminology priority, highest first:
1. The user's glossary: when a glossary term appears, always use the glossary \
translation exactly.
2. The domain terminology rules.
3. Your normal best translation."""


def build_user_prompt(req: TranslationRequest) -> str:
    target = get_language(req.target_language)
    source_name = language_name(req.source_language) if req.source_language else "auto-detect"
    domain = get_domain(req.domain)

    parts = [
        f"Source language: {source_name}",
        f"Target language: {target.name if target else req.target_language} "
        f"({req.target_language})",
    ]
    if target and target.translation_notes:
        parts.append(f"Target language rules:\n{target.translation_notes}")
    parts.append(f"Domain: {domain.name}\nDomain terminology rules:\n{domain.instructions}")
    if req.glossary:
        lines = []
        for g in req.glossary:
            entry = f"- {g.term} => {g.translation}"
            if g.note:
                entry += f"  ({g.note})"
            lines.append(entry)
        parts.append("Glossary (highest priority):\n" + "\n".join(lines))
    if req.context_before:
        parts.append(
            "Preceding lines (context only, do not translate):\n"
            + "\n".join(req.context_before)
        )
    lines_json = json.dumps(
        [{"id": item.id, "text": item.text} for item in req.items], ensure_ascii=False, indent=1
    )
    parts.append(f"Lines to translate:\n{lines_json}")
    if req.context_after:
        parts.append(
            "Following lines (context only, do not translate):\n"
            + "\n".join(req.context_after)
        )
    parts.append(
        'Return {"translations": [{"id": <line id>, "text": <translation>}, ...]} '
        "with one entry for each line id above."
    )
    return "\n\n".join(parts)


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}
