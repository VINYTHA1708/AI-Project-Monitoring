import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_db
from app.auth.service import create_access_token
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
from app.main import app


@pytest.fixture
def http_context(monkeypatch):
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
    db = session_factory()
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-jwt-secret-" + "x" * 40)
    monkeypatch.setattr(settings, "OTP_HMAC_SECRET", "test-otp-secret-" + "y" * 40)
    monkeypatch.setattr(settings, "STUDENT_EMAIL_DOMAINS", "university.edu")
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "faculty@university.edu")
    monkeypatch.setattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 0)

    def override_get_db():
        request_db = session_factory()
        try:
            yield request_db
        finally:
            request_db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client, db
    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


def _student_account(db: Session, email: str = "student@university.edu"):
    student = Student(
        name="Test Student",
        email=email,
        registration_number="ST-100",
    )
    account = AuthAccount(
        role="student",
        email=email,
        password_hash=PasswordHasher().hash("a-long-test-password"),
        student=student,
        phone="555-0100",
        department="Computing",
        email_verified=True,
    )
    db.add(account)
    db.commit()
    return account


def _faculty_account(db: Session):
    account = AuthAccount(
        role="faculty",
        email="faculty@university.edu",
        password_hash=PasswordHasher().hash("another-long-test-password"),
        faculty_id="FAC-100",
        faculty_name="Test Faculty",
        email_verified=True,
        faculty_approved=True,
    )
    db.add(account)
    db.commit()
    return account


def _bearer(account):
    token, _lifetime = create_access_token(account)
    return {"Authorization": f"Bearer {token}"}


def test_http_registration_login_otp_and_protected_request(
    http_context, monkeypatch
):
    client, db = http_context
    sent = []
    monkeypatch.setattr(
        "app.auth.service.send_otp_email",
        lambda email, code: sent.append((email, code)),
    )
    registration = client.post(
        "/auth/register/faculty",
        json={
            "name": "Test Faculty",
            "faculty_id": "FAC-101",
            "email": "faculty@university.edu",
            "password": "a-long-test-password",
            "department": "Computing",
        },
    )
    assert registration.status_code == 202
    assert sent[-1][0] == "faculty@university.edu"
    registration_code = sent[-1][1]

    verified = client.post(
        "/auth/otp/verify",
        json={
            "email": "faculty@university.edu",
            "code": registration_code,
            "purpose": "registration",
        },
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"] is None

    login = client.post(
        "/auth/login",
        json={
            "email": "faculty@university.edu",
            "password": "a-long-test-password",
        },
    )
    assert login.status_code == 202
    login_code = sent[-1][1]
    authenticated = client.post(
        "/auth/otp/verify",
        json={
            "email": "faculty@university.edu",
            "code": login_code,
            "purpose": "login",
        },
    )
    assert authenticated.status_code == 200
    token = authenticated.json()["access_token"]
    assert token
    account = db.query(AuthAccount).one()
    profile = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["id"] == account.id
    assert profile.json()["role"] == "faculty"


def test_http_duplicate_registration_wrong_password_and_otp_reuse(
    http_context, monkeypatch
):
    client, _db = http_context
    sent = []
    monkeypatch.setattr(
        "app.auth.service.send_otp_email",
        lambda email, code: sent.append((email, code)),
    )
    payload = {
        "name": "Test Student",
        "registration_number": "ST-200",
        "email": "student@university.edu",
        "phone": "555-0101",
        "department": "Computing",
        "password": "a-long-test-password",
    }
    assert client.post("/auth/register/student", json=payload).status_code == 202
    assert client.post("/auth/register/student", json=payload).status_code == 409
    code = sent[-1][1]
    first_verify = client.post(
        "/auth/otp/verify",
        json={
            "email": payload["email"],
            "code": code,
            "purpose": "registration",
        },
    )
    assert first_verify.status_code == 200
    second_verify = client.post(
        "/auth/otp/verify",
        json={
            "email": payload["email"],
            "code": code,
            "purpose": "registration",
        },
    )
    assert second_verify.status_code == 400
    wrong_password = client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "wrong-password-123"},
    )
    assert wrong_password.status_code == 401


