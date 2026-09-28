"""Database models.

Each stage of the pipeline owns its own data so any stage can be re-run
without touching the others:

  Project.file_key / audio_key  -> uploaded media and extracted audio (storage)
  Transcript                    -> raw ASR output, never edited
  Segment.original_text + times -> subtitle segmentation (editable)
  Segment.translated_text       -> translation (editable, re-translatable)
  exports                       -> generated on demand, never stored
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(str, enum.Enum):
    CREATED = "CREATED"
    UPLOADED = "UPLOADED"
    PROCESSING_AUDIO = "PROCESSING_AUDIO"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSLATING = "TRANSLATING"
    READY = "READY"
    FAILED = "FAILED"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Order matters: it is the order shown on the processing page.
PIPELINE_STEPS = ["upload", "audio", "transcription", "segmentation", "translation", "finalize"]


def default_steps() -> dict:
    return {name: {"status": StepStatus.PENDING.value, "error": None} for name in PIPELINE_STEPS}


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)

    filename: Mapped[str | None] = mapped_column(String(512))
    file_type: Mapped[str | None] = mapped_column(String(16))
    file_size: Mapped[int | None] = mapped_column(Integer)
    file_key: Mapped[str | None] = mapped_column(String(1024))  # storage key of the upload
    audio_key: Mapped[str | None] = mapped_column(String(1024))  # storage key of extracted WAV
    duration: Mapped[float | None] = mapped_column(Float)

    source_language: Mapped[str] = mapped_column(String(16), default="auto")
    detected_language: Mapped[str | None] = mapped_column(String(16))
    target_language: Mapped[str | None] = mapped_column(String(16))
    domain: Mapped[str] = mapped_column(String(32), default="general")
    subtitle_mode: Mapped[str] = mapped_column(String(16), default="bilingual")

    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.CREATED.value, index=True)
    steps: Mapped[dict] = mapped_column(JSON, default=default_steps)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    segments: Mapped[list["Segment"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Segment.segment_index",
    )
    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def effective_source_language(self) -> str | None:
        if self.source_language and self.source_language != "auto":
            return self.source_language
        return self.detected_language


class Transcript(Base):
    """Raw ASR output, kept verbatim so segmentation can be re-run without ASR."""

    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(16))
    duration: Mapped[float | None] = mapped_column(Float)
    # [{id, start, end, text, confidence, words: [{start, end, word, probability}]}]
    segments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project] = relationship(back_populates="transcripts")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    segment_index: Mapped[int] = mapped_column(Integer, index=True)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    original_text: Mapped[str] = mapped_column(Text, default="")
    translated_text: Mapped[str | None] = mapped_column(Text)
    translation_language: Mapped[str | None] = mapped_column(String(16))
    speaker: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    project: Mapped[Project] = relationship(back_populates="segments")


class GlossaryTerm(Base):
    """User-maintained terminology. project_id NULL means a global term."""

    __tablename__ = "glossary_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(256))
    translation: Mapped[str] = mapped_column(String(512))
    # Restrict the entry to one target language; NULL applies to all.
    target_language: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
