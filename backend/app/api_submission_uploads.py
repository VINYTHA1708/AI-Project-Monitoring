import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_db, require_project_access
from app.core.config import settings
from app.db.models import AuthAccount, FacultyProjectAssignment, Project, Student, Submission
from app.services.n8n_notifier import (
    generate_submission_event_id,
    notify_faculty_submission,
)

router = APIRouter(
    prefix="/projects",
    tags=["Submission Uploads"],
    dependencies=[Depends(require_project_access)],
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_TYPES = {
    "report": {".pdf", ".docx"},
    "presentation": {".ppt", ".pptx"},
    "srs": {".pdf", ".docx"},
}


def _valid_signature(extension: str, header: bytes) -> bool:
    if extension == ".pdf":
        return b"%PDF-" in header[:1024]
    if extension in {".pptx", ".docx"}:
        return header.startswith(b"PK\x03\x04")
    if extension == ".ppt":
        return header.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    return False


async def save_file(file: UploadFile, category: str) -> tuple[str, str, int]:
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in ALLOWED_TYPES[category]:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {category} file type.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{uuid4().hex}{extension}"
    total_size = 0

    try:
        header = await file.read(1024)
        await file.seek(0)
        if not _valid_signature(extension, header):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {category} file content.",
            )

        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"{category.capitalize()} exceeds 10 MB.",
                    )

                output.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail=f"{category.capitalize()} file is empty.",
            )

        if extension == ".pptx":
            try:
                with zipfile.ZipFile(destination) as archive:
                    valid_presentation = "ppt/presentation.xml" in archive.namelist()
            except (OSError, zipfile.BadZipFile):
                valid_presentation = False
            if not valid_presentation:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid presentation file content.",
                )

        if extension == ".docx":
            try:
                with zipfile.ZipFile(destination) as archive:
                    valid_doc = "word/document.xml" in archive.namelist()
            except (OSError, zipfile.BadZipFile):
                valid_doc = False
            if not valid_doc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid {category} file content.",
                )

        # Write sidecar metadata JSON to disk for long-term file identity preservation
        meta_file = destination.with_suffix(destination.suffix + ".meta.json")
        try:
            with meta_file.open("w", encoding="utf-8") as meta_out:
                json.dump(
                    {
                        "original_filename": original_name,
                        "category": category,
                        "file_size": total_size,
                        "extension": extension,
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    },
                    meta_out,
                )
        except Exception:
            pass

        return destination.name, original_name, total_size

    except Exception:
        destination.unlink(missing_ok=True)
        destination.with_suffix(destination.suffix + ".meta.json").unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/{project_id}/submissions/upload", status_code=201)
