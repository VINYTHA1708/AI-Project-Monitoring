from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Project, Submission

router = APIRouter(prefix="/projects", tags=["Submission Uploads"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_TYPES = {
    "report": {".pdf"},
    "presentation": {".ppt", ".pptx"},
    "srs": {".pdf"},
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def save_file(file: UploadFile, category: str) -> str:
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in ALLOWED_TYPES[category]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {category} file type.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{uuid4().hex}{extension}"
    total_size = 0

    try:
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

        return str(destination)

    except Exception:
        destination.unlink(missing_ok=True)
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
):
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
        report_path = await save_file(report, "report") if report else None
        if report_path:
            saved_paths.append(report_path)

        presentation_path = (
            await save_file(presentation, "presentation")
            if presentation else None
        )
        if presentation_path:
            saved_paths.append(presentation_path)

        srs_path = await save_file(srs, "srs") if srs else None
        if srs_path:
            saved_paths.append(srs_path)

        submission = Submission(
            project_id=project_id,
            week_number=week_number,
            report_path=report_path,
            presentation_path=presentation_path,
            srs_path=srs_path,
            notes=notes,
            submitted_at=datetime.now(),
            status="SUBMITTED",
        )

        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "message": "Submission uploaded and recorded successfully",
            "submission_id": submission.id,
            "project_id": project_id,
            "week_number": week_number,
            "report_path": report_path,
            "presentation_path": presentation_path,
            "srs_path": srs_path,
            "status": submission.status,
        }

    except Exception:
        db.rollback()
        for path in saved_paths:
            Path(path).unlink(missing_ok=True)
        raise
