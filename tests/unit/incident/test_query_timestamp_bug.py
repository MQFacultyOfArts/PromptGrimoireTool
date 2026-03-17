"""RED test: CLI query window drops events in the first second.

CLI _aedt_to_utc produces 'YYYY-MM-DDTHH:MM:SSZ' but parsers store
'YYYY-MM-DDTHH:MM:SS.ffffffZ'. SQLite string comparison
'...00.000000Z' >= '...00Z' evaluates false because '.' < 'Z'.

Also tests malformed JSONL timestamp resilience.
"""

from __future__ import annotations

import sqlite3

from scripts.incident.parsers.jsonl import parse_jsonl
from scripts.incident.queries import query_timeline


class TestQueryStartSecondBug:
    """Events at exactly the start second should be included."""

    def test_event_at_window_start_included(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        from scripts.incident.schema import create_schema

        create_schema(conn)

        # Insert a source
        conn.execute(
            """INSERT INTO sources
               (filename, format, sha256, size, mtime, hostname, timezone,
                window_start_utc, window_end_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "test.jsonl",
                "jsonl",
                "abc123",
                100,
                1000,
                "test",
                "UTC",
                "2026-03-16T05:00:00.000000Z",
                "2026-03-16T06:00:00.000000Z",
            ),
        )
        source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert event at exactly 05:00:00 (microsecond format)
        conn.execute(
            """INSERT INTO jsonl_events
               (source_id, ts_utc, level, event)
               VALUES (?, ?, ?, ?)""",
            (source_id, "2026-03-16T05:00:00.000000Z", "info", "start-event"),
        )
        conn.commit()

        # Query with the same start time but in SSZ format (what CLI produces)
        results = query_timeline(
            conn,
            "2026-03-16T05:00:00Z",
            "2026-03-16T06:00:00Z",
        )
        conn.close()

        assert len(results) == 1, (
            f"Event at window start dropped: got {len(results)} results. "
            "This is the CLI timestamp format mismatch bug."
        )


class TestJsonlMalformedTimestampResilience:
    """Malformed timestamp strings should be skipped, not crash ingest."""

    def test_bad_timestamp_string_skipped(self) -> None:
        lines = (
            b'{"timestamp":"not-a-date","level":"info","event":"bad"}\n'
            b'{"timestamp":"2026-03-16T05:00:00Z","level":"info","event":"good"}\n'
        )
        result = parse_jsonl(
            lines,
            "2026-03-16T04:00:00Z",
            "2026-03-16T06:00:00Z",
        )
        assert len(result) == 1
        assert result[0]["event"] == "good"
