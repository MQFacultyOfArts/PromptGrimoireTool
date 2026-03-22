"""Tarball ingest orchestration -- extract, register sources, dispatch parsers."""

from __future__ import annotations

import sqlite3
import sys
import tarfile
import tempfile
from typing import TYPE_CHECKING

from scripts.incident.parsers.haproxy import parse_haproxy
from scripts.incident.parsers.journal import parse_journal
from scripts.incident.parsers.jsonl import parse_jsonl
from scripts.incident.parsers.pglog import parse_pglog_auto
from scripts.incident.provenance import format_to_table, parse_manifest
from scripts.incident.schema import create_schema

if TYPE_CHECKING:
    from pathlib import Path

# Maps format string to (parser_func, table_name, column_names).
# Parser funcs: (data: bytes, window_start: str, window_end: str) -> list[dict]
# Exception: haproxy parser returns (list[dict], int) — see _dispatch_parser.
_PARSERS: dict[str, tuple[object, str, list[str]]] = {
    "journal": (
        parse_journal,
        "journal_events",
        [
            "source_id",
            "ts_utc",
            "priority",
            "pid",
            "unit",
            "message",
            "raw_json",
        ],
    ),
    "jsonl": (
        parse_jsonl,
        "jsonl_events",
        [
            "source_id",
            "ts_utc",
            "level",
            "event",
            "user_id",
            "workspace_id",
            "request_path",
            "exc_info",
            "extra_json",
        ],
    ),
    "haproxy": (
        parse_haproxy,
        "haproxy_events",
        [
            "source_id",
            "ts_utc",
            "client_ip",
            "status_code",
            "tr_ms",
            "tw_ms",
            "tc_ms",
            "tr_resp_ms",
            "ta_ms",
            "backend",
            "server",
            "method",
            "path",
            "bytes_read",
        ],
    ),
    "pglog": (
        parse_pglog_auto,
        "pg_events",
        [
            "source_id",
            "ts_utc",
            "pid",
            "level",
            "error_type",
            "detail",
            "statement",
            "message",
        ],
    ),
}


def _dispatch_parser(
    conn: sqlite3.Connection,
    fmt: str,
    source_id: int,
    file_data: bytes,
    window_start_utc: str,
    window_end_utc: str,
    timezone: str = "",
) -> None:
    """Run the registered parser for *fmt* and insert events."""
    parser_entry = _PARSERS.get(fmt)
    if parser_entry is None:
        return

    parse_fn, table_name, columns = parser_entry

    # HAProxy parser has a different signature: returns (events, count)
    # and requires a timezone parameter.
    unparseable_count = 0
    if fmt == "haproxy":
        events, unparseable_count = parse_fn(  # type: ignore[operator]
            file_data, window_start_utc, window_end_utc, timezone
        )
    else:
        events = parse_fn(  # type: ignore[operator]
            file_data, window_start_utc, window_end_utc
        )

    if not events:
        return

    for ev in events:
        ev["source_id"] = source_id
    placeholders = ", ".join(f":{c}" for c in columns)
    col_names = ", ".join(columns)
    conn.executemany(
        f"INSERT INTO {table_name} ({col_names}) "  # noqa: S608
        f"VALUES ({placeholders})",
        events,
    )

    if unparseable_count:
        print(
            f"  \u2192 {len(events)} events parsed"
            f" ({unparseable_count} unparseable lines skipped)"
        )
    else:
        print(f"  \u2192 {len(events)} events parsed")


def run_ingest(tarball: Path, db_path: Path) -> None:
    """Ingest a telemetry tarball into the SQLite database.

    1. Extract tarball to a temp directory.
    2. Read and parse ``manifest.json`` (AC2.6: clear error if missing).
    3. Open/create SQLite database, apply schema.
    4. For each file in manifest, insert into ``sources`` (AC2.5: sha256 dedup).
    5. Print summary of ingested/skipped files.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = __import__("pathlib").Path(tmp)

        # Extract tarball
        try:
            with tarfile.open(tarball, "r:gz") as tar:
                tar.extractall(path=tmp_dir, filter="data")
        except tarfile.TarError as exc:
            print(f"Error: cannot open tarball: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        # Read manifest (AC2.6)
        manifest_path = tmp_dir / "manifest.json"
        if not manifest_path.exists():
            print(
                "Error: tarball does not contain manifest.json",
                file=sys.stderr,
            )
            raise SystemExit(1)

        try:
            manifest = parse_manifest(manifest_path.read_bytes())
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        # Open/create database
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        hostname = manifest["hostname"]
        timezone = manifest["timezone"]
        window = manifest["requested_window"]
        window_start_utc = window["start_utc"]
        window_end_utc = window["end_utc"]

        ingested = 0
        skipped = 0

        for file_entry in manifest["files"]:
            filename = file_entry["filename"]
            sha256 = file_entry["sha256"]
            size = file_entry["size"]
            mtime = file_entry["mtime"]

            # AC2.5: sha256 dedup -- skip if already ingested
            existing = conn.execute(
                "SELECT id FROM sources WHERE sha256 = ?", (sha256,)
            ).fetchone()
            if existing is not None:
                skipped += 1
                continue

            fmt = format_to_table(filename)
            if not fmt:
                print(f"  Skipping unknown file: {filename}", file=sys.stderr)
                skipped += 1
                continue

            source_path = file_entry.get("source_path")
            collection_method = file_entry.get("method")

            conn.execute(
                """INSERT INTO sources
                   (filename, format, sha256, size, mtime, hostname, timezone,
                    window_start_utc, window_end_utc, source_path,
                    collection_method)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filename,
                    fmt,
                    sha256,
                    size,
                    mtime,
                    hostname,
                    timezone,
                    window_start_utc,
                    window_end_utc,
                    source_path,
                    collection_method,
                ),
            )
            source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Dispatch to parser if registered
            file_data = (tmp_dir / filename).read_bytes()
            _dispatch_parser(
                conn,
                fmt,
                source_id,
                file_data,
                window_start_utc,
                window_end_utc,
                timezone=timezone,
            )

            ingested += 1

        conn.commit()
        conn.close()

        print(f"Ingested {ingested} source(s), skipped {skipped} (dedup).")
