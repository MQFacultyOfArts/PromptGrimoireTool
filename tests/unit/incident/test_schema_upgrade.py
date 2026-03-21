"""Test that create_schema upgrades existing databases.

Codex blocker: pre-existing incident.db without source_path/collection_method
columns must gain them via ALTER TABLE, not fail at ingest.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from scripts.incident.schema import create_schema

if TYPE_CHECKING:
    from pathlib import Path


class TestSchemaUpgrade:
    """Existing databases gain new provenance columns."""

    def test_old_schema_upgraded_with_new_columns(self, tmp_path: Path) -> None:
        """Create a v1 sources table (no provenance cols), then run create_schema."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE TABLE sources (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                format TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL,
                mtime INTEGER NOT NULL,
                hostname TEXT NOT NULL,
                timezone TEXT NOT NULL,
                window_start_utc TEXT NOT NULL,
                window_end_utc TEXT NOT NULL,
                ingested_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )"""
        )
        conn.commit()

        # This must NOT raise OperationalError
        create_schema(conn)

        # New columns must exist
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }
        assert "source_path" in columns
        assert "collection_method" in columns

        # Insert with new columns must work
        conn.execute(
            """INSERT INTO sources
               (filename, format, sha256, size, mtime, hostname, timezone,
                window_start_utc, window_end_utc, source_path, collection_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "test.jsonl",
                "jsonl",
                "abc",
                100,
                1000,
                "host",
                "UTC",
                "2026-03-16T00:00:00Z",
                "2026-03-16T01:00:00Z",
                "/path/to/source",
                "jq filter",
            ),
        )
        conn.commit()
        conn.close()

    def test_fresh_schema_has_provenance_columns(self, tmp_path: Path) -> None:
        """Fresh database gets provenance columns from DDL directly."""
        db_path = tmp_path / "fresh.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }
        assert "source_path" in columns
        assert "collection_method" in columns
        conn.close()

    def test_idempotent_migration(self, tmp_path: Path) -> None:
        """Running create_schema twice does not fail."""
        db_path = tmp_path / "idem.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        create_schema(conn)  # Must not raise
        conn.close()
