"""Tests for CLI query commands: sources, timeline, breakdown.

Verifies:
- AC4.1: timeline interleaves HAProxy, JSONL, PG events by ts_utc
- AC4.2: breakdown produces deterministic counts between runs
- AC4.3: sources displays provenance (format, sha256, tz, timestamps)
- AC4.4: timeline with start > end exits with error
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest
from scripts.incident.queries import (
    query_breakdown,
    query_sources,
    query_timeline,
)
from scripts.incident.schema import create_schema
from scripts.incident_db import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture: pre-populated SQLite database
# ---------------------------------------------------------------------------

_SOURCES = [
    (
        1,
        "journal.json",
        "journal",
        "aabbccddee110000",
        5000,
        1710568200,
        "grimoire.drbbs.org",
        "Australia/Sydney",
        "2026-03-16T03:50:00Z",
        "2026-03-16T06:20:00Z",
    ),
    (
        2,
        "structlog.jsonl",
        "jsonl",
        "ff00112233440000",
        3000,
        1710568200,
        "grimoire.drbbs.org",
        "Australia/Sydney",
        "2026-03-16T03:50:00Z",
        "2026-03-16T06:20:00Z",
    ),
    (
        3,
        "haproxy.log",
        "haproxy",
        "9988776655440000",
        8000,
        1710568200,
        "grimoire.drbbs.org",
        "Australia/Sydney",
        "2026-03-16T03:50:00Z",
        "2026-03-16T06:20:00Z",
    ),
    (
        4,
        "postgresql.log",
        "pglog",
        "deadbeef12340000",
        2000,
        1710568200,
        "grimoire.drbbs.org",
        "Australia/Sydney",
        "2026-03-16T03:50:00Z",
        "2026-03-16T06:20:00Z",
    ),
]

# Events timed in the 16:05-16:14 AEDT window (05:05-05:14 UTC).
_JOURNAL_EVENTS = [
    (
        1,
        "2026-03-16T05:06:00Z",
        3,
        100,
        "nicegui.service",
        "Connection pool exhausted",
    ),
]
_JSONL_EVENTS = [
    (
        2,
        "2026-03-16T05:07:00Z",
        "warning",
        "INVALIDATE",
        None,
        None,
        None,
        None,
        None,
    ),
    (
        2,
        "2026-03-16T05:09:00Z",
        "error",
        "INVALIDATE",
        None,
        None,
        None,
        None,
        None,
    ),
]
_HAPROXY_EVENTS = [
    (
        3,
        "2026-03-16T05:05:30Z",
        "1.2.3.4",
        504,
        30000,
        0,
        50,
        30050,
        30100,
        "app",
        "srv1",
        "GET",
        "/upload",
        0,
    ),
    (
        3,
        "2026-03-16T05:08:00Z",
        "1.2.3.5",
        504,
        30000,
        0,
        50,
        30050,
        30100,
        "app",
        "srv1",
        "POST",
        "/api/save",
        0,
    ),
    (
        3,
        "2026-03-16T05:12:00Z",
        "1.2.3.6",
        200,
        150,
        0,
        10,
        160,
        170,
        "app",
        "srv1",
        "GET",
        "/healthz",
        0,
    ),
]
_PG_EVENTS = [
    (
        4,
        "2026-03-16T05:06:30Z",
        200,
        "FATAL",
        "too_many_connections",
        "connection limit exceeded",
        None,
        "too many connections",
    ),
    (
        4,
        "2026-03-16T05:10:00Z",
        201,
        "ERROR",
        "lock_timeout",
        "canceling statement",
        "SELECT 1",
        "lock timeout",
    ),
]

_SQL_SOURCES = (
    "INSERT INTO sources"
    " (id, filename, format, sha256, size, mtime,"
    " hostname, timezone, window_start_utc, window_end_utc)"
    " VALUES (?,?,?,?,?,?,?,?,?,?)"
)
_SQL_JOURNAL = (
    "INSERT INTO journal_events"
    " (source_id, ts_utc, priority, pid, unit, message)"
    " VALUES (?,?,?,?,?,?)"
)
_SQL_JSONL = (
    "INSERT INTO jsonl_events"
    " (source_id, ts_utc, level, event, user_id,"
    " workspace_id, request_path, exc_info, extra_json)"
    " VALUES (?,?,?,?,?,?,?,?,?)"
)
_SQL_HAPROXY = (
    "INSERT INTO haproxy_events"
    " (source_id, ts_utc, client_ip, status_code,"
    " tr_ms, tw_ms, tc_ms, tr_resp_ms, ta_ms,"
    " backend, server, method, path, bytes_read)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_SQL_PG = (
    "INSERT INTO pg_events"
    " (source_id, ts_utc, pid, level, error_type,"
    " detail, statement, message)"
    " VALUES (?,?,?,?,?,?,?,?)"
)


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """Create and return path to a pre-populated incident database."""
    db_path = tmp_path / "test_incident.db"
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    conn.executemany(_SQL_SOURCES, _SOURCES)
    conn.executemany(_SQL_JOURNAL, _JOURNAL_EVENTS)
    conn.executemany(_SQL_JSONL, _JSONL_EVENTS)
    conn.executemany(_SQL_HAPROXY, _HAPROXY_EVENTS)
    conn.executemany(_SQL_PG, _PG_EVENTS)

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Pure query function tests
# ---------------------------------------------------------------------------


class TestQuerySources:
    """AC4.3: sources returns provenance."""

    def test_returns_all_sources(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_sources(conn)
        conn.close()

        assert len(result) == 4
        formats = {r["format"] for r in result}
        assert formats == {"journal", "jsonl", "haproxy", "pglog"}

    def test_sha256_prefix_is_12_chars(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_sources(conn)
        conn.close()

        for row in result:
            assert len(row["sha256_prefix"]) == 12

    def test_event_counts(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_sources(conn)
        conn.close()

        counts = {r["format"]: r["event_count"] for r in result}
        assert counts["journal"] == 1
        assert counts["jsonl"] == 2
        assert counts["haproxy"] == 3
        assert counts["pglog"] == 2

    def test_first_last_timestamps(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_sources(conn)
        conn.close()

        haproxy = next(r for r in result if r["format"] == "haproxy")
        assert haproxy["first_ts"] == "2026-03-16T05:05:30Z"
        assert haproxy["last_ts"] == "2026-03-16T05:12:00Z"


class TestQueryTimeline:
    """AC4.1: cross-source events interleaved by ts_utc."""

    def test_returns_events_in_window(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_timeline(
            conn,
            "2026-03-16T05:05:00Z",
            "2026-03-16T05:14:00Z",
        )
        conn.close()

        # All 8 events fall within this window.
        assert len(result) == 8

    def test_events_interleaved_by_ts(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_timeline(
            conn,
            "2026-03-16T05:05:00Z",
            "2026-03-16T05:14:00Z",
        )
        conn.close()

        timestamps = [r["ts_utc"] for r in result]
        assert timestamps == sorted(timestamps)

        # Multiple sources interleaved.
        sources_seen = [r["source"] for r in result]
        assert len(set(sources_seen)) >= 3

    def test_level_filter(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_timeline(
            conn,
            "2026-03-16T05:00:00Z",
            "2026-03-16T05:15:00Z",
            level_filter="504",
        )
        conn.close()

        assert len(result) == 2
        assert all(r["level_or_status"] == "504" for r in result)

    def test_narrow_window_excludes_events(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_timeline(
            conn,
            "2026-03-16T05:05:00Z",
            "2026-03-16T05:06:15Z",
        )
        conn.close()

        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert sources == {"haproxy", "journal"}


class TestQueryBreakdown:
    """AC4.2: breakdown produces deterministic counts."""

    def test_deterministic_between_runs(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        run1 = query_breakdown(conn)
        run2 = query_breakdown(conn)
        conn.close()

        assert run1 == run2

    def test_counts_correct(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_breakdown(conn)
        conn.close()

        by_key = {(r["source"], r["level_or_status"]): r["count"] for r in result}
        assert by_key[("haproxy", "504")] == 2
        assert by_key[("haproxy", "200")] == 1
        assert by_key[("pglog", "FATAL")] == 1
        assert by_key[("pglog", "ERROR")] == 1

    def test_ordered_by_count_desc(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        result = query_breakdown(conn)
        conn.close()

        counts = [r["count"] for r in result]
        assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# CLI integration tests (via typer.testing.CliRunner)
# ---------------------------------------------------------------------------


class TestSourcesCLI:
    """AC4.3: sources CLI command."""

    def test_sources_table_output(self, populated_db: Path) -> None:
        result = runner.invoke(app, ["sources", "--db", str(populated_db)])
        assert result.exit_code == 0
        assert "journal" in result.output
        assert "haproxy" in result.output

    def test_sources_json_output(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            ["sources", "--db", str(populated_db), "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4
        assert all("format" in r for r in data)

    def test_sources_csv_output(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            ["sources", "--db", str(populated_db), "--csv"],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) == 5  # header + 4 data rows
        assert "filename" in lines[0]


class TestTimelineCLI:
    """AC4.1 + AC4.4: timeline CLI command."""

    def test_timeline_shows_interleaved_events(self, populated_db: Path) -> None:
        """AC4.1: HAProxy 504s, JSONL INVALIDATEs, PG FATALs."""
        result = runner.invoke(
            app,
            [
                "timeline",
                "--db",
                str(populated_db),
                "--start",
                "2026-03-16 16:05",
                "--end",
                "2026-03-16 16:14",
            ],
        )
        assert result.exit_code == 0
        assert "haproxy" in result.output or "504" in result.output

    def test_timeline_json(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            [
                "timeline",
                "--db",
                str(populated_db),
                "--start",
                "2026-03-16 16:05",
                "--end",
                "2026-03-16 16:14",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 8

    def test_timeline_csv(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            [
                "timeline",
                "--db",
                str(populated_db),
                "--start",
                "2026-03-16 16:05",
                "--end",
                "2026-03-16 16:14",
                "--csv",
            ],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) == 9  # header + 8 events

    def test_start_after_end_exits_with_error(self, populated_db: Path) -> None:
        """AC4.4: start > end produces error, not empty results."""
        result = runner.invoke(
            app,
            [
                "timeline",
                "--db",
                str(populated_db),
                "--start",
                "2026-03-16 17:00",
                "--end",
                "2026-03-16 16:00",
            ],
        )
        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_level_filter_cli(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            [
                "timeline",
                "--db",
                str(populated_db),
                "--start",
                "2026-03-16 16:05",
                "--end",
                "2026-03-16 16:14",
                "--level",
                "FATAL",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["level_or_status"] == "FATAL"


class TestBreakdownCLI:
    """AC4.2: breakdown CLI command."""

    def test_breakdown_deterministic(self, populated_db: Path) -> None:
        result1 = runner.invoke(app, ["breakdown", "--db", str(populated_db)])
        result2 = runner.invoke(app, ["breakdown", "--db", str(populated_db)])
        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_breakdown_json(self, populated_db: Path) -> None:
        result = runner.invoke(
            app,
            ["breakdown", "--db", str(populated_db), "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert all("count" in r for r in data)
