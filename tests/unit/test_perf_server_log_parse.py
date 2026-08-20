"""Unit tests for the perf probes' server-log aggregation.

``summarise_page_load_profile`` turns raw structlog JSONL lines into the
``server_page_load`` block the soak and cram probes write to their diag
JSON.  It is the only place the probes' server-side latency numbers come
from, so its window filtering, coverage reporting and percentile
arithmetic are checked here against hand-computed expectations rather
than against the parser's own output.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from tests.e2e.perf_reporting import find_server_jsonl, summarise_page_load_profile

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

WINDOW_START = datetime(2026, 8, 19, 5, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 19, 5, 30, 0, tzinfo=UTC)

SERVER_PID = 4169473
OTHER_PID = 3792888


def _line(**fields: object) -> str:
    """Serialise one structlog-shaped JSON log line."""
    return json.dumps(fields)


def _profile(
    timestamp: str,
    total_ms: float,
    *,
    pid: int = SERVER_PID,
    request_path: str | None = "/annotation",
    db_resolve_ms: float = 1.0,
) -> str:
    """One ``page_load_profile`` line as the annotation page emits it."""
    return _line(
        event="page_load_profile",
        timestamp=timestamp,
        pid=pid,
        request_path=request_path,
        total_ms=total_ms,
        db_resolve_ms=db_resolve_ms,
        tab_panels_ms=5.0,
        branch="perf/soak-full-crud",
        commit="e6fd6b20",
        workspace_id="bfc9d81d-2101-4037-8a3d-18a06ecf4432",
    )


def _summarise(lines: list[str]) -> dict:
    """Run the aggregation over the default window."""
    return summarise_page_load_profile(
        lines,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
    )


class TestWindowFiltering:
    """Only page loads inside the run window feed the aggregate."""

    def test_events_outside_the_window_are_excluded_and_counted(self) -> None:
        """Before/after events are reported separately, not aggregated."""
        result = _summarise(
            [
                _profile("2026-08-19T04:59:59.000000Z", 9000.0),
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
                _profile("2026-08-19T05:29:59.000000Z", 200.0),
                _profile("2026-08-19T05:30:01.000000Z", 8000.0),
            ]
        )

        assert result["count"] == 2
        assert result["total_ms"]["max"] == 200.0
        assert result["coverage"]["profiles_before_window"] == 1
        assert result["coverage"]["profiles_after_window"] == 1

    def test_non_annotation_paths_are_excluded_and_counted(self) -> None:
        """A profile from another route never enters the latency stats."""
        result = _summarise(
            [
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
                _profile(
                    "2026-08-19T05:00:02.000000Z", 7000.0, request_path="/navigator"
                ),
            ]
        )

        assert result["count"] == 1
        assert result["total_ms"]["max"] == 100.0
        assert result["coverage"]["profiles_other_path"] == 1

    def test_null_request_path_is_still_aggregated(self) -> None:
        """An unbound request_path must not silently empty the aggregate.

        The path filter exists to drop other routes.  If a future build
        stops binding request_path, dropping those events would report a
        confident zero instead of the loads that actually happened.
        """
        result = _summarise(
            [_profile("2026-08-19T05:00:01.000000Z", 100.0, request_path=None)]
        )

        assert result["count"] == 1
        assert result["coverage"]["profiles_other_path"] == 0


class TestLocatingTheServerLog:
    """Which file was read, and how confidently it was identified.

    The two strategies are not equally trustworthy, so the run JSON
    records which one applied: a glob fallback can land on a previous
    run's or another branch's log and produce plausible numbers with no
    other symptom.
    """

    def test_startup_line_names_the_measured_process_log(self, tmp_path: Path) -> None:
        """setup_logging()'s own line is the authoritative locator."""
        jsonl = tmp_path / "promptgrimoire-somebranch.jsonl"
        jsonl.write_text("", encoding="utf-8")
        stdout_log = tmp_path / "test-e2e-server.log"
        stdout_log.write_text(
            _line(
                event=f"Structured logging configured. Log file: {jsonl}",
                timestamp="2026-08-19T05:00:00.000000Z",
            )
            + "\n",
            encoding="utf-8",
        )

        assert find_server_jsonl(stdout_log) == (jsonl, "startup_line")

    def test_missing_stdout_log_falls_back_to_glob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the startup line the newest logs/ file is a guess."""
        sessions = tmp_path / "logs" / "sessions"
        sessions.mkdir(parents=True)
        guessed = sessions / "promptgrimoire-otherbranch.jsonl"
        guessed.write_text("", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        found, strategy = find_server_jsonl(tmp_path / "absent.log")

        # The fallback globs a relative "logs/", so it returns a
        # cwd-relative path where the startup line returns an absolute one.
        assert found is not None
        assert found.resolve() == guessed.resolve()
        assert strategy == "glob_fallback"

    def test_no_log_anywhere_reports_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing log is a gap in the evidence, not a quiet None."""
        monkeypatch.chdir(tmp_path)

        assert find_server_jsonl(tmp_path / "absent.log") == (None, "not_found")


