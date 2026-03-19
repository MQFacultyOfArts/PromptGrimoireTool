"""Tests for epoch enrichment functions (journal + GitHub)."""

from __future__ import annotations

import json
import sqlite3

from scripts.incident.analysis import (
    _parse_memory_bytes,
    enrich_epochs_github,
    enrich_epochs_journal,
    extract_epochs,
)
from scripts.incident.schema import create_schema

_SOURCE_INSERT = (
    "INSERT INTO sources"
    " (filename, format, sha256, size, mtime,"
    "  hostname, timezone, window_start_utc, window_end_utc)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_SOURCE_VALS = (
    "test",
    "jsonl",
    "abc123",
    0,
    0,
    "localhost",
    "UTC",
    "2026-03-15T00:00:00Z",
    "2026-03-16T00:00:00Z",
)


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute(_SOURCE_INSERT, _SOURCE_VALS)
    return conn


def _insert_jsonl(
    conn: sqlite3.Connection,
    ts_utc: str,
    commit: str,
    source_id: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO jsonl_events"
        " (source_id, ts_utc, level, event, extra_json)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            source_id,
            ts_utc,
            "info",
            "test_event",
            json.dumps({"commit": commit}),
        ),
    )


def _insert_journal(
    conn: sqlite3.Connection,
    ts_utc: str,
    message: str,
    source_id: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO journal_events"
        " (source_id, ts_utc, priority, message)"
        " VALUES (?, ?, ?, ?)",
        (source_id, ts_utc, 6, message),
    )


def _insert_github(
    conn: sqlite3.Connection,
    ts_utc: str,
    pr_number: int,
    title: str,
    author: str,
    commit_oid: str,
    url: str,
    source_id: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO github_events"
        " (source_id, ts_utc, pr_number, title,"
        "  author, commit_oid, url)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source_id, ts_utc, pr_number, title, author, commit_oid, url),
    )


