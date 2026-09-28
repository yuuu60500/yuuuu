from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Project, ProjectStatus, Segment, StepStatus
from ..schemas import (
    ExportRequest,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SegmentOut,
    TranscribeRequest,
    TranslateRequest,
)
from ..services import export as exporter
from ..services import media, pipeline
from ..services.translation import TranslationError
from ..services.translator import translate_segments
from ..storage import get_storage
from .deps import get_project_or_404, project_out

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _ensure_idle(project: Project) -> None:
    if pipeline.is_busy(project):
        raise HTTPException(409, "This project is currently being processed.")


# ------------------------------------------------------------------ CRUD


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    return project_out(db, project)


@router.get("", response_model=list[ProjectOut])
def list_projects(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).order_by(Project.created_at.desc()).limit(limit)).all()
    return [project_out(db, p) for p in projects]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return project_out(db, project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    body: ProjectUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    return project_out(db, project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    _ensure_idle(project)
    storage = get_storage()
    for key in (project.file_key, project.audio_key):
        if key:
            try:
                storage.delete(key)
            except Exception:
                pass
    db.delete(project)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ upload & media


@router.post("/{project_id}/upload", response_model=ProjectOut)
def upload_file(
    file: UploadFile = File(...),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    _ensure_idle(project)
    filename = file.filename or "upload"
    ext = media.file_extension(filename)
    if ext not in media.SUPPORTED_EXTENSIONS:
        supported = ", ".join(e.upper() for e in media.SUPPORTED_EXTENSIONS)
        raise HTTPException(400, f"Unsupported file type .{ext}. Supported: {supported}.")

    storage = get_storage()
    key = f"projects/{project.id}/source.{ext}"
    size = storage.save(key, file.file)
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if size > max_bytes:
        storage.delete(key)
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB.")
    try:
        with storage.local_path(key) as path:
            info = media.probe(path)
    except media.MediaError as exc:
        storage.delete(key)
        raise HTTPException(400, str(exc)) from exc
    if not info["has_audio"]:
        storage.delete(key)
        raise HTTPException(400, "The file has no audio track.")

    if project.audio_key:
        storage.delete(project.audio_key)
    project.filename = filename
    project.file_type = ext
    project.file_size = size
    project.file_key = key
    project.audio_key = None
    project.duration = info["duration"]
    project.detected_language = None
    project.status = ProjectStatus.UPLOADED.value
    project.error_message = None
    pipeline.prepare_steps(db, project, ["upload"])
    pipeline.set_step(project, "upload", StepStatus.COMPLETED)
    db.commit()
    return project_out(db, project)


@router.get("/{project_id}/media")
def get_media(project: Project = Depends(get_project_or_404)):
    if not project.file_key:
        raise HTTPException(404, "No file uploaded")
    storage = get_storage()
    local = storage.local_file(project.file_key)
    if local:
        return FileResponse(local, filename=project.filename)
    url = storage.public_url(project.file_key)
    if not url:
        raise HTTPException(404, "Media not available")
    return RedirectResponse(url)


# ------------------------------------------------------------------ processing


def _require_upload(project: Project) -> None:
    if not project.file_key:
        raise HTTPException(400, "Upload a file first.")


@router.post("/{project_id}/process", response_model=ProjectOut)
def process(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    """Generate Subtitle: run the whole pipeline."""
    _require_upload(project)
    try:
        pipeline.start(db, project, from_step="audio")
    except pipeline.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(project)
    return project_out(db, project)


@router.post("/{project_id}/retry", response_model=ProjectOut)
def retry(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    """Resume from the first failed (or unfinished) step, keeping completed work."""
    _require_upload(project)
    step = pipeline.first_failed_step(project)
    if step is None:
        raise HTTPException(400, "Nothing to retry.")
    if step == "transcription" and not project.audio_key:
        step = "audio"
    # Retrying translation keeps lines that were already translated.
    kwargs = {"translation": {"only_missing": True}} if step == "translation" else None
    try:
        pipeline.start(db, project, from_step=step, step_kwargs=kwargs)
    except pipeline.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(project)
    return project_out(db, project)


@router.post("/{project_id}/transcribe", response_model=ProjectOut)
def transcribe(
    body: TranscribeRequest | None = None,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    """Run speech recognition + segmentation only (no translation)."""
    _require_upload(project)
    if body and body.source_language:
        project.source_language = body.source_language
        db.commit()
    steps = ["transcription", "segmentation"]
    if not project.audio_key:
        steps.insert(0, "audio")
    try:
        pipeline.start(db, project, only=steps)
    except pipeline.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(project)
    return project_out(db, project)


@router.post("/{project_id}/resegment", response_model=ProjectOut)
def resegment(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    """Rebuild subtitles from the stored transcript (discards subtitle edits, no ASR)."""
    try:
        pipeline.start(db, project, only=["segmentation"])
    except pipeline.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(project)
    return project_out(db, project)


@router.post("/{project_id}/translate")
def translate(
    body: TranslateRequest | None = None,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    """Translation only - never re-runs speech recognition.

    With `segment_ids` the selected lines are translated synchronously and
    returned; otherwise the whole project is re-translated in the background.
    """
    body = body or TranslateRequest()
    _ensure_idle(project)
    if body.target_language:
        project.target_language = body.target_language
    if body.domain:
        project.domain = body.domain
    if not project.target_language:
        raise HTTPException(400, "Choose a target language first.")
    if project.subtitle_mode == "original":
        project.subtitle_mode = "bilingual"
    db.commit()

    has_segments = db.scalar(select(Segment.id).where(Segment.project_id == project.id).limit(1))
    if not has_segments:
        raise HTTPException(400, "No subtitles to translate yet.")

    if body.segment_ids is not None:
        try:
            outcome = translate_segments(
                db, project, project.target_language, segment_ids=body.segment_ids
            )
        except TranslationError as exc:
            raise HTTPException(502, str(exc)) from exc
        segments = db.scalars(
            select(Segment).where(Segment.id.in_(body.segment_ids)).order_by(Segment.segment_index)
        ).all()
        return {
            "project": project_out(db, project),
            "segments": [SegmentOut.model_validate(s) for s in segments],
            "untranslated": outcome.untranslated,
        }

    try:
        pipeline.start(db, project, only=["translation"])
    except pipeline.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(project)
    return {"project": project_out(db, project), "segments": None, "untranslated": []}


# ------------------------------------------------------------------ export


def _export(project: Project, db: Session, req: ExportRequest) -> Response:
    segments = db.scalars(
        select(Segment).where(Segment.project_id == project.id).order_by(Segment.segment_index)
    ).all()
    if not segments:
        raise HTTPException(400, "No subtitles to export.")
    if req.content in ("translation", "bilingual") and not any(s.translated_text for s in segments):
        raise HTTPException(400, "This project has no translation yet.")
    cues = [
        exporter.Cue(s.start_time, s.end_time, s.original_text, s.translated_text, s.speaker)
        for s in segments
    ]
    body = exporter.render(cues, req.format, req.content, req.order)
    base = (project.filename or "subtitles").rsplit(".", 1)[0]
    lang = {
        "original": project.effective_source_language or "original",
        "translation": project.target_language or "translation",
        "bilingual": "bilingual",
    }[req.content]
    filename = f"{base}.{lang}.{req.format}"
    return Response(
        content=body.encode("utf-8"),
        media_type=exporter.MEDIA_TYPES[req.format],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_quote(filename)}",
        },
    )


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


@router.post("/{project_id}/export")
def export_post(
    body: ExportRequest, project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return _export(project, db, body)


@router.get("/{project_id}/export")
def export_get(
    format: str = "srt",
    content: str = "original",
    order: str = "original_first",
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    try:
        req = ExportRequest(format=format, content=content, order=order)
    except ValueError as exc:
        raise HTTPException(422, "Invalid export options") from exc
    return _export(project, db, req)
