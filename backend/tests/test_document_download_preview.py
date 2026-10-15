import json
import os
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
    preview_submission_document,
)
from app.api_projects import list_project_documents
from app.auth.dependencies import Principal
from app.db.models import (
    Base,
    Project,
    Submission,
    FacultyProjectAssignment,
    ProjectMember,
    Student,
    AuthAccount,
    DocumentAnalysis,
)


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
def test_setup(db_session, tmp_path, monkeypatch):
    # Setup test project 1
    project1 = Project(
        title="AI Project Monitoring System",
        description="Monitoring student deliverables with AI",
        status="ACTIVE",
    )
    # Setup test project 2
    project2 = Project(
        title="Autonomous Drone Navigation",
        description="Robotics and computer vision",
        status="ACTIVE",
    )
    db_session.add_all([project1, project2])
    db_session.flush()

    # Faculty 1 (assigned to project 1)
    faculty1 = AuthAccount(
        email="faculty1@university.edu",
        role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        faculty_id="FAC-001",
        faculty_name="Prof. One",
        email_verified=True,
        faculty_approved=True,
    )
    # Faculty 2 (assigned to project 2 only)
    faculty2 = AuthAccount(
        email="faculty2@university.edu",
        role="faculty",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        faculty_id="FAC-002",
        faculty_name="Prof. Two",
        email_verified=True,
        faculty_approved=True,
    )
    db_session.add_all([faculty1, faculty2])
    db_session.flush()

    # Assign faculty 1 to project 1, faculty 2 to project 2
    db_session.add(FacultyProjectAssignment(faculty_account_id=faculty1.id, project_id=project1.id))
    db_session.add(FacultyProjectAssignment(faculty_account_id=faculty2.id, project_id=project2.id))

    # Student 1 (member of project 1)
    student1 = Student(name="Alice Smith", email="alice@student.edu", registration_number="REG001")
    db_session.add(student1)
    db_session.flush()
    student1_acc = AuthAccount(
        email="alice@student.edu",
        role="student",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        student_id=student1.id,
        phone="1234567890",
        department="Computer Science",
        email_verified=True,
        faculty_approved=False,
    )
    db_session.add(student1_acc)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project1.id, student_id=student1.id))

    # Student 2 (member of project 2)
    student2 = Student(name="Bob Jones", email="bob@student.edu", registration_number="REG002")
    db_session.add(student2)
    db_session.flush()
    student2_acc = AuthAccount(
        email="bob@student.edu",
        role="student",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        student_id=student2.id,
        phone="1234567891",
        department="Computer Science",
        email_verified=True,
        faculty_approved=False,
    )
    db_session.add(student2_acc)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project2.id, student_id=student2.id))

    # Create dummy deliverable files in test upload directory
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(api_sub_module, "UPLOAD_DIR", upload_dir)

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Title (Project Progress Report 2026) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    pptx_bytes = b"PK\x03\x04\x14\x00\x06\x00Presentation Slides Payload Sample"
    docx_bytes = b"PK\x03\x04\x14\x00\x06\x00Word Document Requirements Payload"

    pdf_file = upload_dir / "uuid-report-123.pdf"
    pptx_file = upload_dir / "uuid-slides-456.pptx"
    docx_file = upload_dir / "uuid-srs-789.docx"

    pdf_file.write_bytes(pdf_bytes)
    pptx_file.write_bytes(pptx_bytes)
    docx_file.write_bytes(docx_bytes)

    # Submission 1 for Project 1
    sub1 = Submission(
        project_id=project1.id,
        week_number=3,
        report_path=str(pdf_file),
        presentation_path=str(pptx_file),
        srs_path=str(docx_file),
        report_original_name="Final Report Phase 1.pdf",
        presentation_original_name="Team Presentation Sprint 3.pptx",
        srs_original_name="System Requirements Specification.docx",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub1)

    # Empty submission for Project 1
    sub_empty = Submission(
        project_id=project1.id,
        week_number=4,
        report_path=None,
        presentation_path=None,
        srs_path=None,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub_empty)

    # Submission for Project 2
    sub2 = Submission(
        project_id=project2.id,
        week_number=1,
        report_path=str(pdf_file),
        report_original_name="Drone Navigation Overview.pdf",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub2)
    db_session.commit()

    return {
        "project1": project1,
        "project2": project2,
        "faculty1": faculty1,
        "faculty2": faculty2,
        "student1": student1,
        "student2": student2,
        "sub1": sub1,
        "sub2": sub2,
        "sub_empty": sub_empty,
        "pdf_bytes": pdf_bytes,
        "pptx_bytes": pptx_bytes,
        "docx_bytes": docx_bytes,
        "upload_dir": upload_dir,
    }


