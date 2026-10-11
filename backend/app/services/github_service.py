import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings

GITHUB_API_URL = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 15
MAX_COMMITS_TO_INSPECT = 100

LIMITATIONS_DISCLAIMER = (
    "Limitations Notice: Commit indicators and repository statistics reflect recorded "
    "Git commit history only. They do not measure software architecture quality, "
    "problem difficulty, documentation, or offline student collaboration."
)


class GitHubServiceError(RuntimeError):
    """Raised when GitHub data cannot be retrieved or processed safely."""


def parse_github_url(url: str) -> tuple[str, str]:
    """Validate and parse a GitHub repository URL into (owner, repo)."""
    if not url or not isinstance(url, str):
        raise ValueError("A valid repository URL is required.")
    
    clean_url = url.strip()
    match = re.match(
        r"^https?://(?:www\.)?github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?(?:/.*)?$",
        clean_url,
    )
    if not match:
        raise ValueError("Invalid GitHub repository URL. Must be in format https://github.com/owner/repo")

    owner, repo = match.groups()
    if owner in (".", "..") or repo in (".", ".."):
        raise ValueError("Invalid repository owner or name.")
    return owner, repo


def _github_request(endpoint: str, token: str | None = None) -> Any:
    url = f"{GITHUB_API_URL}/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Project-Monitoring-System",
    }
    auth_token = token or getattr(settings, "GITHUB_TOKEN", None)
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token.strip()}"

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        if exc.code == 404:
            raise GitHubServiceError("Repository not found or access is restricted.") from None
        if exc.code in (403, 429):
            raise GitHubServiceError("GitHub API rate limit exceeded or access forbidden.") from None
        raise GitHubServiceError(f"GitHub API request failed with status {exc.code}.") from None
    except (URLError, TimeoutError) as exc:
        raise GitHubServiceError("Failed to connect to GitHub API.") from exc
    except json.JSONDecodeError as exc:
        raise GitHubServiceError("Invalid JSON received from GitHub API.") from exc


def fetch_github_contributions(
    repo_url: str,
    token: str | None = None,
    project_members: list[dict] | None = None,
) -> dict[str, Any]:
    """Fetch commits and contributor statistics from GitHub repository."""
    owner, repo = parse_github_url(repo_url)
    
    # 1. Fetch repo metadata
    repo_data = _github_request(f"/repos/{owner}/{repo}", token=token)
    default_branch = repo_data.get("default_branch", "main")

    # 2. Fetch recent commits
    commits_endpoint = f"/repos/{owner}/{repo}/commits?per_page={MAX_COMMITS_TO_INSPECT}"
    commits_data = _github_request(commits_endpoint, token=token)

    if not isinstance(commits_data, list):
        commits_data = []

    # 3. Aggregate contributor statistics
    contributor_map: dict[str, dict[str, Any]] = {}
    for commit in commits_data:
        author_info = commit.get("author") or {}
        commit_details = commit.get("commit", {}) or {}
        git_author = commit_details.get("author", {}) or {}

        username = author_info.get("login") or git_author.get("name") or "Unknown"
        email = git_author.get("email") or ""
        name = git_author.get("name") or username

        key = username.lower()
        if key not in contributor_map:
            contributor_map[key] = {
                "username": username,
                "name": name,
                "email": email,
                "commits": 0,
                "avatar_url": author_info.get("avatar_url") or "",
                "matched_member": None,
                "match_confidence": "unmatched",
            }
        contributor_map[key]["commits"] += 1

    # 4. Match contributors with enrolled project members
    stats = list(contributor_map.values())
    if project_members:
        for stat in stats:
            stat_name = stat["name"].lower().strip()
            stat_email = stat["email"].lower().strip()
            stat_user = stat["username"].lower().strip()

            for member in project_members:
                m_name = (member.get("name") or "").lower().strip()
                m_email = (member.get("email") or "").lower().strip()

                if stat_email and stat_email == m_email:
                    stat["matched_member"] = member.get("name")
                    stat["match_confidence"] = "verified"
                    break
                elif m_name and (stat_name == m_name or stat_user == m_name.replace(" ", "")):
                    stat["matched_member"] = member.get("name")
                    stat["match_confidence"] = "probable"
                    break

    # Sort contributors by commit count descending
    stats.sort(key=lambda s: s["commits"], reverse=True)

    last_commit_date = None
    if commits_data:
        first_commit = commits_data[0].get("commit", {}) or {}
        last_commit_date = (first_commit.get("author") or {}).get("date")

    return {
        "repo_url": repo_url,
        "repo_name": f"{owner}/{repo}",
        "default_branch": default_branch,
        "total_commits": len(commits_data),
        "contributor_stats": stats,
        "recent_activity": {
            "last_commit_date": last_commit_date,
            "inspected_commit_window": len(commits_data),
        },
        "limitations_disclaimer": LIMITATIONS_DISCLAIMER,
    }
