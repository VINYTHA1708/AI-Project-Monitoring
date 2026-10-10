import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import status
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuthAccount, AuthOTPChallenge, Student
from app.services.email_service import EmailServiceError, send_otp_email

password_hasher = PasswordHasher()
OTP_WINDOW = timedelta(hours=1)
PLACEHOLDER_PREFIXES = ("your-", "change-me", "changeme", "replace-with-")


class AuthServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _require_secret(name: str, value: str | None) -> bytes:
    if (
        not value
        or len(value.encode("utf-8")) < 32
        or value.strip().lower().startswith(PLACEHOLDER_PREFIXES)
    ):
        raise AuthServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{name} is not configured for authentication.",
        )
    return value.encode("utf-8")


def _faculty_is_approved(account: AuthAccount) -> bool:
    return (
        account.role == "faculty"
        and account.faculty_approved
        and account.email in settings.faculty_email_allowlist
    )


def _email_in_student_domain(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1]
    return bool(settings.student_email_domains) and domain in settings.student_email_domains


def _new_challenge(
    db: Session,
    account: AuthAccount,
    purpose: str,
) -> tuple[AuthOTPChallenge, str]:
    now = datetime.now(timezone.utc)
    _require_secret("OTP_HMAC_SECRET", settings.OTP_HMAC_SECRET)
    cutoff = now - OTP_WINDOW

    latest = db.scalar(
        select(AuthOTPChallenge)
        .where(
            AuthOTPChallenge.account_id == account.id,
            AuthOTPChallenge.purpose == purpose,
            AuthOTPChallenge.delivery_status.in_(("pending", "delivered")),
            AuthOTPChallenge.consumed_at.is_(None),
        )
        .order_by(AuthOTPChallenge.created_at.desc())
        .limit(1)
    )
    if latest and _utc(latest.created_at) > now - timedelta(
        seconds=settings.AUTH_OTP_RESEND_COOLDOWN_SECONDS
    ):
        raise AuthServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Please wait before requesting another verification code.",
        )

    recent = db.execute(
        select(
            func.count(AuthOTPChallenge.id),
            func.coalesce(func.sum(AuthOTPChallenge.attempt_count), 0),
        ).where(
            AuthOTPChallenge.account_id == account.id,
            AuthOTPChallenge.purpose == purpose,
            AuthOTPChallenge.created_at >= cutoff,
        )
    ).one()
    if recent[0] >= settings.AUTH_OTP_MAX_SENDS_PER_HOUR:
        raise AuthServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "The verification-code request limit has been reached. Try again later.",
        )
    if recent[1] >= settings.AUTH_OTP_MAX_ATTEMPTS:
        raise AuthServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many incorrect verification attempts. Try again later.",
        )

    db.execute(
        text(
            "UPDATE auth_otp_challenges "
            "SET delivery_status = 'superseded', consumed_at = :now "
            "WHERE account_id = :account_id AND purpose = :purpose "
            "AND delivery_status IN ('pending', 'delivered') "
            "AND consumed_at IS NULL"
        ),
        {"now": now, "account_id": account.id, "purpose": purpose},
    )

    challenge_id = uuid4()
    code = f"{secrets.randbelow(1_000_000):06d}"
    message = f"{account.id}:{purpose}:{challenge_id}:{code}".encode("utf-8")
    digest = hmac.new(
        _require_secret("OTP_HMAC_SECRET", settings.OTP_HMAC_SECRET),
        message,
        hashlib.sha256,
    ).hexdigest()
    challenge = AuthOTPChallenge(
        id=challenge_id,
        account_id=account.id,
        purpose=purpose,
        code_digest=digest,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.AUTH_OTP_LIFETIME_SECONDS),
        attempt_count=0,
        delivery_status="pending",
    )
    db.add(challenge)
    db.flush()
    return challenge, code


