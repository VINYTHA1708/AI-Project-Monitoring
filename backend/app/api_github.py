from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_project_access
from app.db.models import (
    GitHubAnalysisSnapshot,
    Project,
    ProjectMember,
    Student,
)
from app.services.github_service import (
    GitHubServiceError,
    fetch_github_contributions,
)

router = APIRouter(
    prefix="/projects/{project_id}/github",
    tags=["GitHub Integration"],
    dependencies=[Depends(require_project_access)],
)


class ContributorStat(BaseModel):
    username: str
    name: str
    email: str
    commits: int
    avatar_url: str = ""
    matched_member: str | None = None
    match_confidence: str = "unmatched"


class GitHubAnalysisResponse(BaseModel):
    id: int
    project_id: int
    repo_url: str
    total_commits: int
    contributor_stats: list[ContributorStat] = []
    recent_activity: dict | list | None = None
    limitations_disclaimer: str | None = None
    analyzed_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _get_enrolled_members(project_id: int, db: Session) -> list[dict]:
    members = (
        db.query(Student)
        .join(ProjectMember, ProjectMember.student_id == Student.id)
        .filter(ProjectMember.project_id == project_id)
        .all()
    )
    return [
        {
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "registration_number": s.registration_number,
        }
        for s in members
    ]


@router.get("/analysis", response_model=GitHubAnalysisResponse | None)
def get_github_analysis(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    snapshot = None
    try:
        snapshot = (
            db.query(GitHubAnalysisSnapshot)
            .filter_by(project_id=project_id)
            .order_by(GitHubAnalysisSnapshot.analyzed_at.desc())
            .first()
        )
    except Exception:
        db.rollback()
        snapshot = None
    return snapshot


@router.post(
    "/analyze",
    response_model=GitHubAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_github_repository(
    project_id: int,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This project does not have an associated GitHub repository URL.",
        )

    enrolled = _get_enrolled_members(project_id, db)

    try:
        data = fetch_github_contributions(
            repo_url=project.github_url,
            project_members=enrolled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except GitHubServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        snapshot = GitHubAnalysisSnapshot(
            project_id=project_id,
            repo_url=data["repo_url"],
            total_commits=data["total_commits"],
            contributor_stats=data["contributor_stats"],
            recent_activity=data["recent_activity"],
            limitations_disclaimer=data["limitations_disclaimer"],
            analyzed_at=datetime.now(timezone.utc),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist GitHub analysis snapshot to database. Ensure migration 0003_github_and_ai_summaries.sql is applied.",
        ) from exc
