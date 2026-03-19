"""Tests for the `github` CLI subcommand in scripts/incident_db.py."""

from __future__ import annotations

import hashlib
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """In-memory SQLite database with schema applied.

    Returns a MagicMock wrapping the real connection so that the CLI's
    ``conn.close()`` call is a no-op, preserving the in-memory DB for
    post-invocation assertions.
    """
    from scripts.incident.schema import create_schema

    real_conn = sqlite3.connect(":memory:")
    create_schema(real_conn)

    # Wrap so close() is interceptable, but all other calls go through
    wrapper = MagicMock(wraps=real_conn)
    wrapper.close = MagicMock()  # no-op
    return wrapper


@pytest.fixture
def sample_prs() -> list[dict]:
    """Known PR data returned by mocked fetch_github_prs."""
    return [
        {
            "ts_utc": "2026-03-16T16:10:00.000000Z",
            "pr_number": 10,
            "title": "Fix bug",
            "author": "alice",
            "commit_oid": "sha10",
            "url": "https://github.com/org/repo/pull/10",
        },
        {
            "ts_utc": "2026-03-16T16:05:00.000000Z",
            "pr_number": 13,
            "title": "Hotfix",
            "author": "carol",
            "commit_oid": "sha13",
            "url": "https://github.com/org/repo/pull/13",
        },
    ]


def _dedup_sha(repo: str, start_utc: str, end_utc: str) -> str:
    return hashlib.sha256(f"github:{repo}:{start_utc}:{end_utc}".encode()).hexdigest()


