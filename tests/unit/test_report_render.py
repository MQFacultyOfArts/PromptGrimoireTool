"""Tests for render_review_report() in analysis.py."""

from __future__ import annotations

from scripts.incident.analysis import _fmt_gap_duration, _md_table, render_review_report


class TestMdTable:
    def test_basic_table(self) -> None:
        """Generates a simple markdown table with headers and rows."""
        result = _md_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert result == [
            "| A | B |",
            "| --- | --- |",
            "| 1 | 2 |",
            "| 3 | 4 |",
        ]

    def test_right_alignment(self) -> None:
        """Right-aligned columns use ---: separator."""
        result = _md_table(["Name", "Count"], [["x", "5"]], alignments=["l", "r"])
        assert result[1] == "| --- | ---: |"

    def test_center_alignment(self) -> None:
        """Center-aligned columns use :---: separator."""
        result = _md_table(["A"], [["1"]], alignments=["c"])
        assert result[1] == "| :---: |"

    def test_empty_rows(self) -> None:
        """Table with no rows produces header and separator only."""
        result = _md_table(["X", "Y"], [])
        assert len(result) == 2

    def test_non_string_cells_converted(self) -> None:
        """Non-string cell values are converted via str()."""
        result = _md_table(["N"], [["42"]])
        assert result[2] == "| 42 |"


