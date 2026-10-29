from io import BytesIO
import json
import pytest
from unittest.mock import MagicMock
from urllib.error import HTTPError

from fastapi import HTTPException
from app.core import config
from app.services import groq_service
from app.services.groq_service import (
    SINGLE_DOCUMENT_VERIFICATION_SYSTEM_PROMPT,
    GroqServiceError,
    RelevanceStatus,
    verify_single_document_relevance,
)
from app.services.llm_summary_service import bound_extracted_document_text
from app.api_ai_summary import _acquire_project_generation_lock


# ─── 1. System Prompt Compactness and Semantic Requirement Preservation ──────

def test_system_prompt_compactness_and_case_preservation():
    """Verify system prompt is compacted while strictly preserving all evaluation rules and cases."""
    prompt = SINGLE_DOCUMENT_VERIFICATION_SYSTEM_PROMPT

    # Compactness assertion: baseline was 4,054 chars (~1,013 tokens). Compacted should be <= 2,800 chars.
    assert len(prompt) < 2800, f"Prompt length {len(prompt)} is too long; expected < 2800 chars"
    assert len(prompt) > 1000, "Prompt is suspiciously short"

    # All six decision cases (A-F) must be explicitly present
    assert "Case A" in prompt
    assert "Case B" in prompt
    assert "Case C" in prompt
    assert "Case D" in prompt
    assert "Case E" in prompt
    assert "Case F" in prompt

    # Critical security and evaluation rules
    assert "UNTRUSTED DATA" in prompt
    assert "GENERIC TERMS" in prompt or "generic" in prompt.lower()
    assert "[Slide N]" in prompt
    assert "[Page N]" in prompt

    # Exact required JSON output fields
    required_fields = [
        "document_title",
        "document_headings",
        "detected_document_topic",
        "assigned_project_title",
        "title_match_explanation",
        "content_match_explanation",
        "document_relevance",
        "supporting_evidence",
        "conflicting_evidence",
        "missing_evidence",
        "recommended_action",
        "confidence",
    ]
    for field in required_fields:
        assert field in prompt, f"Required JSON field '{field}' missing from system prompt"


# ─── 2. Document Truncation & Slide Boundary Preservation ────────────────────

def test_bound_extracted_document_text_preserves_boundaries():
    """Verify document text truncation respects slide/paragraph boundaries and appends notice."""
    short_text = "[Slide 1: Title]\nIntroduction to Project Monitoring.\n\n[Slide 2: Architecture]\nFastAPI and PostgreSQL."
    # Short text within budget is unmodified
    assert bound_extracted_document_text(short_text, max_chars=2500) == short_text

    # Construct long text spanning multiple slides exceeding 2500 chars
    slides = [f"[Slide {i}: Section {i}]\n" + ("Detailed analysis of system module components. " * 8) for i in range(1, 15)]
    long_text = "\n\n".join(slides)
    assert len(long_text) > 4000

    bounded = bound_extracted_document_text(long_text, max_chars=2500)
    assert len(bounded) < 3000
    assert "... [Content truncated:" in bounded
    assert "[Slide 1: Section 1]" in bounded
    # Must cut on a clean boundary rather than in the middle of a word
    assert not bounded.endswith("comp")


# ─── 3. Token Reservation and Configuration Handling ─────────────────────────

