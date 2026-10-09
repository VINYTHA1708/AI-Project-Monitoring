import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"


def _resolve_uploaded_pdf_path(file_name: str | Path) -> Path:
    if file_name is None or str(file_name).strip() == "":
        raise ValueError("No PDF file name provided.")

    base_dir = UPLOADS_DIR.resolve()
    candidate = Path(str(file_name))
    resolved_path = (
        candidate.resolve() if candidate.is_absolute()
        else (base_dir / candidate).resolve()
    )

    try:
        resolved_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(
            "Only files inside the configured uploads directory are allowed."
        ) from exc

    if not resolved_path.exists():
        raise FileNotFoundError("File does not exist in the uploads directory.")

    if not resolved_path.is_file():
        raise ValueError("The requested path is not a file.")

    if resolved_path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are allowed.")

    return resolved_path


def extract_pdf_text_from_upload(file_name: str | Path) -> dict[str, Any]:
    result = {
        "status": "failed",
        "error": "",
        "extracted_text": "",
        "page_count": 0,
        "word_count": 0,
        "meaningful_text_found": False,
    }

    try:
        pdf_path = _resolve_uploaded_pdf_path(file_name)
    except (ValueError, FileNotFoundError) as exc:
        result["error"] = str(exc)
        return result

    try:
        reader = PdfReader(str(pdf_path))
    except (PdfReadError, OSError, ValueError) as exc:
        result["error"] = f"Invalid or corrupt PDF: {exc}"
        return result

    if reader.is_encrypted:
        try:
            decrypt_status = reader.decrypt("")
        except Exception:
            decrypt_status = 0

        if decrypt_status == 0:
            result["error"] = (
                "This PDF is encrypted or password-protected and cannot be read "
                "without a password."
            )
            return result

    pages = []
    try:
        page_count = len(reader.pages)
    except Exception as exc:
        result["error"] = f"Unable to read PDF pages: {exc}"
        return result

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            result["error"] = f"Unable to extract text from page {page_index}: {exc}"
            return result

        if page_text:
            pages.append(page_text.strip())

    extracted_text = "\n\n".join(page for page in pages if page)
    normalized_text = " ".join(extracted_text.split())
    word_count = len(re.findall(r"\b\w+\b", normalized_text))
    meaningful_text_found = bool(re.search(r"[A-Za-z0-9]", normalized_text))

    if not meaningful_text_found:
        result["status"] = "no_text_found"
        result["error"] = (
            "No selectable text found. The PDF may be scanned, image-only, or empty; "
            "OCR is not implemented in this phase."
        )
    else:
        result["status"] = "success"
        result["error"] = ""

    result["extracted_text"] = extracted_text
    result["page_count"] = page_count
    result["word_count"] = word_count
    result["meaningful_text_found"] = meaningful_text_found

    return result
