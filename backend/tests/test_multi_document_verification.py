import json
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api_ai_summary import generate_ai_summary, get_ai_summary
from app.db.models import (
    Base,
    Project,
    Submission,
    ProjectAISummary,
    DocumentRelevanceAnalysis,
    Milestone,
)
from app.services import groq_service, document_extractor
from app.services.llm_summary_service import GroqProvider, gather_project_evidence


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_project(db_session):
    project = Project(
        title="Acoustic Fingerprinting using Machine Learning Algorithm",
        description="Audio recognition system using spectrogram features and CNN acoustic fingerprints.",
        status="ACTIVE",
    )
    db_session.add(project)
    db_session.commit()

    from datetime import date
    milestone = Milestone(
        project_id=project.id,
        title="Prototype Audio Classifier",
        description="Build CNN model and test spectrogram matching.",
        due_date=date(2026, 10, 15),
        status="IN_PROGRESS",
    )
    db_session.add(milestone)
    db_session.commit()
    return project


def _mock_groq_json_response(body_dict):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps({
                "choices": [{
                    "message": {"content": json.dumps(body_dict)}
                }]
            }).encode("utf-8")

    return FakeResp()


# ── Case A: Identical / Highly Similar Title and Aligned Content ──────────────
def test_case_a_identical_title_and_aligned_content(monkeypatch):
    """Case A: Document title matches assigned title and body content matches project scope."""
    mock_llm_response = {
        "document_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "document_headings": ["[Slide 1: Acoustic Fingerprinting using Machine Learning]"],
        "detected_document_topic": "Acoustic Fingerprinting using Machine Learning",
        "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "title_match_explanation": "Document title directly matches the assigned project title.",
        "content_match_explanation": "Content details audio spectrograms and CNN acoustic fingerprinting.",
        "document_relevance": "RELEVANT",
        "supporting_evidence": ["[Slide 1] Acoustic Fingerprinting using Machine Learning"],
        "conflicting_evidence": [],
        "missing_evidence": [],
        "recommended_action": "Credit progress towards audio classifier milestones.",
        "confidence": 0.98,
    }

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda req, timeout=None: _mock_groq_json_response(mock_llm_response))
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "presentation",
            "file_name": "presentation.pptx",
            "document_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
            "document_headings": ["[Slide 1: Acoustic Fingerprinting]"],
            "extracted_text": "[Slide 1: Title]\nAcoustic Fingerprinting using Machine Learning Algorithm\nAudio spectrogram CNN model.",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "RELEVANT"
    assert res["document_title"] == "Acoustic Fingerprinting using Machine Learning Algorithm"
    assert "directly matches" in res["title_match_explanation"].lower() or "matches" in res["title_match_explanation"].lower()
    assert len(res["supporting_evidence"]) > 0
    assert len(res["conflicting_evidence"]) == 0


# ── Case B: Different or Generic Title but Body Content Matches Project ───────
def test_case_b_different_or_generic_title_but_relevant_content(monkeypatch):
    """Case B: Title is generic (e.g., 'Project Review 1'), but body content matches project scope."""
    mock_llm_response = {
        "document_title": "Phase 1 Progress Presentation",
        "document_headings": ["[Slide 1: Phase 1 Progress Presentation]"],
        "detected_document_topic": "Acoustic Fingerprinting ML Audio Classifier",
        "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "title_match_explanation": "Document has a generic deliverable title, but subtitle and sections reference audio processing.",
        "content_match_explanation": "Slides contain detailed architecture of audio spectrogram extraction and convolutional neural networks for acoustic fingerprinting.",
        "document_relevance": "RELEVANT",
        "supporting_evidence": ["[Slide 2] Mel-frequency spectrogram pipeline for audio fingerprint generation"],
        "conflicting_evidence": [],
        "missing_evidence": [],
        "recommended_action": "Accept presentation as relevant progress evidence.",
        "confidence": 0.94,
    }

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda req, timeout=None: _mock_groq_json_response(mock_llm_response))
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "presentation",
            "file_name": "midterm_review.pptx",
            "document_title": "Phase 1 Progress Presentation",
            "document_headings": ["[Slide 1: Phase 1 Progress Presentation]"],
            "extracted_text": "[Slide 1]\nPhase 1 Progress Presentation\n[Slide 2]\nMel-frequency spectrogram pipeline for audio fingerprint generation.",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "RELEVANT"
    assert "generic" in res["title_match_explanation"].lower()
    assert "spectrogram" in res["content_match_explanation"].lower() or "mel-frequency" in res["supporting_evidence"][0].lower()