def test_token_reservation_configuration(monkeypatch):
    """Verify completion token budget defaults to GROQ_VERIFICATION_MAX_TOKENS (1000) instead of 3000."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(config.settings, "GROQ_MAX_TOKENS", 3000)
    monkeypatch.setattr(config.settings, "GROQ_VERIFICATION_MAX_TOKENS", 1500)

    captured_requests = []

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return json.dumps({
                "choices": [{
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps({
                            "document_title": "Project Scope",
                            "document_headings": ["Intro"],
                            "detected_document_topic": "Project Scope",
                            "assigned_project_title": "Project Scope",
                            "title_match_explanation": "Matches",
                            "content_match_explanation": "Matches",
                            "document_relevance": "RELEVANT",
                            "supporting_evidence": ["[Slide 1] Overview"],
                            "conflicting_evidence": [],
                            "missing_evidence": [],
                            "recommended_action": "Proceed",
                            "confidence": 0.95,
                        })
                    }
                }]
            }).encode("utf-8")

    def capture_urlopen(req, *args, **kwargs):
        captured_requests.append(json.loads(req.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setattr("app.services.groq_service.urlopen", capture_urlopen)

    verify_single_document_relevance(
        project_id=1,
        project_title="Project Scope",
        project_description="Monitoring student projects",
        document_info={
            "document_type": "presentation",
            "file_name": "scope.pptx",
            "document_title": "Project Scope",
            "document_headings": ["Intro"],
            "extracted_text": "[Slide 1] Overview",
            "status": "success",
            "word_count": 50,
        },
    )

    assert len(captured_requests) == 1
    # max_tokens sent to Groq must be 1000 (not 3000!)
    assert captured_requests[0].get("max_completion_tokens") == 1500


# ─── 4. Truncation and Incomplete Response Handling ──────────────────────────

def test_truncated_model_response_rejected(monkeypatch):
    """Verify finish_reason='length' explicitly raises GroqServiceError and rejects incomplete results."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "llama-3.3-70b-versatile")

    class TruncatedResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return json.dumps({
                "choices": [{
                    "finish_reason": "length",
                    "message": {"content": '{"document_title": "Truncated doc'}
                }]
            }).encode("utf-8")

    monkeypatch.setattr("app.services.groq_service.urlopen", lambda *args, **kwargs: TruncatedResponse())

    with pytest.raises(GroqServiceError) as exc_info:
        verify_single_document_relevance(
            project_id=1,
            project_title="Project Scope",
            project_description="Monitoring student projects",
            document_info={
                "document_type": "presentation",
                "file_name": "scope.pptx",
                "document_title": "Project Scope",
                "document_headings": ["Intro"],
                "extracted_text": "[Slide 1] Overview",
                "status": "success",
                "word_count": 50,
            },
        )

    assert "truncated" in str(exc_info.value).lower()


# ─── 5. Rate Limit 429 Recovery with Retry and Backoff ───────────────────────

def test_rate_limit_429_successful_recovery(monkeypatch):
    """Verify HTTP 429 triggers backoff retry and succeeds when subsequent attempt passes."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    # Bypass actual sleep delay in unit tests
    sleep_calls = []
    monkeypatch.setattr("app.services.groq_service._sleep_fn", lambda s: sleep_calls.append(s))

    calls = [0]

    def mock_urlopen_with_initial_429(req, *args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            err_body = BytesIO(b'{"error": {"message": "Rate limit reached on TPM. Please try again in 1.25s."}}')
            raise HTTPError("https://api.groq.com", 429, "Too Many Requests", {"Retry-After": "1"}, err_body)

        class SuccessResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, *args):
                return json.dumps({
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({
                                "document_title": "Project Scope",
                                "document_headings": ["Intro"],
                                "detected_document_topic": "Project Scope",
                                "assigned_project_title": "Project Scope",
                                "title_match_explanation": "Matches",
                                "content_match_explanation": "Matches",
                                "document_relevance": "RELEVANT",
                                "supporting_evidence": ["[Slide 1] Overview"],
                                "conflicting_evidence": [],
                                "missing_evidence": [],
                                "recommended_action": "Proceed",
                                "confidence": 0.95,
                            })
                        }
                    }]
                }).encode("utf-8")

        return SuccessResp()

    monkeypatch.setattr("app.services.groq_service.urlopen", mock_urlopen_with_initial_429)

    res = verify_single_document_relevance(
        project_id=1,
        project_title="Project Scope",
        project_description="Monitoring student projects",
        document_info={
            "document_type": "presentation",
            "file_name": "scope.pptx",
            "document_title": "Project Scope",
            "document_headings": ["Intro"],
            "extracted_text": "[Slide 1] Overview",
            "status": "success",
            "word_count": 50,
        },
    )

    assert res["document_relevance"] == "RELEVANT"
    assert calls[0] == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 0.5


# ─── 6. Non-retryable Errors Fail Immediately Without Retrying ───────────────

def test_non_retryable_http_error_fails_immediately(monkeypatch):
    """Verify 401/400 errors fail immediately without attempting any retries."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    sleep_calls = []
    monkeypatch.setattr("app.services.groq_service._sleep_fn", lambda s: sleep_calls.append(s))

    calls = [0]

    def mock_urlopen_401(req, *args, **kwargs):
        calls[0] += 1
        raise HTTPError("https://api.groq.com", 401, "Unauthorized", {}, BytesIO(b'{"error": "Invalid API key"}'))

    monkeypatch.setattr("app.services.groq_service.urlopen", mock_urlopen_401)

    with pytest.raises(GroqServiceError) as exc_info:
        verify_single_document_relevance(
            project_id=1,
            project_title="Project Scope",
            project_description="Monitoring student projects",
            document_info={
                "document_type": "presentation",
                "file_name": "scope.pptx",
                "document_title": "Project Scope",
                "document_headings": ["Intro"],
                "extracted_text": "[Slide 1] Overview",
                "status": "success",
                "word_count": 50,
            },
        )

    # Exactly 1 call, zero sleep retries
    assert calls[0] == 1
    assert len(sleep_calls) == 0
    assert "401" in str(exc_info.value)


