"""Fire-and-forget helper that posts a submission notification to an n8n webhook.

The function is intentionally non-blocking: it runs in a background thread via
``loop.run_in_executor`` so the upload response is never delayed by network
latency.  Any exception is logged but never re-raised, so a misconfigured or
offline n8n instance cannot break submissions.

Environment variable:
    N8N_WEBHOOK_URL  -- full URL of the n8n webhook trigger node.
                        If empty or unset, notifications are silently skipped.
"""

from __future__ import annotations

import asyncio
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


def notify_faculty_submission(
    *,
    project_id: int,
    project_name: str,
    submission_id: int,
    submitted_at: datetime,
    student_name: str,
    student_email: str,
    faculty_email: str,
    submission_title: str,
) -> None:
    """Schedule a non-blocking n8n webhook POST.

    Sends exactly the eight fields required by the n8n ``Validate Required
    Fields`` node:
        project_id, project_name, student_name, student_email,
        faculty_email, submission_title, submission_id, submitted_at.

    Call this after a successful DB commit; safe to call from any async context
    because it schedules the work on the default executor.
    """
    if not settings.N8N_WEBHOOK_URL:
        logger.debug(
            "N8N_WEBHOOK_URL not configured -- skipping submission notification "
            "for project %s (submission %s).",
            project_id,
            submission_id,
        )
        return

    payload: dict[str, Any] = {
        "project_id":       project_id,
        "project_name":     project_name,
        "student_name":     student_name,
        "student_email":    student_email,
        "faculty_email":    faculty_email,
        "submission_title": submission_title,
        "submission_id":    submission_id,
        "submitted_at":     submitted_at.isoformat(),
    }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. during tests) -- call synchronously
        _post_to_n8n(payload)
        return

    loop.run_in_executor(None, _post_to_n8n, payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _post_to_n8n(payload: dict[str, Any]) -> None:
    """Synchronous HTTP POST executed in a thread pool worker."""
    url = settings.N8N_WEBHOOK_URL
    if not url:
        return

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ProjectScope/1.0 n8n-notifier",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.status
            if status_code < 200 or status_code >= 300:
                logger.warning(
                    "n8n webhook returned non-2xx status %s for submission payload.",
                    status_code,
                )
            else:
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