def _finalize_challenge_delivery(
    challenge_id,
    db: Session,
    *,
    delivered: bool,
) -> None:
    now = datetime.now(timezone.utc)
    with db.begin():
        challenge = db.scalar(
            select(AuthOTPChallenge)
            .where(
                AuthOTPChallenge.id == challenge_id,
                AuthOTPChallenge.delivery_status == "pending",
                AuthOTPChallenge.consumed_at.is_(None),
            )
            .with_for_update()
        )
        if challenge is None:
            return
        if delivered:
            challenge.delivery_status = "delivered"
            challenge.delivered_at = now
        else:
            challenge.delivery_status = "failed"
            challenge.consumed_at = now


def _send_challenge(email: str, purpose: str, db: Session) -> None:
    if db.in_transaction():
        db.rollback()
    with db.begin():
        account = db.scalar(
            select(AuthAccount)
            .where(AuthAccount.email == email)
            .with_for_update()
        )
        if account is None:
            raise AuthServiceError(status.HTTP_404_NOT_FOUND, "Account not found.")
        if purpose == "registration" and account.email_verified:
            raise AuthServiceError(
                status.HTTP_400_BAD_REQUEST,
                "This email address is already verified.",
            )
        if purpose == "login" and not account.email_verified:
            raise AuthServiceError(
                status.HTTP_403_FORBIDDEN,
                "Verify your email address before signing in.",
            )
        if purpose == "login" and account.role == "faculty" and not _faculty_is_approved(account):
            raise AuthServiceError(
                status.HTTP_403_FORBIDDEN,
                "Faculty access is pending approval.",
            )
        challenge, code = _new_challenge(db, account, purpose)
        challenge_id = challenge.id
        destination = account.email

    try:
        send_otp_email(destination, code)
    except (EmailServiceError, OSError) as exc:
        _finalize_challenge_delivery(challenge_id, db, delivered=False)
        raise AuthServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Unable to send the verification email. Please try again later.",
        ) from exc
    _finalize_challenge_delivery(challenge_id, db, delivered=True)


def register_student(data, db: Session) -> None:
    email = normalize_email(str(data.email))
    registration_number = data.registration_number.strip()
    normalized_registration = registration_number.casefold()
    if not _email_in_student_domain(email):
        raise AuthServiceError(
            status.HTTP_400_BAD_REQUEST,
            "Use an email address from an approved student domain.",
        )

    password_hash = password_hasher.hash(data.password)
    try:
        with db.begin():
            if db.bind and db.bind.dialect.name == "postgresql":
                for key in sorted(
                    {
                        f"student-register-email:{email}",
                        f"student-register-number:{normalized_registration}",
                    }
                ):
                    db.execute(
                        text(
                            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
                        ),
                        {"key": key},
                    )
            matches = db.scalars(
                select(Student).where(
                    or_(
                        func.lower(func.trim(Student.email)) == email,
                        func.lower(func.trim(Student.registration_number))
                        == normalized_registration,
                    )
                )
            ).all()
            if len(matches) > 1 or (
                matches
                and (
                    normalize_email(matches[0].email) != email
                    or matches[0].registration_number.strip().casefold()
                    != normalized_registration
                )
            ):
                raise AuthServiceError(
                    status.HTTP_409_CONFLICT,
                    "The email or registration number conflicts with an existing student record.",
                )
            if matches:
                student = matches[0]
                if student.auth_account is not None:
                    raise AuthServiceError(
                        status.HTTP_409_CONFLICT,
                        "An account already exists for this student.",
                    )
            else:
                student = Student(
                    name=data.name.strip(),
                    email=email,
                    registration_number=registration_number,
                )
                db.add(student)
                db.flush()
            account = AuthAccount(
                role="student",
                email=email,
                password_hash=password_hash,
                student_id=student.id,
                phone=data.phone.strip(),
                department=data.department.strip(),
            )
            db.add(account)
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AuthServiceError(
            status.HTTP_409_CONFLICT,
            "An account already exists for this email or student record.",
        ) from exc

    _send_challenge(email, "registration", db)


