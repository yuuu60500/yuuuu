"""Translates a project's segments in context batches.

Segments are sent in batches of `batch_size` lines, each with a few lines of
read-only context before and after, and results are mapped back by segment
id so timings never change.
"""

import logging
from collections.abc import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..languages import same_language
from ..models import GlossaryTerm, Project, Segment
from .translation import (
    GlossaryEntry,
    TranslationError,
    TranslationItem,
    TranslationProvider,
    TranslationRequest,
    get_translation_provider,
)

log = logging.getLogger(__name__)


def load_glossary(db: Session, project: Project, target_language: str) -> list[GlossaryEntry]:
    """Global terms plus project terms; project terms override global ones."""
    rows = db.scalars(
        select(GlossaryTerm)
        .where(or_(GlossaryTerm.project_id.is_(None), GlossaryTerm.project_id == project.id))
        .where(
            or_(
                GlossaryTerm.target_language.is_(None),
                GlossaryTerm.target_language == target_language,
            )
        )
    ).all()
    by_term: dict[str, GlossaryTerm] = {}
    for row in sorted(rows, key=lambda r: r.project_id is not None):
        by_term[row.term.lower()] = row
    return [GlossaryEntry(r.term, r.translation, r.note) for r in by_term.values()]


def _flatten(text: str) -> str:
    return text.replace("\n", " ")


def translate_segments(
    db: Session,
    project: Project,
    target_language: str,
    segment_ids: list[str] | None = None,
    provider: TranslationProvider | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    extra_glossary: list[GlossaryEntry] | None = None,
) -> int:
    """Translate the given segments (all when None). Returns the count translated."""
    settings = get_settings()
    all_segments = list(
        db.scalars(
            select(Segment).where(Segment.project_id == project.id).order_by(Segment.segment_index)
        )
    )
    wanted = set(segment_ids) if segment_ids is not None else None
    targets = [s for s in all_segments if wanted is None or s.id in wanted]
    if not targets:
        return 0

    source = project.effective_source_language
    if same_language(source, target_language):
        for seg in targets:
            seg.translated_text = seg.original_text
            seg.translation_language = target_language
        db.commit()
        return len(targets)

    provider = provider or get_translation_provider()
    glossary = load_glossary(db, project, target_language)
    if extra_glossary:
        known = {g.term.lower() for g in extra_glossary}
        glossary = [g for g in glossary if g.term.lower() not in known] + list(extra_glossary)
    position = {s.id: i for i, s in enumerate(all_segments)}
    ctx = settings.translation_context_size
    size = max(1, settings.translation_batch_size)

    done = 0
    for b in range(0, len(targets), size):
        batch = targets[b : b + size]
        first, last = position[batch[0].id], position[batch[-1].id]
        batch_ids = {s.id for s in batch}
        before = [_flatten(s.original_text) for s in all_segments[max(0, first - ctx) : first]]
        after = [_flatten(s.original_text) for s in all_segments[last + 1 : last + 1 + ctx]]
        # Non-contiguous selections: lines in between are useful context too.
        between = [
            s for s in all_segments[first : last + 1] if s.id not in batch_ids
        ]
        if between:
            before = before + [_flatten(s.original_text) for s in between]

        # Short numeric ids keep the model's job simple; map back afterwards.
        local = {str(i + 1): seg for i, seg in enumerate(batch)}
        request = TranslationRequest(
            items=[TranslationItem(k, seg.original_text) for k, seg in local.items()],
            source_language=source,
            target_language=target_language,
            domain=project.domain,
            glossary=glossary,
            context_before=before,
            context_after=after,
        )
        result = provider.translate_batch(request)
        missing = [k for k in local if not result.get(k)]
        if missing:
            # One retry for lines the model skipped, translated with the batch as context.
            retry = TranslationRequest(
                items=[TranslationItem(k, local[k].original_text) for k in missing],
                source_language=source,
                target_language=target_language,
                domain=project.domain,
                glossary=glossary,
                context_before=before + [_flatten(s.original_text) for s in batch],
                context_after=after,
            )
            result.update(provider.translate_batch(retry))
            still = [k for k in missing if not result.get(k)]
            if still:
                raise TranslationError(f"Model did not return translations for {len(still)} line(s).")
        for key, seg in local.items():
            seg.translated_text = result[key]
            seg.translation_language = target_language
        db.commit()
        done += len(batch)
        if on_progress:
            on_progress(done, len(targets))
    return done
