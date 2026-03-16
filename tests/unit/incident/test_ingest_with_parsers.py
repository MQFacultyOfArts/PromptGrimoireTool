"""Integration tests: ingest dispatch with real parsers wired in.

Verifies:
- AC2.1: end-to-end ingest with parsers populates event tables
- journal_events rows have correct ts_utc from microsecond epoch conversion
- jsonl_events rows have correct field extraction
- Re-ingest dedup still works (no duplicate events)
"""

from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from typing import TYPE_CHECKING

from scripts.incident.ingest import run_ingest
from scripts.incident.provenance import compute_sha256

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

# Window: 2026-03-16T03:50:00Z to 2026-03-16T06:20:00Z
# With 5-min buffer: 03:45:00Z to 06:25:00Z

# Journal lines: __REALTIME_TIMESTAMP is microseconds since epoch.
# 2026-03-16T04:00:00Z = 1773633600 s = 1773633600000000 µs
# 2026-03-16T05:00:00Z = 1773637200 s = 1773637200000000 µs
# 2026-03-16T05:30:00Z = 1773639000 s = 1773639000000000 µs
_JOURNAL_LINES = [
    {
        "__REALTIME_TIMESTAMP": "1773633600000000",
        "PRIORITY": "3",
        "_PID": "1234",
        "_SYSTEMD_UNIT": "promptgrimoire.service",
        "MESSAGE": "journal event 1",
    },
    {
        "__REALTIME_TIMESTAMP": "1773637200000000",
        "PRIORITY": "6",
        "_PID": "1234",
        "_SYSTEMD_UNIT": "promptgrimoire.service",
        "MESSAGE": "journal event 2",
    },
    {
        "__REALTIME_TIMESTAMP": "1773639000000000",
        "PRIORITY": "4",
        "_PID": "5678",
        "_SYSTEMD_UNIT": "postgresql.service",
        "MESSAGE": "journal event 3",
    },
]
_JOURNAL_BYTES = (
    "\n".join(json.dumps(line) for line in _JOURNAL_LINES) + "\n"
).encode()

# JSONL lines: already UTC timestamps within window
_JSONL_LINES = [
    {
        "timestamp": "2026-03-16T04:10:00Z",
        "level": "error",
        "event": "db_connection_failed",
        "logger": "promptgrimoire.db",
        "pid": 12345,
        "user_id": "user-aaa",
        "workspace_id": "ws-111",
        "request_path": "/annotation/ws-111",
        "exc_info": "ValueError: connection refused",
    },
    {
        "timestamp": "2026-03-16T05:00:00Z",
        "level": "warning",
        "event": "high_memory",
        "logger": "promptgrimoire.monitor",
        "pid": 12345,
        "user_id": None,
        "workspace_id": None,
        "request_path": None,
        "exc_info": None,
    },
    {
        "timestamp": "2026-03-16T05:45:00Z",
        "level": "info",
        "event": "request_served",
        "logger": "promptgrimoire.pages",
        "pid": 12345,
        "user_id": "user-bbb",
        "workspace_id": "ws-222",
        "request_path": "/courses/list",
        "exc_info": None,
    },
]
_JSONL_BYTES = ("\n".join(json.dumps(line) for line in _JSONL_LINES) + "\n").encode()


def _make_manifest(
    files: list[dict],
    *,
    hostname: str = "grimoire.drbbs.org",
    timezone: str = "Australia/Sydney",
) -> bytes:
    return json.dumps(
        {
            "hostname": hostname,
            "timezone": timezone,
            "collection_timestamp": "2026-03-16T06:00:00Z",
            "requested_window": {
                "start_local": "2026-03-16 14:50",
                "end_local": "2026-03-16 17:20",
                "start_utc": "2026-03-16T03:50:00Z",
                "end_utc": "2026-03-16T06:20:00Z",
            },
            "files": files,
        }
    ).encode()


def _make_tarball(
    tmp_path: Path, file_contents: dict[str, bytes], manifest: bytes
) -> Path:
    tarball_path = tmp_path / "telemetry.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest)
        tar.addfile(manifest_info, io.BytesIO(manifest))

        for name, content in file_contents.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

    return tarball_path


def _file_entries(tmp_path: Path, file_contents: dict[str, bytes]) -> list[dict]:
    entries = []
    for name, content in file_contents.items():
        p = tmp_path / name
        p.write_bytes(content)
        entries.append(
            {
                "filename": name,
                "sha256": compute_sha256(p),
                "size": len(content),
                "mtime": 1773878400,
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestWithParsers:
    """AC2.1: end-to-end ingest populates event tables."""

    def test_journal_events_populated(self, tmp_path: Path) -> None:
        contents = {"journal.json": _JOURNAL_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_id, ts_utc, priority, pid, unit, message "
            "FROM journal_events ORDER BY ts_utc"
        ).fetchall()
        assert len(rows) == 3

        # Verify source_id is set
        source_id = conn.execute("SELECT id FROM sources").fetchone()[0]
        assert all(r[0] == source_id for r in rows)

        # Verify ts_utc conversion from microsecond epoch
        assert rows[0][1] == "2026-03-16T04:00:00+00:00"
        assert rows[1][1] == "2026-03-16T05:00:00+00:00"
        assert rows[2][1] == "2026-03-16T05:30:00+00:00"

        # Verify field extraction
        assert rows[0][2] == 3  # priority
        assert rows[0][3] == 1234  # pid
        assert rows[0][4] == "promptgrimoire.service"  # unit
        assert rows[0][5] == "journal event 1"  # message

        conn.close()

    def test_jsonl_events_populated(self, tmp_path: Path) -> None:
        contents = {"structlog.jsonl": _JSONL_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_id, ts_utc, level, event, user_id, workspace_id, "
            "request_path, exc_info, extra_json FROM jsonl_events ORDER BY ts_utc"
        ).fetchall()
        assert len(rows) == 3

        source_id = conn.execute("SELECT id FROM sources").fetchone()[0]
        assert all(r[0] == source_id for r in rows)

        # First row: error with exc_info
        assert rows[0][1] == "2026-03-16T04:10:00Z"
        assert rows[0][2] == "error"
        assert rows[0][3] == "db_connection_failed"
        assert rows[0][4] == "user-aaa"
        assert rows[0][5] == "ws-111"
        assert rows[0][6] == "/annotation/ws-111"
        assert rows[0][7] == "ValueError: connection refused"

        # AC3.5: exc_info null -> Python None (SQL NULL)
        assert rows[1][7] is None
        assert rows[2][7] is None

        # extra_json contains non-extracted fields
        extra = json.loads(rows[0][8])
        assert "logger" in extra
        assert "pid" in extra
        # Extracted fields should NOT be in extra_json
        assert "timestamp" not in extra
        assert "level" not in extra
        assert "event" not in extra
        assert "user_id" not in extra

        conn.close()

    def test_both_formats_together(self, tmp_path: Path) -> None:
        contents = {
            "journal.json": _JOURNAL_BYTES,
            "structlog.jsonl": _JSONL_BYTES,
        }
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM jsonl_events").fetchone()[0] == 3
        conn.close()

    def test_reingest_dedup_no_duplicate_events(self, tmp_path: Path) -> None:
        contents = {
            "journal.json": _JOURNAL_BYTES,
            "structlog.jsonl": _JSONL_BYTES,
        }
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)
        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM jsonl_events").fetchone()[0] == 3
        conn.close()