def register_faculty(data, db: Session) -> None:
    email = normalize_email(str(data.email))
    account = AuthAccount(
        role="faculty",
        email=email,
        password_hash=password_hasher.hash(data.password),
        faculty_id=data.faculty_id.strip(),
        faculty_name=data.name.strip(),
        department=data.department.strip() if data.department else None,
        faculty_approved=False,
    )
    try:
        with db.begin():
            db.add(account)
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AuthServiceError(
            status.HTTP_409_CONFLICT,
            "An account already exists for this email or faculty ID.",
        ) from exc
    _send_challenge(email, "registration", db)


def resend_otp(email: str, purpose: str, db: Session) -> None:
    normalized_email = normalize_email(email)
    account_exists = db.scalar(
        select(AuthAccount.id).where(AuthAccount.email == normalized_email)
    )
    if db.in_transaction():
        db.rollback()
    if account_exists is None:
        return
    try:
        _send_challenge(normalized_email, purpose, db)
    except AuthServiceError as exc:
        if exc.status_code in {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        }:
            return
        raise


def begin_login(email: str, password: str, db: Session) -> None:
    _require_secret("JWT_SECRET_KEY", settings.JWT_SECRET_KEY)
    normalized_email = normalize_email(email)
    if db.in_transaction():
        db.rollback()
    error: AuthServiceError | None = None
    permitted = False
    now = datetime.now(timezone.utc)
    with db.begin():
        account = db.scalar(
            select(AuthAccount)
            .where(AuthAccount.email == normalized_email)
            .with_for_update()
        )
        if account is None:
            error = AuthServiceError(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid email or password.",
            )
        elif account.locked_until and _utc(account.locked_until) > now:
            error = AuthServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many sign-in attempts. Try again later.",
            )
        else:
            if account.locked_until:
                account.failed_login_count = 0
                account.locked_until = None
            try:
                password_hasher.verify(account.password_hash, password)
                valid_password = True
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                valid_password = False
            if not valid_password:
                account.failed_login_count += 1
                if account.failed_login_count >= settings.AUTH_LOGIN_MAX_ATTEMPTS:
                    account.locked_until = now + timedelta(
                        seconds=settings.AUTH_LOGIN_LOCKOUT_SECONDS
                    )
                error = AuthServiceError(
                    status.HTTP_401_UNAUTHORIZED,
                    "Invalid email or password.",
                )
            else:
                account.failed_login_count = 0
                account.locked_until = None
                if not account.email_verified:
                    error = AuthServiceError(
                        status.HTTP_403_FORBIDDEN,
                        "Verify your email address before signing in.",
                    )
                elif account.role == "faculty" and not _faculty_is_approved(account):
                    error = AuthServiceError(
                        status.HTTP_403_FORBIDDEN,
                        "Faculty access is pending approval.",
                    )
                else:
                    permitted = True
    if error:
        raise error
    if not permitted:
        raise AuthServiceError(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password.",
        )
    _send_challenge(normalized_email, "login", db)


