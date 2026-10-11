import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_faculty_project, require_project_access
from app.db.models import DocumentAnalysis, Project, Submission
from app.services.document_completeness import (
    ANALYSIS_LIMITATION_DISCLAIMER,
    SECTION_RATIONALES,
    analyze_document_completeness,
)

router = APIRouter(
    prefix="/projects",
    tags=["Document Analysis"],
    dependencies=[Depends(require_project_access)],
)


class AnalyzeDocumentRequest(BaseModel):
    document_type: Literal["report", "srs"]


class DocumentAnalysisResponse(BaseModel):
    id: int
    submission_id: int
    document_type: str
    analysis_status: str
    completeness_percentage: float | None
    detected_sections: list[str] | None
    missing_sections: list[str] | None
    page_count: int | None
    word_count: int | None
    warnings: list[str] | None
    extraction_errors: list[str] | None
    analyzed_at: datetime
    disclaimer: str | None = None
    section_rationales: dict[str, str] = {}

    model_config = ConfigDict(from_attributes=True)


def _analysis_payload(analysis: DocumentAnalysis) -> dict:
    return {
        "id": analysis.id,
        "submission_id": analysis.submission_id,
        "document_type": analysis.document_type,
        "analysis_status": analysis.analysis_status,
        "completeness_percentage": analysis.completeness_percentage,
        "detected_sections": analysis.detected_sections or [],
        "missing_sections": analysis.missing_sections or [],
        "page_count": analysis.page_count,
        "word_count": analysis.word_count,
        "warnings": analysis.warnings or [],
        "extraction_errors": analysis.extraction_errors or [],
        "analyzed_at": analysis.analyzed_at,
        "disclaimer": ANALYSIS_LIMITATION_DISCLAIMER,
        "section_rationales": SECTION_RATIONALES.get(analysis.document_type, {}),
    }



def _safe_messages(messages: list[str]) -> list[str]:
    return [
        re.sub(r"(?:[A-Za-z]:\\|\\\\|/)[^\s\"'<>]+", "[local file]", str(message))
        for message in messages
    ]


@router.post(
    "/{project_id}/submissions/{submission_id}/analyze",
    response_model=DocumentAnalysisResponse,
    dependencies=[Depends(require_faculty_project)],
)
def analyze_submission_document(
    project_id: int,
    submission_id: int,
    data: AnalyzeDocumentRequest,
    db: Session = Depends(get_db),
):
    try:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        submission = db.query(Submission).filter_by(
            id=submission_id,
            project_id=project_id,
        ).first()
        if submission is None:
            raise HTTPException(status_code=404, detail="Submission not found")

        file_path = (
            submission.report_path
            if data.document_type == "report"
            else submission.srs_path
        )
        if not file_path:
            raise HTTPException(
                status_code=400,
                detail=f"No {data.document_type} document has been uploaded for this submission.",
            )

        analysis_result = analyze_document_completeness(
            document_type=data.document_type,
            file_name=file_path,
        )

        analysis = db.query(DocumentAnalysis).filter_by(
            submission_id=submission_id,
            document_type=data.document_type,
        ).first()
        if analysis is None:
            analysis = DocumentAnalysis(
                submission_id=submission_id,
                document_type=data.document_type,
            )
            db.add(analysis)

        analysis.analysis_status = analysis_result["analysis_status"]
        analysis.completeness_percentage = analysis_result[
            "completeness_percentage"
        ]
        analysis.detected_sections = analysis_result["detected_sections"]
        analysis.missing_sections = analysis_result["missing_sections"]
        analysis.page_count = analysis_result["page_count"]
        analysis.word_count = analysis_result["word_count"]
        analysis.warnings = _safe_messages(analysis_result["warnings"])
        analysis.extraction_errors = _safe_messages(
            analysis_result["extraction_errors"]
        )
        analysis.analyzed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(analysis)
        return _analysis_payload(analysis)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save document analysis.",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to analyze the requested document.",
        ) from exc


@router.get(
    "/{project_id}/submissions/{submission_id}/analysis",
    response_model=list[DocumentAnalysisResponse],
)
def get_submission_analyses(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    try:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        submission = db.query(Submission).filter_by(
            id=submission_id,
            project_id=project_id,
        ).first()
        if submission is None:
            raise HTTPException(status_code=404, detail="Submission not found")

        analyses = (
            db.query(DocumentAnalysis)
            .filter_by(submission_id=submission_id)
            .order_by(DocumentAnalysis.document_type)
            .all()
        )
        return [_analysis_payload(analysis) for analysis in analyses]
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve document analyses.",
        ) from exc


@router.get(
    "/{project_id}/submissions/{submission_id}/analysis/{document_type}/download",
)
def download_analysis_summary(
    project_id: int,
    submission_id: int,
    document_type: str,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    analysis = db.query(DocumentAnalysis).filter_by(
        submission_id=submission_id,
        document_type=document_type,
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Document analysis not found.")

    doc_label = "Software Requirements Specification (SRS)" if document_type == "srs" else "Project Report"
    rationales = SECTION_RATIONALES.get(document_type, {})

    detected_text = "\n".join(f"- [x] {s}" for s in (analysis.detected_sections or [])) or "- None detected"
    missing_text = "\n".join(
        f"- [ ] {s} — *Why expected*: {rationales.get(s, 'Standard required section')}"
        for s in (analysis.missing_sections or [])
    ) or "- None (All expected sections detected)"

    warnings_text = "\n".join(f"- {w}" for w in (analysis.warnings or [])) or "- None"

    content = f"""# Document Completeness Analysis Summary

**Project**: {project.title} (ID #{project.id})
**Submission**: #{submission.id} (Week {submission.week_number})
**Document Type**: {doc_label}
**Analyzed At**: {analysis.analyzed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
**Status**: {analysis.analysis_status}
**Completeness Score**: {analysis.completeness_percentage if analysis.completeness_percentage is not None else 'N/A'}%
**Page Count**: {analysis.page_count or 'N/A'}
**Word Count**: {analysis.word_count or 'N/A'}

---

## Detected Sections ({len(analysis.detected_sections or [])})
{detected_text}

## Missing Required Sections ({len(analysis.missing_sections or [])})
{missing_text}

## Analysis Warnings & Heuristic Flags
{warnings_text}

---

### Methodological Disclaimer
{ANALYSIS_LIMITATION_DISCLAIMER}
"""

    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="analysis_{project_id}_sub{submission_id}_{document_type}.md"',
        },
    )

