"""Tests for user activity metrics and static counts in analysis.py."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest
from scripts.incident.analysis import (
    LOGIN_EVENT_PATTERN,
    load_static_counts,
    query_epoch_users,
    query_summative_users,
)
from scripts.incident.schema import create_schema

if TYPE_CHECKING:
    from pathlib import Path


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


# ── query_epoch_users ──────────────────────────────────────────────


class TestQueryEpochUsers:
    def test_distinct_counts(self) -> None:
        """Verify all four distinct count metrics with known data."""
        conn = _make_db()
        # User A: login event with workspace
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id, workspace_id)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
            " 'Login successful (magic_link)', 'user-a', 'ws-1')",
        )
        # User A again (same user, should not double-count)
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id, workspace_id)"
            " VALUES (1, '2026-03-15T10:05:00Z', 'info',"
            " 'Page loaded', 'user-a', 'ws-1')",
        )
        # User B: non-login event with workspace
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id, workspace_id)"
            " VALUES (1, '2026-03-15T10:10:00Z', 'info',"
            " 'Page loaded', 'user-b', 'ws-2')",
        )
        # User C: login event, no workspace
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T10:15:00Z', 'info',"
            " 'Login successful (passkey)', 'user-c')",
        )

        result = query_epoch_users(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        # Only user-a and user-c had login events
        assert result["unique_logins"] == 2
        # All three users were active
        assert result["active_users"] == 3
        # ws-1 and ws-2
        assert result["active_workspaces"] == 2
        # user-a (ws-1) and user-b (ws-2); user-c has no workspace
        assert result["workspace_users"] == 2

    def test_login_pattern_filtering(self) -> None:
        """Only events matching 'Login successful%' count as logins."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
            " 'Login successful (magic_link)', 'user-a')",
        )
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T10:01:00Z', 'info',"
            " 'Login failed', 'user-b')",
        )
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T10:02:00Z', 'info',"
            " 'Page loaded', 'user-c')",
        )

        result = query_epoch_users(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["unique_logins"] == 1

    def test_null_user_excluded(self) -> None:
        """Events with NULL user_id are excluded from user counts."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, workspace_id)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
            " 'Login successful (anon)', 'ws-1')",
        )

        result = query_epoch_users(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["unique_logins"] == 0
        assert result["active_users"] == 0
        assert result["workspace_users"] == 0
        # workspace still counted
        assert result["active_workspaces"] == 1

    def test_empty_epoch(self) -> None:
        """No events in window returns all zeros."""
        conn = _make_db()

        result = query_epoch_users(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["unique_logins"] == 0
        assert result["active_users"] == 0
        assert result["active_workspaces"] == 0
        assert result["workspace_users"] == 0

    def test_time_window_filtering(self) -> None:
        """Events outside the time window are excluded."""
        conn = _make_db()
        # Inside window
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
            " 'Page loaded', 'user-a')",
        )
        # Outside window
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id)"
            " VALUES (1, '2026-03-15T12:00:00Z', 'info',"
            " 'Page loaded', 'user-b')",
        )

        result = query_epoch_users(
            conn,
            "2026-03-15T09:00:00Z",
            "2026-03-15T11:00:00Z",
        )

        assert result["active_users"] == 1


# ── query_summative_users ──────────────────────────────────────────


class TestQuerySummativeUsers:
    def test_user_counted_once_across_ranges(self) -> None:
        """User active in two different time ranges counted once."""
        conn = _make_db()
        # Same user, two different timestamps
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id, workspace_id)"
            " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
            " 'Login successful (magic_link)', 'user-a', 'ws-1')",
        )
        conn.execute(
            "INSERT INTO jsonl_events"
            " (source_id, ts_utc, level, event, user_id, workspace_id)"
            " VALUES (1, '2026-03-15T14:00:00Z', 'info',"
            " 'Login successful (passkey)', 'user-a', 'ws-2')",
        )

        result = query_summative_users(conn)

        assert result["unique_logins"] == 1
        assert result["active_users"] == 1
        assert result["active_workspaces"] == 2
        assert result["workspace_users"] == 1

    def test_multiple_users(self) -> None:
        """Multiple distinct users counted correctly."""
        conn = _make_db()
        for user_id in ("user-a", "user-b", "user-c"):
            conn.execute(
                "INSERT INTO jsonl_events"
                " (source_id, ts_utc, level, event, user_id)"
                " VALUES (1, '2026-03-15T10:00:00Z', 'info',"
                " 'Page loaded', ?)",
                (user_id,),
            )

        result = query_summative_users(conn)

        assert result["active_users"] == 3
        assert result["unique_logins"] == 0

    def test_empty_db(self) -> None:
        """No JSONL events returns all zeros."""
        conn = _make_db()
        result = query_summative_users(conn)

        assert result["unique_logins"] == 0
        assert result["active_users"] == 0
        assert result["active_workspaces"] == 0
        assert result["workspace_users"] == 0


# ── load_static_counts ─────────────────────────────────────────────


class TestLoadStaticCounts:
    def test_valid_json(self, tmp_path: Path) -> None:
        """Valid JSON file returns parsed dict."""
        counts_file = tmp_path / "counts.json"
        data = {"enrolled": 42, "staff": 3}
        counts_file.write_text(json.dumps(data))

        result = load_static_counts(counts_file)

        assert result == data

    def test_none_returns_none(self) -> None:
        """None path returns None."""
        result = load_static_counts(None)
        assert result is None

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Invalid JSON raises JSONDecodeError."""
        counts_file = tmp_path / "bad.json"
        counts_file.write_text("not json {{{")

        with pytest.raises(json.JSONDecodeError):
            load_static_counts(counts_file)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        missing = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_static_counts(missing)


# ── LOGIN_EVENT_PATTERN ────────────────────────────────────────────


class TestLoginEventPattern:
    def test_pattern_value(self) -> None:
        """LOGIN_EVENT_PATTERN is a SQL LIKE pattern for login events."""
        assert LOGIN_EVENT_PATTERN == "Login successful%"
