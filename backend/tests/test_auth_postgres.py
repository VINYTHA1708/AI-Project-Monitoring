import hashlib
import hmac
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.service import AuthServiceError, begin_login, verify_otp
from app.core.config import settings
from app.db.models import (
    AuthAccount,
    AuthOTPChallenge,
    FacultyProjectAssignment,
    Project,
    Student,
)


POSTGRES_TEST_URL = os.getenv("AUTH_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="Set AUTH_TEST_POSTGRES_URL to an isolated PostgreSQL test database.",
)


@pytest.fixture
def migrated_postgres_schema(monkeypatch):
    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("AUTH_TEST_POSTGRES_URL must use PostgreSQL.")
    database_name = (engine.url.database or "").lower()
    if "test" not in database_name:
        engine.dispose()
        pytest.fail(
            "Refusing PostgreSQL integration tests unless the database name contains 'test'."
        )

    schema = f"auth_it_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quoted_schema}")

    @event.listens_for(engine, "connect")
    def set_test_search_path(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET search_path TO {quoted_schema}")
        cursor.close()

    engine.dispose()

    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "0001_auth_foundation.sql"
    )
    migration_sql = migration_file.read_text(encoding="utf-8")
    migration_sql = migration_sql.removeprefix("BEGIN;").rsplit("COMMIT;", 1)[0]
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE students (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                registration_number VARCHAR(50) NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE projects (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                github_url VARCHAR(500),
                status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for statement in migration_sql.split(";"):
            if statement.strip():
                connection.execute(text(statement))

    monkeypatch.setattr(
        settings,
        "JWT_SECRET_KEY",
        secrets.token_urlsafe(48),
    )
    monkeypatch.setattr(
        settings,
        "OTP_HMAC_SECRET",
        secrets.token_urlsafe(48),
    )
    monkeypatch.setattr(settings, "FACULTY_EMAIL_ALLOWLIST", "faculty@test.edu")
    monkeypatch.setattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "AUTH_OTP_MAX_SENDS_PER_HOUR", 5)
    monkeypatch.setattr(settings, "AUTH_OTP_MAX_ATTEMPTS", 5)

    try:
        yield engine, sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        event.remove(engine, "connect", set_test_search_path)
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {quoted_schema} CASCADE")
        engine.dispose()


def _seed_account(session: Session) -> AuthAccount:
    student = Student(
        name="Integration Student",
        email="student@test.edu",
        registration_number=f"R-{uuid4().hex[:10]}",
    )
    project = Project(title="Integration project")
    session.add_all([student, project])
    session.flush()
    account = AuthAccount(
        role="faculty",
        email="faculty@test.edu",
        password_hash=PasswordHasher().hash("a-long-integration-password"),
        faculty_id=f"F-{uuid4().hex[:10]}",
        faculty_name="Integration Faculty",
        email_verified=True,
        faculty_approved=True,
    )
    session.add(account)
    session.flush()
    session.add(
        FacultyProjectAssignment(
            faculty_account_id=account.id,
            project_id=project.id,
        )
    )
    session.commit()
    return account


def test_postgres_constraints_and_transaction_rollback(migrated_postgres_schema):
    _engine, make_session = migrated_postgres_schema
    with make_session() as session:
        account = _seed_account(session)
        session.add(
            AuthAccount(
                role="faculty",
                email="other-faculty@test.edu",
                password_hash=PasswordHasher().hash("a-long-other-password"),
                faculty_id=account.faculty_id.lower(),
                faculty_name="Duplicate Faculty ID",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            AuthAccount(
                role="faculty",
                email=account.email.upper(),
                password_hash=PasswordHasher().hash("a-long-other-password"),
                faculty_id=f"F-{uuid4().hex[:10]}",
                faculty_name="Duplicate Email",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count(AuthAccount.id))) == 1

        now = datetime.now(timezone.utc)
        session.add(
            AuthOTPChallenge(
                id=uuid4(),
                account_id=account.id,
                purpose="login",
                code_digest="g" * 64,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        first = AuthOTPChallenge(
            id=uuid4(),
            account_id=account.id,
            purpose="login",
            code_digest="a" * 64,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        session.add(first)
        session.commit()
        session.add(
            AuthOTPChallenge(
                id=uuid4(),
                account_id=account.id,
                purpose="login",
                code_digest="b" * 64,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(
            select(func.count(AuthOTPChallenge.id)).where(
                AuthOTPChallenge.consumed_at.is_(None)
            )
        ) == 1

        from app.db.models import AuthRateLimitBucket

        session.add(
            AuthRateLimitBucket(
                action="login",
                scope="email",
                subject_digest="z" * 64,
                window_started_at=now,
                expires_at=now + timedelta(minutes=15),
                hit_count=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            AuthOTPChallenge(
                id=uuid4(),
                account_id=account.id,
                purpose="registration",
                code_digest="c" * 64,
                delivery_status="delivered",
                delivered_at=None,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_postgres_serializes_concurrent_otp_issue_and_verification(
    migrated_postgres_schema,
    monkeypatch,
):
    _engine, make_session = migrated_postgres_schema
    with make_session() as session:
        account = _seed_account(session)
        email = account.email
        account_id = account.id

    delivered_codes: list[str] = []
    delivered_lock = Lock()
    first_send_started = Event()
    second_send_finished = Event()

    def fake_send(_email, code):
        with delivered_lock:
            delivered_codes.append(code)
            send_number = len(delivered_codes)
        if send_number == 1:
            first_send_started.set()
            second_send_finished.wait(timeout=10)
        else:
            second_send_finished.set()

    monkeypatch.setattr("app.auth.service.send_otp_email", fake_send)

    def issue_code():
        with make_session() as session:
            begin_login(email, "a-long-integration-password", session)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _item: issue_code(), range(2)))
    assert first_send_started.is_set()
    assert second_send_finished.is_set()

    with make_session() as session:
        active = session.scalar(
            select(AuthOTPChallenge).where(
                AuthOTPChallenge.account_id == account_id,
                AuthOTPChallenge.purpose == "login",
                AuthOTPChallenge.consumed_at.is_(None),
            )
        )
        assert active is not None
        assert session.scalar(
            select(func.count(AuthOTPChallenge.id)).where(
                AuthOTPChallenge.account_id == account_id,
                AuthOTPChallenge.consumed_at.is_(None),
            )
        ) == 1
        candidates = list(delivered_codes)

    active_code = next(
        code
        for code in candidates
        if hmac.compare_digest(
            hmac.new(
                settings.OTP_HMAC_SECRET.encode("utf-8"),
                f"{account_id}:login:{active.id}:{code}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest(),
            active.code_digest,
        )
    )

    def verify_code():
        with make_session() as session:
            try:
                verify_otp(email, active_code, "login", session)
                return "accepted"
            except AuthServiceError:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _item: verify_code(), range(2)))
    assert outcomes.count("accepted") == 1
    assert outcomes.count("rejected") == 1
