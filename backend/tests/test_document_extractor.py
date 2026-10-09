from pathlib import Path

from pypdf import PdfWriter

from app.services import document_extractor


SAMPLE_PDF = (
    Path(__file__).resolve().parents[1] / "uploads" / "3ad4d90a13474217b98e56596235bff1.pdf"
)


def test_extracts_text_from_valid_pdf(monkeypatch):
    monkeypatch.setattr(document_extractor, "UPLOADS_DIR", SAMPLE_PDF.parent)

    result = document_extractor.extract_pdf_text_from_upload(SAMPLE_PDF.name)

    assert result["status"] == "success"
    assert result["error"] == ""
    assert result["page_count"] == 6
    assert result["meaningful_text_found"] is True
    assert "Machine-Aware Acoustic Fingerprinting" in result["extracted_text"]
    assert result["word_count"] > 0


def test_extracts_from_legacy_absolute_upload_path():
    assert document_extractor.UPLOADS_DIR.resolve() == SAMPLE_PDF.parent.resolve()

    result = document_extractor.extract_pdf_text_from_upload(str(SAMPLE_PDF.resolve()))

    assert result["status"] == "success"
    assert result["page_count"] == 6
    assert result["meaningful_text_found"] is True


def test_rejects_invalid_non_pdf_files_and_path_traversal(tmp_path, monkeypatch):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("not a pdf", encoding="utf-8")
    monkeypatch.setattr(document_extractor, "UPLOADS_DIR", tmp_path)

    result = document_extractor.extract_pdf_text_from_upload("notes.txt")
    assert result["status"] == "failed"
    assert "Only PDF files are allowed" in result["error"]

    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"not a real pdf")
    result = document_extractor.extract_pdf_text_from_upload("../outside.pdf")
    assert result["status"] == "failed"
    assert "uploads directory" in result["error"]

    outside_pdf = tmp_path.parent / "outside.pdf"
    outside_pdf.write_bytes(b"not a real pdf")
    result = document_extractor.extract_pdf_text_from_upload(str(outside_pdf.resolve()))
    assert result["status"] == "failed"
    assert "uploads directory" in result["error"]


def test_handles_blank_no_text_pdf(tmp_path, monkeypatch):
    blank_pdf = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with blank_pdf.open("wb") as file_obj:
        writer.write(file_obj)
    monkeypatch.setattr(document_extractor, "UPLOADS_DIR", tmp_path)

    result = document_extractor.extract_pdf_text_from_upload("blank.pdf")

    assert result["status"] == "no_text_found"
    assert "OCR is not implemented" in result["error"]
    assert result["page_count"] == 1
    assert result["meaningful_text_found"] is False


def test_handles_encrypted_pdf(tmp_path, monkeypatch):
    encrypted_pdf = tmp_path / "locked.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret")
    with encrypted_pdf.open("wb") as file_obj:
        writer.write(file_obj)
    monkeypatch.setattr(document_extractor, "UPLOADS_DIR", tmp_path)

    result = document_extractor.extract_pdf_text_from_upload("locked.pdf")

    assert result["status"] == "failed"
    assert "password" in result["error"].lower()
