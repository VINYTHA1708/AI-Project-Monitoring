import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Project, Submission, ProjectAISummary
from app.services.llm_summary_service import gather_project_evidence, GroqProvider
from app.services import groq_service


def test_reproduce_ppt_mismatch_overridden_by_report(tmp_path, monkeypatch):
    """Reproduce: When a submission has a relevant report and an unrelated PPT,

    the current single-prompt architecture evaluates them together and allows

    the relevant report to override the unrelated PPT, returning a single RELEVANT

    status with no per-document verification.

    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)

    # Create project: Acoustic Fingerprinting
    project = Project(
        title="Acoustic Fingerprinting using Machine Learning Algorithm",
        description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        status="ACTIVE",
    )
    session.add(project)
    session.commit()

    # Create submission with both report and presentation
    # Mock files in uploads directory
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    monkeypatch.setattr("app.services.document_extractor.UPLOADS_DIR", uploads_dir)

    # Create a dummy report file (pdf) and presentation file (pptx)
    report_file = uploads_dir / "report.pdf"
    report_file.write_text("dummy")
    ppt_file = uploads_dir / "presentation.pptx"
    ppt_file.write_text("dummy")

    submission = Submission(
        project_id=project.id,
        week_number=1,
        report_path="report.pdf",
        presentation_path="presentation.pptx",
    )
    session.add(submission)
    session.commit()

    # Mock extract_document_text_from_upload
    def fake_extract(file_name):
        fn = str(file_name)
        if "report" in fn:
            return {
                "status": "success",
                "extracted_text": "[Page 1]\nAcoustic Fingerprinting using Machine Learning Algorithm\nAudio spectrogram CNN model.",
                "page_count": 1,
                "word_count": 50,
                "meaningful_text_found": True,
            }
        else:
            return {
                "status": "success",
                "extracted_text": "[Slide 1]\nSensor Data Compression Using Lossless Algorithms\nIoT sensor data encoding benchmarks.",
                "page_count": 1,
                "word_count": 50,
                "meaningful_text_found": True,
            }

    monkeypatch.setattr("app.services.document_extractor.extract_document_text_from_upload", fake_extract)

    evidence = gather_project_evidence(project.id, session)

    # In current implementation, evidence has uploaded_documents with both files
    assert len(evidence["uploaded_documents"]) == 2

    def fake_urlopen(req, timeout=None):
        req_data = json.loads(req.data.decode("utf-8"))
        user_msg = req_data["messages"][1]["content"]

        if "presentation.pptx" in user_msg or "Sensor Data Compression" in user_msg:
            resp_body = {
                "document_title": "Sensor Data Compression Using Lossless Algorithms",
                "document_headings": ["Slide 1: Sensor Data Compression Using Lossless Algorithms"],
                "detected_document_topic": "Sensor Data Compression Using Lossless Algorithms",
                "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "title_match_explanation": "Title describes sensor compression rather than acoustic fingerprinting.",
                "content_match_explanation": "Body content concerns lossless IoT sensor encoding benchmarks.",
                "document_relevance": "NOT_RELEVANT",
                "supporting_evidence": [],
                "conflicting_evidence": ["[Slide 1] Sensor Data Compression Using Lossless Algorithms"],
                "missing_evidence": ["Acoustic fingerprinting machine learning models."],
                "recommended_action": "Ask student to upload the correct presentation for acoustic fingerprinting.",
                "confidence": 0.98,
            }
        else:
            resp_body = {
                "document_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "document_headings": ["Page 1: Acoustic Fingerprinting using Machine Learning Algorithm"],
                "detected_document_topic": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "title_match_explanation": "Title matches assigned acoustic fingerprinting project.",
                "content_match_explanation": "Content details audio spectrogram CNN classifier.",
                "document_relevance": "RELEVANT",
                "supporting_evidence": ["[Page 1] Acoustic Fingerprinting using Machine Learning Algorithm"],
                "conflicting_evidence": [],
                "missing_evidence": [],
                "recommended_action": "Proceed with evaluation.",
                "confidence": 0.95,
            }

        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, *args):
                return json.dumps({
                    "choices": [{
                        "message": {"content": json.dumps(resp_body)}
                    }]
                }).encode("utf-8")

        return FakeResp()

    monkeypatch.setattr("app.services.groq_service.urlopen", fake_urlopen)
    monkeypatch.setattr("app.services.llm_summary_service.urlopen", fake_urlopen)
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key-12345")
    monkeypatch.setattr("app.core.config.settings.GROQ_MODEL", "llama-3.3-70b-versatile")

    provider = GroqProvider()
    result = provider.generate_summary(evidence)

    # VERIFY THE INDEPENDENT PIPELINE FIX:
    # 1. document_results contains BOTH documents independently analyzed
    assert "document_results" in result
    assert len(result["document_results"]) == 2

    doc_map = {d["file_name"]: d for d in result["document_results"]}
    assert "presentation.pptx" in doc_map
    assert "report.pdf" in doc_map

    # 2. Report is verified as RELEVANT
    assert doc_map["report.pdf"]["document_relevance"] == "RELEVANT"
    assert "Acoustic Fingerprinting" in doc_map["report.pdf"]["detected_document_topic"]

    # 3. PPT is verified as NOT_RELEVANT -- it was NOT overridden by the report!
    assert doc_map["presentation.pptx"]["document_relevance"] == "NOT_RELEVANT"
    assert "Sensor Data Compression" in doc_map["presentation.pptx"]["detected_document_topic"]

    # 4. Overall status detects contradictory topics
    assert result["submission_verification_status"] == "CONTRADICTORY_TOPICS"
    assert result["unrelated_documents_count"] == 1
    assert result["relevant_documents_count"] == 1
    assert "Contradictory topics detected" in result["relevance_explanation"]

    # 5. Unrelated presentation cannot contribute to positive progress
    assert "cannot be treated as valid evidence of project progress" in result["progress_assessment"].lower()
    session.close()