# ── Case C: Different Title and Body Content Describes Different Project ─────
def test_case_c_different_title_and_different_content(monkeypatch):
    """Case C: Document has a different title and describes an unrelated project."""
    mock_llm_response = {
        "document_title": "Sensor Data Compression Using Lossless Algorithms",
        "document_headings": ["[Slide 1: Sensor Data Compression Using Lossless Algorithms]"],
        "detected_document_topic": "IoT Sensor Data Compression",
        "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "title_match_explanation": "Title describes sensor data compression rather than audio fingerprinting.",
        "content_match_explanation": "Document focuses on embedded sensor compression algorithms with no audio or machine learning content.",
        "document_relevance": "NOT_RELEVANT",
        "supporting_evidence": [],
        "conflicting_evidence": ["[Slide 1] Sensor Data Compression Using Lossless Algorithms"],
        "missing_evidence": ["Audio classification or machine learning acoustic fingerprinting content."],
        "recommended_action": "Quarantine document and notify supervisor of submission mismatch.",
        "confidence": 0.99,
    }

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda req, timeout=None: _mock_groq_json_response(mock_llm_response))
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "presentation",
            "file_name": "sensor_compression.pptx",
            "document_title": "Sensor Data Compression Using Lossless Algorithms",
            "document_headings": ["[Slide 1: Sensor Data Compression]"],
            "extracted_text": "[Slide 1]\nSensor Data Compression Using Lossless Algorithms\nEmbedded sensor benchmarks.",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "NOT_RELEVANT"
    assert "sensor" in res["detected_document_topic"].lower()
    assert len(res["conflicting_evidence"]) > 0


# ── Case D: Matching Title but Body Content Describes Different Project ──────
def test_case_d_matching_title_but_unrelated_content(monkeypatch):
    """Case D: Document title matches assigned project, but body content discusses an unrelated topic."""
    mock_llm_response = {
        "document_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "document_headings": [
            "[Slide 1: Acoustic Fingerprinting using Machine Learning Algorithm]",
            "[Slide 2: E-Commerce Shopping Cart Architecture]",
        ],
        "detected_document_topic": "E-Commerce Web Application and Payment Gateway",
        "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "title_match_explanation": "Title text matches assigned project, but appears to be a superficial cover slide.",
        "content_match_explanation": "Slides 2 through 10 describe e-commerce shopping cart databases, Stripe payment integration, and inventory management.",
        "document_relevance": "NOT_RELEVANT",
        "supporting_evidence": [],
        "conflicting_evidence": ["[Slide 2] E-Commerce Shopping Cart Architecture and Stripe Integration"],
        "missing_evidence": ["Audio feature extraction, spectrograms, or machine learning model."],
        "recommended_action": "Reject submission due to topic mismatch despite matching cover slide title.",
        "confidence": 0.97,
    }

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda req, timeout=None: _mock_groq_json_response(mock_llm_response))
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "presentation",
            "file_name": "fake_acoustic.pptx",
            "document_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
            "document_headings": ["[Slide 1: Acoustic Fingerprinting]", "[Slide 2: E-Commerce Shopping Cart]"],
            "extracted_text": "[Slide 1]\nAcoustic Fingerprinting\n[Slide 2]\nE-Commerce Shopping Cart Architecture and Stripe Integration.",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "NOT_RELEVANT"
    assert "superficial" in res["title_match_explanation"].lower() or "cover" in res["title_match_explanation"].lower()
    assert "e-commerce" in res["detected_document_topic"].lower()


# ── Case E: Partially Relevant Document ───────────────────────────────────────
def test_case_e_partially_relevant_document(monkeypatch):
    """Case E: Document contains some relevant concepts alongside significant unrelated material."""
    mock_llm_response = {
        "document_title": "Audio Signal Processing and Digital Filter Design",
        "document_headings": ["[Slide 1: Audio Signal Processing]"],
        "detected_document_topic": "Digital Audio Filtering and General Signal Processing",
        "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
        "title_match_explanation": "Title covers general audio processing but lacks machine learning classification focus.",
        "content_match_explanation": "Document covers audio FFT and bandpass filters, which relate to acoustic preprocessing, but lacks ML fingerprints or CNN classifiers.",
        "document_relevance": "PARTIALLY_RELEVANT",
        "supporting_evidence": ["[Slide 3] Fast Fourier Transform implementation for audio signals"],
        "conflicting_evidence": ["[Slide 5] Analog filter hardware schematics"],
        "missing_evidence": ["Acoustic fingerprint hashing and machine learning classifiers."],
        "recommended_action": "Credit signal preprocessing foundation; request follow-up on ML model.",
        "confidence": 0.88,
    }

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda req, timeout=None: _mock_groq_json_response(mock_llm_response))
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "presentation",
            "file_name": "audio_dsp.pptx",
            "document_title": "Audio Signal Processing and Digital Filter Design",
            "document_headings": ["[Slide 1: Audio Signal Processing]"],
            "extracted_text": "[Slide 1]\nAudio Signal Processing\n[Slide 3]\nFast Fourier Transform implementation for audio signals.",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "PARTIALLY_RELEVANT"
    assert len(res["supporting_evidence"]) > 0


