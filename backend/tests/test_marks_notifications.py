import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api_reviews import (
    ReviewCreate,
    ReviewUpdate,
    create_review,
    update_review,
)
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
    SubmissionReview,
)
from app.services.n8n_notifier import (
    generate_marks_event_id,
    notify_faculty_submission,
    notify_student_marks,
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


@pytest.fixture
def marks_test_env(monkeypatch):
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
        "N8N_MARKS_UPDATED_WEBHOOK_URL",
        "https://projectscope-vinytha.app.n8n.cloud/webhook/projectscope/marks-updated",
    )
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "test-projectscope-secret-1234")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173")

    # Seed base test entities
    faculty1 = AuthAccount(
        role="faculty",
        email="prof.smith@univ.edu",
        faculty_name="Prof. Smith",
        faculty_id="FAC-001",
        email_verified=True,
        faculty_approved=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    faculty2 = AuthAccount(
        role="faculty",
        email="prof.jones@univ.edu",
        faculty_name="Prof. Jones",
        faculty_id="FAC-002",
        email_verified=True,
        faculty_approved=True,
        password_hash=TEST_PASSWORD_HASH,
    )
    student = Student(
        name="Alice Student",
        email="alice@univ.edu",
        registration_number="REG-101",
    )
    project = Project(
        title="AI Evaluation System",
        description="Monitoring platform",
        status="ACTIVE",
    )
    session.add_all([faculty1, faculty2, student, project])
    session.flush()

    member = ProjectMember(
        project_id=project.id,
        student_id=student.id,
        role="LEADER",
    )
    assignment = FacultyProjectAssignment(
        faculty_account_id=faculty1.id,
        project_id=project.id,
    )
    submission = Submission(
        project_id=project.id,
        week_number=2,
        status="SUBMITTED",
    )
    session.add_all([member, assignment, submission])
    session.commit()

    faculty1_principal = Principal(
        id=faculty1.id, role="faculty", email=faculty1.email, student_id=None
    )
    faculty2_principal = Principal(
        id=faculty2.id, role="faculty", email=faculty2.email, student_id=None
    )

    yield {
        "session": session,
        "faculty1": faculty1,
        "faculty2": faculty2,
        "faculty1_principal": faculty1_principal,
        "faculty2_principal": faculty2_principal,
        "student": student,
        "project": project,
        "submission": submission,
        "webhook_calls": webhook_calls,
    }

    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Requirement 1: Initial marks assignment triggers the notification
# ---------------------------------------------------------------------------


def test_create_review_triggers_marks_notification(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    data = ReviewCreate(score=87.5, feedback="Great literature survey and methodology.")
    result = create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=data,
        account=env["faculty1_principal"],
        db=session,
    )

    assert result["score"] == 87.5
    assert result["reviewer_name"] == "Prof. Smith"
    assert env["submission"].status == "REVIEWED"

    # Exactly 1 webhook POST made
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://projectscope-vinytha.app.n8n.cloud/webhook/projectscope/marks-updated"
    assert call["method"] == "POST"

    # Header authentication verification
    headers = call["headers"]
    assert headers.get("X-projectscope-secret") == "test-projectscope-secret-1234"
    assert "test-projectscope-secret-1234" not in json.dumps(call["data"])

    # Payload contract verification
    payload = call["data"]
    assert payload["student_id"] == env["student"].id
    assert payload["student_name"] == "Alice Student"
    assert payload["student_email"] == "alice@univ.edu"
    assert payload["project_id"] == env["project"].id
    assert payload["project_name"] == "AI Evaluation System"
    assert payload["submission_id"] == env["submission"].id
    assert payload["submission_title"] == "Week 2 Submission \u2013 AI Evaluation System"
    assert payload["marks_awarded"] == 87.5
    assert payload["max_marks"] == 100
    assert isinstance(payload["max_marks"], int)
    assert payload["updated_by"] == "Prof. Smith"
    assert payload["frontend_url"] == "http://localhost:5173/#reviews"
    assert payload["feedback"] == "Great literature survey and methodology."
    assert payload["event_id"].startswith(f"marks-rev{result['id']}-stu{env['student'].id}-")


# ---------------------------------------------------------------------------
# Requirement 2: Changed marks trigger the notification
# ---------------------------------------------------------------------------


def test_update_review_with_changed_marks_triggers_notification(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Initial review
    create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=70.0, feedback="Initial review draft."),
        account=env["faculty1_principal"],
        db=session,
    )
    assert len(calls) == 1
    initial_event_id = calls[0]["data"]["event_id"]

    # Update score to 85.0
    review_record = session.query(SubmissionReview).first()
    update_result = update_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        review_id=review_record.id,
        data=ReviewUpdate(score=85.0, feedback="Revised score after evaluation interview."),
        account=env["faculty1_principal"],
        db=session,
    )

    assert update_result["score"] == 85.0
    assert len(calls) == 2
    update_call = calls[1]
    update_payload = update_call["data"]
    assert update_payload["marks_awarded"] == 85.0
    assert update_payload["feedback"] == "Revised score after evaluation interview."
    assert update_payload["event_id"] != initial_event_id
    assert update_payload["event_id"].startswith(f"marks-rev{review_record.id}-stu{env['student'].id}-")


