from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Milestone, Project, Submission

router = APIRouter(prefix="/projects", tags=["Progress Monitoring"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{project_id}/progress")
def get_project_progress(
    project_id: int,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    milestones = (
        db.query(Milestone)
        .filter(Milestone.project_id == project_id)
        .all()
    )

    submissions = (
        db.query(Submission)
        .filter(Submission.project_id == project_id)
        .order_by(Submission.week_number)
        .all()
    )

    total_milestones = len(milestones)
    completed_milestones = sum(1 for m in milestones if m.completed)
    overdue_milestones = [
        {
            "id": m.id,
            "title": m.title,
            "due_date": m.due_date.isoformat(),
        }
        for m in milestones
        if not m.completed and m.due_date and m.due_date < date.today()
    ]

    completion_percentage = (
        round(completed_milestones / total_milestones * 100, 2)
        if total_milestones
        else 0
    )

    submission_details = []
    for submission in submissions:
        missing_documents = []

        if not submission.report_path:
            missing_documents.append("report")
        if not submission.presentation_path:
            missing_documents.append("presentation")
        if not submission.srs_path:
            missing_documents.append("SRS")

        submission_details.append({
            "submission_id": submission.id,
            "week_number": submission.week_number,
            "status": submission.status,
            "missing_documents": missing_documents,
            "submitted_at": (
                submission.submitted_at.isoformat()
                if submission.submitted_at else None
            ),
        })

    if overdue_milestones:
        overall_status = "AT_RISK"
    elif total_milestones > 0 and completed_milestones == total_milestones:
        overall_status = "COMPLETED"
    elif total_milestones == 0:
        overall_status = "NOT_STARTED"
    else:
        overall_status = "IN_PROGRESS"

    return {
        "project_id": project.id,
        "project_title": project.title,
        "project_status": project.status,
        "overall_status": overall_status,
        "milestones": {
            "total": total_milestones,
            "completed": completed_milestones,
            "pending": total_milestones - completed_milestones,
            "completion_percentage": completion_percentage,
            "overdue": overdue_milestones,
        },
        "submissions": {
            "total": len(submissions),
            "weeks_submitted": [s.week_number for s in submissions],
            "details": submission_details,
        },
    }
