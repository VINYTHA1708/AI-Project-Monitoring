from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.auth.dependencies import (
    get_db,
    require_faculty_project,
    require_project_access,
)
from app.db.models import DocumentRelevanceAnalysis, Project, ProjectAISummary
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

    # Document-Project Relevance Analysis fields
    document_relevance: str | None = None
    detected_document_topic: str | None = None
    assigned_project_topic: str | None = None
    relevance_explanation: str | None = None
    supporting_evidence: list[str] = []
    relevant_findings: list[str] = []
    missing_evidence: list[str] = []
    progress_assessment: str | None = None
    confidence: float | None = None

    # Document-level verification results
    document_results: list[dict] = []
    submission_verification_status: str | None = None
    relevant_documents_count: int = 0
    partially_relevant_documents_count: int = 0
    unrelated_documents_count: int = 0
    insufficient_content_documents_count: int = 0

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
                document_relevance=getattr(latest, "document_relevance", None),
                detected_document_topic=getattr(latest, "detected_document_topic", None),
                assigned_project_topic=getattr(latest, "assigned_project_topic", None),
                relevance_explanation=getattr(latest, "relevance_explanation", None),
                supporting_evidence=getattr(latest, "supporting_evidence", None) or [],
                relevant_findings=getattr(latest, "relevant_findings", None) or getattr(latest, "key_points", None) or [],
                missing_evidence=getattr(latest, "missing_evidence", None) or [],
                progress_assessment=getattr(latest, "progress_assessment", None),
                confidence=getattr(latest, "confidence", None),
                document_results=getattr(latest, "document_results", None) or [],
                submission_verification_status=getattr(latest, "submission_verification_status", None),
                relevant_documents_count=getattr(latest, "relevant_documents_count", 0) or 0,
                partially_relevant_documents_count=getattr(latest, "partially_relevant_documents_count", 0) or 0,
                unrelated_documents_count=getattr(latest, "unrelated_documents_count", 0) or 0,
                insufficient_content_documents_count=getattr(latest, "insufficient_content_documents_count", 0) or 0,
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
        logger.error("Evidence validation error generating AI summary for project %s: %s", project_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceError as exc:
        logger.error("Provider failure generating AI summary for project %s: %s", project_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        # Persist individual document relevance analyses
        for doc_res in summary_result.get("document_results", []):
            sub_id = doc_res.get("submission_id")
            f_type = doc_res.get("file_type")
            if sub_id and f_type:
                existing_analysis = db.query(DocumentRelevanceAnalysis).filter_by(
                    submission_id=sub_id,
                    file_type=f_type,
                ).first()
                if existing_analysis is None:
                    existing_analysis = DocumentRelevanceAnalysis(
                        project_id=project_id,
                        submission_id=sub_id,
                        file_type=f_type,
                        document_identifier=doc_res.get("document_identifier", f"sub_{sub_id}_{f_type}"),
                        file_name=doc_res.get("file_name", ""),
                    )
                    db.add(existing_analysis)
                existing_analysis.document_title = doc_res.get("document_title", "Not extractable")
                existing_analysis.document_headings = doc_res.get("document_headings") or []
                existing_analysis.detected_document_topic = doc_res.get("detected_document_topic", "")
                existing_analysis.assigned_project_title = project.title
                existing_analysis.title_match_explanation = doc_res.get("title_match_explanation")
                existing_analysis.content_match_explanation = doc_res.get("content_match_explanation")
                existing_analysis.document_relevance = doc_res.get("document_relevance", "INSUFFICIENT_CONTENT")
                existing_analysis.supporting_evidence = doc_res.get("supporting_evidence") or []
                existing_analysis.conflicting_evidence = doc_res.get("conflicting_evidence") or []
                existing_analysis.missing_evidence = doc_res.get("missing_evidence") or []
                existing_analysis.recommended_action = doc_res.get("recommended_action")
                existing_analysis.confidence = doc_res.get("confidence")
                existing_analysis.analyzed_at = datetime.now(timezone.utc)

        db_summary = ProjectAISummary(
            project_id=project_id,
            provider=summary_result.get("provider") or provider.get_provider_name(),
            model_name=summary_result.get("model_name") or provider.get_model_name(),
            summary_text=summary_result.get("summary") or summary_result.get("summary_text") or "",
            key_points=summary_result.get("key_points") or [],
            risks=summary_result.get("risks") or [],
            recommended_next_steps=summary_result.get("recommended_next_steps") or [],
            review_questions=summary_result.get("review_questions") or [],
            evidence_sources=summary_result.get("evidence_sources") or [],
            advisory_disclaimer=summary_result.get("advisory_disclaimer"),
            document_relevance=summary_result.get("document_relevance"),
            detected_document_topic=summary_result.get("detected_document_topic"),
            assigned_project_topic=summary_result.get("assigned_project_topic"),
            relevance_explanation=summary_result.get("relevance_explanation"),
            supporting_evidence=summary_result.get("supporting_evidence"),
            relevant_findings=summary_result.get("relevant_findings"),
            missing_evidence=summary_result.get("missing_evidence"),
            progress_assessment=summary_result.get("progress_assessment"),
            confidence=summary_result.get("confidence"),
            document_results=summary_result.get("document_results") or [],
            submission_verification_status=summary_result.get("submission_verification_status"),
            relevant_documents_count=summary_result.get("relevant_documents_count", 0),
            partially_relevant_documents_count=summary_result.get("partially_relevant_documents_count", 0),
            unrelated_documents_count=summary_result.get("unrelated_documents_count", 0),
            insufficient_content_documents_count=summary_result.get("insufficient_content_documents_count", 0),
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_summary)
        db.commit()
        db.refresh(db_summary)
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to persist AI summary for project %s: %s: %s",
            project_id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to persist AI summary snapshot. "
                "Ensure database migrations 0003_github_and_ai_summaries.sql, "
                "0004_ai_summary_relevance.sql, and 0005_document_relevance_analyses.sql are applied."
            ),
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
        document_relevance=getattr(db_summary, "document_relevance", None),
        detected_document_topic=getattr(db_summary, "detected_document_topic", None),
        assigned_project_topic=getattr(db_summary, "assigned_project_topic", None),
        relevance_explanation=getattr(db_summary, "relevance_explanation", None),
        supporting_evidence=getattr(db_summary, "supporting_evidence", None) or [],
        relevant_findings=getattr(db_summary, "relevant_findings", None) or getattr(db_summary, "key_points", None) or [],
        missing_evidence=getattr(db_summary, "missing_evidence", None) or [],
        progress_assessment=getattr(db_summary, "progress_assessment", None),
        confidence=getattr(db_summary, "confidence", None),
        document_results=getattr(db_summary, "document_results", None) or [],
        submission_verification_status=getattr(db_summary, "submission_verification_status", None),
        relevant_documents_count=getattr(db_summary, "relevant_documents_count", 0) or 0,
        partially_relevant_documents_count=getattr(db_summary, "partially_relevant_documents_count", 0) or 0,
        unrelated_documents_count=getattr(db_summary, "unrelated_documents_count", 0) or 0,
        insufficient_content_documents_count=getattr(db_summary, "insufficient_content_documents_count", 0) or 0,
    )
