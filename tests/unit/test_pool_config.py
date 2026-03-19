"""Tests for detect_pool_config() pool size extraction."""

from __future__ import annotations

import sqlite3

from scripts.incident.analysis import detect_pool_config
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


class TestDetectPoolConfig:
    def test_invalidate_event(self) -> None:
        """AC3.1: Extracts pool_size and max_overflow from INVALIDATE event."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'warning',"
            " 'INVALIDATE Connection 0xdeadbeef"
            " (Pool size=10 checked_in=5 checked_out=3 overflow=2/20)')",
        )

        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )

        assert result is not None
        assert result["pool_size"] == 10
        assert result["max_overflow"] == 20

    def test_no_matching_events(self) -> None:
        """AC3.3: No INVALIDATE/QueuePool events returns None."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info', 'normal event')",
        )

        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )

        assert result is None

    def test_empty_epoch(self) -> None:
        """Empty epoch returns None."""
        conn = _make_db()
        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )
        assert result is None

    def test_partial_match_no_overflow(self) -> None:
        """Event with size but no overflow returns partial config."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'warning',"
            " 'INVALIDATE Connection 0xabc (Pool size=5)')",
        )

        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )

        assert result is not None
        assert result["pool_size"] == 5
        assert result["max_overflow"] is None

    def test_queuepool_limit_format_without_size_eq(self) -> None:
        """QueuePool limit event without size=N syntax returns None.

        The LIKE '%QueuePool limit%' SQL branch can match events that
        don't use the size=N format. When _POOL_SIZE_RE fails to match,
        the function correctly returns None.
        """
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'warning',"
            " 'QueuePool limit of size 10 overflow 20 reached')",
        )

        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )

        assert result is None

    def test_invalidate_preferred_over_queuepool(self) -> None:
        """INVALIDATE events are preferred over QueuePool via ORDER BY.

        Even when QueuePool has a lower rowid, the query orders by
        INVALIDATE match descending so the parseable event is returned.
        """
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'warning',"
            " 'QueuePool limit of size 10 overflow 20 reached')",
        )
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event)"
            " VALUES (1, '2026-03-15T10:01:00Z', 'warning',"
            " 'INVALIDATE Connection 0xabc"
            " (Pool size=10 checked_in=5 checked_out=3 overflow=2/20)')",
        )

        result = detect_pool_config(
            conn, "2026-03-15T09:00:00Z", "2026-03-15T11:00:00Z"
        )

        assert result is not None
        assert result["pool_size"] == 10
        assert result["max_overflow"] == 20
