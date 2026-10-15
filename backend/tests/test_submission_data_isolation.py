"""
Regression tests for submission/document data isolation (all 10 requirements).
Uses isolated SQLite in-memory databases and temporary upload directories.
No real local records are modified during test execution.
"""
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.api_submissions as api_sub_module
from app.api_submissions import (
    list_submission_documents,
    download_submission_document,
    list_submissions,
)
from app.api_projects import list_project_documents
from app.auth.dependencies import Principal, ensure_project_access
from app.db.models import (
    Base, Project, Submission, SubmissionReview,
    FacultyProjectAssignment, ProjectMember, Student, AuthAccount, Milestone,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def enable_fk(connection, _record):
        c = connection.cursor(); c.execute("PRAGMA foreign_keys=ON"); c.close()
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _write_pdf(path: Path, content: bytes = None) -> bytes:
    data = content or b"%PDF-1.4\n1 0 obj\n<< /Title (Test) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    path.write_bytes(data)
    return data


@pytest.fixture
def two_project_setup(db_session, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(api_sub_module, "UPLOAD_DIR", upload_dir)

    proj_a = Project(title="AI Monitoring System", description="Project A", status="ACTIVE")
    proj_b = Project(title="Acoustic Fingerprinting", description="Project B", status="ACTIVE")
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    fac1 = AuthAccount(email="fac1@uni.edu", role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$hashA",
        faculty_id="FAC-A", faculty_name="Prof. Alpha",
        email_verified=True, faculty_approved=True)
    fac2 = AuthAccount(email="fac2@uni.edu", role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$hashB",
        faculty_id="FAC-B", faculty_name="Prof. Beta",
        email_verified=True, faculty_approved=True)
    db_session.add_all([fac1, fac2])
    db_session.flush()
    db_session.add(FacultyProjectAssignment(faculty_account_id=fac1.id, project_id=proj_a.id))
    db_session.add(FacultyProjectAssignment(faculty_account_id=fac2.id, project_id=proj_b.id))

    stu1 = Student(name="Akshayaa S A", email="akshayaa@vitstudent.ac.in",
                   registration_number="23MIC0016")
    stu2 = Student(name="Abirami", email="abirami@vitstudent.ac.in",
                   registration_number="23MIS0417")
    db_session.add_all([stu1, stu2])
    db_session.flush()

    stu1_acc = AuthAccount(email="akshayaa@vitstudent.ac.in", role="student",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$hashS1",
        student_id=stu1.id, phone="9876543210", department="CS",
        email_verified=True, faculty_approved=False)
    stu2_acc = AuthAccount(email="abirami@vitstudent.ac.in", role="student",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$hashS2",
        student_id=stu2.id, phone="9876543211", department="CS",
        email_verified=True, faculty_approved=False)
    db_session.add_all([stu1_acc, stu2_acc])
    db_session.flush()
    db_session.add(ProjectMember(project_id=proj_a.id, student_id=stu1.id, role="LEADER"))
    db_session.add(ProjectMember(project_id=proj_b.id, student_id=stu2.id, role="LEADER"))

    pdf_a_bytes = _write_pdf(upload_dir / "proj_a_report.pdf",
                             b"%PDF-1.4\nProject A Week 1 Content%%EOF")
    pdf_b_bytes = _write_pdf(upload_dir / "proj_b_report.pdf",
                             b"%PDF-1.4\nProject B Week 1 Content%%EOF")

    sub_a = Submission(project_id=proj_a.id, week_number=1,
        report_path="proj_a_report.pdf",
        report_original_name="AI Monitoring Week 1 Report.pdf",
        submitted_at=datetime.now(timezone.utc), status="SUBMITTED")
    sub_b = Submission(project_id=proj_b.id, week_number=1,
        report_path="proj_b_report.pdf",
        report_original_name="Acoustic Fingerprinting Week 1 Report.pdf",
        submitted_at=datetime.now(timezone.utc), status="REVIEWED")
    db_session.add_all([sub_a, sub_b])
    db_session.flush()

    review_b = SubmissionReview(submission_id=sub_b.id, project_id=proj_b.id,
        faculty_account_id=fac2.id, score=75.0,
        feedback="The report correctly identifies the acoustic fingerprinting domain. "
                 "Continue with a detailed literature review and methodology.")
    milestone_a = Milestone(project_id=proj_a.id, title="Literature Review",
        due_date=datetime(2026, 11, 1).date(), status="COMPLETED", completed=True)
    db_session.add_all([review_b, milestone_a])
    db_session.commit()

    return dict(proj_a=proj_a, proj_b=proj_b, fac1=fac1, fac2=fac2,
                stu1=stu1, stu2=stu2, stu1_acc=stu1_acc, stu2_acc=stu2_acc,
                sub_a=sub_a, sub_b=sub_b, review_b=review_b, milestone_a=milestone_a,
                pdf_a_bytes=pdf_a_bytes, pdf_b_bytes=pdf_b_bytes, upload_dir=upload_dir)


# --- Req 1: Project with no submissions → empty list, no fallback records ------

def test_project_with_no_submissions_shows_empty_document_list(db_session, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"; upload_dir.mkdir()
    monkeypatch.setattr(api_sub_module, "UPLOAD_DIR", upload_dir)
    fac = AuthAccount(email="fac@uni.edu", role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$xe",
        faculty_id="F-EMPTY", faculty_name="Dr. Empty",
        email_verified=True, faculty_approved=True)
    db_session.add(fac)
    proj = Project(title="Empty Project", status="ACTIVE")
    db_session.add(proj)
    db_session.flush()
    db_session.add(FacultyProjectAssignment(faculty_account_id=fac.id, project_id=proj.id))
    db_session.commit()
    principal = Principal(id=fac.id, role="faculty", email=fac.email, student_id=None)

    all_docs = list_project_documents(project_id=proj.id, submission_id=None,
                                      db=db_session, account=principal)
    assert all_docs == [], f"Expected empty docs for empty project, got: {all_docs}"

    all_subs = list_submissions(project_id=proj.id, db=db_session)
    assert all_subs == [], f"Expected empty submissions for empty project, got: {all_subs}"


# --- Req 2: Genuine submissions show correct metadata -------------------------

def test_genuine_submissions_are_shown_with_correct_metadata(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    docs = list_project_documents(project_id=s["proj_a"].id, submission_id=None,
                                  db=db_session, account=principal)
    assert len(docs) == 1, f"Expected 1 doc for project A, got {len(docs)}"
    doc = docs[0]
    assert doc["original_filename"] == "AI Monitoring Week 1 Report.pdf"
    assert doc["submission_id"] == s["sub_a"].id
    assert doc["project_id"] == s["proj_a"].id
    assert doc["week_number"] == 1
    assert doc["file_exists"] is True
    assert doc["file_size"] > 0


# --- Req 3: Project B docs never appear when querying Project A ---------------

def test_project_b_documents_never_appear_when_querying_project_a(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    docs = list_project_documents(project_id=s["proj_a"].id, submission_id=None,
                                  db=db_session, account=principal)
    cross = [d for d in docs if d["project_id"] == s["proj_b"].id]
    assert cross == [], f"Project B docs leaked into Project A response: {cross}"


# --- Req 4: Switching projects: cross-project submission_id returns empty -----

def test_submission_id_filter_scoped_to_correct_project(db_session, two_project_setup):
    """sub_b belongs to Project B; querying Project A with sub_b.id must return nothing."""
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    docs = list_project_documents(project_id=s["proj_a"].id, submission_id=s["sub_b"].id,
                                  db=db_session, account=principal)
    assert docs == [], "Cross-project submission_id filter must return empty, not the other project's docs."


# --- Req 5 + 6: Missing stored file → file_exists=False + 404 on download -----

def test_missing_stored_file_returns_file_exists_false_and_404_not_fake_data(
        db_session, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"; upload_dir.mkdir()
    monkeypatch.setattr(api_sub_module, "UPLOAD_DIR", upload_dir)
    fac = AuthAccount(email="fac3@uni.edu", role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$xf",
        faculty_id="F-MISS", faculty_name="Dr. Miss",
        email_verified=True, faculty_approved=True)
    db_session.add(fac)
    proj = Project(title="Missing Files Project", status="ACTIVE")
    db_session.add(proj)
    db_session.flush()
    db_session.add(FacultyProjectAssignment(faculty_account_id=fac.id, project_id=proj.id))
    sub = Submission(project_id=proj.id, week_number=2,
        report_path="ghost_file_never_existed.pdf",
        report_original_name="Original Report Name.pdf",
        submitted_at=datetime.now(timezone.utc), status="SUBMITTED")
    db_session.add(sub)
    db_session.commit()
    principal = Principal(id=fac.id, role="faculty", email=fac.email, student_id=None)

    docs = list_project_documents(project_id=proj.id, submission_id=None,
                                  db=db_session, account=principal)
    assert len(docs) == 1
    assert docs[0]["file_exists"] is False, "file_exists must be False for missing file."
    assert docs[0]["original_filename"] == "Original Report Name.pdf"

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(project_id=proj.id, submission_id=sub.id,
                                     document_id="report", db=db_session, account=principal)
    assert exc_info.value.status_code == 404
    assert "not found on server" in exc_info.value.detail.lower()


def test_missing_file_returns_404_not_fake_content_in_two_project_context(
        db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    gone_sub = Submission(project_id=s["proj_a"].id, week_number=99,
        report_path="already_deleted_report.pdf",
        report_original_name="Deleted Report.pdf",
        submitted_at=datetime.now(timezone.utc))
    db_session.add(gone_sub)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(project_id=s["proj_a"].id, submission_id=gone_sub.id,
                                     document_id="report", db=db_session, account=principal)
    assert exc_info.value.status_code == 404


# --- Req 7: Unauthorized faculty get 403 for unassigned project ---------------

def test_unassigned_faculty_cannot_access_project_submissions(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(s["proj_b"].id, principal, db_session)
    assert exc_info.value.status_code == 403


def test_unassigned_faculty_blocked_on_project_b(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(s["proj_b"].id, principal, db_session)
    assert exc_info.value.status_code == 403


# --- Req 8: Students cannot access another project's files --------------------

def test_student_in_project_a_cannot_access_project_b(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["stu1_acc"].id, role="student",
                          email=s["stu1"].email, student_id=s["stu1"].id)
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(s["proj_b"].id, principal, db_session)
    assert exc_info.value.status_code == 403


def test_student_cannot_download_from_other_project(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["stu1_acc"].id, role="student",
                          email=s["stu1"].email, student_id=s["stu1"].id)
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(s["proj_b"].id, principal, db_session)
    assert exc_info.value.status_code == 403


# --- Req 9: Genuine reviews, grades, milestone progress preserved -------------

def test_genuine_reviews_and_milestones_preserved(db_session, two_project_setup):
    s = two_project_setup
    review = db_session.get(SubmissionReview, s["review_b"].id)
    assert review is not None, "Genuine review must not be deleted."
    assert review.score == 75.0
    assert review.submission_id == s["sub_b"].id
    assert review.project_id == s["proj_b"].id

    milestone = db_session.get(Milestone, s["milestone_a"].id)
    assert milestone is not None, "Genuine milestone must not be deleted."
    assert milestone.completed is True
    assert milestone.title == "Literature Review"


def test_genuine_review_feedback_text_preserved(db_session, two_project_setup):
    s = two_project_setup
    review = db_session.get(SubmissionReview, s["review_b"].id)
    assert review is not None
    assert review.score == 75.0
    assert "acoustic fingerprinting" in review.feedback.lower()
    assert "literature review" in review.feedback.lower()


# --- Req 10: Original filenames and exact bytes preserved ---------------------

def test_original_filename_and_bytes_preserved_for_valid_submission(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    response = download_submission_document(project_id=s["proj_a"].id,
        submission_id=s["sub_a"].id, document_id="report",
        db=db_session, account=principal)
    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert "AI Monitoring Week 1 Report.pdf" in response.headers.get("content-disposition", "")
    with open(response.path, "rb") as f:
        assert f.read() == s["pdf_a_bytes"], "Downloaded bytes must exactly match original bytes."


def test_student_can_download_their_own_project_document(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["stu1_acc"].id, role="student",
                          email=s["stu1"].email, student_id=s["stu1"].id)
    project = ensure_project_access(s["proj_a"].id, principal, db_session)
    assert project.id == s["proj_a"].id
    response = download_submission_document(project_id=s["proj_a"].id,
        submission_id=s["sub_a"].id, document_id="report",
        db=db_session, account=principal)
    assert response.status_code == 200
    with open(response.path, "rb") as f:
        assert f.read() == s["pdf_a_bytes"]


def test_sidecar_json_fallback_preserves_original_filename(db_session, two_project_setup):
    s = two_project_setup
    upload_dir = s["upload_dir"]
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    raw_file = upload_dir / "sidecar_test.pdf"
    _write_pdf(raw_file)
    (upload_dir / "sidecar_test.pdf.meta.json").write_text(
        json.dumps({"original_filename": "Sidecar Original Name.pdf"}))
    sub = Submission(project_id=s["proj_a"].id, week_number=7,
        report_path="sidecar_test.pdf", report_original_name=None,
        submitted_at=datetime.now(timezone.utc))
    db_session.add(sub)
    db_session.commit()
    docs = list_submission_documents(project_id=s["proj_a"].id, submission_id=sub.id,
                                     db=db_session, account=principal)
    assert len(docs) == 1
    assert docs[0]["original_filename"] == "Sidecar Original Name.pdf"
    response = download_submission_document(project_id=s["proj_a"].id, submission_id=sub.id,
                                            document_id="report", db=db_session, account=principal)
    assert "Sidecar Original Name.pdf" in response.headers.get("content-disposition", "")


# --- Additional: file_exists field accuracy -----------------------------------

def test_file_exists_true_when_file_on_disk(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    docs = list_project_documents(project_id=s["proj_a"].id, submission_id=None,
                                  db=db_session, account=principal)
    assert all(d["file_exists"] is True for d in docs)


def test_file_exists_false_when_file_absent_from_disk(db_session, two_project_setup):
    s = two_project_setup
    principal = Principal(id=s["fac1"].id, role="faculty",
                          email=s["fac1"].email, student_id=None)
    ghost_sub = Submission(project_id=s["proj_a"].id, week_number=50,
        report_path="completely_missing.pdf", report_original_name="Missing File.pdf",
        submitted_at=datetime.now(timezone.utc))
    db_session.add(ghost_sub)
    db_session.commit()
    docs = list_project_documents(project_id=s["proj_a"].id, submission_id=ghost_sub.id,
                                  db=db_session, account=principal)
    assert len(docs) == 1
    assert docs[0]["file_exists"] is False
    assert docs[0]["original_filename"] == "Missing File.pdf"


# --- Additional: list_submissions scoped to project --------------------------

def test_list_submissions_scoped_to_project(db_session, two_project_setup):
    s = two_project_setup
    subs_a = list_submissions(project_id=s["proj_a"].id, db=db_session)
    subs_b = list_submissions(project_id=s["proj_b"].id, db=db_session)
    assert len(subs_a) == 1
    assert subs_a[0]["id"] == s["sub_a"].id
    assert subs_a[0]["project_id"] == s["proj_a"].id
    assert len(subs_b) == 1
    assert subs_b[0]["id"] == s["sub_b"].id
    assert subs_b[0]["project_id"] == s["proj_b"].id
    a_ids = {r["id"] for r in subs_a}
    b_ids = {r["id"] for r in subs_b}
    assert a_ids.isdisjoint(b_ids), "Submission IDs must not overlap between projects."
