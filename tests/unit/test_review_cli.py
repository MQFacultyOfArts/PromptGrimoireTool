"""Tests for the `review` CLI subcommand in incident_db.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.incident_db import app
from typer.testing import CliRunner

runner = CliRunner()


class TestReviewOrchestration:
    """AC6.1: review command calls all analysis functions in sequence."""

    @patch("scripts.incident_db.sqlite3")
    def test_orchestration_calls_all_functions(self, mock_sqlite3: MagicMock) -> None:
        """All analysis functions are called and markdown output is produced."""
        mock_conn = MagicMock()
        mock_sqlite3.connect.return_value = mock_conn

        mock_epochs = [
            {
                "commit": "aaa111",
                "start_utc": "2026-03-15T10:00:00Z",
                "end_utc": "2026-03-15T16:00:00Z",
                "event_count": 5000,
                "duration_seconds": 21600,
                "is_crash_bounce": False,
            }
        ]

        with (
            patch(
                "scripts.incident.analysis.extract_epochs",
                return_value=mock_epochs,
            ) as mock_extract,
            patch(
                "scripts.incident.analysis.enrich_epochs_journal",
            ) as mock_enrich_journal,
            patch(
                "scripts.incident.analysis.enrich_epochs_github",
            ) as mock_enrich_github,
            patch(
                "scripts.incident.analysis.query_epoch_errors",
                return_value=[],
            ) as mock_errors,
            patch(
                "scripts.incident.analysis.query_epoch_haproxy",
                return_value={
                    "status_codes": [],
                    "total_requests": 0,
                    "count_5xx": 0,
                    "rate_5xx": None,
                    "requests_per_minute": None,
                    "p50_ms": None,
                    "p95_ms": None,
                    "p99_ms": None,
                    "sample_count": 0,
                },
            ) as mock_haproxy,
            patch(
                "scripts.incident.analysis.query_epoch_resources",
                return_value={
                    "mean_cpu": None,
                    "max_cpu": None,
                    "mean_mem": None,
                    "max_mem": None,
                    "mean_load": None,
                    "max_load": None,
                },
            ) as mock_resources,
            patch(
                "scripts.incident.analysis.query_epoch_pg",
                return_value=[],
            ) as mock_pg,
            patch(
                "scripts.incident.analysis.query_epoch_journal_anomalies",
                return_value=[],
            ) as mock_anomalies,
            patch(
                "scripts.incident.analysis.query_epoch_users",
                return_value={
                    "unique_logins": 0,
                    "active_users": 0,
                    "active_workspaces": 0,
                    "workspace_users": 0,
                },
            ) as mock_users,
            patch(
                "scripts.incident.analysis.query_summative_users",
                return_value={
                    "unique_logins": 0,
                    "active_users": 0,
                    "active_workspaces": 0,
                    "workspace_users": 0,
                },
            ) as mock_summative,
            patch(
                "scripts.incident.analysis.compute_trends",
                return_value=[],
            ) as mock_trends,
            patch(
                "scripts.incident.analysis.render_review_report",
                return_value="# Operational Review Report\n",
            ) as mock_render,
            patch(
                "scripts.incident.queries.query_sources",
                return_value=[],
            ) as mock_sources,
            patch(
                "scripts.incident.schema.create_schema",
            ) as mock_schema,
        ):
            result = runner.invoke(app, ["review", "--db", "test.db"])

            assert result.exit_code == 0, result.output
            mock_schema.assert_called_once()
            mock_sources.assert_called_once()
            mock_extract.assert_called_once()
            mock_enrich_journal.assert_called_once()
            mock_enrich_github.assert_called_once()
            mock_errors.assert_called_once()
            mock_haproxy.assert_called_once()
            mock_resources.assert_called_once()
            mock_pg.assert_called_once()
            mock_anomalies.assert_called_once()
            mock_users.assert_called_once()
            mock_summative.assert_called_once()
            mock_trends.assert_called_once()
            mock_render.assert_called_once()
            assert "Operational Review Report" in result.output

    @patch("scripts.incident_db.sqlite3")
    def test_missing_counts_json(self, mock_sqlite3: MagicMock) -> None:
        """AC6.2: review with no counts_json completes; no static counts in report."""
        mock_conn = MagicMock()
        mock_sqlite3.connect.return_value = mock_conn

        mock_epochs = [
            {
                "commit": "aaa111",
                "start_utc": "2026-03-15T10:00:00Z",
                "end_utc": "2026-03-15T16:00:00Z",
                "event_count": 5000,
                "duration_seconds": 21600,
                "is_crash_bounce": False,
            }
        ]

        with (
            patch(
                "scripts.incident.analysis.extract_epochs",
                return_value=mock_epochs,
            ),
            patch("scripts.incident.analysis.enrich_epochs_journal"),
            patch("scripts.incident.analysis.enrich_epochs_github"),
            patch(
                "scripts.incident.analysis.query_epoch_errors",
                return_value=[],
            ),
            patch(
                "scripts.incident.analysis.query_epoch_haproxy",
                return_value={
                    "status_codes": [],
                    "total_requests": 0,
                    "count_5xx": 0,
                    "rate_5xx": None,
                    "requests_per_minute": None,
                    "p50_ms": None,
                    "p95_ms": None,
                    "p99_ms": None,
                    "sample_count": 0,
                },
            ),
            patch(
                "scripts.incident.analysis.query_epoch_resources",
                return_value={
                    "mean_cpu": None,
                    "max_cpu": None,
                    "mean_mem": None,
                    "max_mem": None,
                    "mean_load": None,
                    "max_load": None,
                },
            ),
            patch(
                "scripts.incident.analysis.query_epoch_pg",
                return_value=[],
            ),
            patch(
                "scripts.incident.analysis.query_epoch_journal_anomalies",
                return_value=[],
            ),
            patch(
                "scripts.incident.analysis.query_epoch_users",
                return_value={
                    "unique_logins": 0,
                    "active_users": 0,
                    "active_workspaces": 0,
                    "workspace_users": 0,
                },
            ),
            patch(
                "scripts.incident.analysis.query_summative_users",
                return_value={
                    "unique_logins": 0,
                    "active_users": 0,
                    "active_workspaces": 0,
                    "workspace_users": 0,
                },
            ),
            patch(
                "scripts.incident.analysis.compute_trends",
                return_value=[],
            ),
            patch(
                "scripts.incident.analysis.render_review_report",
                return_value="# Report\nNo static counts\n",
            ) as mock_render,
            patch("scripts.incident.queries.query_sources", return_value=[]),
            patch("scripts.incident.schema.create_schema"),
        ):
            result = runner.invoke(app, ["review", "--db", "test.db"])

            assert result.exit_code == 0, result.output
            # render_review_report should be called with static_counts=None
            call_kwargs = mock_render.call_args
            assert call_kwargs[1].get("static_counts") is None or (
                len(call_kwargs[0]) >= 6 and call_kwargs[0][5] is None
            )

    @patch("scripts.incident_db.sqlite3")
    def test_no_epochs_early_exit(self, mock_sqlite3: MagicMock) -> None:
        """When no epochs are found, prints message and exits cleanly."""
        mock_conn = MagicMock()
        mock_sqlite3.connect.return_value = mock_conn

        with (
            patch(
                "scripts.incident.analysis.extract_epochs",
                return_value=[],
            ),
            patch("scripts.incident.queries.query_sources", return_value=[]),
            patch("scripts.incident.schema.create_schema"),
        ):
            result = runner.invoke(app, ["review", "--db", "test.db"])

            assert result.exit_code == 0
            assert "No epochs found" in result.output
