"""Tests for Student Submission Email Notifications to All Project Faculty.

Verifies:
1. Student submission sends an email notification to one assigned faculty member.
2. Student submission sends notifications to all eligible faculty members assigned to the project.
3. Multiple faculty members receive the same submission event payload.
4. Duplicate faculty email addresses are deduplicated.
5. Faculty members assigned to other projects are excluded.
6. Unapproved faculty members are excluded.
7. Faculty members without email addresses are handled safely.
8. The submitting student does not receive their own submission notification.
9. No eligible faculty members does not roll back the submission.
10. n8n webhook failure (HTTP 500, timeout) does not roll back the submission.
11. Existing submission payload compatibility is preserved when invoked with legacy arguments.
12. Submission event ID generation is deterministic and stable across retries.
13. X-ProjectScope-Secret authentication header is included when configured.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi import UploadFile
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api_submission_uploads as submission_uploads_module
from app.api_submission_uploads import upload_submission
from app.auth.dependencies import Principal
from app.core.config import settings
from app.db.models import (
    AuthAccount,
    Base,
    FacultyProjectAssignment,
    Project,
    ProjectMember,
    Student,
    Submission,
)
from app.services.n8n_notifier import (
    _post_to_n8n,
    generate_submission_event_id,
    notify_faculty_submission,
)

password_hasher = PasswordHasher()
TEST_PASSWORD_HASH = password_hasher.hash("TestPassword123!")


class MockHTTPResponse:
    def __init__(self, status_code: int = 200, body: bytes = b'{"success": true}'):
        self.status = status_code
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def make_dummy_pdf(filename: str = "report.pdf") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(b"%PDF-1.4\n%ProjectScope test deliverable\n%%EOF"),
    )


@pytest.fixture
def submission_env(monkeypatch):
    """Setup isolated in-memory test database and mock n8n configuration."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    webhook_calls = []

    def mock_urlopen(req, timeout=10):
        webhook_calls.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "data": json.loads(req.data.decode("utf-8")),
            "timeout": timeout,
            "method": req.get_method(),
        })
        return MockHTTPResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(
        settings,
        "N8N_WEBHOOK_URL",
        "http://localhost:5678/webhook/submission-notify",
    )
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "test-projectscope-secret-1234")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173")

    # Mock save_file so disk writes are bypassed in tests
    async def mock_save_file(file, category):
        return f"mock_{category}_{file.filename}", file.filename, 512

    monkeypatch.setattr(submission_uploads_module, "save_file", mock_save_file)

    # Seed base entities
    student_record = Student(
        name="Alice Student",
        email="alice@univ.edu",
        registration_number="REG-101",
    )
    session.add(student_record)
    session.flush()

    student_account = AuthAccount(
        role="student",
        email="alice@univ.edu",
        student_id=student_record.id,
        department="Computer Science",
        phone="+919876500000",
        faculty_approved=False,
        email_verified=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    faculty_primary = AuthAccount(
        role="faculty",
        email="prof.smith@univ.edu",
        faculty_name="Prof. Smith",
        faculty_id="FAC-001",
        department="Computer Science",
        email_verified=True,
        faculty_approved=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    faculty_secondary = AuthAccount(
        role="faculty",
        email="prof.jones@univ.edu",
        faculty_name="Prof. Jones",
        faculty_id="FAC-002",
        department="Computer Science",
        email_verified=True,
        faculty_approved=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    project_a = Project(
        title="AI Evaluation System",
        description="Monitoring platform A",
        status="ACTIVE",
    )
    project_b = Project(
        title="Robotics Arm Control",
        description="Hardware platform B",
        status="ACTIVE",
    )
    session.add_all([student_account, faculty_primary, faculty_secondary, project_a, project_b])
    session.flush()

    member = ProjectMember(
        project_id=project_a.id,
        student_id=student_record.id,
        role="LEADER",
    )
    assignment1 = FacultyProjectAssignment(
        faculty_account_id=faculty_primary.id,
        project_id=project_a.id,
    )
    assignment2 = FacultyProjectAssignment(
        faculty_account_id=faculty_secondary.id,
        project_id=project_a.id,
    )
    session.add_all([member, assignment1, assignment2])
    session.commit()

    principal = Principal(
        id=student_account.id,
        role="student",
        email=student_account.email,
        student_id=student_record.id,
    )

    yield {
        "session": session,
        "student_record": student_record,
        "student_account": student_account,
        "faculty_primary": faculty_primary,
        "faculty_secondary": faculty_secondary,
        "project_a": project_a,
        "project_b": project_b,
        "principal": principal,
        "webhook_calls": webhook_calls,
    }

    session.close()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_submission_notifies_all_assigned_faculty(submission_env):
    """Verify student submission sends one event containing ALL assigned approved faculty."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    student = env["student_record"]
    fac1 = env["faculty_primary"]
    fac2 = env["faculty_secondary"]

    import asyncio
    result = asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=3,
            report=make_dummy_pdf("week3_report.pdf"),
            presentation=None,
            srs=None,
            notes="Completed deliverable",
            account=env["principal"],
            db=session,
        )
    )

    assert result["message"] == "Submission uploaded and recorded successfully"
    sub_id = result["submission_id"]

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://localhost:5678/webhook/submission-notify"
    headers_lower = {k.lower(): v for k, v in call["headers"].items()}
    assert headers_lower.get("x-projectscope-secret") == "test-projectscope-secret-1234"

    payload = call["data"]
    # Base 8 fields present
    assert payload["project_id"] == project.id
    assert payload["project_name"] == project.title
    assert payload["student_name"] == student.name
    assert payload["student_email"] == student.email
    assert payload["faculty_email"] == fac1.email  # Primary faculty email
    assert payload["submission_title"] == f"Week 3 Submission – {project.title}"
    assert payload["submission_id"] == sub_id
    assert "submitted_at" in payload

    # Multi-faculty enriched fields
    assert payload["notification_type"] == "student_submission"
    assert payload["event_id"].startswith(f"sub-{sub_id}-")
    assert payload["student_registration_number"] == student.registration_number
    assert payload["week_number"] == 3
    assert payload["dashboard_url"] == f"http://localhost:5173/projects/{project.id}"

    # Verify both faculty members are present in faculty_recipients
    recipients = payload["faculty_recipients"]
    assert len(recipients) == 2
    recipients_by_email = {r["faculty_email"]: r for r in recipients}
    assert fac1.email in recipients_by_email
    assert fac2.email in recipients_by_email
    assert recipients_by_email[fac1.email]["faculty_id"] == fac1.faculty_id
    assert recipients_by_email[fac1.email]["faculty_name"] == fac1.faculty_name
    assert recipients_by_email[fac2.email]["faculty_id"] == fac2.faculty_id
    assert recipients_by_email[fac2.email]["faculty_name"] == fac2.faculty_name


def test_submission_single_faculty_recipient(submission_env):
    """When only one faculty is assigned, faculty_recipients has exactly one entry."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    fac2 = env["faculty_secondary"]

    # Remove second faculty assignment
    assignment2 = session.execute(
        FacultyProjectAssignment.__table__.select().where(
            FacultyProjectAssignment.faculty_account_id == fac2.id,
            FacultyProjectAssignment.project_id == project.id,
        )
    ).first()
    if assignment2:
        session.query(FacultyProjectAssignment).filter_by(
            faculty_account_id=fac2.id, project_id=project.id
        ).delete()
        session.commit()

    import asyncio
    result = asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=4,
            report=make_dummy_pdf("week4_report.pdf"),
            presentation=None,
            srs=None,
            notes="Single faculty project",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    payload = calls[0]["data"]
    assert payload["faculty_email"] == env["faculty_primary"].email
    recipients = payload["faculty_recipients"]
    assert len(recipients) == 1
    assert recipients[0]["faculty_email"] == env["faculty_primary"].email


def test_duplicate_faculty_emails_deduplicated(submission_env, monkeypatch):
    """If query results contain duplicate accounts or normalized emails, recipients list contains only 1 entry."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    fac1 = env["faculty_primary"]

    # Mock db.execute for faculty accounts query to simulate duplicate accounts returned
    orig_execute = session.execute

    class DummyScalars:
        def __init__(self, items):
            self._items = items
        def all(self):
            return self._items
        def first(self):
            return self._items[0] if self._items else None

    class DummyResult:
        def __init__(self, items):
            self._items = items
        def scalars(self):
            return DummyScalars(self._items)

    def mock_execute(statement, *args, **kwargs):
        stmt_str = str(statement)
        if "faculty_project_assignments" in stmt_str and "auth_accounts" in stmt_str:
            # Return duplicate fac1 instances
            return DummyResult([fac1, fac1])
        return orig_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", mock_execute)

    import asyncio
    asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=5,
            report=make_dummy_pdf("week5_report.pdf"),
            presentation=None,
            srs=None,
            notes="Deduplication test",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    recipients = calls[0]["data"]["faculty_recipients"]
    assert len(recipients) == 1
    assert recipients[0]["faculty_email"] == fac1.email.lower()


def test_faculty_assigned_to_other_projects_excluded(submission_env):
    """Faculty assigned only to Project B must not receive notifications for Project A."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project_a = env["project_a"]
    project_b = env["project_b"]

    faculty_b = AuthAccount(
        role="faculty",
        email="prof.other@univ.edu",
        faculty_name="Prof. Other",
        faculty_id="FAC-099",
        department="Robotics",
        email_verified=True,
        faculty_approved=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    session.add(faculty_b)
    session.flush()

    # Assign faculty_b ONLY to project_b
    assignment_b = FacultyProjectAssignment(
        faculty_account_id=faculty_b.id,
        project_id=project_b.id,
    )
    session.add(assignment_b)
    session.commit()

    import asyncio
    asyncio.run(
        upload_submission(
            project_id=project_a.id,
            week_number=6,
            report=make_dummy_pdf("week6_report.pdf"),
            presentation=None,
            srs=None,
            notes="Project A deliverable",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    recipients = calls[0]["data"]["faculty_recipients"]
    recipient_emails = [r["faculty_email"] for r in recipients]
    assert "prof.other@univ.edu" not in recipient_emails


def test_unapproved_faculty_excluded(submission_env):
    """Faculty accounts with faculty_approved=False must be excluded from recipients."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    fac2 = env["faculty_secondary"]

    # Mark fac2 unapproved
    fac2.faculty_approved = False
    session.commit()

    import asyncio
    asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=7,
            report=make_dummy_pdf("week7_report.pdf"),
            presentation=None,
            srs=None,
            notes="Approved check",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    recipients = calls[0]["data"]["faculty_recipients"]
    recipient_emails = [r["faculty_email"] for r in recipients]
    assert fac2.email not in recipient_emails
    assert env["faculty_primary"].email in recipient_emails


def test_submitting_student_email_excluded_from_faculty_recipients(submission_env):
    """If a faculty account happens to have the same email as the canonical student, it must be excluded."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    student = env["student_record"]
    fac2 = env["faculty_secondary"]

    # Set student_record email to match fac2 email (student record is in students table, separate from auth_accounts)
    student.email = fac2.email.upper()
    session.commit()

    import asyncio
    asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=8,
            report=make_dummy_pdf("week8_report.pdf"),
            presentation=None,
            srs=None,
            notes="Student email exclusion check",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    recipients = calls[0]["data"]["faculty_recipients"]
    recipient_emails = [r["faculty_email"] for r in recipients]
    assert fac2.email.lower() not in recipient_emails
    assert env["faculty_primary"].email in recipient_emails


def test_no_eligible_faculty_preserves_submission(submission_env):
    """If no eligible faculty members exist, submission is still committed and succeeds."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]

    # Delete all faculty assignments for project_a
    session.query(FacultyProjectAssignment).filter_by(project_id=project.id).delete()
    session.commit()

    import asyncio
    result = asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=9,
            report=make_dummy_pdf("week9_report.pdf"),
            presentation=None,
            srs=None,
            notes="No faculty assigned",
            account=env["principal"],
            db=session,
        )
    )

    assert result["message"] == "Submission uploaded and recorded successfully"
    sub_id = result["submission_id"]
    db_sub = session.get(Submission, sub_id)
    assert db_sub is not None
    assert db_sub.week_number == 9
    # Webhook was safely skipped
    assert len(calls) == 0


def test_webhook_failure_does_not_rollback_submission(submission_env, monkeypatch):
    """Webhook HTTP error does not rollback the committed submission."""
    env = submission_env
    session = env["session"]
    project = env["project_a"]

    def mock_http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="http://localhost:5678/webhook/submission-notify",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b"n8n webhook error"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_http_error)

    import asyncio
    result = asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=10,
            report=make_dummy_pdf("week10_report.pdf"),
            presentation=None,
            srs=None,
            notes="Webhook error test",
            account=env["principal"],
            db=session,
        )
    )

    sub_id = result["submission_id"]
    db_sub = session.get(Submission, sub_id)
    assert db_sub is not None
    assert db_sub.week_number == 10
    assert db_sub.status == "SUBMITTED"


def test_legacy_submission_notifier_exact_compatibility(monkeypatch):
    """Calling notify_faculty_submission with only the 8 base fields retains exact backwards compatibility."""
    calls = []

    def mock_urlopen(req, timeout=10):
        calls.append(json.loads(req.data.decode("utf-8")))
        return MockHTTPResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/submission-notify")

    now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=timezone.utc)
    notify_faculty_submission(
        project_id=1,
        project_name="AI Monitor",
        submission_id=10,
        submitted_at=now,
        student_name="Alice Student",
        student_email="alice@univ.edu",
        faculty_email="prof@univ.edu",
        submission_title="Week 1 Submission – AI Monitor",
    )

    assert len(calls) == 1
    assert calls[0] == {
        "project_id": 1,
        "project_name": "AI Monitor",
        "student_name": "Alice Student",
        "student_email": "alice@univ.edu",
        "faculty_email": "prof@univ.edu",
        "submission_title": "Week 1 Submission – AI Monitor",
        "submission_id": 10,
        "submitted_at": now.isoformat(),
    }


def test_submission_event_id_stable_across_retries():
    """Verify event ID is deterministic, stable across retries, and unique for distinct inputs."""
    ts1 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
    ts_diff = datetime(2026, 10, 30, 13, 0, 0, tzinfo=timezone.utc)

    id1 = generate_submission_event_id(submission_id=50, submitted_at=ts1)
    id2 = generate_submission_event_id(submission_id=50, submitted_at=ts2)
    id_other_ts = generate_submission_event_id(submission_id=50, submitted_at=ts_diff)
    id_other_sub = generate_submission_event_id(submission_id=51, submitted_at=ts1)

    assert id1 == id2, "Event ID must be identical for the same logical event"
    assert id1 != id_other_ts, "Different timestamp must produce a distinct event ID"
    assert id1 != id_other_sub, "Different submission ID must produce a distinct event ID"
    assert id1.startswith("sub-50-")


def test_secret_header_attached_to_submission_webhook(monkeypatch):
    """Verify X-ProjectScope-Secret header is sent to n8n and not leaked into payload."""
    headers_seen = {}

    def mock_urlopen(req, timeout=10):
        headers_seen.update(dict(req.headers))
        return MockHTTPResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/submission-notify")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "super-secret-token-xyz")

    payload = {"project_id": 1, "submission_id": 2}
    _post_to_n8n(payload)

    headers_lower = {k.lower(): v for k, v in headers_seen.items()}
    assert headers_lower.get("x-projectscope-secret") == "super-secret-token-xyz"
    assert "super-secret-token-xyz" not in json.dumps(payload)


def test_faculty_with_invalid_email_filtered(submission_env):
    """Faculty with missing @ or malformed email string are safely excluded."""
    env = submission_env
    session = env["session"]
    calls = env["webhook_calls"]
    project = env["project_a"]
    fac2 = env["faculty_secondary"]

    # Set fac2 email to invalid string
    fac2.email = "notanemail"
    session.commit()

    import asyncio
    asyncio.run(
        upload_submission(
            project_id=project.id,
            week_number=11,
            report=make_dummy_pdf("week11_report.pdf"),
            presentation=None,
            srs=None,
            notes="Invalid email filter check",
            account=env["principal"],
            db=session,
        )
    )

    assert len(calls) == 1
    recipients = calls[0]["data"]["faculty_recipients"]
    assert len(recipients) == 1
    assert recipients[0]["faculty_email"] == env["faculty_primary"].email


def test_n8n_partial_failure_response_handled_safely(monkeypatch):
    """When n8n responds with a partial failure summary, the backend logs safely without crashing."""
    def mock_partial_urlopen(req, timeout=10):
        body = b'{"status": "partial_failure", "total": 2, "sent": 1, "failed": 1, "message": "1 of 2 emails sent"}'
        return MockHTTPResponse(200, body=body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_partial_urlopen)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/submission-notify")

    payload = {
        "project_id": 1,
        "submission_id": 2,
        "faculty_recipients": [
            {"faculty_email": "prof1@univ.edu"},
            {"faculty_email": "prof2@univ.edu"},
        ],
    }
    # Must execute without throwing exceptions
    _post_to_n8n(payload)


def test_n8n_array_response_handled_safely(monkeypatch):
    """When n8n responds with a multi-item JSON array, the backend parses safely without crashing."""
    def mock_array_urlopen(req, timeout=10):
        body = b'[{"json": {"success": true}}, {"json": {"success": true}}]'
        return MockHTTPResponse(200, body=body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_array_urlopen)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/submission-notify")

    payload = {
        "project_id": 1,
        "submission_id": 3,
    }
    # Must execute without throwing exceptions
    _post_to_n8n(payload)
