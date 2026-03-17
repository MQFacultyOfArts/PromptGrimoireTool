"""Integration tests: ingest dispatch for HAProxy and PG parsers.

Verifies:
- HAProxy ingest: tuple return handled, events inserted, unparseable count reported
- PG auto-detection: JSON vs text format sniffed correctly
- PG ingest: events inserted into pg_events table
- format_to_table maps both postgresql.log and postgresql.json -> pglog
- AC3.4: unparseable HAProxy lines counted in output
"""

# ruff: noqa: E501 — log line fixtures must match real format exactly.

from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from typing import TYPE_CHECKING

from scripts.incident.ingest import run_ingest
from scripts.incident.parsers.pglog import parse_pglog_auto
from scripts.incident.provenance import compute_sha256, format_to_table

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture data — window matches test_ingest_with_parsers.py
# ---------------------------------------------------------------------------

# Window: 2026-03-16T03:50:00Z to 2026-03-16T06:20:00Z

# HAProxy log lines — mix of parseable and unparseable
# 2026-03-16T15:00:00+11:00 = 2026-03-16T04:00:00Z (in window)
_HAPROXY_LINES = """\
2026-03-16T15:00:00+11:00 grimoire haproxy[2345]: 192.0.2.100:45678 [16/Mar/2026:15:00:00.123 +1100] http-in backend/srv01 10/2/5/150/167 200 1234 - - ---- 1/1/1/1/0 0/0 {|} {|} "GET /annotation/ws-xyz HTTP/1.1"
this is garbage
2026-03-16T16:00:00+11:00 grimoire haproxy[2345]: 192.0.2.101:12345 [16/Mar/2026:16:00:00.456 +1100] http-in backend/srv01 5/1/3/200/209 504 0 - - ---- 1/1/1/1/0 0/0 {|} {|} "POST /api/save HTTP/1.1"
also garbage
""".strip()
_HAPROXY_BYTES = _HAPROXY_LINES.encode()

# PG text log — ERROR + DETAIL + STATEMENT (multi-line)
_PG_TEXT_LOG = """\
2026-03-16 04:32:52.000 UTC [1234] ERROR:  duplicate key value violates unique constraint "uq_tag_workspace_name"
2026-03-16 04:32:52.000 UTC [1234] DETAIL:  Key (workspace_id, name)=(dbf5feaa, Important Info) already exists.
2026-03-16 04:32:52.000 UTC [1234] STATEMENT:  INSERT INTO tag (id, workspace_id, name) VALUES ($1, $2, $3)
2026-03-16 04:50:16.000 UTC [5678] FATAL:  connection to client lost
""".strip()
_PG_TEXT_BYTES = _PG_TEXT_LOG.encode()

# PG JSON log — two entries
_PG_JSON_LINES = [
    {
        "timestamp": "2026-03-16 04:32:52.000 GMT",
        "pid": 1234,
        "error_severity": "ERROR",
        "message": 'duplicate key value violates unique constraint "uq_tag_workspace_name"',
        "detail": "Key (workspace_id, name)=(dbf5feaa, Important Info) already exists.",
        "statement": "INSERT INTO tag (id, workspace_id, name) VALUES ($1, $2, $3)",
    },
    {
        "timestamp": "2026-03-16 04:50:16.000 GMT",
        "pid": 5678,
        "error_severity": "FATAL",
        "message": "connection to client lost",
    },
]
_PG_JSON_BYTES = (
    "\n".join(json.dumps(line) for line in _PG_JSON_LINES) + "\n"
).encode()


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_ingest_with_parsers.py)
# ---------------------------------------------------------------------------


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
# Tests: provenance mapping
# ---------------------------------------------------------------------------


class TestFormatToTable:
    """format_to_table handles both PG filename variants."""

    def test_postgresql_log_maps_to_pglog(self) -> None:
        assert format_to_table("postgresql.log") == "pglog"

    def test_postgresql_json_maps_to_pglog(self) -> None:
        assert format_to_table("postgresql.json") == "pglog"


class TestPglogAuto:
    """Auto-detection sniffs JSON vs text format."""

    def test_json_format_detected(self) -> None:
        events = parse_pglog_auto(
            _PG_JSON_BYTES,
            "2026-03-16T03:50:00Z",
            "2026-03-16T06:20:00Z",
        )
        assert len(events) == 2
        assert events[0]["level"] == "ERROR"

    def test_text_format_detected(self) -> None:
        events = parse_pglog_auto(
            _PG_TEXT_BYTES,
            "2026-03-16T03:50:00Z",
            "2026-03-16T06:20:00Z",
        )
        # Multi-line grouping: ERROR+DETAIL+STATEMENT = 1 entry, FATAL = 1
        assert len(events) == 2
        assert events[0]["level"] == "ERROR"
        assert events[0]["detail"] is not None

    def test_empty_data_returns_empty(self) -> None:
        events = parse_pglog_auto(
            b"",
            "2026-03-16T03:50:00Z",
            "2026-03-16T06:20:00Z",
        )
        assert events == []

    def test_whitespace_only_returns_empty(self) -> None:
        events = parse_pglog_auto(
            b"  \n  \n  ",
            "2026-03-16T03:50:00Z",
            "2026-03-16T06:20:00Z",
        )
        assert events == []