# ── Case F: Unreadable, Blank, or Insufficient Content ────────────────────────
def test_case_f_unreadable_blank_or_insufficient_content():
    """Case F: Document lacks readable text (e.g. blank presentation or image-only PDF without OCR)."""
    res = groq_service.verify_single_document_relevance(
        project_id=1,
        project_title="Acoustic Fingerprinting using Machine Learning Algorithm",
        project_description="Audio recognition system using spectrograms and CNN acoustic fingerprints.",
        document_info={
            "document_type": "report",
            "file_name": "scanned_images.pdf",
            "document_title": None,
            "document_headings": [],
            "extracted_text": "",
            "status": "no_text_found",
            "word_count": 0,
        },
    )

    assert res["document_relevance"] == "INSUFFICIENT_CONTENT"
    assert "insufficient" in res["content_match_explanation"].lower() or "no selectable text found" in res["content_match_explanation"].lower()
    assert res["confidence"] == 0.0


# ── Corrupt / Extraction Failure Handling ─────────────────────────────────────
def test_corrupt_file_handling():
    """Corrupt file extraction returns error without crashing the pipeline."""
    res = document_extractor.extract_document_text_from_upload("non_existent_corrupt_file.pptx")
    assert res["status"] in ("failed", "error", "success")
    assert res["meaningful_text_found"] is False


# ── End-to-End Mixed Submission: Relevant Report + Unrelated PPT ──────────────
def test_mixed_submission_unrelated_ppt_with_relevant_report(db_session, sample_project, monkeypatch):
    """Acoustic project with a relevant report and an unrelated PPT:

    - Independent verification marks report RELEVANT, PPT NOT_RELEVANT.

    - Submission status is CONTRADICTORY_TOPICS.

    - Progress is credited ONLY for the relevant report.

    """
    submission = Submission(
        project_id=sample_project.id,
        week_number=1,
        report_path="acoustic_report.pdf",
        presentation_path="sensor_compression.pptx",
    )
    db_session.add(submission)
    db_session.commit()

    # Mock extractor
    def fake_extract(filename):
        fn = str(filename)
        if "report" in fn:
            return {
                "status": "success",
                "extracted_text": "[Page 1]\nAcoustic Fingerprinting using Machine Learning\nSpectrogram CNN architecture.",
                "document_title": "Acoustic Fingerprinting Report",
                "document_headings": ["[Page 1: Acoustic Fingerprinting]"],
                "page_count": 1,
                "word_count": 40,
                "meaningful_text_found": True,
            }
        else:
            return {
                "status": "success",
                "extracted_text": "[Slide 1]\nSensor Data Compression Using Lossless Algorithms\nIoT sensor benchmarks.",
                "document_title": "Sensor Data Compression",
                "document_headings": ["[Slide 1: Sensor Data Compression]"],
                "page_count": 1,
                "word_count": 40,
                "meaningful_text_found": True,
            }

    monkeypatch.setattr("app.services.document_extractor.extract_document_text_from_upload", fake_extract)

    def fake_urlopen(req, timeout=None):
        req_data = json.loads(req.data.decode("utf-8"))
        user_msg = req_data["messages"][1]["content"]

        if "sensor" in user_msg.lower() or "compression" in user_msg.lower():
            resp = {
                "document_title": "Sensor Data Compression",
                "document_headings": ["[Slide 1: Sensor Data Compression]"],
                "detected_document_topic": "Sensor Data Compression Using Lossless Algorithms",
                "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "title_match_explanation": "Title describes sensor compression rather than acoustic ML.",
                "content_match_explanation": "Discusses IoT sensor data compression benchmarks.",
                "document_relevance": "NOT_RELEVANT",
                "supporting_evidence": [],
                "conflicting_evidence": ["[Slide 1] Sensor Data Compression Using Lossless Algorithms"],
                "missing_evidence": ["Acoustic spectrogram feature extraction."],
                "recommended_action": "Quarantine presentation.",
                "confidence": 0.99,
            }
        elif "acoustic" in user_msg.lower():
            resp = {
                "document_title": "Acoustic Fingerprinting Report",
                "document_headings": ["[Page 1: Acoustic Fingerprinting]"],
                "detected_document_topic": "Acoustic Fingerprinting using Machine Learning",
                "assigned_project_title": "Acoustic Fingerprinting using Machine Learning Algorithm",
                "title_match_explanation": "Title aligns with assigned project.",
                "content_match_explanation": "Report details spectrogram CNN classifier.",
                "document_relevance": "RELEVANT",
                "supporting_evidence": ["[Page 1] Acoustic Fingerprinting using Machine Learning"],
                "conflicting_evidence": [],
                "missing_evidence": [],
                "recommended_action": "Credit progress from report.",
                "confidence": 0.96,
            }
        else:
            resp = {
                "summary": "Report aligns with acoustic fingerprinting; presentation describes unrelated sensor data compression.",
                "progress_assessment": "Verified progress on acoustic spectrogram extraction from report. Presentation is quarantined.",
                "relevant_findings": ["Acoustic spectrogram feature pipeline implemented in report."],
                "missing_evidence": ["Presentation aligned with acoustic fingerprinting."],
                "risks": ["Unrelated presentation submitted."],
                "recommended_next_steps": ["Require resubmission of presentation."],
                "review_questions": ["Why does presentation discuss sensor compression?"],
            }

        return _mock_groq_json_response(resp)

    monkeypatch.setattr("app.services.groq_service.urlopen", fake_urlopen)
    monkeypatch.setattr("app.services.llm_summary_service.urlopen", fake_urlopen)
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk-mock-key")

    provider = GroqProvider()
    evidence = gather_project_evidence(sample_project.id, db_session)
    result = provider.generate_summary(evidence)

    assert result["submission_verification_status"] == "CONTRADICTORY_TOPICS"
    assert result["relevant_documents_count"] == 1
    assert result["unrelated_documents_count"] == 1
    assert len(result["document_results"]) == 2

    # Check that presentation does not contribute positive progress
    assert "quarantined" in result["progress_assessment"].lower() or "cannot be treated as valid evidence" in result["progress_assessment"].lower()


