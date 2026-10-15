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


def test_otp_email_wraps_smtp_errors_without_exposing_credentials(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)

    class FailingSMTP:
        def __init__(self, *_args, **_kwargs):
            raise smtplib.SMTPAuthenticationError(535, b"rejected")

    monkeypatch.setattr(email_service.smtplib, "SMTP", FailingSMTP)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "4821")

    assert "test-app-password" not in str(exc_info.value)
    assert "4821" not in str(exc_info.value)
    assert "test-app-password" not in caplog.text
    assert "4821" not in caplog.text


def test_otp_email_missing_smtp_configuration(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SMTP_PASSWORD", None)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "998877")

    assert "SMTP_PASSWORD" in str(exc_info.value)
    assert "998877" not in str(exc_info.value)
    assert "998877" not in caplog.text
    assert "Missing settings: SMTP_PASSWORD" in caplog.text


def test_otp_email_connection_timeout(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)

    class TimeoutSMTP:
        def __init__(self, *_args, **_kwargs):
            raise TimeoutError("connection timed out")

    monkeypatch.setattr(email_service.smtplib, "SMTP", TimeoutSMTP)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "123456")

    assert "timed out" in str(exc_info.value).lower()
    assert "test-app-password" not in str(exc_info.value)
    assert "123456" not in str(exc_info.value)
    assert "123456" not in caplog.text
    assert "test-app-password" not in caplog.text


def test_otp_email_recipient_refused(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)

    class RefusedSMTP:
        def __init__(self, *_args, **_kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def ehlo(self):
            pass
        def starttls(self, context):
            pass
        def login(self, username, password):
            pass
        def send_message(self, message):
            raise smtplib.SMTPRecipientsRefused({"student@example.com": (550, b"User unknown")})

    monkeypatch.setattr(email_service.smtplib, "SMTP", RefusedSMTP)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "654321")

    assert "rejected" in str(exc_info.value).lower()
    assert "654321" not in str(exc_info.value)
    assert "654321" not in caplog.text


def test_otp_email_server_disconnected(monkeypatch, caplog):
    _set_smtp_settings(monkeypatch)

    class DisconnectedSMTP:
        def __init__(self, *_args, **_kwargs):
            raise smtplib.SMTPServerDisconnected("unexpected disconnect")

    monkeypatch.setattr(email_service.smtplib, "SMTP", DisconnectedSMTP)

    with pytest.raises(email_service.EmailServiceError) as exc_info:
        email_service.send_otp_email("student@example.com", "112233")

    assert "disconnected" in str(exc_info.value).lower()
    assert "112233" not in str(exc_info.value)
    assert "112233" not in caplog.text


def test_otp_email_supports_ssl_port_465(monkeypatch):
    _set_smtp_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SMTP_PORT", 465)
    calls = []

    class FakeSSLSMTP:
        def __init__(self, host, port, context, timeout):
            calls.append(("connect_ssl", host, port, timeout))
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def ehlo(self):
            calls.append(("ehlo",))
        def login(self, username, password):
            calls.append(("login", username, password))
        def send_message(self, message):
            calls.append(("send", message))

    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSSLSMTP)
    email_service.send_otp_email("student@example.com", "778899")

    assert calls[0][1:3] == ("smtp.gmail.com", 465)
    assert any(c[0] == "connect_ssl" for c in calls)
    sent_message = next(c[1] for c in calls if c[0] == "send")
    assert "778899" in sent_message.get_content()


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