def verify_otp(email: str, code: str, purpose: str, db: Session) -> dict:
    if db.in_transaction():
        db.rollback()
    normalized_email = normalize_email(email)
    error: AuthServiceError | None = None
    verified_account: AuthAccount | None = None
    now = datetime.now(timezone.utc)
    with db.begin():
        account = db.scalar(
            select(AuthAccount)
            .where(AuthAccount.email == normalized_email)
            .with_for_update()
        )
        if account is None:
            error = AuthServiceError(
                status.HTTP_400_BAD_REQUEST,
                "Invalid or expired verification code.",
            )
        else:
            challenge = db.scalar(
                select(AuthOTPChallenge)
                .where(
                    AuthOTPChallenge.account_id == account.id,
                    AuthOTPChallenge.purpose == purpose,
                    AuthOTPChallenge.delivery_status == "delivered",
                    AuthOTPChallenge.consumed_at.is_(None),
                )
                .order_by(AuthOTPChallenge.created_at.desc())
                .with_for_update()
                .limit(1)
            )
            if challenge is None:
                error = AuthServiceError(
                    status.HTTP_400_BAD_REQUEST,
                    "Invalid or expired verification code.",
                )
            elif _utc(challenge.expires_at) <= now:
                challenge.consumed_at = now
                error = AuthServiceError(
                    status.HTTP_400_BAD_REQUEST,
                    "Invalid or expired verification code.",
                )
            elif challenge.attempt_count >= settings.AUTH_OTP_MAX_ATTEMPTS:
                challenge.consumed_at = now
                error = AuthServiceError(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many incorrect verification attempts. Request a new code later.",
                )
            else:
                message = (
                    f"{account.id}:{purpose}:{challenge.id}:{code}"
                ).encode("utf-8")
                expected_digest = hmac.new(
                    _require_secret("OTP_HMAC_SECRET", settings.OTP_HMAC_SECRET),
                    message,
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(expected_digest, challenge.code_digest):
                    challenge.attempt_count += 1
                    if challenge.attempt_count >= settings.AUTH_OTP_MAX_ATTEMPTS:
                        challenge.consumed_at = now
                    error = AuthServiceError(
                        status.HTTP_400_BAD_REQUEST,
                        "Invalid or expired verification code.",
                    )
                elif purpose == "registration":
                    if account.email_verified:
                        challenge.consumed_at = now
                        error = AuthServiceError(
                            status.HTTP_400_BAD_REQUEST,
                            "This email address is already verified.",
                        )
                    else:
                        account.email_verified = True
                        if account.role == "faculty":
                            account.faculty_approved = (
                                account.email in settings.faculty_email_allowlist
                            )
                        challenge.consumed_at = now
                        verified_account = account
                elif not account.email_verified:
                    challenge.consumed_at = now
                    error = AuthServiceError(
                        status.HTTP_403_FORBIDDEN,
                        "Verify your email address before signing in.",
                    )
                elif account.role == "faculty" and not _faculty_is_approved(account):
                    challenge.consumed_at = now
                    error = AuthServiceError(
                        status.HTTP_403_FORBIDDEN,
                        "Faculty access is pending approval.",
                    )
                else:
                    challenge.consumed_at = now
                    verified_account = account

    if error:
        raise error
    if purpose == "registration":
        pending = bool(
            verified_account
            and verified_account.role == "faculty"
            and not verified_account.faculty_approved
        )
        return {
            "message": (
                "Email verified. Faculty access is pending approval."
                if pending else "Email verified. Sign in to continue."
            ),
            "email_verified": True,
            "faculty_approval_pending": pending,
        }
    assert verified_account is not None
    token, lifetime = create_access_token(verified_account)
    return {
        "message": "Authentication successful.",
        "email_verified": True,
        "faculty_approval_pending": False,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": lifetime,
        "account": account_response(verified_account),
    }


def create_access_token(account: AuthAccount) -> tuple[str, int]:
    secret = _require_secret("JWT_SECRET_KEY", settings.JWT_SECRET_KEY)
    lifetime_seconds = settings.AUTH_TOKEN_LIFETIME_MINUTES * 60
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(account.id),
            "role": account.role,
            "iss": settings.AUTH_TOKEN_ISSUER,
            "aud": settings.AUTH_TOKEN_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=lifetime_seconds),
        },
        secret,
        algorithm="HS256",
    )
    return token, lifetime_seconds


def decode_access_token(token: str) -> dict:
    secret = _require_secret("JWT_SECRET_KEY", settings.JWT_SECRET_KEY)
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=settings.AUTH_TOKEN_ISSUER,
            audience=settings.AUTH_TOKEN_AUDIENCE,
            options={
                "require": ["sub", "role", "iss", "aud", "iat", "exp"],
                "verify_signature": True,
                "verify_exp": True,
            },
        )
    except jwt.PyJWTError as exc:
        raise AuthServiceError(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired authentication token.",
        ) from exc


def account_response(account: AuthAccount) -> dict:
    name = account.student.name if account.role == "student" and account.student else account.faculty_name
    return {
        "id": account.id,
        "role": account.role,
        "email": account.email,
        "name": name or "",
        "student_id": account.student_id,
        "faculty_id": account.faculty_id,
        "department": account.department,
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
