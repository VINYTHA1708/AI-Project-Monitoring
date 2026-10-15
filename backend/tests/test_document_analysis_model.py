from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Base, DocumentAnalysis, DocumentRelevanceAnalysis, Project, ProjectAISummary, Student, Submission


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
        analyzed_at=datetime.now(timezone.utc),
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
        analyzed_at=datetime.now(timezone.utc),
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
        analyzed_at=datetime.now(timezone.utc),
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


def test_document_relevance_analysis_model_crud_and_constraints(db_session):
    project = Project(
        title="Acoustic Fingerprinting",
        description="Audio recognition with ML",
    )
    db_session.add(project)
    db_session.flush()

    submission = Submission(
        project_id=project.id,
        week_number=1,
        report_path="/uploads/acoustic_report.pdf",
        status="SUBMITTED",
    )
    db_session.add(submission)
    db_session.flush()

    analysis = DocumentRelevanceAnalysis(
        project_id=project.id,
        submission_id=submission.id,
        document_identifier="sub_1_report",
        file_name="acoustic_report.pdf",
        file_type="report",
        document_title="Acoustic Fingerprinting Report",
        document_headings=["1. Introduction", "2. Methodology", "3. Results"],
        detected_document_topic="Acoustic Audio Fingerprinting",
        assigned_project_title="Acoustic Fingerprinting",
        title_match_explanation="Document title exactly matches project scope.",
        content_match_explanation="Content outlines audio feature extraction and ML classifier.",
        document_relevance="RELEVANT",
        supporting_evidence=["Audio feature extraction using librosa", "95% classification accuracy"],
        conflicting_evidence=[],
        missing_evidence=[],
        recommended_action="Proceed to integration milestone.",
        confidence=0.96,
        content_hash="abc123hash",
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    assert analysis.id is not None
    assert analysis.project_id == project.id
    assert analysis.submission_id == submission.id
    assert analysis.document_identifier == "sub_1_report"
    assert analysis.file_type == "report"
    assert analysis.document_relevance == "RELEVANT"
    assert len(analysis.supporting_evidence) == 2
    assert analysis.confidence == 0.96

    # Test query filtering by submission_id and file_type (the query that failed during AI summary generation)
    queried = db_session.query(DocumentRelevanceAnalysis).filter_by(
        submission_id=submission.id,
        file_type="report",
    ).first()
    assert queried is not None
    assert queried.id == analysis.id
    assert queried.document_title == "Acoustic Fingerprinting Report"


def test_document_relevance_analysis_unique_submission_file_type(db_session):
    project = Project(title="Unique Project", description="Test")
    db_session.add(project)
    db_session.flush()

    submission = Submission(project_id=project.id, week_number=1, status="SUBMITTED")
    db_session.add(submission)
    db_session.flush()

    doc1 = DocumentRelevanceAnalysis(
        project_id=project.id,
        submission_id=submission.id,
        document_identifier="sub_1_pptx",
        file_name="slides.pptx",
        file_type="pptx",
        detected_document_topic="Topic A",
        assigned_project_title="Unique Project",
        document_relevance="RELEVANT",
    )
    doc2 = DocumentRelevanceAnalysis(
        project_id=project.id,
        submission_id=submission.id,
        document_identifier="sub_1_pptx_dup",
        file_name="slides_dup.pptx",
        file_type="pptx",
        detected_document_topic="Topic B",
        assigned_project_title="Unique Project",
        document_relevance="NOT_RELEVANT",
    )
    db_session.add(doc1)
    db_session.commit()

    db_session.add(doc2)
    with pytest.raises(Exception):
        db_session.commit()
    db_session.rollback()


def test_migration_0005_sql_schema_parity():
    """Verify that every column on DocumentRelevanceAnalysis is present in 0005 migration SQL."""
    migration_path = Path(__file__).resolve().parent.parent / "migrations" / "0005_document_relevance_analyses.sql"
    assert migration_path.exists(), "0005_document_relevance_analyses.sql does not exist!"

    sql_content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS document_relevance_analyses" in sql_content
    assert "uq_document_relevance_submission_file_type" in sql_content

    # Inspect all mapped columns on the model
    model_columns = {col.name for col in DocumentRelevanceAnalysis.__table__.columns}
    for col_name in model_columns:
        assert col_name in sql_content, f"Column '{col_name}' missing from 0005 migration SQL!"

    # Verify project_ai_summaries columns added by 0005
    ai_summary_0005_cols = [
        "document_results",
        "submission_verification_status",
        "relevant_documents_count",
        "partially_relevant_documents_count",
        "unrelated_documents_count",
        "insufficient_content_documents_count",
    ]
    for col in ai_summary_0005_cols:
        assert col in sql_content, f"Column '{col}' missing from 0005 migration SQL!"


def test_postgresql_document_relevance_analyses_table_exists():
    """If connected to PostgreSQL, verify the table exists and can be queried."""
    if not settings.DATABASE_URL.startswith("postgresql"):
        pytest.skip("PostgreSQL not configured in current environment")

    engine = create_engine(settings.DATABASE_URL)
    insp = inspect(engine)
    tables = insp.get_table_names()
    assert "document_relevance_analyses" in tables, (
        "relation 'document_relevance_analyses' does not exist in PostgreSQL! "
        "Apply migration 0005_document_relevance_analyses.sql."
    )

    columns = {c["name"] for c in insp.get_columns("document_relevance_analyses")}
    model_columns = {col.name for col in DocumentRelevanceAnalysis.__table__.columns}
    missing = model_columns - columns
    assert not missing, f"Missing columns in PostgreSQL document_relevance_analyses: {missing}"

    ai_cols = {c["name"] for c in insp.get_columns("project_ai_summaries")}
    for expected in ["document_results", "submission_verification_status", "relevant_documents_count"]:
        assert expected in ai_cols, f"Column '{expected}' missing from project_ai_summaries in PostgreSQL!"

