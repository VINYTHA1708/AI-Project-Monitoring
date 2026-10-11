import json
import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api_reviews import (
    ReviewCreate,
    ReviewUpdate,
    create_review,
    list_submission_reviews,
    get_review,
    update_review,
)
from app.api_github import (
    analyze_github_repository,
    get_github_analysis,
)
from app.api_ai_summary import (
    generate_ai_summary,
    get_ai_summary,
)
from app.auth.dependencies import Principal
from app.db.models import (
    AuthAccount,
    Base,
    GitHubAnalysisSnapshot,
    Milestone,
    Project,
    ProjectAISummary,
    ProjectMember,
    Student,
    Submission,
    SubmissionReview,
)
from app.provision_faculty import (
    approve_faculty,
    assign_faculty,
    list_pending_faculty,
)
from app.services.github_service import (
    parse_github_url,
    fetch_github_contributions,
    GitHubServiceError,
)
from app.services.llm_summary_service import (
    gather_project_evidence,
    get_llm_provider,
    GroqProvider,
    GeminiProvider,
    LLMServiceError,
)


from argon2 import PasswordHasher

password_hasher = PasswordHasher()
TEST_PASSWORD_HASH = password_hasher.hash("TestPassword123!")


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)

    # Setup base entities
    faculty = AuthAccount(
        role="faculty",
        email="prof.smith@univ.edu",
        faculty_name="Prof. Smith",
        faculty_id="FAC-001",
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
        title="Automated Grading Project",
        description="Comprehensive evaluation system",
        github_url="https://github.com/org/repo-demo",
        status="ACTIVE",
    )
    session.add_all([faculty, student, project])
    session.flush()

    member = ProjectMember(
        project_id=project.id,
        student_id=student.id,
        role="LEADER",
    )
    submission = Submission(
        project_id=project.id,
        week_number=1,
        report_path="C:\\uploads\\test_report.pdf",
        status="SUBMITTED",
    )
    session.add_all([member, submission])
    session.commit()

    yield session, faculty, student, project, submission
    session.close()
    engine.dispose()


# ==========================================
# Phase 5: Submission Reviews Tests
# ==========================================

def test_faculty_create_review_success(test_db):
    session, faculty, _student, project, submission = test_db
    faculty_principal = Principal(id=faculty.id, role="faculty", email=faculty.email, student_id=None)

    data = ReviewCreate(score=88.5, feedback="Well-structured report with clear methodology.")
    result = create_review(
        project_id=project.id,
        submission_id=submission.id,
        data=data,
        account=faculty_principal,
        db=session,
    )

    assert result["score"] == 88.5
    assert result["reviewer_name"] == "Prof. Smith"
    assert result["feedback"] == "Well-structured report with clear methodology."
    assert submission.status == "REVIEWED"

    # Verify persisted in database
    review = session.query(SubmissionReview).first()
    assert review is not None
    assert review.score == 88.5


def test_review_score_validation():
    with pytest.raises(ValidationError):
        ReviewCreate(score=105.0, feedback="Invalid high score")

    with pytest.raises(ValidationError):
        ReviewCreate(score=-5.0, feedback="Invalid negative score")

    with pytest.raises(ValidationError):
        ReviewCreate(score=85.0, feedback="")


def test_review_duplicate_conflict(test_db):
    session, faculty, _student, project, submission = test_db
    faculty_principal = Principal(id=faculty.id, role="faculty", email=faculty.email, student_id=None)

    data = ReviewCreate(score=90.0, feedback="Initial review.")
    create_review(
        project_id=project.id,
        submission_id=submission.id,
        data=data,
        account=faculty_principal,
        db=session,
    )

    # Attempt second review by same faculty
    with pytest.raises(HTTPException) as exc_info:
        create_review(
            project_id=project.id,
            submission_id=submission.id,
            data=ReviewCreate(score=92.0, feedback="Second review attempt."),
            account=faculty_principal,
            db=session,
        )
    assert exc_info.value.status_code == 409


