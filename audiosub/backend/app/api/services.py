"""Standalone ASR and translation service endpoints.

These run synchronously and return results directly, so the ASR and
translation engines can be called (and swapped) independently of the
project pipeline.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, ProjectStatus, Segment, Transcript
from ..schemas import GlossaryIn, SegmentOut, TranscribeRequest, TranslateRequest
from ..services import pipeline
from ..services.translation import GlossaryEntry, TranslationError
from ..services.translator import translate_segments

router = APIRouter(prefix="/api", tags=["services"])


class TranscribeServiceRequest(TranscribeRequest):
    file_id: str  # the project that owns the uploaded file


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    confidence: float | None


class TranscribeServiceResponse(BaseModel):
    language: str | None
    duration: float | None
    transcript: str
    segments: list[TranscriptSegment]


@router.post("/transcribe", response_model=TranscribeServiceResponse)
def transcribe_service(body: TranscribeServiceRequest, db: Session = Depends(get_db)):
    project = db.get(Project, body.file_id)
    if project is None or not project.file_key:
        raise HTTPException(404, "File not found")
    if pipeline.is_busy(project):
        raise HTTPException(409, "This project is currently being processed.")
    if body.source_language:
        project.source_language = body.source_language
    try:
        if not project.audio_key:
            pipeline.step_audio(db, project)
        pipeline.step_transcription(db, project)
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Transcription failed: {exc}") from exc
    transcript = db.scalars(
        select(Transcript).where(Transcript.project_id == project.id)
    ).first()
    has_segments = db.scalar(select(Segment.id).where(Segment.project_id == project.id).limit(1))
    project.status = (ProjectStatus.READY if has_segments else ProjectStatus.UPLOADED).value
    db.commit()
    return TranscribeServiceResponse(
        language=transcript.language,
        duration=transcript.duration,
        transcript=" ".join(s["text"] for s in transcript.segments),
        segments=[
            TranscriptSegment(
                id=s["id"], start=s["start"], end=s["end"], text=s["text"],
                confidence=s.get("confidence"),
            )
            for s in transcript.segments
        ],
    )


class TranslateServiceRequest(TranslateRequest):
    project_id: str
    glossary: list[GlossaryIn] = []


@router.post("/translate", response_model=list[SegmentOut])
def translate_service(body: TranslateServiceRequest, db: Session = Depends(get_db)):
    project = db.get(Project, body.project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    if pipeline.is_busy(project):
        raise HTTPException(409, "This project is currently being processed.")
    if body.target_language:
        project.target_language = body.target_language
    if body.domain:
        project.domain = body.domain
    if not project.target_language:
        raise HTTPException(400, "target_language is required")
    db.commit()
    extra = [GlossaryEntry(g.term, g.translation, g.note) for g in body.glossary]
    try:
        translate_segments(
            db, project, project.target_language, segment_ids=body.segment_ids,
            extra_glossary=extra,
        )
    except TranslationError as exc:
        raise HTTPException(502, str(exc)) from exc
    return db.scalars(
        select(Segment).where(Segment.project_id == project.id).order_by(Segment.segment_index)
    ).all()
