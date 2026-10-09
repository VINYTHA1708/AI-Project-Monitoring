from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Project, Submission

router = APIRouter(
    prefix="/projects/{project_id}/submissions",
    tags=["Submissions"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SubmissionCreate(BaseModel):
    week_number: int = Field(ge=1, le=52)
    report_path: str | None = None
    presentation_path: str | None = None
    srs_path: str | None = None
    notes: str | None = None


class SubmissionResponse(BaseModel):
    id: int
    project_id: int
    week_number: int
    report_path: str | None
    presentation_path: str | None
    srs_path: str | None
    submitted_at: datetime | None
    status: str
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


def ensure_project_exists(project_id: int, db: Session):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/", response_model=SubmissionResponse, status_code=201)
def create_submission(
    project_id: int,
    data: SubmissionCreate,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)

    if not any([
        data.report_path,
        data.presentation_path,
        data.srs_path,
    ]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one report, presentation, or SRS path",
        )

    submission = Submission(
        project_id=project_id,
        week_number=data.week_number,
        report_path=data.report_path,
        presentation_path=data.presentation_path,
        srs_path=data.srs_path,
        notes=data.notes,
        submitted_at=datetime.now(),
        status="SUBMITTED",
    )

    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/", response_model=list[SubmissionResponse])
def list_submissions(
    project_id: int,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)

    return (
        db.query(Submission)
        .filter(Submission.project_id == project_id)
        .order_by(Submission.week_number)
        .all()
    )


@router.get("/{submission_id}", response_model=SubmissionResponse)
def get_submission(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()

    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    return submission


@router.delete("/{submission_id}", status_code=204)
def delete_submission(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()

    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    db.delete(submission)
    db.commit()