def test_update_and_list_reviews(test_db):
    session, faculty, _student, project, submission = test_db
    faculty_principal = Principal(id=faculty.id, role="faculty", email=faculty.email, student_id=None)

    create_review(
        project_id=project.id,
        submission_id=submission.id,
        data=ReviewCreate(score=75.0, feedback="Draft review."),
        account=faculty_principal,
        db=session,
    )

    all_reviews = list_submission_reviews(
        project_id=project.id,
        submission_id=submission.id,
        db=session,
    )
    assert len(all_reviews) == 1
    review_id = all_reviews[0]["id"]

    updated = update_review(
        project_id=project.id,
        submission_id=submission.id,
        review_id=review_id,
        data=ReviewUpdate(score=82.0, feedback="Revised after discussion."),
        account=faculty_principal,
        db=session,
    )
    assert updated["score"] == 82.0
    assert updated["feedback"] == "Revised after discussion."


# ==========================================
# Phase 6: GitHub Service & API Tests
# ==========================================

def test_parse_github_url():
    owner, repo = parse_github_url("https://github.com/tensorflow/tensorflow")
    assert owner == "tensorflow"
    assert repo == "tensorflow"

    owner, repo = parse_github_url("http://github.com/my-org/project.git")
    assert owner == "my-org"
    assert repo == "project"

    with pytest.raises(ValueError):
        parse_github_url("https://gitlab.com/user/project")

    with pytest.raises(ValueError):
        parse_github_url("not-a-url")


def test_fetch_github_contributions_with_mock(monkeypatch):
    fake_repo_data = {"default_branch": "develop"}
    fake_commits = [
        {
            "author": {"login": "alice_hub", "avatar_url": "https://avatars.com/alice"},
            "commit": {
                "author": {"name": "Alice Student", "email": "alice@univ.edu", "date": "2026-10-10T12:00:00Z"}
            },
        },
        {
            "author": {"login": "alice_hub", "avatar_url": "https://avatars.com/alice"},
            "commit": {
                "author": {"name": "Alice Student", "email": "alice@univ.edu", "date": "2026-10-09T12:00:00Z"}
            },
        },
        {
            "author": {"login": "bob_git", "avatar_url": ""},
            "commit": {
                "author": {"name": "Bob Guest", "email": "bob@other.com", "date": "2026-10-08T12:00:00Z"}
            },
        },
    ]

    def fake_github_request(endpoint, token=None):
        if "commits" in endpoint:
            return fake_commits
        return fake_repo_data

    monkeypatch.setattr("app.services.github_service._github_request", fake_github_request)

    members = [
        {"name": "Alice Student", "email": "alice@univ.edu"},
        {"name": "Charlie", "email": "charlie@univ.edu"},
    ]
    result = fetch_github_contributions("https://github.com/org/repo-demo", project_members=members)

    assert result["repo_name"] == "org/repo-demo"
    assert result["total_commits"] == 3
    stats = result["contributor_stats"]
    assert len(stats) == 2

    alice_stat = next(s for s in stats if s["username"] == "alice_hub")
    assert alice_stat["commits"] == 2
    assert alice_stat["match_confidence"] == "verified"
    assert alice_stat["matched_member"] == "Alice Student"

    bob_stat = next(s for s in stats if s["username"] == "bob_git")
    assert bob_stat["match_confidence"] == "unmatched"


def test_trigger_project_github_analysis_persists_snapshot(test_db, monkeypatch):
    session, _faculty, _student, project, _submission = test_db

    fake_result = {
        "repo_url": "https://github.com/org/repo-demo",
        "repo_name": "org/repo-demo",
        "default_branch": "main",
        "total_commits": 12,
        "contributor_stats": [{"username": "alice", "commits": 12, "match_confidence": "verified"}],
        "recent_activity": {"last_commit_date": "2026-10-10T12:00:00Z", "inspected_commit_window": 12},
        "limitations_disclaimer": "Advisory only.",
    }
    monkeypatch.setattr(
        "app.api_github.fetch_github_contributions",
        lambda *args, **kwargs: fake_result,
    )

    snapshot = analyze_github_repository(
        project_id=project.id,
        db=session,
    )
    assert snapshot.total_commits == 12
    assert snapshot.repo_url == "https://github.com/org/repo-demo"

    # Verify snapshot in db
    fetched = get_github_analysis(project_id=project.id, db=session)
    assert fetched is not None
    assert fetched.total_commits == 12


# ==========================================
# Phase 7: LLM Synthesis Service & API Tests
# ==========================================

from datetime import date, datetime, timezone

