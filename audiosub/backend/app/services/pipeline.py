"""Processing pipeline: audio -> transcription -> segmentation -> translation.

Every step persists its own output and status, so a failed step can be
retried on its own (e.g. "Retry Translation") without redoing earlier steps.
"""

import logging
import os
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..config import get_settings
from ..database import SessionLocal
from ..languages import AUTO_DETECT, get_language, normalize_language
from ..models import (
    PIPELINE_STEPS,
    Project,
    ProjectStatus,
    Segment,
    StepStatus,
    Transcript,
)
from . import media
from .asr import get_asr_provider
from .segmentation import segment_transcript
from .translator import translate_segments

log = logging.getLogger(__name__)

# Share of the overall progress bar per step.
STEP_WEIGHTS = {
    "upload": 5,
    "audio": 10,
    "transcription": 45,
    "segmentation": 5,
    "translation": 30,
    "finalize": 5,
}
PROCESSABLE_STEPS = ["audio", "transcription", "segmentation", "translation"]
BUSY_STATUSES = {
    ProjectStatus.PROCESSING_AUDIO.value,
    ProjectStatus.TRANSCRIBING.value,
    ProjectStatus.TRANSLATING.value,
}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
_active: set[str] = set()
_active_lock = threading.Lock()


class PipelineError(Exception):
    pass


# ---------------------------------------------------------------- state helpers


def set_step(project: Project, step: str, status: StepStatus, error: str | None = None,
             progress: float | None = None) -> None:
    steps = dict(project.steps or {})
    entry = dict(steps.get(step) or {})
    entry["status"] = status.value
    entry["error"] = error
    if progress is not None:
        entry["progress"] = progress
    elif status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
        entry["progress"] = 1.0
    elif status == StepStatus.PENDING:
        entry["progress"] = 0.0
    steps[step] = entry
    project.steps = steps
    flag_modified(project, "steps")
    project.progress = compute_progress(steps)


def compute_progress(steps: dict) -> float:
    total = sum(STEP_WEIGHTS.values())
    acc = 0.0
    for name in PIPELINE_STEPS:
        entry = steps.get(name) or {}
        status = entry.get("status")
        if status in (StepStatus.COMPLETED.value, StepStatus.SKIPPED.value):
            acc += STEP_WEIGHTS[name]
        elif status == StepStatus.RUNNING.value:
            acc += STEP_WEIGHTS[name] * float(entry.get("progress") or 0)
    return round(100 * acc / total, 1)


def needs_translation(project: Project) -> bool:
    return bool(project.target_language) and project.subtitle_mode != "original"


def is_busy(project: Project) -> bool:
    with _active_lock:
        return project.id in _active


# ---------------------------------------------------------------- steps


def step_audio(db: Session, project: Project) -> None:
    project.status = ProjectStatus.PROCESSING_AUDIO.value
    set_step(project, "audio", StepStatus.RUNNING)
    db.commit()
    storage = media_storage()
    with storage.local_path(project.file_key) as src:
        info = media.probe(src)
        if not info["has_audio"]:
            raise PipelineError("The file has no audio track.")
        fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            duration = media.extract_audio(src, tmp_wav)
            audio_key = f"projects/{project.id}/audio.wav"
            storage.save_path(audio_key, tmp_wav)
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)
    project.audio_key = audio_key
    project.duration = info["duration"] or duration
    set_step(project, "audio", StepStatus.COMPLETED)
    db.commit()


def step_transcription(db: Session, project: Project) -> None:
    if not project.audio_key:
        raise PipelineError("Audio has not been extracted yet.")
    project.status = ProjectStatus.TRANSCRIBING.value
    set_step(project, "transcription", StepStatus.RUNNING)
    db.commit()

    asr_lang = None
    if project.source_language and project.source_language != AUTO_DETECT:
        lang = get_language(project.source_language)
        asr_lang = lang.asr_code if lang else None

    provider = get_asr_provider()
    with media_storage().local_path(project.audio_key) as wav:
        result = provider.transcribe(wav, language=asr_lang)

    db.execute(delete(Transcript).where(Transcript.project_id == project.id))
    data = result.to_dict()
    db.add(
        Transcript(
            project_id=project.id,
            provider=result.provider,
            model=result.model,
            language=result.language,
            duration=result.duration,
            segments=data["segments"],
        )
    )
    detected = normalize_language(result.language)
    project.detected_language = detected or result.language
    if result.duration and not project.duration:
        project.duration = result.duration
    set_step(project, "transcription", StepStatus.COMPLETED)
    db.commit()