def test_http_limits_unknown_emails_and_unauthorized_project_access(
    http_context, monkeypatch
):
    client, db = http_context
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_EMAIL_MAX", 1)
    first = client.post(
        "/auth/login",
        json={"email": "missing@university.edu", "password": "incorrect-pass-123"},
    )
    second = client.post(
        "/auth/login",
        json={"email": "missing@university.edu", "password": "incorrect-pass-123"},
    )
    assert first.status_code == 401
    assert second.status_code == 429

    account = _student_account(db)
    project = Project(title="Private project")
    db.add(project)
    db.commit()
    denied = client.get(
        f"/projects/{project.id}/progress",
        headers=_bearer(account),
    )
    assert denied.status_code == 403


def test_http_login_ip_limit_covers_multiple_unknown_emails(http_context, monkeypatch):
    client, _db = http_context
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_EMAIL_MAX", 10)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_IP_MAX", 1)
    first = client.post(
        "/auth/login",
        json={"email": "missing-one@university.edu", "password": "incorrect-pass-123"},
    )
    second = client.post(
        "/auth/login",
        json={"email": "missing-two@university.edu", "password": "incorrect-pass-123"},
    )
    assert first.status_code == 401
    assert second.status_code == 429


def test_http_registration_ip_limit_covers_multiple_accounts(
    http_context, monkeypatch
):
    client, _db = http_context
    sent = []
    monkeypatch.setattr(
        "app.auth.service.send_otp_email",
        lambda email, code: sent.append((email, code)),
    )
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REGISTRATION_EMAIL_MAX", 10)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REGISTRATION_IP_MAX", 1)
    first = client.post(
        "/auth/register/student",
        json={
            "name": "First Student",
            "registration_number": "IP-1",
            "email": "first@university.edu",
            "phone": "555-0101",
            "department": "Computing",
            "password": "a-long-test-password",
        },
    )
    second = client.post(
        "/auth/register/student",
        json={
            "name": "Second Student",
            "registration_number": "IP-2",
            "email": "second@university.edu",
            "phone": "555-0102",
            "department": "Computing",
            "password": "another-long-test-password",
        },
    )
    assert first.status_code == 202
    assert second.status_code == 429
    assert len(sent) == 1


def test_http_student_roster_is_project_scoped_and_read_only(http_context):
    client, db = http_context
    faculty = _faculty_account(db)
    project = Project(title="Assigned project")
    visible = Student(
        name="Visible Student",
        email="visible@university.edu",
        registration_number="VIS-100",
    )
    hidden = Student(
        name="Hidden Student",
        email="hidden@university.edu",
        registration_number="HID-100",
    )
    db.add_all([project, visible, hidden])
    db.flush()
    db.add_all([
        FacultyProjectAssignment(
            faculty_account_id=faculty.id,
            project_id=project.id,
        ),
        ProjectMember(project_id=project.id, student_id=visible.id),
    ])
    db.commit()

    headers = _bearer(faculty)
    roster = client.get("/students/", headers=headers)
    assert roster.status_code == 200
    assert [student["id"] for student in roster.json()] == [visible.id]
    assert client.get(f"/students/{hidden.id}", headers=headers).status_code == 404
    assert client.put(
        f"/students/{visible.id}",
        json={
            "name": "Changed",
            "email": "changed@university.edu",
            "registration_number": "CHG-1",
        },
        headers=headers,
    ).status_code == 405
    assert client.delete(f"/students/{visible.id}", headers=headers).status_code == 405


