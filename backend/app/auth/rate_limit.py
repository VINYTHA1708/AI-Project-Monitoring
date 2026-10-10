import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.service import AuthServiceError, _require_secret
from app.core.config import settings
from app.db.models import AuthRateLimitBucket


def _policy(action: str) -> tuple[int, int, int]:
    policies = {
        "login": (
            settings.AUTH_RATE_LIMIT_AUTH_WINDOW_SECONDS,
            settings.AUTH_RATE_LIMIT_LOGIN_EMAIL_MAX,
            settings.AUTH_RATE_LIMIT_LOGIN_IP_MAX,
        ),
        "registration": (
            settings.AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS,
            settings.AUTH_RATE_LIMIT_REGISTRATION_EMAIL_MAX,
            settings.AUTH_RATE_LIMIT_REGISTRATION_IP_MAX,
        ),
        "verify": (
            settings.AUTH_RATE_LIMIT_AUTH_WINDOW_SECONDS,
            settings.AUTH_RATE_LIMIT_VERIFY_EMAIL_MAX,
            settings.AUTH_RATE_LIMIT_VERIFY_IP_MAX,
        ),
        "resend": (
            settings.AUTH_RATE_LIMIT_RESEND_WINDOW_SECONDS,
            settings.AUTH_RATE_LIMIT_RESEND_EMAIL_MAX,
            settings.AUTH_RATE_LIMIT_RESEND_IP_MAX,
        ),
    }
    try:
        return policies[action]
    except KeyError as exc:
        raise ValueError("Unknown authentication rate-limit action.") from exc


def _subject_digest(scope: str, subject: str, secret: bytes) -> str:
    value = subject.strip().lower() if scope == "email" else subject.strip()
    message = f"auth-rate-limit:{scope}:{value}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def enforce_auth_rate_limit(
    action: str,
    email: str,
    client_ip: str | None,
    db: Session,
) -> None:
    window_seconds, email_limit, ip_limit = _policy(action)
    secret = _require_secret("OTP_HMAC_SECRET", settings.OTP_HMAC_SECRET)
    now = datetime.now(timezone.utc)
    window_epoch = int(now.timestamp()) // window_seconds * window_seconds
    window_started_at = datetime.fromtimestamp(window_epoch, timezone.utc)
    expires_at = window_started_at + timedelta(seconds=window_seconds)
    subjects = (
        ("email", email, email_limit),
        ("ip", client_ip or "unknown-client", ip_limit),
    )
    exceeded = False

    try:
        with db.begin():
            db.execute(
                delete(AuthRateLimitBucket).where(
                    AuthRateLimitBucket.expires_at <= now
                )
            )
            for scope, subject, limit in subjects:
                values = {
                    "action": action,
                    "scope": scope,
                    "subject_digest": _subject_digest(scope, subject, secret),
                    "window_started_at": window_started_at,
                    "expires_at": expires_at,
                    "hit_count": 1,
                }
                dialect_name = db.get_bind().dialect.name
                if dialect_name == "postgresql":
                    insert = postgres_insert(AuthRateLimitBucket).values(**values)
                elif dialect_name == "sqlite":
                    insert = sqlite_insert(AuthRateLimitBucket).values(**values)
                else:
                    raise AuthServiceError(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Shared authentication rate limiting is unavailable.",
                    )

                statement = (
                    insert.on_conflict_do_update(
                        index_elements=[
                            AuthRateLimitBucket.action,
                            AuthRateLimitBucket.scope,
                            AuthRateLimitBucket.subject_digest,
                            AuthRateLimitBucket.window_started_at,
                        ],
                        set_={
                            "hit_count": AuthRateLimitBucket.hit_count + 1,
                        },
                    )
                    .returning(AuthRateLimitBucket.hit_count)
                )
                hit_count = db.execute(statement).scalar_one()
                exceeded = exceeded or hit_count > limit
    except AuthServiceError:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise AuthServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authentication rate limiting is temporarily unavailable.",
        ) from None

    if exceeded:
        raise AuthServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many authentication requests. Try again later.",
        )
