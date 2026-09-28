from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domains import DOMAINS
from .languages import AUTO_DETECT, LANGUAGES, normalize_language

SubtitleMode = Literal["original", "translation", "bilingual"]


def _source_lang(v: str | None) -> str:
    code = normalize_language(v or AUTO_DETECT)
    if code is None or (code != AUTO_DETECT and not LANGUAGES[code].can_be_source):
        raise ValueError(f"Unsupported source language: {v}")
    return code


def _target_lang(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    code = normalize_language(v)
    if code is None or code == AUTO_DETECT or not LANGUAGES[code].can_be_target:
        raise ValueError(f"Unsupported target language: {v}")
    return code


def _domain(v: str | None) -> str:
    v = v or "general"
    if v not in DOMAINS:
        raise ValueError(f"Unknown domain: {v}")
    return v


class ProjectCreate(BaseModel):
    source_language: str = AUTO_DETECT
    target_language: str | None = None
    domain: str = "general"
    subtitle_mode: SubtitleMode = "bilingual"

    @field_validator("source_language")
    @classmethod
    def v_source(cls, v):
        return _source_lang(v)

    @field_validator("target_language")
    @classmethod
    def v_target(cls, v):
        return _target_lang(v)

    @field_validator("domain")
    @classmethod
    def v_domain(cls, v):
        return _domain(v)


class ProjectUpdate(BaseModel):
    source_language: str | None = None
    target_language: str | None = None
    domain: str | None = None
    subtitle_mode: SubtitleMode | None = None

    @field_validator("source_language")
    @classmethod
    def v_source(cls, v):
        return None if v is None else _source_lang(v)

    @field_validator("target_language")
    @classmethod
    def v_target(cls, v):
        return _target_lang(v)

    @field_validator("domain")
    @classmethod
    def v_domain(cls, v):
        return None if v is None else _domain(v)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str | None
    file_type: str | None
    file_size: int | None
    duration: float | None
    media_kind: str | None = None
    source_language: str
    detected_language: str | None
    target_language: str | None
    domain: str
    subtitle_mode: str
    status: str
    steps: dict
    progress: float
    error_message: str | None
    segment_count: int = 0
    created_at: datetime
    updated_at: datetime


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    segment_index: int
    start_time: float
    end_time: float
    original_text: str
    translated_text: str | None
    translation_language: str | None
    speaker: str | None
    confidence: float | None
    updated_at: datetime


class SegmentUpdate(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)
    original_text: str | None = None
    translated_text: str | None = None
    speaker: str | None = None


class SegmentCreate(BaseModel):
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    original_text: str = ""
    translated_text: str | None = None
    speaker: str | None = None


class SplitRequest(BaseModel):
    # Time at which to split; defaults to the midpoint.
    at_time: float | None = None
    # Character offsets in the texts where the second part begins.
    original_split: int | None = None
    translated_split: int | None = None


class MergeRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=2)


class TranscribeRequest(BaseModel):
    source_language: str | None = None

    @field_validator("source_language")
    @classmethod
    def v_source(cls, v):
        return None if v is None else _source_lang(v)


class TranslateRequest(BaseModel):
    target_language: str | None = None
    domain: str | None = None
    # Only these segments (Retranslate / Retranslate Selected); all when omitted.
    segment_ids: list[str] | None = None

    @field_validator("target_language")
    @classmethod
    def v_target(cls, v):
        return _target_lang(v)

    @field_validator("domain")
    @classmethod
    def v_domain(cls, v):
        return None if v is None else _domain(v)


class ExportRequest(BaseModel):
    format: Literal["srt", "vtt", "txt"] = "srt"
    content: Literal["original", "translation", "bilingual"] = "original"
    order: Literal["original_first", "translation_first"] = "original_first"


class GlossaryIn(BaseModel):
    term: str = Field(min_length=1, max_length=256)
    translation: str = Field(min_length=1, max_length=512)
    target_language: str | None = None
    project_id: str | None = None
    note: str | None = None

    @field_validator("target_language")
    @classmethod
    def v_target(cls, v):
        return _target_lang(v)


class GlossaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    term: str
    translation: str
    target_language: str | None
    project_id: str | None
    note: str | None
