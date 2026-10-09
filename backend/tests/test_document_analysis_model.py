from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.models import Base, DocumentAnalysis, Project, Student, Submission


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def test_document_analysis_model_fields_and_fk(db_session):
    student = Student(
        name="Test Student",
        email="student@example.com",
        registration_number="REG-001",
    )
    project = Project(
        title="AI Monitoring System",
        description="Project for testing",
        github_url="https://github.com/example/project",
    )
    db_session.add_all([student, project])
    db_session.flush()

    submission = Submission(
        project_id=project.id,
        week_number=1,
        report_path="/uploads/report.pdf",
        srs_path="/uploads/srs.pdf",
        status="SUBMITTED",
        notes="Weekly submission",
    )
    db_session.add(submission)
    db_session.flush()

    analysis = DocumentAnalysis(
        submission_id=submission.id,
        document_type="report",
        analysis_status="complete",
        completeness_percentage=95.0,
        detected_sections=["Abstract", "Introduction"],
        missing_sections=["References"],
        page_count=7,
        word_count=1200,
        warnings=["Short document"],
        extraction_errors=[],
        analyzed_at=datetime.utcnow(),
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    assert analysis.id is not None
    assert analysis.submission_id == submission.id
    assert analysis.document_type == "report"
    assert analysis.analysis_status == "complete"
    assert analysis.completeness_percentage == 95.0
    assert analysis.detected_sections == ["Abstract", "Introduction"]
    assert analysis.missing_sections == ["References"]
    assert analysis.page_count == 7
    assert analysis.word_count == 1200
    assert analysis.warnings == ["Short document"]
    assert analysis.extraction_errors == []
    assert analysis.submission.id == submission.id


def test_document_analysis_enforces_unique_submission_type(db_session):
    student = Student(
        name="Test Student",
        email="student2@example.com",
        registration_number="REG-002",
    )
    project = Project(
        title="Another Project",
        description="Project for unique check",
    )
    db_session.add_all([student, project])
    db_session.flush()

    submission = Submission(
        project_id=project.id,
        week_number=2,
        report_path="/uploads/report-2.pdf",
        srs_path="/uploads/srs-2.pdf",
        status="SUBMITTED",
    )
    db_session.add(submission)
    db_session.flush()

    first = DocumentAnalysis(
        submission_id=submission.id,
        document_type="srs",
        analysis_status="incomplete",
        completeness_percentage=70.0,
        detected_sections=["Introduction"],
        missing_sections=["System Requirements"],
        page_count=4,
        word_count=500,
        warnings=[],
        extraction_errors=[],
        analyzed_at=datetime.utcnow(),
    )
    second = DocumentAnalysis(
        submission_id=submission.id,
        document_type="srs",
        analysis_status="complete",
        completeness_percentage=100.0,
        detected_sections=["Introduction", "System Requirements"],
        missing_sections=[],
        page_count=5,
        word_count=650,
        warnings=[],
        extraction_errors=[],
        analyzed_at=datetime.utcnow(),
    )

    db_session.add(first)
    db_session.commit()

    db_session.add(second)
    with pytest.raises(Exception):
        db_session.commit()

    db_session.rollback()
    stored = db_session.query(DocumentAnalysis).filter_by(
        submission_id=submission.id,
        document_type="srs",
    ).all()
    assert len(stored) == 1
    assert stored[0].analysis_status == "incomplete"