def test_gather_project_evidence(test_db):
    session, _faculty, student, project, submission = test_db

    # Add a milestone
    milestone = Milestone(
        project_id=project.id,
        title="Requirements Document",
        due_date=date(2026, 11, 1),
        status="PENDING",
    )
    session.add(milestone)
    session.commit()

    evidence = gather_project_evidence(project.id, session)

    assert evidence["project_id"] == project.id
    assert evidence["title"] == "Automated Grading Project"
    assert len(evidence["members"]) == 1
    assert evidence["members"][0]["name"] == student.name
    assert len(evidence["milestones"]) == 1
    assert len(evidence["submissions"]) == 1


def test_generate_ai_summary_with_mock_provider(test_db, monkeypatch):
    session, _faculty, _student, project, _submission = test_db

    mock_summary = {
        "summary": "Project is on track with 1 submission recorded.",
        "key_points": ["Submitted week 1 report on time."],
        "risks": ["SRS documentation has not yet been uploaded."],
        "recommended_next_steps": ["Submit system architecture diagram."],
        "review_questions": ["What is the planned deployment strategy?"],
        "evidence_sources": [{"source_type": "submission", "reference": "Week 1", "detail": "PDF uploaded"}],
        "advisory_disclaimer": "Advisory only.",
        "provider": "mock-llm",
        "model_name": "mock-v1",
    }

    class MockLLMProvider:
        def is_configured(self):
            return True
        def get_provider_name(self):
            return "mock-llm"
        def get_model_name(self):
            return "mock-v1"
        def generate_summary(self, evidence):
            return mock_summary

    monkeypatch.setattr("app.api_ai_summary.get_llm_provider", lambda: MockLLMProvider())

    response = generate_ai_summary(
        project_id=project.id,
        db=session,
    )

    assert response.summary_text == "Project is on track with 1 submission recorded."
    assert len(response.risks) == 1
    assert response.provider == "mock-llm"

    # Check status endpoint
    status_resp = get_ai_summary(project_id=project.id, db=session)
    assert status_resp.provider_configured is True
    assert status_resp.latest_summary is not None
    assert status_resp.latest_summary.summary_text == "Project is on track with 1 submission recorded."


def test_generate_ai_summary_unconfigured_provider(test_db, monkeypatch):
    session, _faculty, _student, project, _submission = test_db

    class UnconfiguredProvider:
        def is_configured(self):
            return False
        def get_provider_name(self):
            return "groq"
        def get_model_name(self):
            return "llama-3.3-70b-versatile"
        def generate_summary(self, evidence):
            raise LLMServiceError("Not configured")

    monkeypatch.setattr("app.api_ai_summary.get_llm_provider", lambda: UnconfiguredProvider())

    with pytest.raises(HTTPException) as exc_info:
        generate_ai_summary(
            project_id=project.id,
            db=session,
        )
    assert exc_info.value.status_code == 503
    assert "not configured" in exc_info.value.detail.lower()


# ==========================================
# Phase 2: Faculty Approval CLI Logic Tests
# ==========================================

def test_approve_faculty_lifecycle(test_db, monkeypatch):
    session, _f, _s, project, _sub = test_db
    monkeypatch.setattr(
        "app.core.config.settings.FACULTY_EMAIL_ALLOWLIST",
        "pending.prof@univ.edu,prof.smith@univ.edu",
    )

    # Create a pending unapproved faculty
    pending = AuthAccount(
        role="faculty",
        email="pending.prof@univ.edu",
        faculty_name="Prof. Pending",
        faculty_id="FAC-999",
        email_verified=True,
        faculty_approved=False,
        password_hash=TEST_PASSWORD_HASH,
    )
    session.add(pending)
    session.commit()

    # List pending
    pending_list = list_pending_faculty(db=session)
    assert any(acc.email == "pending.prof@univ.edu" for acc in pending_list)

    # Approve
    approved = approve_faculty("pending.prof@univ.edu", db=session)
    assert approved.faculty_approved is True

    # Assign to project
    assignment = assign_faculty("pending.prof@univ.edu", project.id, db=session)
    assert assignment.faculty_account_id == pending.id
    assert assignment.project_id == project.id


# ========================================================
# Phase 8: Groq & GitHub Insights Error Handling & Defense
# ========================================================

from io import BytesIO
from urllib.error import HTTPError
from app.core.config import settings