async def upload_submission(
    project_id: int,
    week_number: int = Form(..., ge=1, le=52),
    report: UploadFile | None = File(None),
    presentation: UploadFile | None = File(None),
    srs: UploadFile | None = File(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    account: Principal = Depends(require_project_access),
):
    # This endpoint is student-only: faculty review via the reviews API.
    if account.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students may upload project submissions.",
        )

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not any([report, presentation, srs]):
        raise HTTPException(
            status_code=400,
            detail="Upload at least one document.",
        )

    saved_paths = []
    try:
        report_path, report_orig, report_size = (
            await save_file(report, "report") if report else (None, None, 0)
        )
        if report_path:
            saved_paths.append(report_path)

        presentation_path, presentation_orig, pres_size = (
            await save_file(presentation, "presentation")
            if presentation else (None, None, 0)
        )
        if presentation_path:
            saved_paths.append(presentation_path)

        srs_path, srs_orig, srs_size = (
            await save_file(srs, "srs") if srs else (None, None, 0)
        )
        if srs_path:
            saved_paths.append(srs_path)

        submission = Submission(
            project_id=project_id,
            week_number=week_number,
            report_path=report_path,
            report_original_name=report_orig,
            presentation_path=presentation_path,
            presentation_original_name=presentation_orig,
            srs_path=srs_path,
            srs_original_name=srs_orig,
            notes=notes,
            submitted_at=datetime.now(timezone.utc),
            status="SUBMITTED",
        )

        db.add(submission)
        db.commit()
        db.refresh(submission)

        # Return the HTTP response immediately; the notification is dispatched
        # after this block so that neither a missing student record nor an
        # absent faculty supervisor can affect the committed submission.
        response_payload = {
            "message": "Submission uploaded and recorded successfully",
            "submission_id": submission.id,
            "project_id": project_id,
            "week_number": week_number,
            "report_uploaded": bool(report_path),
            "report_filename": report_orig,
            "presentation_uploaded": bool(presentation_path),
            "presentation_filename": presentation_orig,
            "srs_uploaded": bool(srs_path),
            "srs_filename": srs_orig,
            "status": submission.status,
        }

    except Exception:
        db.rollback()
        for path in saved_paths:
            (UPLOAD_DIR / path).unlink(missing_ok=True)
            (UPLOAD_DIR / (path + ".meta.json")).unlink(missing_ok=True)
        raise

    # ── n8n e-mail notification ───────────────────────────────────────────────
    # Placed OUTSIDE the rollback try/except: the submission is already
    # committed.  Any failure here must never roll back files or DB rows.
    #
    # Student identity ── load the Student row via account.student_id so we
    # send the student's canonical name and email, not the auth-account email.
    student = db.get(Student, account.student_id) if account.student_id else None
    if student is None:
        logger.warning(
            "n8n notification skipped for submission %s: student record not found "
            "(account_id=%s, student_id=%s).",
            submission.id,
            account.id,
            account.student_id,
        )
        return response_payload

    # Faculty identity ── retrieve ALL approved faculty assigned to the project.
    # We query the authoritative FacultyProjectAssignment and AuthAccount relationship,
    # filtering by project_id, faculty role, and approved status.
    faculty_accounts = db.execute(
        select(AuthAccount)
        .join(
            FacultyProjectAssignment,
            FacultyProjectAssignment.faculty_account_id == AuthAccount.id,
        )
        .where(
            FacultyProjectAssignment.project_id == project_id,
            AuthAccount.role == "faculty",
            AuthAccount.faculty_approved.is_(True),
        )
        .order_by(FacultyProjectAssignment.assigned_at, AuthAccount.id)
    ).scalars().all()

    student_email_normalized = student.email.strip().lower() if student.email else ""
    seen_emails: set[str] = set()
    faculty_recipients: list[dict[str, Any]] = []

    for fac in faculty_accounts:
        if not fac.email or not fac.email.strip():
            continue
        norm_email = fac.email.strip().lower()
        if "@" not in norm_email or len(norm_email) < 5:
            continue
        # Never send the notification to the submitting student's email address
        if norm_email == student_email_normalized:
            continue
        if norm_email in seen_emails:
            continue
        seen_emails.add(norm_email)
        faculty_recipients.append({
            "faculty_id": fac.faculty_id or "",
            "faculty_name": fac.faculty_name or "",
            "faculty_email": norm_email,
        })

    if not faculty_recipients:
        logger.warning(
            "n8n notification skipped for submission %s: no approved faculty "
            "members with valid email assigned to project %s.",
            submission.id,
            project_id,
        )
        return response_payload

    evt_id = generate_submission_event_id(submission.id, submission.submitted_at)
    primary_faculty_email = faculty_recipients[0]["faculty_email"]
    frontend_base = (settings.FRONTEND_URL or "").rstrip("/")
    dashboard_url = f"{frontend_base}/projects/{project_id}" if frontend_base else None

    notify_faculty_submission(
        project_id=project_id,
        project_name=project.title,
        submission_id=submission.id,
        submitted_at=submission.submitted_at,
        student_name=student.name,
        student_email=student.email,
        faculty_email=primary_faculty_email,
        faculty_recipients=faculty_recipients,
        submission_title=f"Week {week_number} Submission \u2013 {project.title}",
        event_id=evt_id,
        student_registration_number=student.registration_number,
        week_number=week_number,
        dashboard_url=dashboard_url,
        notification_type="student_submission",
    )
    # ─────────────────────────────────────────────────────────────────────────

    return response_payload
