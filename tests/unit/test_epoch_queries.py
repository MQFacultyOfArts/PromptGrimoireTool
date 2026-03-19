"""Tests for per-epoch query functions in analysis.py."""

from __future__ import annotations

import sqlite3

from scripts.incident.analysis import (
    query_epoch_errors,
    query_epoch_haproxy,
    query_epoch_journal_anomalies,
    query_epoch_pg,
    query_epoch_resources,
)
from scripts.incident.schema import create_schema


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute(
        "INSERT INTO sources"
        " (filename, format, sha256, size, mtime,"
        "  hostname, timezone, window_start_utc, window_end_utc)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "test",
            "jsonl",
            "test_sha",
            0,
            0,
            "localhost",
            "UTC",
            "2026-03-15T00:00:00Z",
            "2026-03-16T00:00:00Z",
        ),
    )
    return conn


# ── query_epoch_errors ──────────────────────────────────────────────


class TestQueryEpochErrors:
    def test_filters_by_level(self) -> None:
        """Only error, warning, critical levels returned — not info."""
        conn = _make_db()
        for level in ("error", "warning", "critical", "info", "info"):
            conn.execute(
                "INSERT INTO jsonl_events"
                " (source_id, ts_utc, level, event)"
                " VALUES (1, '2026-03-15T10:00:00Z', ?, 'evt')",
                (level,),
            )

        result = query_epoch_errors(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        levels = {r["level"] for r in result}
        assert levels == {"error", "warning", "critical"}
        assert all(r["count"] == 1 for r in result)

    def test_per_hour_calculation(self) -> None:
        """For a 1-hour epoch, per_hour equals the raw count."""
        conn = _make_db()
        for _ in range(5):
            conn.execute(
                "INSERT INTO jsonl_events"
                " (source_id, ts_utc, level, event)"
                " VALUES (1, '2026-03-15T10:00:00Z', 'error', 'crash')",
            )

        result = query_epoch_errors(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        assert len(result) == 1
        assert result[0]["count"] == 5
        assert result[0]["per_hour"] == 5.0
        assert result[0]["is_crash_bounce"] is False

    def test_crash_bounce(self) -> None:
        """Short epoch (< 300s) sets per_hour=None and is_crash_bounce=True."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'error', 'crash')",
        )

        result = query_epoch_errors(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=120,
        )

        assert result[0]["per_hour"] is None
        assert result[0]["is_crash_bounce"] is True

    def test_groups_by_level_and_event(self) -> None:
        """Same level + different events produce separate rows."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'error', 'crash')",
        )
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'error', 'timeout')",
        )

        result = query_epoch_errors(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        events = {r["event"] for r in result}
        assert events == {"crash", "timeout"}

    def test_empty_epoch(self) -> None:
        """No matching events returns empty list."""
        conn = _make_db()
        result = query_epoch_errors(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )
        assert result == []


# ── query_epoch_haproxy ─────────────────────────────────────────────


class TestQueryEpochHaproxy:
    def test_status_distribution_and_totals(self) -> None:
        """Verify status codes, total requests, and 5xx count."""
        conn = _make_db()
        for status, ta in [(200, 50), (200, 60), (500, 200), (502, 300)]:
            conn.execute(
                "INSERT INTO haproxy_events"
                " (source_id, ts_utc, status_code, ta_ms)"
                " VALUES (1, '2026-03-15T10:00:00Z', ?, ?)",
                (status, ta),
            )

        result = query_epoch_haproxy(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        assert result["total_requests"] == 4
        assert result["count_5xx"] == 2
        # 2 5xx per hour for a 1-hour epoch
        assert result["rate_5xx"] == 2.0
        assert result["requests_per_minute"] == 4.0 / 60

        status_map = {s["status_code"]: s["count"] for s in result["status_codes"]}
        assert status_map[200] == 2
        assert status_map[500] == 1
        assert status_map[502] == 1

    def test_percentiles(self) -> None:
        """Verify p50/p95/p99 from known sorted ta_ms values."""
        conn = _make_db()
        # Insert 100 events with ta_ms = 1..100
        for i in range(1, 101):
            conn.execute(
                "INSERT INTO haproxy_events"
                " (source_id, ts_utc, status_code, ta_ms)"
                " VALUES (1, '2026-03-15T10:00:00Z', 200, ?)",
                (i,),
            )

        result = query_epoch_haproxy(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        assert result["sample_count"] == 100
        # p50 ~ 51 (OFFSET 50), p95 ~ 96 (OFFSET 95), p99 ~ 100 (OFFSET 99)
        assert result["p50_ms"] == 51
        assert result["p95_ms"] == 96
        assert result["p99_ms"] == 100

    def test_empty_epoch(self) -> None:
        """No haproxy events → zeroed totals and None percentiles."""
        conn = _make_db()
        result = query_epoch_haproxy(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=3600,
        )

        assert result["total_requests"] == 0
        assert result["count_5xx"] == 0
        assert result["p50_ms"] is None
        assert result["p95_ms"] is None
        assert result["p99_ms"] is None
        assert result["sample_count"] == 0

    def test_crash_bounce_rates(self) -> None:
        """Crash-bounce epoch has None for rate_5xx and requests_per_minute."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO haproxy_events"
            " (source_id, ts_utc, status_code, ta_ms)"
            " VALUES (1, '2026-03-15T10:00:00Z', 500, 100)",
        )

        result = query_epoch_haproxy(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
            duration_seconds=120,
        )

        assert result["rate_5xx"] is None
        assert result["requests_per_minute"] is None


# ── query_epoch_resources ───────────────────────────────────────────


class TestQueryEpochResources:
    def test_mean_and_max(self) -> None:
        """Verify mean/max aggregation from known values."""
        conn = _make_db()
        for cpu, mem, load in [(10.0, 50.0, 1.0), (20.0, 60.0, 3.0)]:
            conn.execute(
                "INSERT INTO beszel_metrics"
                " (source_id, ts_utc, cpu, mem_percent, load_1)"
                " VALUES (1, '2026-03-15T10:00:00Z', ?, ?, ?)",
                (cpu, mem, load),
            )

        result = query_epoch_resources(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["mean_cpu"] == 15.0
        assert result["max_cpu"] == 20.0
        assert result["mean_mem"] == 55.0
        assert result["max_mem"] == 60.0
        assert result["mean_load"] == 2.0
        assert result["max_load"] == 3.0

    def test_no_data(self) -> None:
        """No beszel metrics → all None."""
        conn = _make_db()
        result = query_epoch_resources(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["mean_cpu"] is None
        assert result["max_cpu"] is None
        assert result["mean_mem"] is None
        assert result["max_mem"] is None
        assert result["mean_load"] is None
        assert result["max_load"] is None


# ── query_epoch_pg ──────────────────────────────────────────────────


class TestQueryEpochPg:
    def test_grouped_counts(self) -> None:
        """Events grouped by level + error_type with correct counts."""
        conn = _make_db()
        for level, error_type in [
            ("ERROR", "UniqueViolation"),
            ("ERROR", "UniqueViolation"),
            ("ERROR", "DeadlockDetected"),
            ("WARNING", "SlowQuery"),
        ]:
            conn.execute(
                "INSERT INTO pg_events"
                " (source_id, ts_utc, level, error_type, message)"
                " VALUES (1, '2026-03-15T10:00:00Z', ?, ?, 'test')",
                (level, error_type),
            )

        result = query_epoch_pg(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        by_type = {(r["level"], r["error_type"]): r["count"] for r in result}
        assert by_type[("ERROR", "UniqueViolation")] == 2
        assert by_type[("ERROR", "DeadlockDetected")] == 1
        assert by_type[("WARNING", "SlowQuery")] == 1

    def test_empty(self) -> None:
        conn = _make_db()
        result = query_epoch_pg(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )
        assert result == []


# ── query_epoch_journal_anomalies ───────────────────────────────────


class TestQueryEpochJournalAnomalies:
    def test_filters_by_priority(self) -> None:
        """Only priority <= 3 returned (emerg=0, alert=1, crit=2, err=3)."""
        conn = _make_db()
        for priority, msg in [
            (2, "crit-msg"),
            (3, "err-msg"),
            (5, "notice-msg"),
            (6, "info-msg"),
        ]:
            conn.execute(
                "INSERT INTO journal_events"
                " (source_id, ts_utc, priority, unit, message)"
                " VALUES (1, '2026-03-15T10:00:00Z', ?, 'test.service', ?)",
                (priority, msg),
            )

        result = query_epoch_journal_anomalies(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        messages = [r["message"] for r in result]
        assert "crit-msg" in messages
        assert "err-msg" in messages
        assert "notice-msg" not in messages
        assert "info-msg" not in messages

    def test_ordered_by_timestamp(self) -> None:
        """Results are ordered by ts_utc."""
        conn = _make_db()
        for ts in [
            "2026-03-15T10:30:00Z",
            "2026-03-15T10:00:00Z",
            "2026-03-15T10:15:00Z",
        ]:
            conn.execute(
                "INSERT INTO journal_events"
                " (source_id, ts_utc, priority, unit, message)"
                " VALUES (1, ?, 2, 'test.service', 'msg')",
                (ts,),
            )

        result = query_epoch_journal_anomalies(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        timestamps = [r["ts_utc"] for r in result]
        assert timestamps == sorted(timestamps)

    def test_empty(self) -> None:
        conn = _make_db()
        result = query_epoch_journal_anomalies(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )
        assert result == []

    def test_returns_all_fields(self) -> None:
        """Each result dict has ts_utc, priority, unit, message."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO journal_events"
            " (source_id, ts_utc, priority, unit, message)"
            " VALUES (1, '2026-03-15T10:00:00Z', 2, 'kernel', 'OOM killer')",
        )

        result = query_epoch_journal_anomalies(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert len(result) == 1
        row = result[0]
        assert row["ts_utc"] == "2026-03-15T10:00:00Z"
        assert row["priority"] == 2
        assert row["unit"] == "kernel"
        assert row["message"] == "OOM killer"
