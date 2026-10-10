import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_faculty_project, require_project_access
from app.db.models import DocumentAnalysis, Project, Submission
from app.services.document_completeness import analyze_document_completeness

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

    model_config = ConfigDict(from_attributes=True)


def _analysis_payload(analysis: DocumentAnalysis) -> dict:
    return {
        "id": analysis.id,
        "submission_id": analysis.submission_id,
        "document_type": analysis.document_type,
        "analysis_status": analysis.analysis_status,
        "completeness_percentage": analysis.completeness_percentage,
        "detected_sections": analysis.detected_sections,
        "missing_sections": analysis.missing_sections,
        "page_count": analysis.page_count,
        "word_count": analysis.word_count,
        "warnings": analysis.warnings,
        "extraction_errors": analysis.extraction_errors,
        "analyzed_at": analysis.analyzed_at,
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
        analysis.analyzed_at = datetime.now()

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
