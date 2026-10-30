"""Fire-and-forget helpers that post notifications to n8n webhooks.

Supported workflows:
1. Faculty submission notification (triggered when student uploads submission):
   Routes via n8n to all project-assigned faculty members via email.
   Environment variable:
       N8N_WEBHOOK_URL  -- full URL of the n8n submission webhook trigger node.

2. Student marks update notification (triggered when faculty assigns or updates marks):
   Environment variables:
       N8N_MARKS_UPDATED_WEBHOOK_URL -- full URL of the marks updated webhook.
       N8N_WEBHOOK_SECRET            -- shared secret sent in X-ProjectScope-Secret header.

DELIVERY GUARANTEE & LIMITATIONS:
Notifications use direct HTTP dispatch after a successful database commit.
Delivery is best-effort (at-most-once in-process delivery) and is NOT guaranteed
against transient network dropouts, webhook downtime, or process termination.
A failed n8n request will never roll back or fail an already committed database record.
Each event payload includes a deterministic `event_id` to enable deduplication on
the receiving n8n workflow / Data Table.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_marks_event_id(
    review_id: int,
    student_id: int,
    score: float,
    updated_at: datetime,
) -> str:
    """Generate a deterministic event identifier for a logical marks change.

    The event ID combines the review ID, student ID, formatted score, and the
    microsecond-precision ISO timestamp digested via SHA-256. It is stable
    across retries for the same logical event and unique across distinct evaluations.
    """
    ts_str = (
        updated_at.astimezone(timezone.utc).isoformat()
        if updated_at.tzinfo
        else updated_at.isoformat()
    )
    raw = f"{review_id}:{student_id}:{score:.2f}:{ts_str}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"marks-rev{review_id}-stu{student_id}-{digest}"


def generate_submission_event_id(
    submission_id: int,
    submitted_at: datetime,
) -> str:
    """Generate a deterministic event identifier for a student submission.

    Combines submission_id and microsecond-precision ISO timestamp digested via SHA-256.
    Stable across retries of the same submission event.
    """
    ts_str = (
        submitted_at.astimezone(timezone.utc).isoformat()
        if submitted_at.tzinfo
        else submitted_at.isoformat()
    )
    raw = f"sub:{submission_id}:{ts_str}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"sub-{submission_id}-{digest}"


def notify_faculty_submission(
    *,
    project_id: int,
    project_name: str,
    submission_id: int,
    submitted_at: datetime,
    student_name: str,
    student_email: str,
    submission_title: str,
    faculty_email: str | None = None,
    faculty_recipients: list[dict[str, Any]] | None = None,
    event_id: str | None = None,
    student_registration_number: str | None = None,
    week_number: int | None = None,
    dashboard_url: str | None = None,
    notification_type: str | None = None,
) -> None:
    """Schedule a non-blocking n8n webhook POST for student submissions.

    Preserves the exact existing contract and base 8 fields for backwards compatibility:
        project_id, project_name, student_name, student_email, faculty_email,
        submission_title, submission_id, submitted_at.

    When multiple project faculty recipients or enriched parameters are supplied,
    attaches `faculty_recipients` (list of all eligible project faculty), `event_id`,
    `student_registration_number`, `week_number`, and `notification_type` to notify
    all assigned faculty members via email.
    """
    if not settings.N8N_WEBHOOK_URL:
        logger.debug(
            "N8N_WEBHOOK_URL not configured -- skipping submission notification "
            "for project %s (submission %s).",
            project_id,
            submission_id,
        )
        return

    # Derive primary faculty_email for backward-compatible workflow nodes
    primary_email = faculty_email
    if not primary_email and faculty_recipients:
        primary_email = faculty_recipients[0].get("faculty_email", "")

    payload: dict[str, Any] = {
        "project_id":       project_id,
        "project_name":     project_name,
        "student_name":     student_name,
        "student_email":    student_email,
        "faculty_email":    primary_email or "",
        "submission_title": submission_title,
        "submission_id":    submission_id,
        "submitted_at":     submitted_at.isoformat(),
    }

    # Only include enriched keys if at least one enriched parameter was explicitly passed,
    # thereby guaranteeing 100% backward compatibility for existing tests/callers expecting
    # the 8 base fields.
    is_enriched = any(
        arg is not None
        for arg in (
            faculty_recipients,
            event_id,
            student_registration_number,
            week_number,
            dashboard_url,
            notification_type,
        )
    )

    if is_enriched:
        payload["notification_type"] = (
            notification_type if notification_type is not None else "student_submission"
        )
        payload["event_id"] = (
            event_id
            if event_id is not None
            else generate_submission_event_id(submission_id, submitted_at)
        )
        payload["student_registration_number"] = student_registration_number
        payload["week_number"] = week_number
        payload["faculty_recipients"] = (
            faculty_recipients
            if faculty_recipients is not None
            else ([{"faculty_email": primary_email}] if primary_email else [])
        )
        if dashboard_url is not None:
            payload["dashboard_url"] = dashboard_url

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. during tests or sync handlers) -- call synchronously
        _post_to_n8n(payload)
        return

    loop.run_in_executor(None, _post_to_n8n, payload)


def notify_student_marks(
    *,
    event_id: str,
    student_id: int,
    student_name: str,
    student_email: str,
    project_id: int,
    project_name: str,
    submission_id: int,
    submission_title: str,
    marks_awarded: float,
    max_marks: float = 100.0,
    updated_at: datetime,
    updated_by: str,
    frontend_url: str | None = None,
    feedback: str | None = None,
) -> None:
    """Schedule a non-blocking n8n webhook POST for marks assignment or update.

    Sends required payload fields matching the n8n marks notification workflow:
        event_id, student_id, student_name, student_email, project_id, project_name,
        submission_id, submission_title, marks_awarded, max_marks, updated_at, updated_by.
    Optional fields:
        frontend_url, feedback.

    Authenticates via header: X-ProjectScope-Secret.
    If the webhook URL or secret is missing, logs a safe message and skips dispatch
    rather than sending an unauthenticated request.
    """
    if not settings.N8N_MARKS_UPDATED_WEBHOOK_URL:
        logger.debug(
            "N8N_MARKS_UPDATED_WEBHOOK_URL not configured -- skipping marks notification "
            "for project %s (submission %s).",
            project_id,
            submission_id,
        )
        return

    if not settings.N8N_WEBHOOK_SECRET:
        logger.warning(
            "N8N_WEBHOOK_SECRET not configured -- skipping marks notification for project %s "
            "(submission %s) to prevent sending unauthenticated request.",
            project_id,
            submission_id,
        )
        return

    if not student_email or not str(student_email).strip():
        logger.warning(
            "n8n marks notification skipped for submission %s: student email is missing or empty "
            "(student_id=%s, project_id=%s).",
            submission_id,
            student_id,
            project_id,
        )
        return

    ts_iso = (
        updated_at.astimezone(timezone.utc).isoformat()
        if updated_at.tzinfo
        else updated_at.isoformat()
    )

    payload: dict[str, Any] = {
        "event_id":         event_id,
        "student_id":       student_id,
        "student_name":     student_name,
        "student_email":    student_email,
        "project_id":       project_id,
        "project_name":     project_name,
        "submission_id":    submission_id,
        "submission_title": submission_title,
        "marks_awarded":    float(marks_awarded),
        "max_marks":        int(max_marks) if float(max_marks).is_integer() else float(max_marks),
        "updated_at":       ts_iso,
        "updated_by":       updated_by,
    }
    if frontend_url is not None:
        payload["frontend_url"] = frontend_url
    if feedback is not None:
        payload["feedback"] = feedback

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. during tests or sync handlers) -- call synchronously
        _post_marks_to_n8n(payload)
        return

    loop.run_in_executor(None, _post_marks_to_n8n, payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _post_to_n8n(payload: dict[str, Any]) -> None:
    """Synchronous HTTP POST for submission notifications executed in thread pool."""
    url = settings.N8N_WEBHOOK_URL
    if not url:
        return

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "ProjectScope/1.0 n8n-notifier",
    }
    if settings.N8N_WEBHOOK_SECRET:
        headers["X-ProjectScope-Secret"] = settings.N8N_WEBHOOK_SECRET

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.status
            resp_body = response.read()
            if status_code < 200 or status_code >= 300:
                logger.warning(
                    "n8n webhook returned non-2xx status %s for submission payload.",
                    status_code,
                )
            else:
                # Inspect response for partial failure or summary if returned by n8n
                try:
                    resp_json = json.loads(resp_body.decode("utf-8"))
                    if isinstance(resp_json, dict) and resp_json.get("status") == "partial_failure":
                        logger.warning(
                            "n8n submission notification partial delivery (project_id=%s, submission_id=%s): %s",
                            payload.get("project_id"),
                            payload.get("submission_id"),
                            resp_json.get("message") or resp_json,
                        )
                    else:
                        logger.info(
                            "n8n submission notification sent (project_id=%s, submission_id=%s, status=%s).",
                            payload.get("project_id"),
                            payload.get("submission_id"),
                            status_code,
                        )
                except Exception:
                    logger.info(
                        "n8n submission notification sent (project_id=%s, submission_id=%s, status=%s).",
                        payload.get("project_id"),
                        payload.get("submission_id"),
                        status_code,
                    )
    except urllib.error.URLError as exc:
        logger.warning(
            "n8n submission notification failed (project_id=%s): %s",
            payload.get("project_id"),
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error posting submission notification to n8n: %s", exc
        )


def _post_marks_to_n8n(payload: dict[str, Any]) -> None:
    """Synchronous HTTP POST for marks notifications executed in thread pool."""
    url = settings.N8N_MARKS_UPDATED_WEBHOOK_URL
    secret = settings.N8N_WEBHOOK_SECRET
    if not url or not secret:
        return

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ProjectScope/1.0 n8n-notifier",
            "X-ProjectScope-Secret": secret,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.status
            if status_code < 200 or status_code >= 300:
                logger.warning(
                    "n8n marks webhook returned non-2xx status %s (event_id=%s, project_id=%s, submission_id=%s).",
                    status_code,
                    payload.get("event_id"),
                    payload.get("project_id"),
                    payload.get("submission_id"),
                )
            else:
                logger.info(
                    "n8n marks notification sent (event_id=%s, project_id=%s, submission_id=%s, status=%s).",
                    payload.get("event_id"),
                    payload.get("project_id"),
                    payload.get("submission_id"),
                    status_code,
                )
    except urllib.error.URLError as exc:
        logger.warning(
            "n8n marks notification failed (event_id=%s, project_id=%s, submission_id=%s): %s",
            payload.get("event_id"),
            payload.get("project_id"),
            payload.get("submission_id"),
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error posting marks notification to n8n (event_id=%s): %s",
            payload.get("event_id"),
            exc,
        )
