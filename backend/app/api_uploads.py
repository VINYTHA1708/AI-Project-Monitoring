from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/uploads", tags=["Document Uploads"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
}


@router.post("/")
async def upload_document(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, PPT, and PPTX files are allowed.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}{extension}"
    destination = UPLOAD_DIR / stored_name
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
                        detail="File exceeds the 10 MB size limit.",
                    )

                output.write(chunk)

        if total_size == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        return {
            "message": "File uploaded successfully",
            "original_filename": original_name,
            "stored_filename": stored_name,
            "file_path": str(destination),
            "size_bytes": total_size,
        }

    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