def step_segmentation(db: Session, project: Project) -> None:
    transcript = db.scalars(
        select(Transcript)
        .where(Transcript.project_id == project.id)
        .order_by(Transcript.created_at.desc())
    ).first()
    if transcript is None:
        raise PipelineError("No transcript available; run transcription first.")
    set_step(project, "segmentation", StepStatus.RUNNING)
    db.commit()

    cues = segment_transcript(transcript.segments)
    db.execute(delete(Segment).where(Segment.project_id == project.id))
    for i, cue in enumerate(cues):
        db.add(
            Segment(
                project_id=project.id,
                segment_index=i,
                start_time=cue.start,
                end_time=cue.end,
                original_text=cue.text,
                confidence=cue.confidence,
            )
        )
    set_step(project, "segmentation", StepStatus.COMPLETED)
    # New original text invalidates the old translation.
    if needs_translation(project):
        set_step(project, "translation", StepStatus.PENDING)
    db.commit()


def step_translation(db: Session, project: Project, segment_ids: list[str] | None = None) -> None:
    if not needs_translation(project):
        set_step(project, "translation", StepStatus.SKIPPED)
        db.commit()
        return
    project.status = ProjectStatus.TRANSLATING.value
    set_step(project, "translation", StepStatus.RUNNING, progress=0.0)
    db.commit()

    def on_progress(done: int, total: int) -> None:
        set_step(project, "translation", StepStatus.RUNNING, progress=done / total)
        db.commit()

    translate_segments(
        db, project, project.target_language, segment_ids=segment_ids, on_progress=on_progress
    )
    set_step(project, "translation", StepStatus.COMPLETED)
    db.commit()


def step_finalize(db: Session, project: Project) -> None:
    set_step(project, "finalize", StepStatus.COMPLETED)
    project.status = ProjectStatus.READY.value
    project.error_message = None
    db.commit()


STEP_FUNCS: dict[str, Callable[[Session, Project], None]] = {
    "audio": step_audio,
    "transcription": step_transcription,
    "segmentation": step_segmentation,
    "translation": step_translation,
}


def media_storage():
    from ..storage import get_storage

    return get_storage()


# ---------------------------------------------------------------- orchestration


def _run(project_id: str, steps: list[str]) -> None:
    db = SessionLocal()
    current = None
    try:
        project = db.get(Project, project_id)
        if project is None:
            return
        for current in steps:
            STEP_FUNCS[current](db, project)
        current = "finalize"
        step_finalize(db, project)
    except Exception as exc:  # record the failure on the step; keep earlier results
        log.exception("Pipeline step %s failed for project %s", current, project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project is not None:
            message = str(exc) or exc.__class__.__name__
            if current:
                set_step(project, current, StepStatus.FAILED, error=message)
            project.status = ProjectStatus.FAILED.value
            project.error_message = f"{current}: {message}" if current else message
            db.commit()
    finally:
        db.close()
        with _active_lock:
            _active.discard(project_id)


def prepare_steps(db: Session, project: Project, steps: list[str]) -> None:
    """Mark the steps that are about to run (and everything after) as pending."""
    first = PIPELINE_STEPS.index(steps[0])
    for name in PIPELINE_STEPS[first:]:
        set_step(project, name, StepStatus.PENDING)
    project.error_message = None
    db.commit()


def start(db: Session, project: Project, from_step: str = "audio", only: list[str] | None = None) -> None:
    """Run steps from `from_step` to the end (or exactly `only`)."""
    if only is not None:
        steps = only
    else:
        steps = PROCESSABLE_STEPS[PROCESSABLE_STEPS.index(from_step):]
    with _active_lock:
        if project.id in _active:
            raise PipelineError("This project is already being processed.")
        _active.add(project.id)
    try:
        prepare_steps(db, project, steps)
        project.status = {
            "audio": ProjectStatus.PROCESSING_AUDIO,
            "transcription": ProjectStatus.TRANSCRIBING,
            "segmentation": ProjectStatus.TRANSCRIBING,
            "translation": ProjectStatus.TRANSLATING,
        }[steps[0]].value
        db.commit()
    except Exception:
        with _active_lock:
            _active.discard(project.id)
        raise

    if get_settings().run_jobs_in_background:
        _executor.submit(_run, project.id, steps)
    else:
        _run(project.id, steps)


def first_failed_step(project: Project) -> str | None:
    for name in PROCESSABLE_STEPS:
        if (project.steps or {}).get(name, {}).get("status") == StepStatus.FAILED.value:
            return name
    for name in PROCESSABLE_STEPS:
        if (project.steps or {}).get(name, {}).get("status") != StepStatus.COMPLETED.value:
            return name
    return None


def recover_interrupted_jobs() -> None:
    """On startup, mark jobs that were running when the server stopped as failed."""
    db = SessionLocal()
    try:
        for project in db.scalars(select(Project).where(Project.status.in_(BUSY_STATUSES))):
            for name in PROCESSABLE_STEPS:
                if (project.steps or {}).get(name, {}).get("status") == StepStatus.RUNNING.value:
                    set_step(project, name, StepStatus.FAILED, error="Interrupted by server restart.")
            project.status = ProjectStatus.FAILED.value
            project.error_message = "Processing was interrupted; click Retry to continue."
        db.commit()
    finally:
        db.close()
