from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_faculty_project, require_project_access
from app.db.models import Submission

router = APIRouter(
    prefix="/projects/{project_id}/submissions",
    tags=["Submissions"],
    dependencies=[Depends(require_project_access)],
)


class SubmissionResponse(BaseModel):
    id: int
    project_id: int
    week_number: int
    report_uploaded: bool
    presentation_uploaded: bool
    srs_uploaded: bool
    submitted_at: datetime | None
    status: str
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


def _submission_response(submission: Submission) -> dict:
    return {
        "id": submission.id,
        "project_id": submission.project_id,
        "week_number": submission.week_number,
        "report_uploaded": bool(submission.report_path),
        "presentation_uploaded": bool(submission.presentation_path),
        "srs_uploaded": bool(submission.srs_path),
        "submitted_at": submission.submitted_at,
        "status": submission.status,
        "notes": submission.notes,
    }


@router.get("/", response_model=list[SubmissionResponse])
def list_submissions(
    project_id: int,
    db: Session = Depends(get_db),
):
    submissions = (
        db.query(Submission)
        .filter(Submission.project_id == project_id)
        .order_by(Submission.week_number)
        .all()
    )
    return [_submission_response(submission) for submission in submissions]


@router.get("/{submission_id}", response_model=SubmissionResponse)
def get_submission(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()

    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    return _submission_response(submission)


@router.delete(
    "/{submission_id}",
    status_code=204,
    dependencies=[Depends(require_faculty_project)],
)
def delete_submission(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()

    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    db.delete(submission)
    db.commit()
