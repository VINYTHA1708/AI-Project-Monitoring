from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_db,
    require_faculty_project,
    require_project_access,
)
from app.db.models import Project, ProjectAISummary
from app.services.llm_summary_service import (
    LLMServiceError,
    gather_project_evidence,
    get_llm_provider,
)

router = APIRouter(
    prefix="/projects/{project_id}/ai-summary",
    tags=["AI Project Summary"],
    dependencies=[Depends(require_project_access)],
)


class EvidenceSourceItem(BaseModel):
    source_type: str
    reference: str
    detail: str


class AISummaryResponse(BaseModel):
    id: int
    project_id: int
    provider: str
    model_name: str
    summary_text: str
    key_points: list[str] = []
    risks: list[str] = []
    recommended_next_steps: list[str] = []
    review_questions: list[str] = []
    evidence_sources: list[dict] = []
    advisory_disclaimer: str | None = None
    created_at: datetime
    provider_configured: bool = True

    model_config = ConfigDict(from_attributes=True)


class AISummaryStatusResponse(BaseModel):
    provider_configured: bool
    active_provider: str
    active_model: str
    latest_summary: AISummaryResponse | None = None


@router.get("/", response_model=AISummaryStatusResponse)
def get_ai_summary(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    provider = get_llm_provider()
    configured = provider.is_configured()

    summary_payload = None
    try:
        latest = (
            db.query(ProjectAISummary)
            .filter_by(project_id=project_id)
            .order_by(ProjectAISummary.created_at.desc())
            .first()
        )
        if latest:
            summary_payload = AISummaryResponse(
                id=latest.id,
                project_id=latest.project_id,
                provider=latest.provider,
                model_name=latest.model_name,
                summary_text=latest.summary_text,
                key_points=latest.key_points or [],
                risks=latest.risks or [],
                recommended_next_steps=latest.recommended_next_steps or [],
                review_questions=latest.review_questions or [],
                evidence_sources=latest.evidence_sources or [],
                advisory_disclaimer=latest.advisory_disclaimer,
                created_at=latest.created_at,
                provider_configured=configured,
            )
    except Exception:
        db.rollback()
        summary_payload = None

    return AISummaryStatusResponse(
        provider_configured=configured,
        active_provider=provider.get_provider_name(),
        active_model=provider.get_model_name(),
        latest_summary=summary_payload,
    )


@router.post(
    "/generate",
    response_model=AISummaryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_faculty_project)],
)
def generate_ai_summary(
    project_id: int,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    provider = get_llm_provider()
    if not provider.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"LLM provider '{provider.get_provider_name()}' is not configured. "
                "Set GROQ_API_KEY (or GEMINI_API_KEY) in backend/.env to generate project summaries."
            ),
        )

    try:
        evidence = gather_project_evidence(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        summary_result = provider.generate_summary(evidence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        db_summary = ProjectAISummary(
            project_id=project_id,
            provider=summary_result["provider"],
            model_name=summary_result["model_name"],
            summary_text=summary_result["summary"],
            key_points=summary_result["key_points"],
            risks=summary_result["risks"],
            recommended_next_steps=summary_result["recommended_next_steps"],
            review_questions=summary_result["review_questions"],
            evidence_sources=summary_result["evidence_sources"],
            advisory_disclaimer=summary_result["advisory_disclaimer"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_summary)
        db.commit()
        db.refresh(db_summary)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist AI summary snapshot. Ensure database migration 0003_github_and_ai_summaries.sql is applied.",
        ) from exc

    return AISummaryResponse(
        id=db_summary.id,
        project_id=db_summary.project_id,
        provider=db_summary.provider,
        model_name=db_summary.model_name,
        summary_text=db_summary.summary_text,
        key_points=db_summary.key_points or [],
        risks=db_summary.risks or [],
        recommended_next_steps=db_summary.recommended_next_steps or [],
        review_questions=db_summary.review_questions or [],
        evidence_sources=db_summary.evidence_sources or [],
        advisory_disclaimer=db_summary.advisory_disclaimer,
        created_at=db_summary.created_at,
        provider_configured=True,
    )