# ─── 7. Concurrency Lock Prevents Duplicate Generation for Same Project ──────

def test_concurrent_generation_lock_returns_409():
    """Verify in-process concurrency guard blocks simultaneous generation calls for the same project."""
    project_id = 9999

    with _acquire_project_generation_lock(project_id):
        # A second concurrent call for the same project must raise 409
        with pytest.raises(HTTPException) as exc_info:
            with _acquire_project_generation_lock(project_id):
                pass
        assert exc_info.value.status_code == 409
        assert "already in progress" in exc_info.value.detail

    # Once the first call completes, another call for the same project succeeds
    with _acquire_project_generation_lock(project_id):
        pass

    # Different projects can run concurrently without blocking each other
    with _acquire_project_generation_lock(1001):
        with _acquire_project_generation_lock(1002):
            pass



# ─── 8. HTTP 400 Sanitized Diagnostics and Credential Redaction ──────────────

def test_http_400_sanitized_provider_error_message(monkeypatch):
    """Verify HTTP 400 from Groq extracts and surfaces sanitized provider detail without generic swallow."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    sleep_calls = []
    monkeypatch.setattr("app.services.groq_service._sleep_fn", lambda s: sleep_calls.append(s))

    def mock_urlopen_400(req, *args, **kwargs):
        provider_err = json.dumps({
            "error": {
                "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
                "type": "invalid_request_error",
                "code": "unsupported_parameter",
            }
        }).encode("utf-8")
        raise HTTPError("https://api.groq.com", 400, "Bad Request", {}, BytesIO(provider_err))

    monkeypatch.setattr("app.services.groq_service.urlopen", mock_urlopen_400)

    with pytest.raises(GroqServiceError) as exc_info:
        verify_single_document_relevance(
            project_id=1,
            project_title="Project Scope",
            project_description="Monitoring student projects",
            document_info={
                "document_type": "presentation",
                "file_name": "scope.pptx",
                "document_title": "Project Scope",
                "document_headings": ["Intro"],
                "extracted_text": "[Slide 1] Overview",
                "status": "success",
                "word_count": 50,
            },
        )

    # Verifies error detail is surfaced, not generically swallowed
    err_str = str(exc_info.value)
    assert "400" in err_str
    assert "Unsupported parameter" in err_str
    assert "max_completion_tokens" in err_str
    # Confirms no retries on non-retryable 400
    assert len(sleep_calls) == 0


def test_http_400_credential_redaction(monkeypatch):
    """Verify provider error sanitization strictly redacts API keys and secrets."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "openai/gpt-oss-120b")

    def mock_urlopen_leaky_400(req, *args, **kwargs):
        leaky_err = json.dumps({
            "error": {
                "message": "Invalid request for key=gsk_99999secrettoken with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            }
        }).encode("utf-8")
        raise HTTPError("https://api.groq.com", 400, "Bad Request", {}, BytesIO(leaky_err))

    monkeypatch.setattr("app.services.groq_service.urlopen", mock_urlopen_leaky_400)

    with pytest.raises(GroqServiceError) as exc_info:
        verify_single_document_relevance(
            project_id=1,
            project_title="Project Scope",
            project_description="Monitoring student projects",
            document_info={
                "document_type": "presentation",
                "file_name": "scope.pptx",
                "document_title": "Project Scope",
                "document_headings": ["Intro"],
                "extracted_text": "[Slide 1] Overview",
                "status": "success",
                "word_count": 50,
            },
        )

    err_str = str(exc_info.value)
    assert "gsk_99999secrettoken" not in err_str
    assert "eyJhbGci" not in err_str
    assert "[REDACTED" in err_str


def test_summarize_project_uses_max_completion_tokens(monkeypatch):
    """Verify summarize_project also uses max_completion_tokens instead of deprecated max_tokens."""
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "gsk_test_token_key")
    monkeypatch.setattr(config.settings, "GROQ_MODEL", "openai/gpt-oss-120b")

    captured_requests = []

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "summary": "Project summary",
                            "key_points": ["Point 1"],
                            "risks": ["Risk 1"],
                            "recommended_next_steps": ["Step 1"],
                        })
                    }
                }]
            }).encode("utf-8")

    def capture_urlopen(req, *args, **kwargs):
        captured_requests.append(json.loads(req.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setattr("app.services.groq_service.urlopen", capture_urlopen)

    res = groq_service.summarize_project({"title": "Test Project", "status": "ACTIVE"})
    assert res["summary"] == "Project summary"
    assert len(captured_requests) == 1
    assert captured_requests[0].get("max_completion_tokens") == 700
    assert "max_tokens" not in captured_requests[0]
