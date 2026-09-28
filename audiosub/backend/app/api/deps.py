from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, Segment
from ..schemas import ProjectOut
from ..services.media import SUPPORTED_EXTENSIONS


def get_project_or_404(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def get_segment_or_404(segment_id: str, db: Session = Depends(get_db)) -> Segment:
    segment = db.get(Segment, segment_id)
    if segment is None:
        raise HTTPException(404, "Segment not found")
    return segment


def project_out(db: Session, project: Project) -> ProjectOut:
    count = db.scalar(select(func.count()).select_from(Segment).where(Segment.project_id == project.id))
    out = ProjectOut.model_validate(project)
    out.segment_count = count or 0
    out.media_kind = SUPPORTED_EXTENSIONS.get(project.file_type or "")
    return out


def reindex(db: Session, project_id: str) -> None:
    segments = db.scalars(
        select(Segment)
        .where(Segment.project_id == project_id)
        .order_by(Segment.start_time, Segment.segment_index)
    ).all()
    for i, seg in enumerate(segments):
        seg.segment_index = i
