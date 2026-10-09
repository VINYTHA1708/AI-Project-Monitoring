import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api_document_analysis import (
    AnalyzeDocumentRequest,
    analyze_submission_document,
    get_submission_analyses,
)
from app.db.models import Base, DocumentAnalysis, Project, Submission


@pytest.fixture
def api_db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    project = Project(title="Test Project", description="API test project")
    session.add(project)
    session.flush()
    submission = Submission(
        project_id=project.id,
        week_number=1,
        report_path="C:\\uploads\\report.pdf",
        srs_path=None,
    )
    session.add(submission)
    session.commit()
    yield session, project.id, submission.id
    session.close()
    engine.dispose()


def test_analyzes_and_saves_report_without_exposing_path_or_text(
    api_db, monkeypatch
):
    session, project_id, submission_id = api_db

    def fake_extractor(file_name):
        assert file_name == "C:\\uploads\\report.pdf"
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
            "page_count": 4,
            "word_count": 800,
            "meaningful_text_found": True,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )

    response = analyze_submission_document(
        project_id,
        submission_id,
        AnalyzeDocumentRequest(document_type="report"),
        session,
    )

    assert response["document_type"] == "report"
    assert response["analysis_status"] == "complete"
    assert response["completeness_percentage"] == 100.0
    assert response["page_count"] == 4
    assert response["word_count"] == 800
    assert "extracted_text" not in response
    assert "file_path" not in response
    assert session.query(DocumentAnalysis).count() == 1


def test_missing_document_returns_client_error(api_db):
    session, project_id, submission_id = api_db
    submission = session.get(Submission, submission_id)
    submission.report_path = None
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        analyze_submission_document(
            project_id,
            submission_id,
            AnalyzeDocumentRequest(document_type="report"),
            session,
        )

    assert exc_info.value.status_code == 400
    assert "No report document" in exc_info.value.detail


def test_invalid_document_type_is_rejected():
    with pytest.raises(ValidationError):
        AnalyzeDocumentRequest(document_type="presentation")


def test_incorrect_project_submission_combination_returns_not_found(api_db):
    session, _project_id, submission_id = api_db
    other_project = Project(title="Other Project")
    session.add(other_project)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_submission_analyses(other_project.id, submission_id, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Submission not found"


def test_repeated_analysis_updates_existing_record(api_db, monkeypatch):
    session, project_id, submission_id = api_db
    call_count = 0

    def fake_extractor(_file_name):
        nonlocal call_count
        call_count += 1
        heading = "Abstract" if call_count == 1 else "Introduction"
        return {
            "status": "success",
            "error": "",
            "extracted_text": heading,
            "page_count": call_count,
            "word_count": 200,
            "meaningful_text_found": True,
        }

    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        fake_extractor,
    )
    request = AnalyzeDocumentRequest(document_type="report")

    first_response = analyze_submission_document(
        project_id, submission_id, request, session
    )
    first_id = first_response["id"]
    second_response = analyze_submission_document(
        project_id, submission_id, request, session
    )

    assert second_response["id"] == first_id
    assert second_response["page_count"] == 2
    assert session.query(DocumentAnalysis).count() == 1


def test_analysis_failure_persists_unavailable_score(api_db, monkeypatch):
    session, project_id, submission_id = api_db
    monkeypatch.setattr(
        "app.services.document_completeness.extract_pdf_text_from_upload",
        lambda _file_name: {
            "status": "failed",
            "error": "Encrypted document at C:\\uploads\\secret.pdf.",
            "extracted_text": "",
            "page_count": 0,
            "word_count": 0,
            "meaningful_text_found": False,
        },
    )

    response = analyze_submission_document(
        project_id,
        submission_id,
        AnalyzeDocumentRequest(document_type="report"),
        session,
    )

    assert response["analysis_status"] == "failed"
    assert response["completeness_percentage"] is None
    assert response["extraction_errors"] == ["Encrypted document at [local file]"]
    assert "C:\\uploads" not in str(response)


def test_get_analysis_returns_empty_list_when_none_exists(api_db):
    session, project_id, submission_id = api_db

    response = get_submission_analyses(project_id, submission_id, session)

    assert response == []
