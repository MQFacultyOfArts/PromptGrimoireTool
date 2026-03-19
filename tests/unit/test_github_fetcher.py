"""Tests for the GitHub PR fetcher (scripts/incident/parsers/github.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestResolveGithubToken:
    """AC1.2 / AC1.4 — Token resolution order and missing token error."""

    def test_token_override_takes_priority(self) -> None:
        from scripts.incident.parsers.github import resolve_github_token

        result = resolve_github_token(token_override="explicit-token")
        assert result == "explicit-token"

    def test_env_var_used_when_no_override(self) -> None:
        from scripts.incident.parsers.github import resolve_github_token

        with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}):
            result = resolve_github_token()
        assert result == "env-token"

    def test_gh_cli_used_when_no_env_var(self) -> None:
        from scripts.incident.parsers.github import resolve_github_token

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "cli-token\n"

        with (
            patch.dict("os.environ", {}, clear=False),
            patch(
                "os.environ.get",
                side_effect=lambda k, d=None: (
                    d if k == "GITHUB_TOKEN" else os.environ.get(k, d)
                ),
            ),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            # Need to ensure GITHUB_TOKEN is not set
            import os

            env_backup = os.environ.pop("GITHUB_TOKEN", None)
            try:
                result = resolve_github_token()
            finally:
                if env_backup is not None:
                    os.environ["GITHUB_TOKEN"] = env_backup

        assert result == "cli-token"
        mock_run.assert_called_once_with(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_missing_token_raises_runtime_error(self) -> None:
        """AC1.4 — No env var and failed subprocess raises RuntimeError."""
        from scripts.incident.parsers.github import resolve_github_token

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        import os

        env_backup = os.environ.pop("GITHUB_TOKEN", None)
        try:
            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(RuntimeError, match="GITHUB_TOKEN"),
            ):
                resolve_github_token()
        finally:
            if env_backup is not None:
                os.environ["GITHUB_TOKEN"] = env_backup

    def test_env_var_preferred_over_gh_cli(self) -> None:
        """Resolution order: env var before subprocess."""
        from scripts.incident.parsers.github import resolve_github_token

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}),
            patch("subprocess.run") as mock_run,
        ):
            result = resolve_github_token()

        assert result == "env-token"
        mock_run.assert_not_called()


class TestFetchGithubPrs:
    """AC1.1 — Fetcher returns correct dicts for merged PRs in window."""

    @staticmethod
    def _make_pr(
        number: int,
        title: str,
        merged_at: str | None,
        updated_at: str,
        user: str = "alice",
        merge_commit_sha: str = "abc123",
        html_url: str = "https://github.com/org/repo/pull/1",
    ) -> dict:
        return {
            "number": number,
            "title": title,
            "merged_at": merged_at,
            "updated_at": updated_at,
            "user": {"login": user},
            "merge_commit_sha": merge_commit_sha,
            "html_url": html_url,
        }

    def test_returns_merged_prs_in_window(self) -> None:
        """Only merged PRs within the time window are returned."""
        from scripts.incident.parsers.github import fetch_github_prs

        prs_page1 = [
            # Merged inside window
            self._make_pr(
                10,
                "Fix bug",
                "2026-03-16T16:10:00Z",
                "2026-03-16T16:10:00Z",
                user="alice",
                merge_commit_sha="sha10",
                html_url="https://github.com/org/repo/pull/10",
            ),
            # Merged outside window (too late)
            self._make_pr(
                11,
                "Add feature",
                "2026-03-16T17:00:00Z",
                "2026-03-16T17:00:00Z",
                user="bob",
                merge_commit_sha="sha11",
                html_url="https://github.com/org/repo/pull/11",
            ),
            # Not merged (still open)
            self._make_pr(
                12,
                "WIP",
                None,
                "2026-03-16T16:10:00Z",
            ),
            # Merged inside window
            self._make_pr(
                13,
                "Hotfix",
                "2026-03-16T16:05:00Z",
                "2026-03-16T16:05:00Z",
                user="carol",
                merge_commit_sha="sha13",
                html_url="https://github.com/org/repo/pull/13",
            ),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = prs_page1
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        # Second page returns empty to stop pagination
        mock_empty_response = MagicMock()
        mock_empty_response.json.return_value = []
        mock_empty_response.raise_for_status = MagicMock()

        mock_client.get.side_effect = [mock_response, mock_empty_response]

        with patch(
            "scripts.incident.parsers.github.httpx.Client", return_value=mock_client
        ):
            results = fetch_github_prs(
                repo="org/repo",
                start_utc="2026-03-16T16:00:00Z",
                end_utc="2026-03-16T16:30:00Z",
                token="test-token",
            )

        assert len(results) == 2
        # Check dict structure
        pr10 = next(r for r in results if r["pr_number"] == 10)
        assert pr10["title"] == "Fix bug"
        assert pr10["author"] == "alice"
        assert pr10["commit_oid"] == "sha10"
        assert pr10["url"] == "https://github.com/org/repo/pull/10"
        assert "ts_utc" in pr10

        pr13 = next(r for r in results if r["pr_number"] == 13)
        assert pr13["title"] == "Hotfix"
        assert pr13["author"] == "carol"

    def test_pagination_stops_when_all_before_window(self) -> None:
        """Pagination stops when all PRs on a page have updated_at before start."""
        from scripts.incident.parsers.github import fetch_github_prs

        # Page 1: one PR in window
        page1 = [
            self._make_pr(
                20,
                "Recent",
                "2026-03-16T16:10:00Z",
                "2026-03-16T16:10:00Z",
                merge_commit_sha="sha20",
                html_url="https://github.com/org/repo/pull/20",
            ),
        ]

        # Page 2: all PRs before window — should stop
        page2 = [
            self._make_pr(
                15,
                "Old",
                "2026-03-15T10:00:00Z",
                "2026-03-15T10:00:00Z",
                merge_commit_sha="sha15",
                html_url="https://github.com/org/repo/pull/15",
            ),
        ]

        resp1 = MagicMock()
        resp1.json.return_value = page1
        resp1.raise_for_status = MagicMock()

        resp2 = MagicMock()
        resp2.json.return_value = page2
        resp2.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.side_effect = [resp1, resp2]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "scripts.incident.parsers.github.httpx.Client", return_value=mock_client
        ):
            results = fetch_github_prs(
                repo="org/repo",
                start_utc="2026-03-16T16:00:00Z",
                end_utc="2026-03-16T16:30:00Z",
                token="test-token",
            )

        assert len(results) == 1
        assert results[0]["pr_number"] == 20
        # Should have made exactly 2 requests (page 1 + page 2), not a 3rd
        assert mock_client.get.call_count == 2

    def test_empty_first_page_returns_empty(self) -> None:
        """Empty response on first page returns empty list."""
        from scripts.incident.parsers.github import fetch_github_prs

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "scripts.incident.parsers.github.httpx.Client", return_value=mock_client
        ):
            results = fetch_github_prs(
                repo="org/repo",
                start_utc="2026-03-16T16:00:00Z",
                end_utc="2026-03-16T16:30:00Z",
                token="test-token",
            )

        assert results == []