# ---------------------------------------------------------------------------
# Tests: end-to-end ingest
# ---------------------------------------------------------------------------


class TestIngestHaproxy:
    """HAProxy ingest wires through dispatch correctly."""

    def test_haproxy_events_populated(self, tmp_path: Path) -> None:
        contents = {"haproxy.log": _HAPROXY_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_id, ts_utc, client_ip, status_code, tr_ms, "
            "tw_ms, tc_ms, tr_resp_ms, ta_ms, backend, server, method, "
            "path, bytes_read FROM haproxy_events ORDER BY ts_utc"
        ).fetchall()
        # 2 parseable lines, 2 garbage lines
        assert len(rows) == 2

        # First row
        assert rows[0][2] == "192.0.2.100"  # client_ip
        assert rows[0][3] == 200  # status_code
        assert rows[0][11] == "GET"  # method
        assert rows[0][12] == "/annotation/ws-xyz"  # path

        # Second row
        assert rows[1][3] == 504  # status_code
        assert rows[1][11] == "POST"  # method

        # Verify source_id links
        source_id = conn.execute("SELECT id FROM sources").fetchone()[0]
        assert all(r[0] == source_id for r in rows)

        conn.close()

    def test_unparseable_count_in_output(self, tmp_path: Path, capsys) -> None:
        """AC3.4: unparseable count reported."""
        contents = {"haproxy.log": _HAPROXY_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        captured = capsys.readouterr()
        assert "2 events parsed" in captured.out
        assert "2 unparseable" in captured.out


class TestIngestPglog:
    """PG log ingest wires through dispatch correctly."""

    def test_pglog_text_events_populated(self, tmp_path: Path) -> None:
        contents = {"postgresql.log": _PG_TEXT_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_id, ts_utc, pid, level, error_type, detail, "
            "statement, message FROM pg_events ORDER BY ts_utc"
        ).fetchall()
        assert len(rows) == 2

        # First: ERROR with DETAIL+STATEMENT merged
        assert rows[0][3] == "ERROR"  # level
        assert rows[0][5] is not None  # detail
        assert rows[0][6] is not None  # statement

        # Second: FATAL standalone
        assert rows[1][3] == "FATAL"
        assert rows[1][5] is None  # no detail
        assert rows[1][6] is None  # no statement

        conn.close()

    def test_pglog_json_events_populated(self, tmp_path: Path) -> None:
        contents = {"postgresql.json": _PG_JSON_BYTES}
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_id, ts_utc, pid, level, error_type, detail, "
            "statement, message FROM pg_events ORDER BY ts_utc"
        ).fetchall()
        assert len(rows) == 2

        assert rows[0][3] == "ERROR"
        assert rows[0][5] is not None  # detail present
        assert rows[1][3] == "FATAL"
        assert rows[1][5] is None  # no detail

        # Verify format stored as pglog in sources
        fmt = conn.execute("SELECT format FROM sources").fetchone()[0]
        assert fmt == "pglog"

        conn.close()

    def test_all_formats_together(self, tmp_path: Path) -> None:
        """All four source types ingest in a single tarball."""
        # Minimal journal + jsonl data
        journal_bytes = (
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1773633600000000",
                    "PRIORITY": "3",
                    "_PID": "1234",
                    "_SYSTEMD_UNIT": "promptgrimoire.service",
                    "MESSAGE": "test",
                }
            ).encode()
            + b"\n"
        )
        jsonl_bytes = (
            json.dumps(
                {
                    "timestamp": "2026-03-16T04:10:00Z",
                    "level": "info",
                    "event": "test",
                }
            ).encode()
            + b"\n"
        )

        contents = {
            "journal.json": journal_bytes,
            "structlog.jsonl": jsonl_bytes,
            "haproxy.log": _HAPROXY_BYTES,
            "postgresql.log": _PG_TEXT_BYTES,
        }
        entries = _file_entries(tmp_path, contents)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, contents, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM jsonl_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM haproxy_events").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM pg_events").fetchone()[0] == 2
        conn.close()