class TestGithubCliOrchestration:
    """AC1.1 -- CLI orchestrates fetch and DB insertion."""

    def test_fetched_prs_inserted_into_db(
        self, db_conn: sqlite3.Connection, sample_prs: list[dict]
    ) -> None:
        """Mocked fetch_github_prs data ends up in github_events table."""
        from scripts.incident_db import app

        runner = CliRunner()

        with (
            patch("scripts.incident_db.sqlite3.connect", return_value=db_conn),
            patch(
                "scripts.incident.parsers.github.resolve_github_token",
                return_value="fake-token",
            ),
            patch(
                "scripts.incident.parsers.github.fetch_github_prs",
                return_value=sample_prs,
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "github",
                    "--start",
                    "2026-03-16 16:00",
                    "--end",
                    "2026-03-16 16:30",
                    "--repo",
                    "org/repo",
                    "--token",
                    "fake-token",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "2 PRs" in result.output

        rows = db_conn.execute("SELECT * FROM github_events").fetchall()
        assert len(rows) == 2

        # Verify source row was created
        source = db_conn.execute("SELECT * FROM sources").fetchone()
        assert source is not None

    def test_source_row_fields(
        self, db_conn: sqlite3.Connection, sample_prs: list[dict]
    ) -> None:
        """Source row has correct format, hostname, and collection_method."""
        from scripts.incident_db import app

        runner = CliRunner()

        with (
            patch("scripts.incident_db.sqlite3.connect", return_value=db_conn),
            patch(
                "scripts.incident.parsers.github.resolve_github_token",
                return_value="fake-token",
            ),
            patch(
                "scripts.incident.parsers.github.fetch_github_prs",
                return_value=sample_prs,
            ),
        ):
            runner.invoke(
                app,
                [
                    "github",
                    "--start",
                    "2026-03-16 16:00",
                    "--end",
                    "2026-03-16 16:30",
                    "--repo",
                    "org/repo",
                    "--token",
                    "fake-token",
                ],
            )

        row = db_conn.execute(
            "SELECT format, hostname, collection_method, filename FROM sources"
        ).fetchone()
        assert row[0] == "github"
        assert row[1] == "github.com"
        assert row[2] == "REST API"
        assert row[3] == "org/repo"

    def test_github_events_have_correct_source_id(
        self, db_conn: sqlite3.Connection, sample_prs: list[dict]
    ) -> None:
        """All github_events rows reference the correct source_id."""
        from scripts.incident_db import app

        runner = CliRunner()

        with (
            patch("scripts.incident_db.sqlite3.connect", return_value=db_conn),
            patch(
                "scripts.incident.parsers.github.resolve_github_token",
                return_value="fake-token",
            ),
            patch(
                "scripts.incident.parsers.github.fetch_github_prs",
                return_value=sample_prs,
            ),
        ):
            runner.invoke(
                app,
                [
                    "github",
                    "--start",
                    "2026-03-16 16:00",
                    "--end",
                    "2026-03-16 16:30",
                    "--repo",
                    "org/repo",
                    "--token",
                    "fake-token",
                ],
            )

        source_id = db_conn.execute("SELECT id FROM sources").fetchone()[0]
        event_source_ids = db_conn.execute(
            "SELECT DISTINCT source_id FROM github_events"
        ).fetchall()
        assert len(event_source_ids) == 1
        assert event_source_ids[0][0] == source_id


class TestGithubCliDedup:
    """AC1.3 -- Re-ingesting same window deduplicates."""

    def test_second_call_skips_insertion(
        self, db_conn: sqlite3.Connection, sample_prs: list[dict]
    ) -> None:
        """Second invocation with same params does not insert new rows."""
        from scripts.incident_db import app

        runner = CliRunner()
        cli_args = [
            "github",
            "--start",
            "2026-03-16 16:00",
            "--end",
            "2026-03-16 16:30",
            "--repo",
            "org/repo",
            "--token",
            "fake-token",
        ]

        with (
            patch("scripts.incident_db.sqlite3.connect", return_value=db_conn),
            patch(
                "scripts.incident.parsers.github.resolve_github_token",
                return_value="fake-token",
            ),
            patch(
                "scripts.incident.parsers.github.fetch_github_prs",
                return_value=sample_prs,
            ) as mock_fetch,
        ):
            # First call -- inserts
            result1 = runner.invoke(app, cli_args)
            assert result1.exit_code == 0, result1.output
            assert "2 PRs" in result1.output
            assert mock_fetch.call_count == 1

            # Second call -- dedup
            result2 = runner.invoke(app, cli_args)
            assert result2.exit_code == 0, result2.output
            assert (
                "dedup" in result2.output.lower() or "already" in result2.output.lower()
            )
            # fetch_github_prs should NOT have been called again
            assert mock_fetch.call_count == 1

        # Still only 2 rows from the first call
        rows = db_conn.execute("SELECT * FROM github_events").fetchall()
        assert len(rows) == 2

    def test_force_flag_bypasses_dedup(
        self, db_conn: sqlite3.Connection, sample_prs: list[dict]
    ) -> None:
        """--force re-fetches even if window was previously ingested."""
        from scripts.incident_db import app

        runner = CliRunner()
        base_args = [
            "github",
            "--start",
            "2026-03-16 16:00",
            "--end",
            "2026-03-16 16:30",
            "--repo",
            "org/repo",
            "--token",
            "fake-token",
        ]

        with (
            patch("scripts.incident_db.sqlite3.connect", return_value=db_conn),
            patch(
                "scripts.incident.parsers.github.resolve_github_token",
                return_value="fake-token",
            ),
            patch(
                "scripts.incident.parsers.github.fetch_github_prs",
                return_value=sample_prs,
            ) as mock_fetch,
        ):
            # First call
            runner.invoke(app, base_args)
            assert mock_fetch.call_count == 1

            # Second call with --force
            result2 = runner.invoke(app, [*base_args, "--force"])
            assert result2.exit_code == 0, result2.output
            assert mock_fetch.call_count == 2

        # Should have 2 rows (old deleted, new inserted)
        rows = db_conn.execute("SELECT * FROM github_events").fetchall()
        assert len(rows) == 2


class TestDetectGithubRepo:
    """Test the _detect_github_repo helper."""

    def test_detects_ssh_url(self) -> None:
        from scripts.incident_db import _detect_github_repo

        mock_result = type(
            "R", (), {"returncode": 0, "stdout": "git@github.com:org/repo.git\n"}
        )()
        with patch("scripts.incident_db.subprocess.run", return_value=mock_result):
            assert _detect_github_repo() == "org/repo"

    def test_detects_https_url(self) -> None:
        from scripts.incident_db import _detect_github_repo

        mock_result = type(
            "R", (), {"returncode": 0, "stdout": "https://github.com/org/repo.git\n"}
        )()
        with patch("scripts.incident_db.subprocess.run", return_value=mock_result):
            assert _detect_github_repo() == "org/repo"

    def test_no_remote_raises(self) -> None:
        import typer
        from scripts.incident_db import _detect_github_repo

        mock_result = type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "error"}
        )()
        with (
            patch("scripts.incident_db.subprocess.run", return_value=mock_result),
            pytest.raises(typer.BadParameter, match="no git remote"),
        ):
            _detect_github_repo()