class TestPercentiles:
    """Latency statistics are nearest-rank over the in-window values."""

    def test_stats_match_hand_computed_values(self) -> None:
        """10 loads of 10..100 ms: p50=50, p95=100, max=100, mean=55."""
        lines = [
            _profile(f"2026-08-19T05:00:{second:02d}.000000Z", float(second * 10))
            for second in range(1, 11)
        ]

        stats = _summarise(lines)["total_ms"]

        assert stats == {"p50": 50.0, "p95": 100.0, "max": 100.0, "mean": 55.0}

    def test_phase_columns_are_aggregated_separately(self) -> None:
        """db_resolve_ms carries its own stats, not total_ms's."""
        lines = [
            _profile("2026-08-19T05:00:01.000000Z", 100.0, db_resolve_ms=20.0),
            _profile("2026-08-19T05:00:02.000000Z", 300.0, db_resolve_ms=40.0),
        ]

        result = _summarise(lines)

        assert result["total_ms"]["max"] == 300.0
        assert result["db_resolve_ms"]["max"] == 40.0

    def test_no_events_yields_null_stats_not_zero(self) -> None:
        """Zero samples must not render as a 0 ms page load."""
        result = _summarise([])

        assert result["count"] == 0
        assert result["total_ms"] is None


class TestCoverage:
    """The aggregate states what the scan could and could not see."""

    def test_window_start_covered_when_log_predates_the_run(self) -> None:
        """A log line older than the window proves nothing was rotated away."""
        result = _summarise(
            [
                _line(event="db_pool_mode", timestamp="2026-08-19T04:58:00.123456Z"),
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
            ]
        )

        assert result["coverage"]["window_start_covered"] is True
        assert result["coverage"]["earliest_log_ts"] == "2026-08-19T04:58:00.123456Z"

    def test_earliest_log_ts_renders_as_iso_utc(self) -> None:
        """Timestamps are re-rendered, so a whole second loses ".000000".

        ``datetime.isoformat()`` omits a zero microsecond field.  Pinned
        here because the coverage timestamps are read by eye against raw
        log lines, where the two spellings sit side by side.
        """
        result = _summarise(
            [_profile("2026-08-19T04:58:00.000000Z", 100.0)],
        )

        assert result["coverage"]["earliest_log_ts"] == "2026-08-19T04:58:00Z"

    def test_window_start_uncovered_when_rotation_ate_the_head(self) -> None:
        """Oldest retained line inside the window: count is a lower bound."""
        result = _summarise([_profile("2026-08-19T05:10:00.000000Z", 100.0)])

        assert result["coverage"]["window_start_covered"] is False

    def test_malformed_lines_are_counted_not_fatal(self) -> None:
        """A truncated line (rotation tear) must not abort the scan."""
        result = _summarise(
            [
                '{"event": "page_load_profile", "timesta',
                "",
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
            ]
        )

        assert result["count"] == 1
        assert result["coverage"]["unparsed_lines"] == 1
        assert result["coverage"]["lines_scanned"] == 3


class TestProvenance:
    """Run provenance is read back off the measured process's own lines."""

    def test_server_pid_branch_and_commit_come_from_the_events(self) -> None:
        """The dominant in-window pid identifies the measured server."""
        result = _summarise(
            [
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
                _profile("2026-08-19T05:00:02.000000Z", 100.0),
                _profile("2026-08-19T05:00:03.000000Z", 100.0, pid=OTHER_PID),
            ]
        )

        assert result["server_pid"] == SERVER_PID
        assert result["pids"] == {str(SERVER_PID): 2, str(OTHER_PID): 1}
        assert result["server_branch"] == "perf/soak-full-crud"
        assert result["server_commit"] == "e6fd6b20"

    def test_pool_mode_is_taken_from_the_server_pid_before_the_window(self) -> None:
        """db_pool_mode is emitted at server start, ahead of the window."""
        result = _summarise(
            [
                _line(
                    event="db_pool_mode",
                    timestamp="2026-08-19T04:58:00.000000Z",
                    pid=OTHER_PID,
                    mode="NullPool",
                    reason="test",
                ),
                _line(
                    event="db_pool_mode",
                    timestamp="2026-08-19T04:59:00.000000Z",
                    pid=SERVER_PID,
                    mode="QueuePool",
                    reason="pool_fidelity",
                ),
                _profile("2026-08-19T05:00:01.000000Z", 100.0),
            ]
        )

        assert result["pool_mode"]["mode"] == "QueuePool"
        assert result["pool_mode"]["reason"] == "pool_fidelity"

    def test_snapshot_served_events_in_window_are_counted(self) -> None:
        """Bundle deliveries observed server-side, not inferred from env.

        The snapshot service logs to the same JSONL file from its own
        pid, so a nonzero count is evidence the flag was live for this
        run rather than merely set in the harness's environment.
        """
        result = _summarise(
            [
                _line(
                    event="snapshot_served",
                    timestamp="2026-08-19T04:00:00.000000Z",
                    pid=99,
                ),
                _line(
                    event="snapshot_served",
                    timestamp="2026-08-19T05:00:01.000000Z",
                    pid=99,
                ),
                _line(
                    event="snapshot_served",
                    timestamp="2026-08-19T05:00:02.000000Z",
                    pid=99,
                ),
                _profile("2026-08-19T05:00:03.000000Z", 100.0),
            ]
        )

        assert result["snapshot_served"] == 2
