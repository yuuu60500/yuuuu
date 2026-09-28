import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, Segment
from ..schemas import MergeRequest, SegmentCreate, SegmentOut, SegmentUpdate, SplitRequest
from ..services.segmentation import is_cjk, wrap_lines
from .deps import get_project_or_404, get_segment_or_404, reindex

router = APIRouter(tags=["segments"])


def _ordered(db: Session, project_id: str) -> list[Segment]:
    return list(
        db.scalars(
            select(Segment).where(Segment.project_id == project_id).order_by(Segment.segment_index)
        )
    )


@router.get("/api/projects/{project_id}/segments", response_model=list[SegmentOut])
def list_segments(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return _ordered(db, project.id)


@router.post("/api/projects/{project_id}/segments", response_model=SegmentOut, status_code=201)
def add_segment(
    body: SegmentCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    if body.end_time <= body.start_time:
        raise HTTPException(422, "End time must be after start time.")
    seg = Segment(
        project_id=project.id,
        segment_index=10**9,
        start_time=body.start_time,
        end_time=body.end_time,
        original_text=body.original_text,
        translated_text=body.translated_text,
        translation_language=project.target_language if body.translated_text else None,
        speaker=body.speaker,
    )
    db.add(seg)
    db.flush()
    reindex(db, project.id)
    db.commit()
    return seg


@router.patch("/api/segments/{segment_id}", response_model=SegmentOut)
def update_segment(
    body: SegmentUpdate,
    seg: Segment = Depends(get_segment_or_404),
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_time", seg.start_time)
    end = data.get("end_time", seg.end_time)
    if end <= start:
        raise HTTPException(422, "End time must be after start time.")
    for key, value in data.items():
        setattr(seg, key, value)
    if "translated_text" in data and data["translated_text"]:
        seg.translation_language = seg.project.target_language
    if "start_time" in data:
        db.flush()
        reindex(db, seg.project_id)
    db.commit()
    db.refresh(seg)
    return seg


@router.delete("/api/segments/{segment_id}", status_code=204)
def delete_segment(seg: Segment = Depends(get_segment_or_404), db: Session = Depends(get_db)):
    project_id = seg.project_id
    db.delete(seg)
    db.flush()
    reindex(db, project_id)
    db.commit()
    return Response(status_code=204)


def _split_text(text: str | None, ratio: float, at: int | None) -> tuple[str | None, str | None]:
    if text is None:
        return None, None
    flat = text.replace("\n", " ").strip()
    if at is not None:
        at = max(0, min(len(flat), at))
        return flat[:at].strip(), flat[at:].strip()
    if not flat:
        return "", ""
    target = round(len(flat) * ratio)
    if is_cjk(flat):
        return flat[:target].strip(), flat[target:].strip()
    spaces = [m.start() for m in re.finditer(" ", flat)]
    if not spaces:
        return flat, ""
    cut = min(spaces, key=lambda i: abs(i - target))
    return flat[:cut].strip(), flat[cut:].strip()


@router.post("/api/segments/{segment_id}/split", response_model=list[SegmentOut])
def split_segment(
    body: SplitRequest | None = None,
    seg: Segment = Depends(get_segment_or_404),
    db: Session = Depends(get_db),
):
    body = body or SplitRequest()
    at = body.at_time if body.at_time is not None else (seg.start_time + seg.end_time) / 2
    if not (seg.start_time < at < seg.end_time):
        raise HTTPException(422, "Split time must be inside the subtitle.")
    ratio = (at - seg.start_time) / (seg.end_time - seg.start_time)
    o1, o2 = _split_text(seg.original_text, ratio, body.original_split)
    t1, t2 = _split_text(seg.translated_text, ratio, body.translated_split)

    second = Segment(
        project_id=seg.project_id,
        segment_index=seg.segment_index + 1,
        start_time=round(at, 3),
        end_time=seg.end_time,
        original_text=o2 or "",
        translated_text=t2,
        translation_language=seg.translation_language,
        speaker=seg.speaker,
        confidence=seg.confidence,
    )
    second.original_text = wrap_lines(second.original_text)
    second.translated_text = wrap_lines(t2) if t2 else t2
    seg.end_time = round(at, 3)
    seg.original_text = wrap_lines(o1 or "")
    seg.translated_text = wrap_lines(t1) if t1 else t1
    db.add(second)
    db.flush()
    reindex(db, seg.project_id)
    db.commit()
    return [seg, second]


@router.post("/api/projects/{project_id}/segments/merge", response_model=SegmentOut)
def merge_segments(
    body: MergeRequest,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    segs = [s for s in _ordered(db, project.id) if s.id in set(body.segment_ids)]
    if len(segs) != len(set(body.segment_ids)):
        raise HTTPException(404, "Some segments were not found in this project.")

    def join(parts: list[str | None]) -> str | None:
        texts = [p.replace("\n", " ").strip() for p in parts if p and p.strip()]
        if not texts:
            return None
        sep = "" if all(is_cjk(t) for t in texts) else " "
        return wrap_lines(sep.join(texts))

    first = segs[0]
    first.start_time = min(s.start_time for s in segs)
    first.end_time = max(s.end_time for s in segs)
    first.original_text = join([s.original_text for s in segs]) or ""
    first.translated_text = join([s.translated_text for s in segs])
    confidences = [s.confidence for s in segs if s.confidence is not None]
    first.confidence = min(confidences) if confidences else None
    for s in segs[1:]:
        db.delete(s)
    db.flush()
    reindex(db, project.id)
    db.commit()
    db.refresh(first)
    return first
