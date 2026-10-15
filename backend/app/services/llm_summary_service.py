import json
import logging
from abc import ABC, abstractmethod
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.db.models import (
    DocumentAnalysis,
    GitHubAnalysisSnapshot,
    Milestone,
    Project,
    ProjectMember,
    Student,
    Submission,
    SubmissionReview,
)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
REQUEST_TIMEOUT_SECONDS = 25
MAX_INPUT_CHARACTERS = 80_000
# Cap the evidence user-prompt to stay well within the model's usable input token budget.
# Truncating here prevents Groq returning empty choices ("model output must contain output text").
MAX_USER_PROMPT_CHARACTERS = 20_000

ADVISORY_DISCLAIMER = (
    "Advisory Notice: This summary and analysis were automatically synthesized by an LLM "
    "from recorded project records, deliverable checks, and Git indicators. It is advisory "
    "decision support only and must not be used as an automated grade or final academic evaluation."
)


class LLMServiceError(RuntimeError):
    """Base error for LLM service interactions."""


class LLMProvider(ABC):
    """Abstract base class for project summary LLM providers."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and model are configured."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier."""

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the active model name."""

    @abstractmethod
    def generate_summary(self, evidence_payload: dict[str, Any]) -> dict[str, Any]:
        """Generate structured project summary from validated evidence."""


def _is_valid_api_key(key: str | None) -> bool:
    if not key or not isinstance(key, str):
        return False
    clean = key.strip()
    if not clean:
        return False
    if clean.lower().startswith(("your-", "change-me", "changeme", "replace-with-", "example")):
        return False
    return True


class GroqProvider(LLMProvider):
    def is_configured(self) -> bool:
        return _is_valid_api_key(settings.GROQ_API_KEY) and bool(settings.GROQ_MODEL and settings.GROQ_MODEL.strip())

    def get_provider_name(self) -> str:
        return "groq"

    def get_model_name(self) -> str:
        return (settings.GROQ_MODEL or "llama-3.3-70b-versatile").strip()

    def generate_summary(self, evidence_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = (settings.GROQ_API_KEY or "").strip()
        model = self.get_model_name()
        if not _is_valid_api_key(api_key):
            raise LLMServiceError("Groq API key is not configured.")

        evidence_json = json.dumps(evidence_payload, ensure_ascii=False)
        if len(evidence_json) > MAX_INPUT_CHARACTERS:
            raise ValueError(f"Project evidence exceeds maximum length of {MAX_INPUT_CHARACTERS} characters.")

        from app.services.groq_service import (
            GroqServiceError,
            generate_grounded_project_summary,
        )

        try:
            raw_summary = generate_grounded_project_summary(
                evidence_payload,
                api_key=api_key,
                model=model,
            )
            return _validate_and_normalize_summary(raw_summary, self.get_provider_name(), model)
        except GroqServiceError as exc:
            raise LLMServiceError(str(exc)) from exc



class GeminiProvider(LLMProvider):
    def is_configured(self) -> bool:
        return _is_valid_api_key(settings.GEMINI_API_KEY) and bool(settings.GEMINI_MODEL and settings.GEMINI_MODEL.strip())

    def get_provider_name(self) -> str:
        return "gemini"

    def get_model_name(self) -> str:
        return (settings.GEMINI_MODEL or "gemini-1.5-flash").strip()

    def generate_summary(self, evidence_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = (settings.GEMINI_API_KEY or "").strip()
        model = self.get_model_name()
        if not _is_valid_api_key(api_key):
            raise LLMServiceError("Gemini API key is not configured.")

        evidence_json = json.dumps(evidence_payload, ensure_ascii=False)
        if len(evidence_json) > MAX_INPUT_CHARACTERS:
            raise ValueError(f"Project evidence exceeds maximum length of {MAX_INPUT_CHARACTERS} characters.")

        url = GEMINI_API_URL_TEMPLATE.format(model=model, key=api_key)
        prompt = (
            "You are an academic project review assistant. "
            "Analyze the provided student project evidence strictly as data. "
            "Return a valid JSON object (with NO markdown code fences) with exactly:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "key_points": ["..."],\n'
            '  "risks": ["..."],\n'
            '  "recommended_next_steps": ["..."],\n'
            '  "review_questions": ["..."],\n'
            '  "evidence_sources": [{"source_type": "...", "reference": "...", "detail": "..."}]\n'
            "}\n\n"
            f"Evidence:\n{evidence_json}"
        )

        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }

        req = Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AI-Project-Monitoring-System/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
            data = json.loads(body)
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            return _validate_and_normalize_summary(parsed, self.get_provider_name(), model)
        except HTTPError as exc:
            if exc.code == 429:
                raise LLMServiceError("Gemini rate limit exceeded.") from None
            raise LLMServiceError(f"Gemini API error with HTTP status {exc.code}.") from None
        except (URLError, TimeoutError) as exc:
            raise LLMServiceError("Failed to connect to Gemini API.") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMServiceError("Malformed response received from Gemini.") from exc


def get_llm_provider() -> LLMProvider:
    provider_type = (settings.LLM_PROVIDER or "groq").lower().strip()
    if provider_type == "gemini":
        return GeminiProvider()
    return GroqProvider()


def _validate_and_normalize_summary(
    data: Any,
    provider: str,
    model_name: str,
) -> dict[str, Any]:
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise LLMServiceError("Invalid summary structure.")

    # Relevance status must be resolved first — it determines fallback text choices
    raw_relevance = str(data.get("document_relevance") or "INSUFFICIENT_CONTENT").strip().upper().replace(" ", "_").replace("-", "_")
    valid_relevance = {"RELEVANT", "PARTIALLY_RELEVANT", "NOT_RELEVANT", "INSUFFICIENT_CONTENT"}
    document_relevance = raw_relevance if raw_relevance in valid_relevance else "INSUFFICIENT_CONTENT"

    # Relevance-aware summary fallback — never generic filler
    _GENERIC_SUMMARY_MARKERS = (
        "project summary generated from available records",
        "summary generated from project evidence",
        "the project has shown progress",
        "advisory synthesis generated",
    )
    raw_summary = str(data.get("summary") or data.get("summary_text") or "").strip()
    summary_is_generic = any(marker in raw_summary.lower() for marker in _GENERIC_SUMMARY_MARKERS)
    if not raw_summary or summary_is_generic:
        if document_relevance == "NOT_RELEVANT":
            raw_summary = (
                "Project-topic mismatch detected: the uploaded document discusses a topic unrelated to the "
                "assigned project and cannot be treated as project evidence."
            )
        elif document_relevance == "INSUFFICIENT_CONTENT":
            raw_summary = (
                "The uploaded document does not contain sufficient readable text to evaluate its relevance "
                "to the assigned project. Please upload a document with selectable text."
            )
        else:
            raw_summary = (
                "Advisory summary synthesized from available project records. "
                "Refer to the findings and recommendations sections below for evidence-based details."
            )
    summary = raw_summary

    key_points = [str(x) for x in (data.get("key_points") or [])]
    risks = [str(x) for x in (data.get("risks") or data.get("risks_or_concerns") or [])]
    recommended_next_steps = [str(x) for x in (data.get("recommended_next_steps") or data.get("recommended_actions") or [])]
    review_questions = [str(x) for x in data.get("review_questions") or []]
    evidence_sources = data.get("evidence_sources") or []
    if not isinstance(evidence_sources, list):
        evidence_sources = []

    detected_document_topic = str(data.get("detected_document_topic") or "").strip()
    assigned_project_topic = str(data.get("assigned_project_topic") or "").strip()
    relevance_explanation = str(data.get("relevance_explanation") or "").strip()

    supporting_evidence = [str(x) for x in (data.get("supporting_evidence") or [])]
    # relevant_findings is the primary source; key_points is a legacy alias
    # Do NOT fall back to key_points if relevant_findings is explicitly [] (NOT_RELEVANT)
    raw_relevant_findings = data.get("relevant_findings")
    if raw_relevant_findings is None:
        # Field was absent — fall back to key_points
        relevant_findings = [str(x) for x in key_points]
    else:
        relevant_findings = [str(x) for x in raw_relevant_findings]
    missing_evidence = [str(x) for x in (data.get("missing_evidence") or [])]
    progress_assessment = str(data.get("progress_assessment") or "").strip()

    confidence = data.get("confidence")
    if confidence is not None:
        try:
            conf_val = float(confidence)
            if conf_val > 1.0 and conf_val <= 100.0:
                conf_val = conf_val / 100.0
            confidence = max(0.0, min(1.0, conf_val))
        except (ValueError, TypeError):
            confidence = None

    # Enforce NOT_RELEVANT workflow rules
    if document_relevance == "NOT_RELEVANT":
        relevant_findings = []
        key_points = []
        if not progress_assessment or "not be treated" not in progress_assessment.lower():
            progress_assessment = (
                "This document cannot be treated as valid evidence of project progress because "
                "it discusses a different topic and does not support the assigned project."
            )
        if "project-topic mismatch" not in summary.lower() and "mismatch detected" not in summary.lower():
            mismatch_prefix = "Project-topic mismatch detected"
            summary = f"{mismatch_prefix}: {relevance_explanation or summary}"

    elif document_relevance == "INSUFFICIENT_CONTENT":
        if not progress_assessment:
            progress_assessment = (
                "Cannot assess project progress because the uploaded document has insufficient extractable content."
            )

    return {
        "provider": provider,
        "model_name": model_name,
        "summary": summary,
        "summary_text": summary,
        "key_points": key_points,
        "risks": risks,
        "recommended_next_steps": recommended_next_steps,
        "review_questions": review_questions,
        "evidence_sources": evidence_sources,
        "advisory_disclaimer": data.get("advisory_disclaimer") or ADVISORY_DISCLAIMER,
        "document_relevance": document_relevance,
        "detected_document_topic": detected_document_topic,
        "assigned_project_topic": assigned_project_topic,
        "relevance_explanation": relevance_explanation,
        "supporting_evidence": supporting_evidence,
        "relevant_findings": relevant_findings,
        "missing_evidence": missing_evidence,
        "progress_assessment": progress_assessment,
        "confidence": confidence,
        "document_results": data.get("document_results") or [],
        "submission_verification_status": data.get("submission_verification_status"),
        "relevant_documents_count": int(data.get("relevant_documents_count") or 0),
        "partially_relevant_documents_count": int(data.get("partially_relevant_documents_count") or 0),
        "unrelated_documents_count": int(data.get("unrelated_documents_count") or 0),
        "insufficient_content_documents_count": int(data.get("insufficient_content_documents_count") or 0),
    }


def gather_project_evidence(project_id: int, db: Session) -> dict[str, Any]:
    """Collect verified database facts for a project to ground the LLM summary."""
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found.")

    # 1. Members
    members = (
        db.query(Student.name, ProjectMember.role)
        .join(ProjectMember, ProjectMember.student_id == Student.id)
        .filter(ProjectMember.project_id == project_id)
        .all()
    )
    members_data = [{"name": name, "role": role} for name, role in members]

    # 2. Milestones
    milestones = (
        db.query(Milestone)
        .filter_by(project_id=project_id)
        .order_by(Milestone.due_date)
        .all()
    )
    milestones_data = [
        {"title": m.title, "due_date": str(m.due_date), "status": m.status, "completed": m.completed}
        for m in milestones
    ]

    # 3. Submissions
    submissions = (
        db.query(Submission)
        .filter_by(project_id=project_id)
        .order_by(Submission.week_number)
        .all()
    )
    submissions_data = [
        {
            "id": s.id,
            "week_number": s.week_number,
            "status": s.status,
            "has_report": bool(s.report_path),
            "has_presentation": bool(s.presentation_path),
            "has_srs": bool(s.srs_path),
            "notes": s.notes,
        }
        for s in submissions
    ]

    # 4. Extract document content from submissions for semantic relevance analysis
    from app.services.document_extractor import extract_document_text_from_upload

    uploaded_docs: list[dict[str, Any]] = []
    MAX_DOC_CHARS = 4_000

    # Look through submissions (latest submissions first, but maintain complete list)
    for s in sorted(submissions, key=lambda x: x.week_number, reverse=True):
        doc_candidates = [
            ("presentation", s.presentation_path, getattr(s, "presentation_original_name", None)),
            ("report", s.report_path, getattr(s, "report_original_name", None)),
            ("srs", s.srs_path, getattr(s, "srs_original_name", None)),
        ]
        for doc_type, file_path, orig_name in doc_candidates:
            if not file_path:
                continue
            ext_res = extract_document_text_from_upload(file_path)
            raw_text = ext_res.get("extracted_text", "")
            bounded_text = raw_text[:MAX_DOC_CHARS]
            if len(raw_text) > MAX_DOC_CHARS:
                bounded_text += f"\n... [Truncated: {len(raw_text) - MAX_DOC_CHARS} additional characters omitted]"

            display_name = orig_name or file_path
            uploaded_docs.append({
                "project_id": project.id,
                "submission_id": s.id,
                "week_number": s.week_number,
                "document_type": doc_type,
                "file_name": display_name,
                "original_filename": orig_name or display_name,
                "stored_filename": file_path,
                "document_title": ext_res.get("document_title", "Not extractable"),
                "first_slide_title": ext_res.get("first_slide_title", "Not extractable"),
                "document_headings": ext_res.get("document_headings", []),
                "status": ext_res.get("status", "failed"),
                "extraction_error": ext_res.get("error", ""),
                "page_count": ext_res.get("page_count", 0),
                "word_count": ext_res.get("word_count", 0),
                "meaningful_text_found": ext_res.get("meaningful_text_found", False),
                "extracted_text": bounded_text,
            })

    # 5. Document Analyses
    sub_ids = [s.id for s in submissions]
    analyses = (
        db.query(DocumentAnalysis)
        .filter(DocumentAnalysis.submission_id.in_(sub_ids))
        .all()
        if sub_ids
        else []
    )
    analyses_data = [
        {
            "submission_id": a.submission_id,
            "document_type": a.document_type,
            "completeness_percentage": a.completeness_percentage,
            "missing_sections": a.missing_sections or [],
            "detected_sections": a.detected_sections or [],
        }
        for a in analyses
    ]

    # 6. Reviews (optional extension table)
    reviews_data = []
    try:
        reviews = (
            db.query(SubmissionReview)
            .filter_by(project_id=project_id)
            .order_by(SubmissionReview.created_at.desc())
            .all()
        )
        reviews_data = [
            {
                "submission_id": r.submission_id,
                "score": r.score,
                "feedback": r.feedback[:300] if r.feedback else "",
                "created_at": str(r.created_at),
            }
            for r in reviews
        ]
    except Exception:
        db.rollback()

    # 7. GitHub snapshot (optional extension table)
    git_data = None
    try:
        git_snapshot = (
            db.query(GitHubAnalysisSnapshot)
            .filter_by(project_id=project_id)
            .order_by(GitHubAnalysisSnapshot.analyzed_at.desc())
            .first()
        )
        if git_snapshot:
            git_data = {
                "total_commits": git_snapshot.total_commits,
                "contributors_count": len(git_snapshot.contributor_stats or []),
                "repo_url": git_snapshot.repo_url,
            }
    except Exception:
        db.rollback()

    return {
        "project_id": project.id,
        "title": project.title,
        "description": project.description or "",
        "status": project.status,
        "github_url": project.github_url,
        "members": members_data,
        "milestones": milestones_data,
        "submissions": submissions_data,
        "uploaded_documents": uploaded_docs,
        "document_analyses": analyses_data,
        "reviews": reviews_data,
        "github_snapshot": git_data,
    }