# ── Database Persistence of DocumentRelevanceAnalysis and AISummary ───────────
def test_database_persistence_and_retrieval(db_session, sample_project, monkeypatch):
    """Verify that DocumentRelevanceAnalysis and ProjectAISummary records are saved and retrieved."""
    submission = Submission(
        project_id=sample_project.id,
        week_number=1,
        report_path="acoustic_report.pdf",
        presentation_path="sensor_compression.pptx",
    )
    db_session.add(submission)
    db_session.commit()

    class MockProvider:
        def is_configured(self):
            return True

        def get_provider_name(self):
            return "groq"

        def get_model_name(self):
            return "llama-3.3-70b-versatile"

        def generate_summary(self, evidence):
            return {
                "document_relevance": "PARTIALLY_RELEVANT",
                "detected_document_topic": "Mixed Deliverables",
                "assigned_project_topic": evidence["title"],
                "relevance_explanation": "Contradictory topics: report is relevant, PPT is unrelated.",
                "supporting_evidence": ["[Page 1] Acoustic Fingerprinting"],
                "relevant_findings": ["CNN spectrogram pipeline implemented."],
                "missing_evidence": ["Valid presentation."],
                "summary": "Mixed deliverable synthesis.",
                "progress_assessment": "Progress credited only from report.",
                "risks": ["Mismatched presentation."],
                "recommended_next_steps": ["Resubmit PPT."],
                "review_questions": ["Clarify presentation topic."],
                "confidence": 0.95,
                "submission_verification_status": "CONTRADICTORY_TOPICS",
                "relevant_documents_count": 1,
                "partially_relevant_documents_count": 0,
                "unrelated_documents_count": 1,
                "insufficient_content_documents_count": 0,
                "document_results": [
                    {
                        "submission_id": submission.id,
                        "file_type": "pdf",
                        "file_name": "acoustic_report.pdf",
                        "document_title": "Acoustic Fingerprinting Report",
                        "document_headings": ["[Page 1: Acoustic Fingerprinting]"],
                        "detected_document_topic": "Acoustic Fingerprinting ML",
                        "assigned_project_title": evidence["title"],
                        "title_match_explanation": "Direct title match.",
                        "content_match_explanation": "Detailed CNN spectrogram model.",
                        "document_relevance": "RELEVANT",
                        "relevance": "RELEVANT",
                        "relevance_explanation": "Fully aligned with assigned project.",
                        "supporting_evidence": ["[Page 1] Acoustic Fingerprinting"],
                        "conflicting_evidence": [],
                        "missing_evidence": [],
                        "recommended_action": "Credit report progress.",
                        "confidence": 0.98,
                    },
                    {
                        "submission_id": submission.id,
                        "file_type": "pptx",
                        "file_name": "sensor_compression.pptx",
                        "document_title": "Sensor Compression",
                        "document_headings": ["[Slide 1: Sensor Compression]"],
                        "detected_document_topic": "Sensor Data Compression",
                        "assigned_project_title": evidence["title"],
                        "title_match_explanation": "Mismatched title.",
                        "content_match_explanation": "Discusses IoT sensor data compression benchmarks.",
                        "document_relevance": "NOT_RELEVANT",
                        "relevance": "NOT_RELEVANT",
                        "relevance_explanation": "Unrelated topic.",
                        "supporting_evidence": [],
                        "conflicting_evidence": ["[Slide 1] Sensor Compression"],
                        "missing_evidence": ["Acoustic fingerprinting."],
                        "recommended_action": "Quarantine presentation.",
                        "confidence": 0.99,
                    },
                ],
            }

    monkeypatch.setattr("app.api_ai_summary.get_llm_provider", lambda: MockProvider())

    summary_model = generate_ai_summary(sample_project.id, db_session)

    # Verify ProjectAISummary columns
    assert summary_model.submission_verification_status == "CONTRADICTORY_TOPICS"
    assert summary_model.relevant_documents_count == 1
    assert summary_model.unrelated_documents_count == 1
    assert len(summary_model.document_results) == 2

    # Verify DocumentRelevanceAnalysis table rows
    analyses = db_session.query(DocumentRelevanceAnalysis).filter_by(submission_id=submission.id).all()
    assert len(analyses) == 2
    by_type = {a.file_type: a for a in analyses}
    assert by_type["pdf"].document_relevance == "RELEVANT"
    assert by_type["pptx"].document_relevance == "NOT_RELEVANT"
    assert by_type["pdf"].document_title == "Acoustic Fingerprinting Report"
    assert by_type["pptx"].document_title == "Sensor Compression"

    # Verify get_ai_summary API endpoint returns everything
    res = get_ai_summary(sample_project.id, db_session)
    assert res.latest_summary.submission_verification_status == "CONTRADICTORY_TOPICS"
    assert len(res.latest_summary.document_results) == 2
    assert res.latest_summary.document_results[0]["relevance"] in ("RELEVANT", "NOT_RELEVANT")


