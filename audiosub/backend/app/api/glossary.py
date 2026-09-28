from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GlossaryTerm, Project
from ..schemas import GlossaryIn, GlossaryOut

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


@router.get("", response_model=list[GlossaryOut])
def list_terms(project_id: str | None = None, db: Session = Depends(get_db)):
    """Global terms, plus the project's own terms when project_id is given."""
    stmt = select(GlossaryTerm).order_by(GlossaryTerm.term)
    if project_id:
        stmt = stmt.where(
            (GlossaryTerm.project_id.is_(None)) | (GlossaryTerm.project_id == project_id)
        )
    else:
        stmt = stmt.where(GlossaryTerm.project_id.is_(None))
    return db.scalars(stmt).all()


@router.post("", response_model=GlossaryOut, status_code=201)
def create_term(body: GlossaryIn, db: Session = Depends(get_db)):
    if body.project_id and db.get(Project, body.project_id) is None:
        raise HTTPException(404, "Project not found")
    term = GlossaryTerm(**body.model_dump())
    db.add(term)
    db.commit()
    return term


@router.put("/{term_id}", response_model=GlossaryOut)
def update_term(term_id: str, body: GlossaryIn, db: Session = Depends(get_db)):
    term = db.get(GlossaryTerm, term_id)
    if term is None:
        raise HTTPException(404, "Term not found")
    for key, value in body.model_dump().items():
        setattr(term, key, value)
    db.commit()
    return term


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: str, db: Session = Depends(get_db)):
    term = db.get(GlossaryTerm, term_id)
    if term is None:
        raise HTTPException(404, "Term not found")
    db.delete(term)
    db.commit()
    return Response(status_code=204)
