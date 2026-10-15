import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    Principal,
    get_db,
    require_faculty_project,
    require_project_access,
)
from app.db.models import (
    DocumentAnalysis,
    DocumentRelevanceAnalysis,
    Project,
    ProjectMember,
    Student,
    Submission,
)

router = APIRouter(
    prefix="/projects/{project_id}/submissions",
    tags=["Submissions"],
    dependencies=[Depends(require_project_access)],
)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _build_content_disposition(filename: str, disposition: str = "attachment") -> str:
    clean_name = filename.replace("\r", "").replace("\n", "").strip()
    ascii_name = clean_name.encode("ascii", "replace").decode("ascii").replace('"', '\\"')
    quoted_name = quote(clean_name, safe="")
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted_name}'


def _normalize_category(document_id: str) -> str:
    key = str(document_id).lower().strip()
    if key in ("report", "presentation", "srs"):
        return key
    if key.endswith("_report") or key.endswith("-report"):
        return "report"
    if key.endswith("_presentation") or key.endswith("-presentation"):
        return "presentation"
    if key.endswith("_srs") or key.endswith("-srs"):
        return "srs"
    if "report" in key:
        return "report"
    if "presentation" in key or "ppt" in key:
        return "presentation"
    if "srs" in key:
        return "srs"
    raise HTTPException(status_code=404, detail="Document not found for this submission.")


def _resolve_submission_document(
    submission: Submission,
    category: str,
    project: Project,
    db: Session,
) -> dict | None:
    stored_val = getattr(submission, f"{category}_path", None)
    if not stored_val:
        return None

    filename_only = Path(stored_val).name
    file_path = (UPLOAD_DIR / filename_only).resolve()

    # Security check: Ensure file path stays strictly within UPLOAD_DIR
    if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
        return None

    exists = file_path.is_file()
    file_size = file_path.stat().st_size if exists else 0
    ext = file_path.suffix.lower()

    # Determine original filename: 1. DB column, 2. Sidecar .meta.json, 3. Clean fallback
    orig_name = getattr(submission, f"{category}_original_name", None)
    if not orig_name:
        meta_file = file_path.with_suffix(file_path.suffix + ".meta.json")
        if meta_file.exists():
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    orig_name = json.load(f).get("original_filename")
            except Exception:
                pass

    if not orig_name:
        cat_labels = {
            "report": "Report",
            "presentation": "Presentation",
            "srs": "SRS",
        }
        orig_name = f"Project_{submission.project_id}_Week_{submission.week_number}_{cat_labels.get(category, category)}{ext}"

    display_types = {
        "report": "Project Report",
        "presentation": "Presentation Slides",
        "srs": "Software Requirements Specification (SRS)",
    }

    doc_analysis = (
        db.query(DocumentAnalysis)
        .filter_by(submission_id=submission.id, document_type=category)
        .first()
    )

    relevance_analysis = (
        db.query(DocumentRelevanceAnalysis)
        .filter_by(submission_id=submission.id, file_type=category)
        .first()
    )

    analysis_status = "Not analyzed"
    if doc_analysis:
        analysis_status = doc_analysis.analysis_status.upper()
        if doc_analysis.completeness_percentage is not None:
            analysis_status = f"{doc_analysis.completeness_percentage}% Complete"
    elif relevance_analysis:
        analysis_status = relevance_analysis.document_relevance.replace("_", " ").title()

    relevance_status = relevance_analysis.document_relevance if relevance_analysis else None
    detected_topic = relevance_analysis.detected_document_topic if relevance_analysis else None

    # Get team member names
    team_members = [
        name
        for (name,) in db.query(Student.name)
        .join(ProjectMember, ProjectMember.student_id == Student.id)
        .filter(ProjectMember.project_id == project.id)
        .all()
    ]

    can_preview = ext == ".pdf"

    return {
        "document_id": category,
        "document_type": category,
        "display_type": display_types.get(category, category.capitalize()),
        "file_type": ext.lstrip("."),
        "original_filename": orig_name,
        "file_size": file_size,
        "file_size_formatted": _format_file_size(file_size),
        "file_exists": exists,
        "submission_id": submission.id,
        "week_number": submission.week_number,
        "submitted_at": submission.submitted_at,
        "project_id": submission.project_id,
        "project_title": project.title,
        "team_members": team_members,
        "analysis_status": analysis_status,
        "relevance_status": relevance_status,
        "detected_topic": detected_topic,
        "can_preview": can_preview,
        "download_url": f"/projects/{submission.project_id}/submissions/{submission.id}/documents/{category}/download",
        "preview_url": f"/projects/{submission.project_id}/submissions/{submission.id}/documents/{category}/preview",
    }


