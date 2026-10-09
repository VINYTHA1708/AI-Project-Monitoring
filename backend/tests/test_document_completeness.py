from app.services.document_completeness import analyze_document_completeness


def test_complete_report_analysis(monkeypatch):
    def fake_extractor(file_name):
        return {
            "status": "success",
            "error": "",
            "extracted_text": "\n".join([
                "Abstract",
                "Introduction",
                "Problem Statement",
                "Objectives",
                "Methodology",
                "Implementation",
                "Results and Discussion",
                "Conclusion",
                "References",
            ]),
            "page_count": 6,
            "word_count": 1200,
            "meaningful_text_found": True,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    result = analyze_document_completeness("project_report", "report.pdf")

    assert result["analysis_status"] == "complete"
    assert result["completeness_percentage"] == 100.0
    assert result["missing_sections"] == []
    assert result["warnings"] == []
    assert result["extraction_errors"] == []


def test_incomplete_report_analysis_detects_missing_sections(monkeypatch):
    def fake_extractor(file_name):
        return {
            "status": "success",
            "error": "",
            "extracted_text": "\n".join([
                "Abstract",
                "Introduction",
                "Problem Statement",
                "Conclusion",
            ]),
            "page_count": 2,
            "word_count": 350,
            "meaningful_text_found": True,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    result = analyze_document_completeness("project_report", "report.pdf")

    assert result["analysis_status"] == "incomplete"
    assert result["completeness_percentage"] == 44.44
    assert "Objectives" in result["missing_sections"]
    assert "References" in result["missing_sections"]
    assert result["detected_sections"] == [
        "Abstract",
        "Introduction",
        "Problem Statement",
        "Conclusion",
    ]


def test_heading_variations_and_paragraph_mentions(monkeypatch):
    def fake_extractor(file_name):
        return {
            "status": "success",
            "error": "",
            "extracted_text": "\n".join([
                "The introduction explains the problem in a narrative way.",
                "1. Purpose & Scope",
                "2. Functional Requirements",
                "The system requirements are described later in the document.",
                "Constraints",
            ]),
            "page_count": 3,
            "word_count": 600,
            "meaningful_text_found": True,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    result = analyze_document_completeness("srs", "srs.pdf")

    assert "Purpose and Scope" in result["detected_sections"]
    assert "Functional Requirements" in result["detected_sections"]
    assert "Constraints" in result["detected_sections"]
    assert "Introduction" not in result["detected_sections"]
    assert "System Requirements" not in result["detected_sections"]


def test_extraction_failure_returns_unavailable_score(monkeypatch):
    def fake_extractor(file_name):
        return {
            "status": "failed",
            "error": "This PDF is encrypted or password-protected and cannot be read without a password.",
            "extracted_text": "",
            "page_count": 0,
            "word_count": 0,
            "meaningful_text_found": False,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    result = analyze_document_completeness("project_report", "report.pdf")

    assert result["analysis_status"] == "failed"
    assert result["completeness_percentage"] is None
    assert "password" in result["extraction_errors"][0].lower()


def test_no_extractable_text_returns_unavailable_score(monkeypatch):
    def fake_extractor(file_name):
        return {
            "status": "no_text_found",
            "error": "No selectable text found. The PDF may be scanned, image-only, or empty; OCR is not implemented in this phase.",
            "extracted_text": "",
            "page_count": 1,
            "word_count": 0,
            "meaningful_text_found": False,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    result = analyze_document_completeness("srs", "srs.pdf")

    assert result["analysis_status"] == "no_text_found"
    assert result["completeness_percentage"] is None
    assert "OCR is not implemented" in result["warnings"][0]