def test_http_submission_upload_requires_membership_and_never_returns_paths(
    http_context, monkeypatch, tmp_path
):
    client, db = http_context
    monkeypatch.setattr(
        "app.api_submission_uploads.UPLOAD_DIR",
        tmp_path,
    )
    account = _student_account(db)
    project = Project(title="Assigned project")
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, student_id=account.student_id))
    db.commit()

    uploaded = client.post(
        f"/projects/{project.id}/submissions/upload",
        data={"week_number": "1"},
        files={"report": ("report.pdf", b"%PDF-1.7\nexample", "application/pdf")},
        headers=_bearer(account),
    )
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["report_uploaded"] is True
    assert "report_path" not in payload
    submission = db.query(Submission).one()
    assert submission.report_path.endswith(".pdf")
    assert "/" not in submission.report_path
    assert "\\" not in submission.report_path
    assert (tmp_path / submission.report_path).is_file()

    listed = client.get(
        f"/projects/{project.id}/submissions/",
        headers=_bearer(account),
    )
    assert listed.status_code == 200
    assert listed.json()[0]["report_uploaded"] is True
    assert "report_path" not in listed.text


def test_http_rejects_path_submission_and_invalid_or_unauthorized_upload(
    http_context, monkeypatch, tmp_path
):
    client, db = http_context
    monkeypatch.setattr(
        "app.api_submission_uploads.UPLOAD_DIR",
        tmp_path,
    )
    account = _student_account(db)
    project = Project(title="Other project")
    db.add(project)
    db.commit()

    db.add(ProjectMember(project_id=project.id, student_id=account.student_id))
    db.commit()
    path_request = client.post(
        f"/projects/{project.id}/submissions/",
        json={"week_number": 1, "report_path": str(tmp_path / "outside.pdf")},
        headers=_bearer(account),
    )
    assert path_request.status_code == 405
    assert db.query(Submission).count() == 0

    member = Project(title="Member project")
    db.add(member)
    db.flush()
    db.add(ProjectMember(project_id=member.id, student_id=account.student_id))
    db.commit()
    invalid = client.post(
        f"/projects/{member.id}/submissions/upload",
        data={"week_number": "1"},
        files={"report": ("report.pdf", b"not a pdf", "application/pdf")},
        headers=_bearer(account),
    )
    assert invalid.status_code == 400
    assert db.query(Submission).count() == 0
    assert list(tmp_path.iterdir()) == []


def test_http_faculty_assignment_and_legacy_upload_route_are_scoped(http_context):
    client, db = http_context
    faculty = _faculty_account(db)
    project = Project(title="Faculty project")
    db.add(project)
    db.flush()
    db.add(
        FacultyProjectAssignment(
            faculty_account_id=faculty.id,
            project_id=project.id,
        )
    )
    db.commit()

    allowed = client.get(
        f"/projects/{project.id}/progress",
        headers=_bearer(faculty),
    )
    assert allowed.status_code == 200
    legacy_upload = client.post("/uploads/", headers=_bearer(faculty))
    assert legacy_upload.status_code == 410


def test_http_submission_deletion_requires_assigned_faculty_and_project_ownership(
    http_context,
):
    client, db = http_context
    faculty = _faculty_account(db)
    assigned_project = Project(title="Assigned project")
    other_project = Project(title="Unassigned project")
    db.add_all([assigned_project, other_project])
    db.flush()
    submission = Submission(
        project_id=assigned_project.id,
        week_number=1,
        report_path="server-generated.pdf",
        status="SUBMITTED",
    )
    db.add(submission)
    db.add(
        FacultyProjectAssignment(
            faculty_account_id=faculty.id,
            project_id=assigned_project.id,
        )
    )
    db.commit()
    submission_id = submission.id
    headers = _bearer(faculty)

    forbidden = client.delete(
        f"/projects/{other_project.id}/submissions/{submission_id}",
        headers=headers,
    )
    assert forbidden.status_code == 403
    wrong_project = client.delete(
        f"/projects/{assigned_project.id}/submissions/{submission_id + 100}",
        headers=headers,
    )
    assert wrong_project.status_code == 404
    deleted = client.delete(
        f"/projects/{assigned_project.id}/submissions/{submission_id}",
        headers=headers,
    )
    assert deleted.status_code == 204
    db.expire_all()
    assert db.get(Submission, submission_id) is None