# ---------------------------------------------------------------------------
# Requirement 3: An unchanged marks update does not trigger duplicate notification
# ---------------------------------------------------------------------------


def test_update_review_with_unchanged_evaluation_skips_notification(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Create review
    create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=92.0, feedback="Solid architecture design."),
        account=env["faculty1_principal"],
        db=session,
    )
    assert len(calls) == 1

    review_record = session.query(SubmissionReview).first()

    # Submitting identical score and trimmed feedback
    update_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        review_id=review_record.id,
        data=ReviewUpdate(score=92.0, feedback="Solid architecture design.  "),
        account=env["faculty1_principal"],
        db=session,
    )

    # Call count must still be 1 (duplicate avoided)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Requirement 4: Failed validation does not trigger notification
# ---------------------------------------------------------------------------


def test_failed_validation_does_not_trigger_notification(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Score > 100 validation error
    with pytest.raises(ValidationError):
        ReviewCreate(score=105.0, feedback="Invalid high score")

    # Score < 0 validation error
    with pytest.raises(ValidationError):
        ReviewCreate(score=-5.0, feedback="Invalid negative score")

    # Empty feedback validation error in route
    with pytest.raises(HTTPException) as exc_info:
        create_review(
            project_id=env["project"].id,
            submission_id=env["submission"].id,
            data=ReviewCreate(score=80.0, feedback="    "),
            account=env["faculty1_principal"],
            db=session,
        )
    assert exc_info.value.status_code == 422

    assert len(calls) == 0


# ---------------------------------------------------------------------------
# Requirement 5: Unauthorized faculty cannot trigger notification
# ---------------------------------------------------------------------------


def test_unauthorized_faculty_cannot_edit_other_review(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Faculty 1 creates review
    create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=88.0, feedback="Approved by Faculty 1."),
        account=env["faculty1_principal"],
        db=session,
    )
    assert len(calls) == 1

    review_record = session.query(SubmissionReview).first()

    # Faculty 2 tries to edit Faculty 1's review
    with pytest.raises(HTTPException) as exc_info:
        update_review(
            project_id=env["project"].id,
            submission_id=env["submission"].id,
            review_id=review_record.id,
            data=ReviewUpdate(score=50.0, feedback="Tampered review."),
            account=env["faculty2_principal"],
            db=session,
        )

    assert exc_info.value.status_code == 403
    # No extra notification sent
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Requirement 6: A rolled-back transaction does not trigger notification
# ---------------------------------------------------------------------------


def test_rolled_back_transaction_does_not_trigger_notification(marks_test_env, monkeypatch):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    def failing_commit():
        raise RuntimeError("Simulated database disk failure")

    monkeypatch.setattr(session, "commit", failing_commit)

    with pytest.raises(RuntimeError, match="Simulated database disk failure"):
        create_review(
            project_id=env["project"].id,
            submission_id=env["submission"].id,
            data=ReviewCreate(score=80.0, feedback="Will fail on commit."),
            account=env["faculty1_principal"],
            db=session,
        )

    assert len(calls) == 0


# ---------------------------------------------------------------------------
# Requirement 7: Missing student mapping or email is handled safely
# ---------------------------------------------------------------------------


def test_missing_student_email_handled_safely(marks_test_env, caplog):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Set student's email to empty
    student = env["student"]
    student.email = "   "
    session.commit()

    result = create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=91.0, feedback="Good work."),
        account=env["faculty1_principal"],
        db=session,
    )

    # Review is successfully created despite missing student email
    assert result["score"] == 91.0
    # Webhook POST was safely skipped
    assert len(calls) == 0
    assert "student email is missing or empty" in caplog.text


def test_missing_project_students_handled_safely(marks_test_env, caplog):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Remove all members from project
    session.query(ProjectMember).delete()
    session.commit()

    result = create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=75.0, feedback="Evaluation for unassigned team."),
        account=env["faculty1_principal"],
        db=session,
    )

    assert result["score"] == 75.0
    assert len(calls) == 0
    assert "no students assigned to project" in caplog.text


# ---------------------------------------------------------------------------
# Requirement 8: n8n timeout or HTTP failure does not undo already committed marks
# ---------------------------------------------------------------------------


