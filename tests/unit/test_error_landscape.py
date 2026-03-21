"""Tests for compute_error_landscape() appeared/resolved error diffing."""

from __future__ import annotations

import sqlite3

from scripts.incident.analysis import compute_error_landscape
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


def _insert_jsonl(
    conn: sqlite3.Connection,
    ts: str,
    level: str,
    event: str,
) -> None:
    conn.execute(
        "INSERT INTO jsonl_events"
        " (source_id, ts_utc, level, event)"
        " VALUES (1, ?, ?, ?)",
        (ts, level, event),
    )


class TestComputeErrorLandscape:
    def test_first_epoch_all_appeared(self) -> None:
        """AC2.3: First epoch shows all its error types as appeared."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00Z", "error", "crash")
        _insert_jsonl(conn, "2026-03-15T10:01:00Z", "warning", "slow query")

        epochs = [
            {"start_utc": "2026-03-15T09:00:00Z", "end_utc": "2026-03-15T11:00:00Z"}
        ]
        result = compute_error_landscape(conn, epochs)

        assert len(result) == 1
        assert result[0]["appeared"] == {"crash", "slow query"}
        assert result[0]["resolved"] == set()

    def test_appeared_and_resolved(self) -> None:
        """AC2.2: Second epoch shows appeared (new) and resolved (gone) types."""
        conn = _make_db()
        # Epoch 1: errors A and B
        _insert_jsonl(conn, "2026-03-15T10:00:00Z", "error", "error_A")
        _insert_jsonl(conn, "2026-03-15T10:01:00Z", "error", "error_B")
        # Epoch 2: errors B and C
        _insert_jsonl(conn, "2026-03-15T12:00:00Z", "error", "error_B")
        _insert_jsonl(conn, "2026-03-15T12:01:00Z", "error", "error_C")

        epochs = [
            {"start_utc": "2026-03-15T09:00:00Z", "end_utc": "2026-03-15T11:00:00Z"},
            {"start_utc": "2026-03-15T11:00:01Z", "end_utc": "2026-03-15T13:00:00Z"},
        ]
        result = compute_error_landscape(conn, epochs)

        assert result[1]["appeared"] == {"error_C"}
        assert result[1]["resolved"] == {"error_A"}

    def test_no_errors_epoch(self) -> None:
        """AC2.4: Epoch with no errors shows empty sets."""
        conn = _make_db()
        # Only info-level events
        _insert_jsonl(conn, "2026-03-15T10:00:00Z", "info", "all good")

        epochs = [
            {"start_utc": "2026-03-15T09:00:00Z", "end_utc": "2026-03-15T11:00:00Z"}
        ]
        result = compute_error_landscape(conn, epochs)

        assert result[0]["appeared"] == set()
        assert result[0]["resolved"] == set()
        assert result[0]["current"] == set()

    def test_normalisation_collapses_classes(self) -> None:
        """Events with different hex addresses normalise to the same class."""
        conn = _make_db()
        _insert_jsonl(conn, "2026-03-15T10:00:00Z", "error", "Error at 0xaaa")
        _insert_jsonl(conn, "2026-03-15T10:01:00Z", "error", "Error at 0xbbb")

        epochs = [
            {"start_utc": "2026-03-15T09:00:00Z", "end_utc": "2026-03-15T11:00:00Z"}
        ]
        result = compute_error_landscape(conn, epochs)

        assert result[0]["current"] == {"Error at <ADDR>"}

    def test_three_epochs_cumulative(self) -> None:
        """Prior classes accumulate: reappearing type is NOT new."""
        conn = _make_db()
        # Epoch 1: A
        _insert_jsonl(conn, "2026-03-15T10:00:00Z", "error", "A")
        # Epoch 2: B
        _insert_jsonl(conn, "2026-03-15T12:00:00Z", "error", "B")
        # Epoch 3: A (was in epoch 1, not new)
        _insert_jsonl(conn, "2026-03-15T14:00:00Z", "error", "A")

        epochs = [
            {"start_utc": "2026-03-15T09:00:00Z", "end_utc": "2026-03-15T11:00:00Z"},
            {"start_utc": "2026-03-15T11:00:01Z", "end_utc": "2026-03-15T13:00:00Z"},
            {"start_utc": "2026-03-15T13:00:01Z", "end_utc": "2026-03-15T15:00:00Z"},
        ]
        result = compute_error_landscape(conn, epochs)

        # Epoch 3: A is NOT appeared (was in epoch 1), B IS resolved
        assert result[2]["appeared"] == set()
        assert result[2]["resolved"] == {"B"}
