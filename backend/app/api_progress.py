from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_project_access
from app.db.models import DocumentAnalysis, Milestone, Project, Submission

router = APIRouter(
    prefix="/projects",
    tags=["Progress Monitoring"],
    dependencies=[Depends(require_project_access)],
)


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
    analyses_by_submission: dict[int, list[DocumentAnalysis]] = {}
    if submissions:
        analyses = (
            db.query(DocumentAnalysis)
            .filter(
                DocumentAnalysis.submission_id.in_(
                    [submission.id for submission in submissions]
                )
            )
            .all()
        )
        for analysis in analyses:
            analyses_by_submission.setdefault(analysis.submission_id, []).append(
                analysis
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
            "document_analyses": _submission_document_analyses(
                submission,
                analyses_by_submission.get(submission.id, []),
            ),
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


def _submission_document_analyses(
    submission: Submission,
    analyses: list[DocumentAnalysis],
) -> list[dict]:
    analyses_by_type = {analysis.document_type: analysis for analysis in analyses}
    documents = []

    for document_type, file_path in (
        ("report", submission.report_path),
        ("srs", submission.srs_path),
    ):
        if not file_path:
            continue

        analysis = analyses_by_type.get(document_type)
        if analysis is None:
            documents.append({
                "submission_id": submission.id,
                "document_type": document_type,
                "status": "not_analyzed",
                "analysis_status": None,
                "completeness_percentage": None,
                "missing_sections": [],
                "warnings": [],
                "extraction_errors": [],
            })
            continue

        analysis_status = analysis.analysis_status
        status = (
            analysis_status
            if analysis_status in {"complete", "incomplete"}
            else "failed"
        )
        documents.append({
            "submission_id": submission.id,
            "document_type": document_type,
            "status": status,
            "analysis_status": analysis_status,
            "completeness_percentage": analysis.completeness_percentage,
            "missing_sections": analysis.missing_sections or [],
            "warnings": analysis.warnings or [],
            "extraction_errors": analysis.extraction_errors or [],
        })

    return documents
