"""GitHub PR fetcher for incident epoch analysis.

Queries the GitHub REST API for merged pull requests within a UTC time
window.  Token resolution tries ``--token`` flag, then ``GITHUB_TOKEN``
env var, then ``gh auth token`` subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

import httpx
from scripts.incident.parsers import normalise_utc

_GITHUB_API = "https://api.github.com"

_STATUS_MESSAGES: dict[int, str] = {
    401: "Error: GitHub API returned 401 Unauthorized. Check your token.",
    403: (
        "Error: GitHub API returned 403 Forbidden. "
        "Token may lack permissions or rate limit exceeded."
    ),
}


def resolve_github_token(token_override: str | None = None) -> str:
    """Resolve a GitHub personal access token.

    Resolution order:
    1. *token_override* parameter (from ``--token`` CLI flag)
    2. ``GITHUB_TOKEN`` environment variable
    3. ``gh auth token`` subprocess

    Raises
    ------
    RuntimeError
        If no token can be found from any source.
    """
    if token_override:
        return token_override

    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token

    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    msg = "No GitHub token found. Set GITHUB_TOKEN or install gh CLI."
    raise RuntimeError(msg)


def _pr_to_dict(pr: dict, merged_dt: datetime) -> dict:
    """Convert a GitHub PR JSON object to a normalised dict."""
    return {
        "ts_utc": normalise_utc(merged_dt),
        "pr_number": pr["number"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "commit_oid": pr["merge_commit_sha"],
        "url": pr["html_url"],
    }


def _process_page(
    prs: list[dict],
    start_dt: datetime,
    end_dt: datetime,
    results: list[dict],
) -> bool:
    """Process a page of PRs, appending matches to *results*.

    Returns True if all PRs on the page have ``updated_at`` before
    *start_dt* (signals pagination should stop).
    """
    all_before_window = True
    for pr in prs:
        updated_at = datetime.fromisoformat(pr["updated_at"])
        if updated_at >= start_dt:
            all_before_window = False

        merged_at_raw = pr.get("merged_at")
        if merged_at_raw is None:
            continue

        merged_dt = datetime.fromisoformat(merged_at_raw)
        if start_dt <= merged_dt <= end_dt:
            results.append(_pr_to_dict(pr, merged_dt))

    return all_before_window


def _handle_http_error(
    exc: httpx.HTTPStatusError,
    repo: str,
) -> None:
    """Print a user-friendly error message and exit."""
    status = exc.response.status_code
    if status == 404:
        msg = f"Error: GitHub API returned 404. Repository '{repo}' not found."
    else:
        msg = _STATUS_MESSAGES.get(status, f"Error: GitHub API returned HTTP {status}.")
    print(msg, file=sys.stderr)
    raise SystemExit(1) from exc


def fetch_github_prs(
    repo: str,
    start_utc: str,
    end_utc: str,
    token: str,
) -> list[dict]:
    """Fetch merged PRs for *repo* within a UTC time window.

    Parameters
    ----------
    repo:
        GitHub repository in ``owner/name`` format.
    start_utc:
        ISO 8601 UTC start time (inclusive).
    end_utc:
        ISO 8601 UTC end time (inclusive).
    token:
        GitHub personal access token.

    Returns
    -------
    list[dict]
        Each dict has keys: ``ts_utc``, ``pr_number``, ``title``,
        ``author``, ``commit_oid``, ``url``.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    start_dt = datetime.fromisoformat(start_utc)
    end_dt = datetime.fromisoformat(end_utc)
    results: list[dict] = []
    page = 1

    try:
        with httpx.Client() as client:
            while True:
                resp = client.get(
                    f"{_GITHUB_API}/repos/{repo}/pulls",
                    params={
                        "state": "closed",
                        "sort": "updated",
                        "direction": "desc",
                        "per_page": 100,
                        "page": page,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                prs = resp.json()

                if not prs:
                    break

                if _process_page(prs, start_dt, end_dt, results):
                    break

                page += 1

    except httpx.HTTPStatusError as exc:
        _handle_http_error(exc, repo)

    return results