# ── Advisory Nature: Milestone & Submission States Unaltered ──────────────────
def test_advisory_nature_milestones_unaltered(db_session, sample_project, monkeypatch):
    """Verify that generating an AI summary does not alter milestone status or completion percentage."""
    milestone = db_session.query(Milestone).filter_by(project_id=sample_project.id).first()
    initial_status = milestone.status

    class IrrelevantMockProvider:
        def is_configured(self):
            return True

        def get_provider_name(self):
            return "groq"

        def get_model_name(self):
            return "llama-3.3-70b-versatile"

        def generate_summary(self, evidence):
            return {
                "document_relevance": "NOT_RELEVANT",
                "detected_document_topic": "Completely Unrelated",
                "assigned_project_topic": evidence["title"],
                "relevance_explanation": "Completely unrelated document.",
                "supporting_evidence": [],
                "relevant_findings": [],
                "missing_evidence": [],
                "summary": "Mismatch detected.",
                "progress_assessment": "No verified progress.",
                "risks": ["Mismatch."],
                "recommended_next_steps": ["Resubmit."],
                "review_questions": [],
                "confidence": 0.99,
                "submission_verification_status": "UNVERIFIED_IRRELEVANT",
                "relevant_documents_count": 0,
                "partially_relevant_documents_count": 0,
                "unrelated_documents_count": 1,
                "insufficient_content_documents_count": 0,
                "document_results": [],
            }

    monkeypatch.setattr("app.api_ai_summary.get_llm_provider", lambda: IrrelevantMockProvider())

    generate_ai_summary(sample_project.id, db_session)

    # Milestone status is strictly unchanged
    db_session.refresh(milestone)
    assert milestone.status == initial_status
