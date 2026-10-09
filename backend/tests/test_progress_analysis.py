import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api_progress import get_project_progress
from app.db.models import Base, DocumentAnalysis, Project, Submission


@pytest.fixture
def progress_db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    project = Project(title="Progress test project")
    session.add(project)
    session.commit()
    yield session, project.id
    session.close()
    engine.dispose()


def _add_submission(session, project_id, week_number, report_path):
    submission = Submission(
        project_id=project_id,
        week_number=week_number,
        report_path=report_path,
    )
    session.add(submission)
    session.flush()
    return submission


def test_progress_includes_complete_incomplete_failed_and_unanalyzed_documents(
    progress_db,
):
    session, project_id = progress_db
    complete = _add_submission(session, project_id, 1, "report-1.pdf")
    incomplete = _add_submission(session, project_id, 2, "report-2.pdf")
    failed = _add_submission(session, project_id, 3, "report-3.pdf")
    unanalyzed = _add_submission(session, project_id, 4, "report-4.pdf")
    session.add_all([
        DocumentAnalysis(
            submission_id=complete.id,
            document_type="report",
            analysis_status="complete",
            completeness_percentage=100.0,
            missing_sections=[],
            warnings=[],
            extraction_errors=[],
        ),
        DocumentAnalysis(
            submission_id=incomplete.id,
            document_type="report",
            analysis_status="incomplete",
            completeness_percentage=66.67,
            missing_sections=["References"],
            warnings=["Document is short."],
            extraction_errors=[],
        ),
        DocumentAnalysis(
            submission_id=failed.id,
            document_type="report",
            analysis_status="failed",
            completeness_percentage=None,
            missing_sections=[
                "Abstract",
                "Introduction",
            ],
            warnings=[],
            extraction_errors=["Encrypted PDF."],
        ),
    ])
    session.commit()

    result = get_project_progress(project_id, session)
    details = {
        entry["submission_id"]: entry
        for entry in result["submissions"]["details"]
    }
    documents = {
        item["submission_id"]: item
        for entry in details.values()
        for item in entry["document_analyses"]
    }

    assert result["project_id"] == project_id
    assert result["submissions"]["total"] == 4
    assert result["submissions"]["weeks_submitted"] == [1, 2, 3, 4]
    assert documents[complete.id]["status"] == "complete"
    assert documents[complete.id]["completeness_percentage"] == 100.0
    assert documents[incomplete.id]["status"] == "incomplete"
    assert documents[incomplete.id]["completeness_percentage"] == 66.67
    assert documents[incomplete.id]["missing_sections"] == ["References"]
    assert documents[incomplete.id]["warnings"] == ["Document is short."]
    assert documents[failed.id]["status"] == "failed"
    assert documents[failed.id]["analysis_status"] == "failed"
    assert documents[failed.id]["completeness_percentage"] is None
    assert documents[failed.id]["extraction_errors"] == ["Encrypted PDF."]
    assert documents[unanalyzed.id]["status"] == "not_analyzed"
    assert documents[unanalyzed.id]["analysis_status"] is None
    assert documents[unanalyzed.id]["completeness_percentage"] is None


def test_progress_returns_empty_analysis_for_project_with_no_submissions(
    progress_db,
):
    session, project_id = progress_db

    result = get_project_progress(project_id, session)

    assert result["submissions"] == {
        "total": 0,
        "weeks_submitted": [],
        "details": [],
    }


def test_progress_distinguishes_no_text_analysis_from_incomplete_document(
    progress_db,
):
    session, project_id = progress_db
    submission = _add_submission(session, project_id, 1, "scanned-report.pdf")
    session.add(DocumentAnalysis(
        submission_id=submission.id,
        document_type="report",
        analysis_status="no_text_found",
        completeness_percentage=None,
        missing_sections=["Abstract"],
        warnings=["OCR is not implemented."],
        extraction_errors=["No selectable text found."],
    ))
    session.commit()

    result = get_project_progress(project_id, session)
    document = result["submissions"]["details"][0]["document_analyses"][0]

    assert document["status"] == "failed"
    assert document["analysis_status"] == "no_text_found"
    assert document["completeness_percentage"] is None
    assert document["extraction_errors"] == ["No selectable text found."]
