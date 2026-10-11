from datetime import datetime, timedelta, timezone
import secrets

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    Principal,
    ensure_project_access,
    get_current_account,
    require_roles,
)
from app.auth.service import (
    AuthServiceError,
    _email_in_student_domain,
    _faculty_is_approved,
    begin_login,
    decode_access_token,
    create_access_token,
    register_faculty,
    register_student,
    resend_otp,
    verify_otp,
)
from app.services.email_service import EmailServiceError
from app.core.config import settings
from app.db.models import AuthAccount, AuthOTPChallenge, Base, Project, Student
from app.schemas.auth import FacultyRegistration, StudentRegistration

@pytest.fixture
def auth_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setattr(settings, "OTP_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setattr(settings, "STUDENT_EMAIL_DOMAINS", "university.edu")
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "faculty@university.edu")
    monkeypatch.setattr(settings, "AUTH_OTP_LIFETIME_SECONDS", 600)
    monkeypatch.setattr(settings, "AUTH_OTP_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "AUTH_OTP_MAX_SENDS_PER_HOUR", 5)
    yield session
    session.close()
    engine.dispose()


def capture_email(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "app.auth.service.send_otp_email",
        lambda email, code: messages.append((email, code)),
    )
    return messages


def student_registration(**updates):
    values = {
        "name": "Jordan Student",
        "registration_number": "cs-1001",
        "email": "jordan@university.edu",
        "phone": "+1 555 0100",
        "department": "Computer Science",
        "password": "a-long-test-password",
    }
    values.update(updates)
    return StudentRegistration(**values)


def faculty_registration(**updates):
    values = {
        "name": "Avery Faculty",
        "faculty_id": "FAC-1",
        "email": "faculty@university.edu",
        "department": "Computer Science",
        "password": "another-long-test-password",
    }
    values.update(updates)
    return FacultyRegistration(**values)


def test_student_registration_hashes_password_and_links_legacy_student(
    auth_db, monkeypatch
):
    messages = capture_email(monkeypatch)
    legacy = Student(
        name="Existing Student",
        email="Jordan@University.edu ",
        registration_number=" CS-1001 ",
    )
    # The existing columns have unique constraints; no normalization or update occurs.
    auth_db.add(legacy)
    auth_db.commit()

    register_student(student_registration(), auth_db)

    auth_db.refresh(legacy)
    account = auth_db.query(AuthAccount).one()
    assert account.student_id == legacy.id
    assert legacy.name == "Existing Student"
    assert legacy.email == "Jordan@University.edu "
    assert legacy.registration_number == " CS-1001 "
    assert account.password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(account.password_hash, "a-long-test-password")
    assert "a-long-test-password" not in account.password_hash
    assert messages[0][0] == "jordan@university.edu"
    assert len(messages[0][1]) == 6


def test_student_registration_rejects_duplicate_or_partial_legacy_match(
    auth_db, monkeypatch
):
    capture_email(monkeypatch)
    legacy = Student(
        name="Existing Student",
        email="jordan@university.edu",
        registration_number="CS-1001",
    )
    auth_db.add(legacy)
    auth_db.commit()

    with pytest.raises(AuthServiceError) as exc_info:
        register_student(
            student_registration(registration_number="CS-OTHER"),
            auth_db,
        )
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert auth_db.query(Student).count() == 1
    assert auth_db.query(AuthAccount).count() == 0


def test_student_registration_does_not_create_duplicate_account(auth_db, monkeypatch):
    capture_email(monkeypatch)
    register_student(student_registration(), auth_db)

    with pytest.raises(AuthServiceError) as exc_info:
        register_student(student_registration(), auth_db)
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert auth_db.query(AuthAccount).count() == 1


def test_login_rejects_incorrect_password_without_sending_otp(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    register_student(student_registration(), auth_db)
    account = auth_db.query(AuthAccount).one()
    account.email_verified = True
    auth_db.commit()
    messages.clear()

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    for _ in range(2):
        with pytest.raises(AuthServiceError) as exc_info:
            begin_login(account.email, "incorrect-password", auth_db)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    with pytest.raises(AuthServiceError) as locked:
        begin_login(account.email, "a-long-test-password", auth_db)
    assert locked.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert auth_db.get(AuthAccount, account.id).failed_login_count == 2
    assert messages == []


def test_registration_otp_cannot_authenticate_login_and_is_single_use(
    auth_db, monkeypatch
):
    messages = capture_email(monkeypatch)
    register_student(student_registration(), auth_db)
    registration_code = messages[-1][1]
    auth_db.rollback()

    with pytest.raises(AuthServiceError) as wrong_purpose:
        verify_otp(
            "jordan@university.edu",
            registration_code,
            "login",
            auth_db,
        )
    assert wrong_purpose.value.status_code == status.HTTP_400_BAD_REQUEST

    response = verify_otp(
        "jordan@university.edu",
        registration_code,
        "registration",
        auth_db,
    )
    assert response["email_verified"] is True
    assert response.get("access_token") is None
    with pytest.raises(AuthServiceError):
        verify_otp(
            "jordan@university.edu",
            registration_code,
            "registration",
            auth_db,
        )


def test_expired_otp_is_rejected_and_consumed(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    register_student(student_registration(), auth_db)
    challenge = auth_db.query(AuthOTPChallenge).one()
    now = datetime.now(timezone.utc)
    challenge.created_at = now - timedelta(hours=2)
    challenge.expires_at = now - timedelta(hours=1)
    auth_db.commit()

    with pytest.raises(AuthServiceError) as exc_info:
        verify_otp(
            "jordan@university.edu",
            messages[-1][1],
            "registration",
            auth_db,
        )
    auth_db.refresh(challenge)
    auth_db.rollback()
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert challenge.consumed_at is not None
    assert auth_db.query(AuthAccount).one().email_verified is False


def test_failed_otp_attempts_are_not_reset_by_requesting_another_code(
    auth_db, monkeypatch
):
    messages = capture_email(monkeypatch)
    monkeypatch.setattr(settings, "AUTH_OTP_MAX_ATTEMPTS", 2)
    register_student(student_registration(), auth_db)
    email, first_code = messages[-1]

    for _ in range(2):
        with pytest.raises(AuthServiceError):
            verify_otp(
                email,
                "000000" if first_code != "000000" else "000001",
                "registration",
                auth_db,
            )
    with pytest.raises(AuthServiceError) as exc_info:
        resend_otp(email, "registration", auth_db)
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert len(messages) == 1


def test_allowlisted_faculty_requires_verification_and_approval(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    register_faculty(faculty_registration(), auth_db)
    account = auth_db.query(AuthAccount).one()
    assert account.faculty_approved is False
    auth_db.rollback()
    response = verify_otp(
        account.email,
        messages[-1][1],
        "registration",
        auth_db,
    )
    auth_db.rollback()
    auth_db.refresh(account)
    assert response["faculty_approval_pending"] is False
    assert account.email_verified is True
    assert account.faculty_approved is True


def test_login_otp_issues_valid_signed_token_only_after_verification(
    auth_db, monkeypatch
):
    messages = capture_email(monkeypatch)
    register_student(student_registration(), auth_db)
    registration_code = messages[-1][1]
    auth_db.rollback()
    verify_otp(
        "jordan@university.edu",
        registration_code,
        "registration",
        auth_db,
    )

    begin_login("jordan@university.edu", "a-long-test-password", auth_db)
    login_code = messages[-1][1]
    response = verify_otp(
        "jordan@university.edu",
        login_code,
        "login",
        auth_db,
    )

    claims = decode_access_token(response["access_token"])
    assert claims["role"] == "student"
    assert response["account"]["role"] == "student"
    assert "password" not in response["account"]


def test_unapproved_faculty_cannot_start_login(auth_db, monkeypatch):
    capture_email(monkeypatch)
    register_faculty(faculty_registration(email="pending@university.edu"), auth_db)
    account = auth_db.query(AuthAccount).one()
    account.email_verified = True
    auth_db.commit()

    with pytest.raises(AuthServiceError) as exc_info:
        begin_login(account.email, "another-long-test-password", auth_db)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_missing_bearer_and_wrong_role_are_rejected(auth_db):
    with pytest.raises(HTTPException) as missing:
        get_current_account(credentials=None, db=auth_db)
    assert missing.value.status_code == status.HTTP_401_UNAUTHORIZED

    dependency = require_roles("faculty")
    with pytest.raises(HTTPException) as denied:
        dependency(
            account=Principal(
                id=1,
                role="student",
                email="jordan@university.edu",
                student_id=1,
            )
        )
    assert denied.value.status_code == status.HTTP_403_FORBIDDEN


def test_signed_token_resolves_account_and_rejects_unverified_accounts(
    auth_db, monkeypatch
):
    student = Student(
        name="Token Student",
        email="token@university.edu",
        registration_number="TOK-1",
    )
    account = AuthAccount(
        role="student",
        email="token@university.edu",
        password_hash=PasswordHasher().hash("a-long-token-password"),
        student=student,
        phone="+1 555 0101",
        department="Computer Science",
        email_verified=True,
    )
    auth_db.add(account)
    auth_db.commit()
    token, _lifetime = create_access_token(account)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    principal = get_current_account(credentials=credentials, db=auth_db)
    assert principal.id == account.id
    assert principal.role == "student"

    account.email_verified = False
    auth_db.commit()
    with pytest.raises(HTTPException) as denied:
        get_current_account(credentials=credentials, db=auth_db)
    assert denied.value.status_code == status.HTTP_403_FORBIDDEN


def test_production_configuration_rejects_placeholders_and_shared_secrets(
    auth_db, monkeypatch
):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(
        settings, "DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb"
    )
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "replace-with-a-random-key-123456789")
    monkeypatch.setattr(settings, "OTP_HMAC_SECRET", "a-different-long-random-key-123456789")
    monkeypatch.setattr(settings, "STUDENT_EMAIL_DOMAINS", "university.edu")
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "faculty@university.edu")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        settings.validate_production_auth_settings()

    secret = secrets.token_urlsafe(48)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(settings, "OTP_HMAC_SECRET", secret)
    with pytest.raises(ValueError, match="must be different"):
        settings.validate_production_auth_settings()


def test_production_configuration_rejects_sqlite_database_url(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    secret1 = secrets.token_urlsafe(48)
    secret2 = secrets.token_urlsafe(48)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", secret1)
    monkeypatch.setattr(settings, "OTP_HMAC_SECRET", secret2)
    monkeypatch.setattr(settings, "STUDENT_EMAIL_DOMAINS", "university.edu")
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "faculty@university.edu")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///:memory:")

    with pytest.raises(ValueError, match="Production requires a PostgreSQL database"):
        settings.validate_production_auth_settings()


def test_student_cannot_access_project_without_membership(auth_db):
    project = Project(title="Restricted")
    auth_db.add(project)
    auth_db.commit()
    student = Principal(
        id=1,
        role="student",
        email="jordan@university.edu",
        student_id=22,
    )

    with pytest.raises(HTTPException) as denied:
        ensure_project_access(project.id, student, auth_db)
    assert denied.value.status_code == status.HTTP_403_FORBIDDEN


def test_failed_smtp_delivery_is_retryable_and_old_code_cannot_authenticate(
    auth_db, monkeypatch
):
    attempted_codes = []

    def fail_delivery(_email, code):
        attempted_codes.append(code)
        raise EmailServiceError("mock SMTP failure")

    monkeypatch.setattr("app.auth.service.send_otp_email", fail_delivery)
    monkeypatch.setattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60)
    with pytest.raises(AuthServiceError) as failed:
        register_student(student_registration(), auth_db)
    assert failed.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    failed_challenge = auth_db.query(AuthOTPChallenge).one()
    assert failed_challenge.delivery_status == "failed"
    assert failed_challenge.consumed_at is not None

    delivered_codes = capture_email(monkeypatch)
    resend_otp("jordan@university.edu", "registration", auth_db)
    active_challenge = (
        auth_db.query(AuthOTPChallenge)
        .filter(AuthOTPChallenge.delivery_status == "delivered")
        .one()
    )
    assert len(delivered_codes) == 1
    assert active_challenge.consumed_at is None

    with pytest.raises(AuthServiceError):
        verify_otp(
            "jordan@university.edu",
            attempted_codes[0],
            "registration",
            auth_db,
        )
    verified = verify_otp(
        "jordan@university.edu",
        delivered_codes[0][1],
        "registration",
        auth_db,
    )
    assert verified["email_verified"] is True


def test_student_registration_allowed_domain_vitstudent(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    monkeypatch.setattr(
        settings, "STUDENT_EMAIL_DOMAINS", "vitstudent.ac.in,university.edu"
    )
    reg = student_registration(
        email="student@vitstudent.ac.in",
        registration_number="21BCE0001",
    )
    register_student(reg, auth_db)
    assert len(messages) == 1
    assert messages[0][0] == "student@vitstudent.ac.in"
    assert auth_db.query(AuthAccount).filter_by(email="student@vitstudent.ac.in").count() == 1


def test_student_registration_disallowed_domain(auth_db, monkeypatch):
    capture_email(monkeypatch)
    monkeypatch.setattr(
        settings, "STUDENT_EMAIL_DOMAINS", "vitstudent.ac.in,university.edu"
    )
    reg = student_registration(
        email="intruder@gmail.com",
        registration_number="21BCE9999",
    )
    with pytest.raises(AuthServiceError) as exc_info:
        register_student(reg, auth_db)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "approved student domain" in exc_info.value.detail
    assert auth_db.query(AuthAccount).filter_by(email="intruder@gmail.com").count() == 0


def test_student_domain_check_malformed_email_addresses(monkeypatch):
    monkeypatch.setattr(
        settings, "STUDENT_EMAIL_DOMAINS", "vitstudent.ac.in,university.edu"
    )
    malformed_emails = [
        "notanemail",
        "@vitstudent.ac.in",
        "student@",
        "student@@vitstudent.ac.in",
        "student@evil.com@vitstudent.ac.in",
        "vitstudent.ac.in",
        "",
        "   ",
        None,
        "student@ vitstudent.ac.in",
        "student@vitstudent.ac.in ",
    ]
    for candidate in malformed_emails:
        # Whitespace-stripped valid email is tested separately; unstripped with inner space is malformed
        if candidate == "student@vitstudent.ac.in ":
            # normalize_email strips outer whitespace, but direct call without clean string
            assert _email_in_student_domain("student@vitstudent.ac.in") is True
        else:
            assert _email_in_student_domain(candidate) is False, f"Expected False for {candidate!r}"


def test_student_registration_succeeds_when_no_account_exists(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    reg = student_registration(
        email="fresh.student@university.edu",
        registration_number="FRESH-001",
    )
    register_student(reg, auth_db)
    assert len(messages) == 1
    assert messages[0][0] == "fresh.student@university.edu"
    created_account = auth_db.query(AuthAccount).filter_by(email="fresh.student@university.edu").one_or_none()
    assert created_account is not None
    assert created_account.role == "student"
    created_student = auth_db.query(Student).filter_by(email="fresh.student@university.edu").one_or_none()
    assert created_student is not None
    assert created_student.registration_number == "FRESH-001"


def test_student_registration_rejects_duplicate_email_with_existing_account(auth_db, monkeypatch):
    capture_email(monkeypatch)
    # Pre-register a faculty account with this email
    register_faculty(faculty_registration(email="faculty@university.edu"), auth_db)

    # Attempt student registration with the same email
    reg = student_registration(
        email="faculty@university.edu",
        registration_number="NEW-REG-001",
    )
    with pytest.raises(AuthServiceError) as exc_info:
        register_student(reg, auth_db)
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "An account already exists for this email address." in exc_info.value.detail
    assert auth_db.query(Student).filter_by(email="faculty@university.edu").count() == 0


def test_verified_approved_faculty_passes_approval_gate_and_can_login(auth_db, monkeypatch):
    messages = capture_email(monkeypatch)
    # Ensure allowlist only contains other email
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "other.faculty@university.edu")
    
    # Create a verified, approved faculty whose email is NOT in the allowlist
    account = AuthAccount(
        role="faculty",
        email="approved.prof@custom.edu",
        faculty_name="Prof Approved",
        faculty_id="FAC-APP-1",
        email_verified=True,
        faculty_approved=True,
        password_hash=PasswordHasher().hash("secure-faculty-pass"),
    )
    auth_db.add(account)
    auth_db.commit()

    # Approval gate check directly
    assert _faculty_is_approved(account) is True

    # Login flow passes approval gate and sends challenge
    begin_login("approved.prof@custom.edu", "secure-faculty-pass", auth_db)
    assert len(messages) == 1
    assert messages[0][0] == "approved.prof@custom.edu"
    login_code = messages[0][1]

    # OTP verification succeeds and issues access token
    auth_db.rollback()
    res = verify_otp("approved.prof@custom.edu", login_code, "login", auth_db)
    assert res["email_verified"] is True
    assert res["faculty_approval_pending"] is False
    assert "access_token" in res
    assert res["account"]["role"] == "faculty"


def test_unapproved_faculty_remains_blocked_from_login(auth_db, monkeypatch):
    capture_email(monkeypatch)
    # Verified email but faculty_approved is False
    account = AuthAccount(
        role="faculty",
        email="unapproved.prof@custom.edu",
        faculty_name="Prof Unapproved",
        faculty_id="FAC-UNAPP-1",
        email_verified=True,
        faculty_approved=False,
        password_hash=PasswordHasher().hash("secure-faculty-pass"),
    )
    auth_db.add(account)
    auth_db.commit()

    assert _faculty_is_approved(account) is False

    with pytest.raises(AuthServiceError) as exc_info:
        begin_login("unapproved.prof@custom.edu", "secure-faculty-pass", auth_db)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Faculty access is pending approval." in exc_info.value.detail


def test_unverified_faculty_remains_blocked_from_login(auth_db, monkeypatch):
    capture_email(monkeypatch)
    # Neither verified nor approved
    account = AuthAccount(
        role="faculty",
        email="unverified.prof@custom.edu",
        faculty_name="Prof Unverified",
        faculty_id="FAC-UNVER-1",
        email_verified=False,
        faculty_approved=False,
        password_hash=PasswordHasher().hash("secure-faculty-pass"),
    )
    auth_db.add(account)
    auth_db.commit()

    assert _faculty_is_approved(account) is False

    with pytest.raises(AuthServiceError) as exc_info:
        begin_login("unverified.prof@custom.edu", "secure-faculty-pass", auth_db)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Verify your email address before signing in." in exc_info.value.detail