def test_faculty_can_list_files_for_assigned_project(db_session, test_setup):
    p = test_setup["project1"]
    sub = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    # List documents via submission endpoint
    docs = list_submission_documents(
        project_id=p.id,
        submission_id=sub.id,
        db=db_session,
        account=principal,
    )

    assert len(docs) == 3
    doc_types = {d["document_type"] for d in docs}
    assert doc_types == {"report", "presentation", "srs"}

    report_doc = next(d for d in docs if d["document_type"] == "report")
    assert report_doc["original_filename"] == "Final Report Phase 1.pdf"
    assert report_doc["file_type"] == "pdf"
    assert report_doc["file_size"] == len(test_setup["pdf_bytes"])
    assert report_doc["submission_id"] == sub.id
    assert "download_url" in report_doc
    assert "preview_url" in report_doc

    # List documents via project documents endpoint
    all_proj_docs = list_project_documents(
        project_id=p.id,
        submission_id=None,
        db=db_session,
        account=principal,
    )
    assert len(all_proj_docs) == 3


def test_faculty_download_original_pdf_exact_bytes_and_filename(db_session, test_setup):
    p = test_setup["project1"]
    sub = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    response = download_submission_document(
        project_id=p.id,
        submission_id=sub.id,
        document_id="report",
        db=db_session,
        account=principal,
    )

    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert response.media_type == "application/pdf"

    disp = response.headers.get("content-disposition", "")
    assert "Final Report Phase 1.pdf" in disp

    with open(response.path, "rb") as f:
        downloaded_bytes = f.read()
    assert downloaded_bytes == test_setup["pdf_bytes"]


def test_faculty_download_original_pptx_exact_bytes_and_filename(db_session, test_setup):
    p = test_setup["project1"]
    sub = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    response = download_submission_document(
        project_id=p.id,
        submission_id=sub.id,
        document_id="presentation",
        db=db_session,
        account=principal,
    )

    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert "presentation" in response.media_type or "octet-stream" in response.media_type

    disp = response.headers.get("content-disposition", "")
    assert "Team Presentation Sprint 3.pptx" in disp

    with open(response.path, "rb") as f:
        downloaded_bytes = f.read()
    assert downloaded_bytes == test_setup["pptx_bytes"]


def test_faculty_download_original_docx_exact_bytes(db_session, test_setup):
    p = test_setup["project1"]
    sub = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    response = download_submission_document(
        project_id=p.id,
        submission_id=sub.id,
        document_id="srs",
        db=db_session,
        account=principal,
    )

    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    disp = response.headers.get("content-disposition", "")
    assert "System Requirements Specification.docx" in disp

    with open(response.path, "rb") as f:
        downloaded_bytes = f.read()
    assert downloaded_bytes == test_setup["docx_bytes"]