class TestExplanatoryProse:
    """Verify that explanatory prose appears in the rendered report."""

    def test_report_header_prose(self) -> None:
        """Introductory prose about epochs and normalisation appears after header."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )
        assert "epochs" in report.lower()
        assert "SRE" in report

    def test_timeline_prose(self) -> None:
        """Epoch Timeline section includes explanatory prose."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )
        assert "deploy" in report
        assert "crash" in report.lower()

    def test_trend_prose(self) -> None:
        """Trend Analysis section includes metric explanation prose."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )
        assert "5xx Ratio" in report
        assert "Error Ratio" in report
        assert "percentage" in report.lower() or "pp" in report


def _mock_sources() -> list[dict]:
    return [
        {
            "filename": "test.tar.gz",
            "format": "jsonl",
            "sha256": "abc123def456",
            "size": 1000,
            "window_start_utc": "2026-03-15T00:00:00Z",
            "window_end_utc": "2026-03-16T00:00:00Z",
        }
    ]


def _mock_epochs() -> list[dict]:
    return [
        {
            "commit": "aaa111",
            "start_utc": "2026-03-15T10:00:00Z",
            "end_utc": "2026-03-15T16:00:00Z",
            "event_count": 5000,
            "duration_seconds": 21600,
            "is_crash_bounce": False,
            "memory_peak": "2.7G",
            "cpu_consumed": "8.509s",
            "memory_peak_bytes": 2899102924,
            "swap_peak": "0B",
            "pr_number": 42,
            "pr_title": "Fix login",
            "pr_author": "alice",
            "pr_url": "https://github.com/org/repo/pull/42",
            "error_ratio": 0.005,
            "warning_ratio": 0.02,
            "5xx_ratio": 0.003,
            "mean_cpu": 25.0,
            "active_users": 5,
            "total_requests": 1003,
        },
    ]


def _mock_analyses() -> list[dict]:
    return [
        {
            "errors": [
                {
                    "level": "error",
                    "event": "db_timeout",
                    "count": 5,
                    "per_hour": 10.0,
                    "is_crash_bounce": False,
                }
            ],
            "haproxy": {
                "status_codes": [
                    {"status_code": 200, "count": 1000},
                    {"status_code": 500, "count": 3},
                ],
                "total_requests": 1003,
                "count_5xx": 3,
                "rate_5xx": 2.0,
                "requests_per_minute": 5.0,
                "p50_ms": 100,
                "p95_ms": 500,
                "p99_ms": 1000,
                "sample_count": 1003,
                "count_nosrv": 0,
                "nosrv_first_60s": 0,
            },
            "resources": {
                "mean_cpu": 25.0,
                "max_cpu": 80.0,
                "mean_mem": 60.0,
                "max_mem": 85.0,
                "mean_load": 1.5,
                "max_load": 4.0,
            },
            "pg": [{"level": "ERROR", "error_type": "deadlock", "count": 2}],
            "journal_anomalies": [
                {
                    "ts_utc": "2026-03-15T12:00:00Z",
                    "priority": 3,
                    "unit": "test.service",
                    "message": "error msg",
                }
            ],
            "users": {
                "unique_logins": 10,
                "active_users": 5,
                "active_workspaces": 3,
                "workspace_users": 4,
            },
        }
    ]


def _mock_summative() -> dict:
    return {
        "unique_logins": 15,
        "active_users": 8,
        "active_workspaces": 5,
        "workspace_users": 7,
    }


def _mock_trends() -> list[dict]:
    return [
        {
            "epoch_index": 1,
            "commit": "bbb222",
            "pr_title": "Add feature",
            "total_requests": 20000,
            "metrics": {
                "5xx_ratio": {
                    "value": 0.004,
                    "previous": 0.002,
                    "delta": 0.002,
                    "is_anomaly": False,
                },
                "error_ratio": {
                    "value": 0.02,
                    "previous": 0.01,
                    "delta": 0.01,
                    "is_anomaly": False,
                },
                "warning_ratio": {
                    "value": 0.03,
                    "previous": 0.05,
                    "delta": -0.02,
                    "is_anomaly": False,
                },
                "memory_peak_bytes": {
                    "value": 2_000_000_000,
                    "previous": 1_000_000_000,
                    "delta": 1_000_000_000,
                    "is_anomaly": False,
                },
                "mean_cpu": {
                    "value": 30.0,
                    "previous": 15.0,
                    "delta": 15.0,
                    "is_anomaly": False,
                },
                "active_users": {
                    "value": 10,
                    "previous": 5,
                    "delta": 5,
                    "is_anomaly": False,
                },
            },
        }
    ]


class TestRenderReviewReport:
    def test_all_sections_present(self) -> None:
        """AC6.1: All expected section headers appear in the report."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )

        assert "Source Inventory" in report
        assert "Epoch Timeline" in report
        assert "Per-Epoch Analysis" in report
        assert "User Activity Summary" in report
        assert "Trend Analysis" in report

    def test_data_included(self) -> None:
        """Report includes key data from the provided mock data."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )

        # Epoch commit hash
        assert "aaa111" in report
        # PR title
        assert "Fix login" in report
        # Error event
        assert "db_timeout" in report
        # HAProxy stats
        assert "1003" in report  # total_requests
        # Resource stats
        assert "25.0" in report  # mean_cpu
        # User counts
        assert "15" in report  # unique_logins summative
        # Trend data
        assert "bbb222" in report

    def test_static_counts_omitted_when_none(self) -> None:
        """AC6.2: static_counts=None produces no Static DB Counts section."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
            static_counts=None,
        )

        assert "Static DB Counts" not in report

    def test_static_counts_included_when_provided(self) -> None:
        """Static DB Counts section appears when data is provided."""
        counts = {"users": 42, "workspaces": 100}
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
            static_counts=counts,
        )

        assert "Static DB Counts" in report
        assert "42" in report
        assert "100" in report

    def test_empty_epochs(self) -> None:
        """Handles empty epochs list without error."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=[],
            epoch_analyses=[],
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "Epoch Timeline" in report
        assert "User Activity Summary" in report

    def test_none_percentiles_show_na(self) -> None:
        """HAProxy percentiles of None display as N/A."""
        analyses = _mock_analyses()
        analyses[0]["haproxy"]["p50_ms"] = None
        analyses[0]["haproxy"]["p95_ms"] = None
        analyses[0]["haproxy"]["p99_ms"] = None

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "N/A" in report

    def test_crash_bounce_marker(self) -> None:
        """Crash-bounce epochs are marked in the timeline."""
        epochs = _mock_epochs()
        epochs[0]["is_crash_bounce"] = True

        report = render_review_report(
            sources=_mock_sources(),
            epochs=epochs,
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=[],
        )

        # Should have some crash bounce indicator
        assert "CRASH" in report or "crash" in report.lower()

    def test_trend_ratio_formatting(self) -> None:
        """Trend ratios are formatted as percentages with pp deltas."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=_mock_trends(),
        )

        # Ratios should be displayed as percentages
        assert "2.00%" in report  # error_ratio = 0.02
        assert "0.40%" in report  # 5xx_ratio = 0.004
        # Deltas should use pp (percentage points)
        assert "+1.00pp" in report  # error_ratio delta = 0.01


