import json
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError

import pytest

from app.core import config
from app.services import email_service, groq_service


def _set_smtp_settings(monkeypatch):
    monkeypatch.setattr(config.settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(config.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(config.settings, "SMTP_USERNAME", "faculty@example.com")
    monkeypatch.setattr(config.settings, "SMTP_PASSWORD", "test-app-password")
    monkeypatch.setattr(config.settings, "SMTP_FROM_EMAIL", "faculty@example.com")


def test_otp_email_uses_starttls_and_never_logs_otp(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, context):
            calls.append(("starttls", context))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message))

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    email_service.send_otp_email("student@example.com", "004281")

    assert calls[0][1:3] == ("smtp.gmail.com", 587)
    assert [call[0] for call in calls].count("starttls") == 1
    sent_message = next(call[1] for call in calls if call[0] == "send")
    assert isinstance(sent_message, EmailMessage)
    assert sent_message["To"] == "student@example.com"
    assert "004281" in sent_message.get_content()
    assert "004281" not in caplog.text


def test_otp_email_wraps_smtp_errors_without_exposing_credentials(monkeypatch):
    _set_smtp_settings(monkeypatch)

    class FailingSMTP:
        def __init__(self, *_args, **_kwargs):
            raise smtplib.SMTPAuthenticationError(535, b"rejected")

    monkeypatch.setattr(email_service.smtplib, "SMTP", FailingSMTP)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "4821")

    assert "test-app-password" not in str(exc_info.value)
    assert "4821" not in str(exc_info.value)


def test_groq_returns_validated_structured_summary(monkeypatch):
    api_key = "test-groq-key"
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", api_key)
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "test-model")
    summary = {
        "summary": "A project monitoring platform.",
        "key_points": ["Tracks milestones"],
        "risks": [],
        "recommended_next_steps": ["Review submissions"],
    }
    body = json.dumps({
        "choices": [{
            "message": {"content": json.dumps(summary)},
        }],
    }).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            assert limit == groq_service.MAX_RESPONSE_BYTES + 1
            return body

    def fake_urlopen(request, timeout):
        assert request.full_url == groq_service.GROQ_API_URL
        assert request.get_header("Authorization") == f"Bearer {api_key}"
        assert timeout == groq_service.REQUEST_TIMEOUT_SECONDS
        payload = json.loads(request.data)
        assert payload["model"] == "test-model"
        assert payload["response_format"] == {"type": "json_object"}
        return FakeResponse()

    monkeypatch.setattr(groq_service, "urlopen", fake_urlopen)

    result = groq_service.summarize_project({
        "title": "Project monitor",
        "status": "ACTIVE",
    })

    assert result == summary


def test_groq_rejects_oversized_input_before_request(monkeypatch):
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "test-model")
    monkeypatch.setattr(
        groq_service,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("Network request must not be made"),
    )

    with pytest.raises(ValueError, match="must not exceed"):
        groq_service.summarize_project({
            "description": "x" * groq_service.MAX_PROJECT_INFO_CHARACTERS,
        })


def test_groq_http_error_does_not_expose_api_key(monkeypatch):
    api_key = "private-test-key"
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", api_key)
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "test-model")

    def fail_request(*_args, **_kwargs):
        raise HTTPError(
            groq_service.GROQ_API_URL,
            401,
            "Unauthorized",
            None,
            None,
        )

    monkeypatch.setattr(groq_service, "urlopen", fail_request)

    with pytest.raises(groq_service.GroqServiceError) as exc_info:
        groq_service.summarize_project({"title": "Project"})

    assert "401" in str(exc_info.value)
    assert api_key not in str(exc_info.value)