class TestEnrichEpochsJournal:
    """AC2.2: Journal Consumed message enrichment."""

    def test_consumed_message_matched(self) -> None:
        """Journal Consumed message near epoch end is parsed."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "aaa")

        consumed_msg = (
            "promptgrimoire.service:"
            " Consumed 8.509s CPU time,"
            " 366.5M memory peak,"
            " 0B memory swap peak."
        )
        _insert_journal(
            conn,
            "2026-03-15T10:10:05.000000Z",
            consumed_msg,
        )

        epochs = extract_epochs(conn)
        enrich_epochs_journal(conn, epochs)

        assert epochs[0]["cpu_consumed"] == "8.509s"
        assert epochs[0]["memory_peak"] == "366.5M"
        assert epochs[0]["swap_peak"] == "0B"
        assert epochs[0]["memory_peak_bytes"] == 384303104

    def test_no_matching_journal_message(self) -> None:
        """Epoch with no nearby Consumed message gets None fields."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "aaa")

        epochs = extract_epochs(conn)
        enrich_epochs_journal(conn, epochs)

        assert epochs[0]["cpu_consumed"] is None
        assert epochs[0]["memory_peak"] is None
        assert epochs[0]["swap_peak"] is None
        assert epochs[0]["memory_peak_bytes"] is None

    def test_epoch_end_correction(self) -> None:
        """Journal ts later than epoch end updates end_utc."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:01:00.000000Z", "aaa")

        # Journal event 30s after last JSONL event
        consumed_msg = (
            "Consumed 1.0s CPU time, 100.0M memory peak, 0B memory swap peak."
        )
        _insert_journal(
            conn,
            "2026-03-15T10:01:30.000000Z",
            consumed_msg,
        )

        epochs = extract_epochs(conn)
        original_end = epochs[0]["end_utc"]
        enrich_epochs_journal(conn, epochs)

        # End should be updated to journal timestamp
        assert epochs[0]["end_utc"] == "2026-03-15T10:01:30.000000Z"
        assert epochs[0]["end_utc"] != original_end
        # Duration recalculated: 90 seconds
        assert epochs[0]["duration_seconds"] == 90.0
        assert epochs[0]["is_crash_bounce"] is True


class TestParseMemoryBytes:
    """Unit tests for _parse_memory_bytes()."""

    def test_gigabytes(self) -> None:
        assert _parse_memory_bytes("2.7G") == 2899102924

    def test_megabytes(self) -> None:
        assert _parse_memory_bytes("366.5M") == 384303104

    def test_zero_bytes(self) -> None:
        assert _parse_memory_bytes("0B") == 0

    def test_kilobytes(self) -> None:
        assert _parse_memory_bytes("512K") == 524288

    def test_invalid_returns_none(self) -> None:
        assert _parse_memory_bytes("garbage") is None


class TestEnrichEpochsGithub:
    """AC2.3 / AC2.4: GitHub PR metadata enrichment."""

    def test_commit_hash_prefix_match(self) -> None:
        """Short commit prefix matches full commit_oid."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "ba70f4fa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "ba70f4fa")

        full_oid = "ba70f4fa1234567890abcdef1234567890abcdef"
        _insert_github(
            conn,
            "2026-03-15T09:00:00.000000Z",
            pr_number=42,
            title="Fix the thing",
            author="dev-person",
            commit_oid=full_oid,
            url="https://github.com/org/repo/pull/42",
        )

        epochs = extract_epochs(conn)
        enrich_epochs_github(conn, epochs)

        assert epochs[0]["pr_number"] == 42
        assert epochs[0]["pr_title"] == "Fix the thing"
        assert epochs[0]["pr_author"] == "dev-person"
        assert epochs[0]["pr_url"] == ("https://github.com/org/repo/pull/42")

    def test_no_matching_pr(self) -> None:
        """Unmatched commit gets pr_title='no PR' and None fields."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "deadbeef")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "deadbeef")

        epochs = extract_epochs(conn)
        enrich_epochs_github(conn, epochs)

        assert epochs[0]["pr_number"] is None
        assert epochs[0]["pr_title"] == "no PR"
        assert epochs[0]["pr_author"] is None
        assert epochs[0]["pr_url"] is None


def _make_epoch(commit: str, start_utc: str, end_utc: str) -> dict:
    """Build a minimal epoch dict for restart classification tests."""
    from datetime import datetime

    dt_start = datetime.fromisoformat(start_utc)
    dt_end = datetime.fromisoformat(end_utc)
    duration = (dt_end - dt_start).total_seconds()
    return {
        "commit": commit,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "event_count": 100,
        "duration_seconds": duration,
        "is_crash_bounce": duration < 300,
    }


class TestEnrichRestartReasons:
    """Tests for restart reason classification."""

    def test_first_epoch_is_first(self) -> None:
        from scripts.incident.analysis import RESTART_FIRST, enrich_restart_reasons

        conn = _make_db()
        epochs = [_make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z")]
        enrich_restart_reasons(conn, epochs)
        assert epochs[0]["restart_reason"] == RESTART_FIRST

    def test_commit_change_is_deploy(self) -> None:
        from scripts.incident.analysis import RESTART_DEPLOY, enrich_restart_reasons

        conn = _make_db()
        # Add a Stopping message in the gap
        conn.execute(
            "INSERT INTO journal_events (source_id, ts_utc, priority, message)"
            " VALUES (1, '2026-03-15T12:00:30Z', 6,"
            " 'Stopping promptgrimoire.service')",
        )
        epochs = [
            _make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z"),
            _make_epoch("bbb", "2026-03-15T12:01:00Z", "2026-03-15T14:00:00Z"),
        ]
        enrich_restart_reasons(conn, epochs)
        assert epochs[1]["restart_reason"] == RESTART_DEPLOY

    def test_same_commit_clean_shutdown_is_manual(self) -> None:
        from scripts.incident.analysis import RESTART_MANUAL, enrich_restart_reasons

        conn = _make_db()
        conn.execute(
            "INSERT INTO journal_events (source_id, ts_utc, priority, message)"
            " VALUES (1, '2026-03-15T12:00:30Z', 6,"
            " 'Stopping promptgrimoire.service')",
        )
        epochs = [
            _make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z"),
            _make_epoch("aaa", "2026-03-15T12:01:00Z", "2026-03-15T14:00:00Z"),
        ]
        enrich_restart_reasons(conn, epochs)
        assert epochs[1]["restart_reason"] == RESTART_MANUAL

    def test_crash_exit_code_is_crash(self) -> None:
        from scripts.incident.analysis import RESTART_CRASH, enrich_restart_reasons

        conn = _make_db()
        conn.execute(
            "INSERT INTO journal_events (source_id, ts_utc, priority, message)"
            " VALUES (1, '2026-03-15T12:00:30Z', 3,"
            " 'Main process exited, code=exited, status=226/NAMESPACE')",
        )
        epochs = [
            _make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z"),
            _make_epoch("aaa", "2026-03-15T12:01:00Z", "2026-03-15T14:00:00Z"),
        ]
        enrich_restart_reasons(conn, epochs)
        assert epochs[1]["restart_reason"] == RESTART_CRASH

    def test_oom_kill_detected(self) -> None:
        from scripts.incident.analysis import RESTART_OOM, enrich_restart_reasons

        conn = _make_db()
        conn.execute(
            "INSERT INTO journal_events (source_id, ts_utc, priority, message)"
            " VALUES (1, '2026-03-15T12:00:30Z', 3,"
            " 'Main process exited, code=killed, status=9/KILL')",
        )
        epochs = [
            _make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z"),
            _make_epoch("aaa", "2026-03-15T12:01:00Z", "2026-03-15T14:00:00Z"),
        ]
        enrich_restart_reasons(conn, epochs)
        assert epochs[1]["restart_reason"] == RESTART_OOM

    def test_no_journal_evidence_is_unknown(self) -> None:
        from scripts.incident.analysis import RESTART_UNKNOWN, enrich_restart_reasons

        conn = _make_db()
        # No journal events in the gap at all
        epochs = [
            _make_epoch("aaa", "2026-03-15T10:00:00Z", "2026-03-15T12:00:00Z"),
            _make_epoch("aaa", "2026-03-15T12:01:00Z", "2026-03-15T14:00:00Z"),
        ]
        enrich_restart_reasons(conn, epochs)
        assert epochs[1]["restart_reason"] == RESTART_UNKNOWN