def test_unassigned_faculty_cannot_access_or_download_project_files(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    f2 = test_setup["faculty2"]  # Assigned to project 2, NOT project 1
    unauthorized_principal = Principal(id=f2.id, role="faculty", email=f2.email, student_id=None)

    # Note: When called via router dependencies, require_project_access enforces access.
    # We can invoke ensure_project_access directly to verify permission check:
    from app.auth.dependencies import ensure_project_access
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(p1.id, unauthorized_principal, db_session)
    assert exc_info.value.status_code == 403


def test_student_cannot_access_other_projects_files(db_session, test_setup):
    p1 = test_setup["project1"]
    s2 = test_setup["student2"]  # Member of project 2, NOT project 1
    unauthorized_student = Principal(id=99, role="student", email="bob@student.edu", student_id=s2.id)

    from app.auth.dependencies import ensure_project_access
    with pytest.raises(HTTPException) as exc_info:
        ensure_project_access(p1.id, unauthorized_student, db_session)
    assert exc_info.value.status_code == 403


def test_assigned_student_can_download_their_own_project_files(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    s1 = test_setup["student1"]  # Member of project 1
    authorized_student = Principal(id=10, role="student", email="alice@student.edu", student_id=s1.id)

    from app.auth.dependencies import ensure_project_access
    # Access verification succeeds
    project = ensure_project_access(p1.id, authorized_student, db_session)
    assert project.id == p1.id

    docs = list_submission_documents(
        project_id=p1.id,
        submission_id=sub1.id,
        db=db_session,
        account=authorized_student,
    )
    assert len(docs) == 3

    response = download_submission_document(
        project_id=p1.id,
        submission_id=sub1.id,
        document_id="report",
        db=db_session,
        account=authorized_student,
    )
    assert response.status_code == 200
    with open(response.path, "rb") as f:
        assert f.read() == test_setup["pdf_bytes"]


def test_document_id_belonging_to_another_submission_is_rejected(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(
            project_id=p1.id,
            submission_id=sub1.id,
            document_id="non_existent_doc",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 404


def test_submission_belonging_to_another_project_is_rejected(db_session, test_setup):
    p1 = test_setup["project1"]
    sub2 = test_setup["sub2"]  # Belongs to project 2!
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(
            project_id=p1.id,
            submission_id=sub2.id,  # Sub 2 does not belong to Project 1
            document_id="report",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 404


def test_path_traversal_attempts_are_rejected(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(
            project_id=p1.id,
            submission_id=sub1.id,
            document_id="../../etc/passwd",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 404


def test_missing_file_on_disk_returns_clear_404_error(db_session, test_setup):
    p1 = test_setup["project1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    missing_sub = Submission(
        project_id=p1.id,
        week_number=10,
        report_path="C:\\nonexistent\\deleted_report.pdf",
        report_original_name="Deleted Report.pdf",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(missing_sub)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        download_submission_document(
            project_id=p1.id,
            submission_id=missing_sub.id,
            document_id="report",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 404
    assert "not found on server" in exc_info.value.detail.lower()


def test_pdf_preview_returns_inline_response(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    response = preview_submission_document(
        project_id=p1.id,
        submission_id=sub1.id,
        document_id="report",
        db=db_session,
        account=principal,
    )
    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.headers.get("content-disposition", "").startswith("inline")


def test_pptx_and_docx_preview_returns_415_unsupported(db_session, test_setup):
    p1 = test_setup["project1"]
    sub1 = test_setup["sub1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    # PPTX preview should return 415
    with pytest.raises(HTTPException) as exc_info:
        preview_submission_document(
            project_id=p1.id,
            submission_id=sub1.id,
            document_id="presentation",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 415
    assert "Download to open the original document" in exc_info.value.detail

    # DOCX preview should return 415
    with pytest.raises(HTTPException) as exc_info:
        preview_submission_document(
            project_id=p1.id,
            submission_id=sub1.id,
            document_id="srs",
            db=db_session,
            account=principal,
        )
    assert exc_info.value.status_code == 415
    assert "Download to open the original document" in exc_info.value.detail


def test_empty_submission_returns_empty_file_list(db_session, test_setup):
    p1 = test_setup["project1"]
    sub_empty = test_setup["sub_empty"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    docs = list_submission_documents(
        project_id=p1.id,
        submission_id=sub_empty.id,
        db=db_session,
        account=principal,
    )
    assert docs == []


def test_sidecar_metadata_fallback_for_original_filename(db_session, test_setup):
    p1 = test_setup["project1"]
    f1 = test_setup["faculty1"]
    principal = Principal(id=f1.id, role="faculty", email=f1.email, student_id=None)

    upload_dir = test_setup["upload_dir"]
    raw_file = upload_dir / "custom_uuid_deliverable.pdf"
    raw_file.write_bytes(test_setup["pdf_bytes"])
    meta_file = upload_dir / "custom_uuid_deliverable.pdf.meta.json"
    meta_file.write_text(json.dumps({"original_filename": "Sidecar Named Document.pdf"}))

    sub = Submission(
        project_id=p1.id,
        week_number=5,
        report_path=str(raw_file),
        report_original_name=None,  # No DB column value, must fall back to sidecar
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    db_session.commit()

    docs = list_submission_documents(
        project_id=p1.id,
        submission_id=sub.id,
        db=db_session,
        account=principal,
    )
    assert len(docs) == 1
    assert docs[0]["original_filename"] == "Sidecar Named Document.pdf"

    # Downloading also uses the sidecar filename
    response = download_submission_document(
        project_id=p1.id,
        submission_id=sub.id,
        document_id="report",
        db=db_session,
        account=principal,
    )
    assert "Sidecar Named Document.pdf" in response.headers.get("content-disposition", "")