class SubmissionResponse(BaseModel):
    id: int
    project_id: int
    week_number: int
    report_uploaded: bool
    report_filename: str | None = None
    presentation_uploaded: bool
    presentation_filename: str | None = None
    srs_uploaded: bool
    srs_filename: str | None = None
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
        "report_filename": submission.report_original_name,
        "presentation_uploaded": bool(submission.presentation_path),
        "presentation_filename": submission.presentation_original_name,
        "srs_uploaded": bool(submission.srs_path),
        "srs_filename": submission.srs_original_name,
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


@router.get("/{submission_id}/documents")
def list_submission_documents(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    account: Principal = Depends(require_project_access),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found for this project.")

    docs = []
    for cat in ("report", "presentation", "srs"):
        doc = _resolve_submission_document(submission, cat, project, db)
        if doc is not None:
            docs.append(doc)
    return docs


@router.get("/{submission_id}/documents/{document_id}/download")
def download_submission_document(
    project_id: int,
    submission_id: int,
    document_id: str,
    db: Session = Depends(get_db),
    account: Principal = Depends(require_project_access),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found for this project.")

    category = _normalize_category(document_id)
    stored_name = getattr(submission, f"{category}_path", None)
    if not stored_name:
        raise HTTPException(
            status_code=404,
            detail=f"No {category} document uploaded for this submission.",
        )

    # Safe filesystem path resolution
    file_name_only = Path(stored_name).name
    resolved_path = (UPLOAD_DIR / file_name_only).resolve()
    if not resolved_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file not found on server.",
        )

    # Resolve original filename
    orig_name = getattr(submission, f"{category}_original_name", None)
    if not orig_name:
        meta_file = resolved_path.with_suffix(resolved_path.suffix + ".meta.json")
        if meta_file.exists():
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    orig_name = json.load(f).get("original_filename")
            except Exception:
                pass
    if not orig_name:
        orig_name = f"Project_{project_id}_Week_{submission.week_number}_{category}{resolved_path.suffix.lower()}"

    ext = resolved_path.suffix.lower()
    media_type = MIME_TYPES.get(ext, "application/octet-stream")
    content_disposition = _build_content_disposition(orig_name, "attachment")

    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=orig_name,
        headers={
            "Content-Disposition": content_disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        },
    )


@router.get("/{submission_id}/documents/{document_id}/preview")
def preview_submission_document(
    project_id: int,
    submission_id: int,
    document_id: str,
    db: Session = Depends(get_db),
    account: Principal = Depends(require_project_access),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    submission = db.query(Submission).filter_by(
        id=submission_id,
        project_id=project_id,
    ).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found for this project.")

    category = _normalize_category(document_id)
    stored_name = getattr(submission, f"{category}_path", None)
    if not stored_name:
        raise HTTPException(
            status_code=404,
            detail=f"No {category} document uploaded for this submission.",
        )

    # Safe filesystem path resolution
    file_name_only = Path(stored_name).name
    resolved_path = (UPLOAD_DIR / file_name_only).resolve()
    if not resolved_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file not found on server.",
        )

    ext = resolved_path.suffix.lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Preview unavailable for this file type. Download to open the original document.",
        )

    # Resolve original filename
    orig_name = getattr(submission, f"{category}_original_name", None)
    if not orig_name:
        meta_file = resolved_path.with_suffix(resolved_path.suffix + ".meta.json")
        if meta_file.exists():
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    orig_name = json.load(f).get("original_filename")
            except Exception:
                pass
    if not orig_name:
        orig_name = f"Project_{project_id}_Week_{submission.week_number}_{category}{resolved_path.suffix.lower()}"

    content_disposition = _build_content_disposition(orig_name, "inline")

    return FileResponse(
        path=resolved_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        },
    )