def test_webhook_http_error_does_not_rollback_committed_marks(marks_test_env, monkeypatch):
    env = marks_test_env
    session = env["session"]

    # Simulate webhook returning 500 error
    def failing_urlopen(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://webhook.test",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)

    # Creating review succeeds despite n8n HTTP 500
    result = create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=84.0, feedback="Evaluation completed."),
        account=env["faculty1_principal"],
        db=session,
    )

    assert result["score"] == 84.0
    # Verify review is genuinely persisted in database
    saved_review = session.query(SubmissionReview).first()
    assert saved_review is not None
    assert saved_review.score == 84.0


def test_webhook_timeout_does_not_rollback_committed_marks(marks_test_env, monkeypatch):
    env = marks_test_env
    session = env["session"]

    def timeout_urlopen(*_args, **_kwargs):
        raise TimeoutError("Connection timed out after 10s")

    monkeypatch.setattr(urllib.request, "urlopen", timeout_urlopen)

    result = create_review(
        project_id=env["project"].id,
        submission_id=env["submission"].id,
        data=ReviewCreate(score=79.5, feedback="Evaluation recorded."),
        account=env["faculty1_principal"],
        db=session,
    )

    assert result["score"] == 79.5
    saved_review = session.query(SubmissionReview).first()
    assert saved_review is not None
    assert saved_review.score == 79.5


# ---------------------------------------------------------------------------
# Requirement 9: The existing student-submission workflow remains unchanged
# ---------------------------------------------------------------------------


def test_existing_submission_notifier_unchanged(monkeypatch):
    calls = []

    def mock_urlopen(req, timeout=10):
        calls.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "data": json.loads(req.data.decode("utf-8")),
            "timeout": timeout,
        })
        return MockHTTPResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/submission-notify"
    )

    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
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
    call = calls[0]
    assert call["url"] == "http://localhost:5678/webhook/submission-notify"
    payload = call["data"]
    # 8 exact fields required by existing workflow
    assert payload == {
        "project_id": 1,
        "project_name": "AI Monitor",
        "student_name": "Alice Student",
        "student_email": "alice@univ.edu",
        "faculty_email": "prof@univ.edu",
        "submission_title": "Week 1 Submission – AI Monitor",
        "submission_id": 10,
        "submitted_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Requirement 10: Event ID stability across retries
# ---------------------------------------------------------------------------


def test_event_id_stable_across_retries():
    ts = datetime(2026, 10, 28, 15, 30, 45, 123456, tzinfo=timezone.utc)

    id_attempt1 = generate_marks_event_id(review_id=5, student_id=2, score=88.5, updated_at=ts)
    id_attempt2 = generate_marks_event_id(review_id=5, student_id=2, score=88.5, updated_at=ts)

    # Identical on retries
    assert id_attempt1 == id_attempt2

    # Different when score changes
    id_diff_score = generate_marks_event_id(review_id=5, student_id=2, score=90.0, updated_at=ts)
    assert id_attempt1 != id_diff_score

    # Different when timestamp changes
    ts_later = datetime(2026, 10, 28, 15, 31, 0, 0, tzinfo=timezone.utc)
    id_diff_time = generate_marks_event_id(review_id=5, student_id=2, score=88.5, updated_at=ts_later)
    assert id_attempt1 != id_diff_time


# ---------------------------------------------------------------------------
# Missing configuration safety
# ---------------------------------------------------------------------------


def test_missing_secret_skips_unauthenticated_request(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: calls.append(1))
    monkeypatch.setattr(settings, "N8N_MARKS_UPDATED_WEBHOOK_URL", "https://webhook.test/marks")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", None)

    notify_student_marks(
        event_id="test-event-1",
        student_id=1,
        student_name="Alice",
        student_email="alice@univ.edu",
        project_id=1,
        project_name="AI Monitor",
        submission_id=1,
        submission_title="Week 1",
        marks_awarded=90.0,
        max_marks=100.0,
        updated_at=datetime.now(timezone.utc),
        updated_by="Prof. Smith",
    )

    assert len(calls) == 0
    assert "N8N_WEBHOOK_SECRET not configured" in caplog.text



# ---------------------------------------------------------------------------
# Week 0 submission title formatting and integer max_marks
# ---------------------------------------------------------------------------


def test_week_zero_submission_title_and_integer_max_marks(marks_test_env):
    env = marks_test_env
    session = env["session"]
    calls = env["webhook_calls"]

    # Create submission with week_number = 0
    submission_zero = Submission(
        project_id=env["project"].id,
        week_number=0,
        status="SUBMITTED",
    )
    session.add(submission_zero)
    session.commit()

    result = create_review(
        project_id=env["project"].id,
        submission_id=submission_zero.id,
        data=ReviewCreate(score=95.0, feedback="Orientation phase evaluated."),
        account=env["faculty1_principal"],
        db=session,
    )

    assert result["score"] == 95.0
    assert len(calls) == 1
    payload = calls[0]["data"]
    assert payload["submission_title"] == "Week 0 Submission – AI Evaluation System"
    assert payload["max_marks"] == 100
    assert isinstance(payload["max_marks"], int)