def test_groq_provider_configuration_validation(monkeypatch):
    provider = GroqProvider()
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")

    # None
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    assert provider.is_configured() is False
    with pytest.raises(LLMServiceError) as exc:
        provider.generate_summary({"test": "data"})
    assert "not configured" in str(exc.value)

    # Empty
    monkeypatch.setattr(settings, "GROQ_API_KEY", "   ")
    assert provider.is_configured() is False

    # Placeholder
    monkeypatch.setattr(settings, "GROQ_API_KEY", "your-groq-api-key")
    assert provider.is_configured() is False
    monkeypatch.setattr(settings, "GROQ_API_KEY", "change-me")
    assert provider.is_configured() is False

    # Valid
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test123456789012345678901234567890")
    assert provider.is_configured() is True


def test_groq_provider_sends_user_agent_and_normalizes_response(monkeypatch):
    provider = GroqProvider()
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_validtestkey")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")

    captured_request = {}

    mock_llm_json = {
        "summary": "Project progress is satisfactory.",
        "key_points": ["Milestone 1 reached"],
        "risks": ["Deployment pending"],
        "recommended_next_steps": ["Complete integration testing"],
        "review_questions": ["What is the test plan?"],
        "evidence_sources": [{"source_type": "milestone", "reference": "M1", "detail": "Completed"}],
    }

    mock_response_body = json.dumps({
        "choices": [
            {"message": {"content": json.dumps(mock_llm_json)}}
        ]
    }).encode("utf-8")

    class MockHTTPResponse:
        def __init__(self):
            pass
        def read(self):
            return mock_response_body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        captured_request["headers"] = dict(req.headers)
        captured_request["url"] = req.full_url
        return MockHTTPResponse()

    monkeypatch.setattr("app.services.llm_summary_service.urlopen", fake_urlopen)

    result = provider.generate_summary({"project_id": 1, "evidence": "sample"})

    # Verify User-Agent header was attached to avoid Cloudflare 1010
    assert "User-agent" in captured_request["headers"] or "User-Agent" in captured_request["headers"]
    header_val = captured_request["headers"].get("User-agent") or captured_request["headers"].get("User-Agent")
    assert "AI-Project-Monitoring" in header_val

    # Verify result structure
    assert result["summary"] == "Project progress is satisfactory."
    assert result["key_points"] == ["Milestone 1 reached"]
    assert result["provider"] == "groq"
    assert result["model_name"] == "llama-3.3-70b-versatile"
    assert "advisory_disclaimer" in result


def test_groq_provider_handles_rate_limits_and_http_errors(monkeypatch):
    provider = GroqProvider()
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_validtestkey")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")

    def fake_urlopen_429(req, timeout=None):
        raise HTTPError(req.full_url, 429, "Too Many Requests", {}, BytesIO(b"{}"))

    monkeypatch.setattr("app.services.llm_summary_service.urlopen", fake_urlopen_429)
    with pytest.raises(LLMServiceError) as exc429:
        provider.generate_summary({"project_id": 1})
    assert "rate limit exceeded" in str(exc429.value)

    def fake_urlopen_500(req, timeout=None):
        raise HTTPError(req.full_url, 500, "Internal Server Error", {}, BytesIO(b"{}"))

    monkeypatch.setattr("app.services.llm_summary_service.urlopen", fake_urlopen_500)
    with pytest.raises(LLMServiceError) as exc500:
        provider.generate_summary({"project_id": 1})
    assert "500" in str(exc500.value)


def test_github_analysis_safe_error_handling(test_db, monkeypatch):
    session, _f, _s, project, _sub = test_db

    # Project without GitHub URL
    project.github_url = None
    session.commit()
    with pytest.raises(HTTPException) as no_url_exc:
        analyze_github_repository(project.id, session)
    assert no_url_exc.value.status_code == 400

    # Project with invalid GitHub URL
    project.github_url = "https://notgithub.com/invalid"
    session.commit()
    with pytest.raises(HTTPException) as inv_url_exc:
        analyze_github_repository(project.id, session)
    assert inv_url_exc.value.status_code == 422

    # GitHub API rate limit error wrapped safely
    project.github_url = "https://github.com/owner/repo"
    session.commit()

    def fake_github_rate_limit(*args, **kwargs):
        raise GitHubServiceError("GitHub API rate limit exceeded or access forbidden.")

    monkeypatch.setattr("app.api_github.fetch_github_contributions", fake_github_rate_limit)

    with pytest.raises(HTTPException) as gh_err_exc:
        analyze_github_repository(project.id, session)
    assert gh_err_exc.value.status_code == 502
    assert "rate limit" in gh_err_exc.value.detail.lower()

