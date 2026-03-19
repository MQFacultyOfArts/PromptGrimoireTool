"""Tests for extract_epochs() — epoch boundary detection from commit transitions."""

from __future__ import annotations

import json
import sqlite3

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
            "abc123",
            0,
            0,
            "localhost",
            "UTC",
            "2026-03-15T00:00:00Z",
            "2026-03-16T00:00:00Z",
        ),
    )
    return conn


def _insert_jsonl(
    conn: sqlite3.Connection, ts_utc: str, commit: str, source_id: int = 1
) -> None:
    conn.execute(
        "INSERT INTO jsonl_events"
        " (source_id, ts_utc, level, event, extra_json)"
        " VALUES (?, ?, ?, ?, ?)",
        (source_id, ts_utc, "info", "test_event", json.dumps({"commit": commit})),
    )


class TestExtractEpochs:
    """AC2.1: Epoch boundary detection from commit hash transitions."""

    def test_two_commits_two_epochs(self) -> None:
        """Two distinct commit hashes produce two epochs with correct boundaries."""
        conn = _make_db()
        # Commit "aaa" — timestamps T1-T3
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:05:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "aaa")
        # Commit "bbb" — timestamps T4-T6
        _insert_jsonl(conn, "2026-03-15T10:15:00.000000Z", "bbb")
        _insert_jsonl(conn, "2026-03-15T10:20:00.000000Z", "bbb")
        _insert_jsonl(conn, "2026-03-15T10:25:00.000000Z", "bbb")

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert len(epochs) == 2

        first, second = epochs
        assert first["commit"] == "aaa"
        assert first["start_utc"] == "2026-03-15T10:00:00.000000Z"
        assert first["end_utc"] == "2026-03-15T10:10:00.000000Z"
        assert first["event_count"] == 3

        assert second["commit"] == "bbb"
        assert second["start_utc"] == "2026-03-15T10:15:00.000000Z"
        assert second["end_utc"] == "2026-03-15T10:25:00.000000Z"
        assert second["event_count"] == 3

        # First epoch ends before second begins
        assert str(first["end_utc"]) < str(second["start_utc"])

    def test_single_commit_one_epoch(self) -> None:
        """All events with same commit hash produce exactly one epoch."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:05:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "aaa")

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert len(epochs) == 1
        assert epochs[0]["commit"] == "aaa"
        assert epochs[0]["event_count"] == 3

    def test_empty_db_empty_list(self) -> None:
        """No JSONL events returns empty list."""
        conn = _make_db()

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert epochs == []

    def test_crash_bounce_detection_short(self) -> None:
        """Epoch < 300 seconds has is_crash_bounce=True."""
        conn = _make_db()
        # 60-second epoch (well under 300s threshold)
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:01:00.000000Z", "aaa")

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert len(epochs) == 1
        assert epochs[0]["duration_seconds"] == 60.0
        assert epochs[0]["is_crash_bounce"] is True

    def test_crash_bounce_detection_long(self) -> None:
        """Epoch >= 300 seconds has is_crash_bounce=False."""
        conn = _make_db()
        # 600-second epoch (well over 300s threshold)
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:10:00.000000Z", "aaa")

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert len(epochs) == 1
        assert epochs[0]["duration_seconds"] == 600.0
        assert epochs[0]["is_crash_bounce"] is False

    def test_crash_bounce_boundary_exactly_300(self) -> None:
        """Epoch exactly 300s: is_crash_bounce=False (>=300 is not a bounce)."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00.000000Z", "aaa")
        _insert_jsonl(conn, "2026-03-15T10:05:00.000000Z", "aaa")

        from scripts.incident.analysis import extract_epochs

        epochs = extract_epochs(conn)

        assert len(epochs) == 1
        assert epochs[0]["duration_seconds"] == 300.0
        assert epochs[0]["is_crash_bounce"] is False