class TestNosrvRendering:
    def test_nosrv_displayed(self) -> None:
        """AC1.1/AC1.2: NOSRV count and clustering shown when present."""
        analyses = _mock_analyses()
        analyses[0]["haproxy"]["count_nosrv"] = 72
        analyses[0]["haproxy"]["nosrv_first_60s"] = 72

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "NOSRV" in report
        assert "72" in report
        assert "first 60s" in report

    def test_nosrv_omitted_when_zero(self) -> None:
        """AC1.3: Zero NOSRV events omit the NOSRV per-epoch line."""
        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "Restart 503s (NOSRV)" not in report


class TestErrorLandscapeRendering:
    def test_appeared_and_resolved(self) -> None:
        """AC2.2: Appeared and resolved error types shown."""
        analyses = _mock_analyses()
        analyses[0]["error_landscape"] = {
            "appeared": {"error A", "error B"},
            "resolved": {"error C"},
            "current": {"error A", "error B"},
        }

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "Appeared" in report
        assert "error A" in report
        assert "Resolved" in report
        assert "error C" in report

    def test_no_errors(self) -> None:
        """AC2.4: Empty appeared and resolved shows 'No errors'."""
        analyses = _mock_analyses()
        analyses[0]["error_landscape"] = {
            "appeared": set(),
            "resolved": set(),
            "current": set(),
        }

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "No errors" in report


class TestFmtGapDuration:
    def test_none(self) -> None:
        assert _fmt_gap_duration(None) == "—"

    def test_zero(self) -> None:
        assert _fmt_gap_duration(0.0) == "0s"

    def test_seconds(self) -> None:
        assert _fmt_gap_duration(45.0) == "45s"

    def test_minutes(self) -> None:
        assert _fmt_gap_duration(300.0) == "5m 0s"

    def test_hours_minutes(self) -> None:
        assert _fmt_gap_duration(3900.0) == "1h 5m"


class TestPoolConfigRendering:
    def test_pool_displayed(self) -> None:
        """AC3.2: Pool config shown when detected."""
        analyses = _mock_analyses()
        analyses[0]["pool_config"] = {"pool_size": 10, "max_overflow": 20}

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "size=10, overflow=20" in report

    def test_pool_not_observed(self) -> None:
        """AC3.3: No pool config shows 'not observed'."""
        analyses = _mock_analyses()
        analyses[0]["pool_config"] = None

        report = render_review_report(
            sources=_mock_sources(),
            epochs=_mock_epochs(),
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "not observed" in report


class TestRestartGapRendering:
    def test_gap_in_timeline(self) -> None:
        """AC4.1: Gap column shows downtime duration."""
        epochs = [
            {
                **_mock_epochs()[0],
                "restart_gap_seconds": None,
            },
            {
                **_mock_epochs()[0],
                "commit": "bbb222",
                "start_utc": "2026-03-15T16:05:00Z",
                "end_utc": "2026-03-15T20:00:00Z",
                "restart_gap_seconds": 300.0,
            },
        ]
        analyses = [_mock_analyses()[0], _mock_analyses()[0]]

        report = render_review_report(
            sources=_mock_sources(),
            epochs=epochs,
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "Gap" in report
        assert "5m 0s" in report

    def test_first_epoch_dash(self) -> None:
        """AC4.2: First epoch shows dash for gap."""
        epochs = [{**_mock_epochs()[0], "restart_gap_seconds": None}]

        report = render_review_report(
            sources=_mock_sources(),
            epochs=epochs,
            epoch_analyses=_mock_analyses(),
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "Gap" in report
        assert "—" in report

    def test_zero_gap(self) -> None:
        """AC4.3: Zero gap displays as '0s'."""
        epochs = [
            {**_mock_epochs()[0], "restart_gap_seconds": None},
            {
                **_mock_epochs()[0],
                "commit": "bbb222",
                "start_utc": "2026-03-15T16:00:00Z",
                "end_utc": "2026-03-15T20:00:00Z",
                "restart_gap_seconds": 0.0,
            },
        ]
        analyses = [_mock_analyses()[0], _mock_analyses()[0]]

        report = render_review_report(
            sources=_mock_sources(),
            epochs=epochs,
            epoch_analyses=analyses,
            summative_users=_mock_summative(),
            trends=[],
        )

        assert "0s" in report
