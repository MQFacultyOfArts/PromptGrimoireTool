"""Ingest orchestration -- extract, register sources, dispatch parsers."""

from __future__ import annotations

import hashlib
import shutil
import socket
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

try:
    from scripts.incident.parsers.beszel import (
        fetch_beszel_metrics as _fetch_beszel,
    )

    _HAS_BESZEL = True
except ImportError:
    _HAS_BESZEL = False
    _fetch_beszel = None  # type: ignore[assignment]

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


def _resolve_data_dir(source: Path) -> tuple[__import__("pathlib").Path, bool]:
    """Resolve source to a data directory.

    Accepts a tarball (.tar.gz) or a directory path.
    Returns (data_dir, is_temp) — caller must clean up if is_temp.
    """
    P = __import__("pathlib").Path
    if source.is_dir():
        return P(source), False

    tmp_dir = P(tempfile.mkdtemp(prefix="incident-ingest-"))
    try:
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(path=tmp_dir, filter="data")
    except tarfile.TarError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"Error: cannot open tarball: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return tmp_dir, True


def _copy_db_snapshot(
    data_dir: __import__("pathlib").Path,
    db_path: __import__("pathlib").Path,
) -> __import__("pathlib").Path | None:
    """Copy db-snapshot.json next to the DB for ``review --counts-json``.

    Returns the destination path, or None if no snapshot found.
    """
    snapshot = data_dir / "db-snapshot.json"
    if not snapshot.exists():
        return None
    dest = db_path.parent / "db-snapshot.json"
    shutil.copy2(snapshot, dest)
    print(f"  Copied db-snapshot.json → {dest}")
    return dest


def run_ingest(source: Path, db_path: Path) -> None:
    """Ingest telemetry from a tarball or directory.

    Accepts either a ``.tar.gz`` tarball or a directory containing
    ``manifest.json`` and log files.

    Steps:
    1. Resolve source to a data directory (extract if tarball).
    2. Read and parse ``manifest.json``.
    3. Open/create SQLite database, apply schema.
    4. For each file in manifest, insert into ``sources``
       (sha256 dedup).
    5. Copy ``db-snapshot.json`` next to the DB if present.
    6. Print summary of ingested/skipped files.
    """
    data_dir, is_temp = _resolve_data_dir(source)
    try:
        _run_ingest_from_dir(data_dir, db_path)
    finally:
        if is_temp:
            shutil.rmtree(data_dir, ignore_errors=True)


def _run_ingest_from_dir(
    data_dir: __import__("pathlib").Path,
    db_path: __import__("pathlib").Path,
) -> None:
    """Core ingest logic operating on an already-extracted directory."""
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        print(
            "Error: source does not contain manifest.json",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        manifest = parse_manifest(manifest_path.read_bytes())
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

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

        existing = conn.execute(
            "SELECT id FROM sources WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if existing is not None:
            skipped += 1
            continue

        fmt = format_to_table(filename)
        if not fmt:
            # db-snapshot.json is metadata, not a log source
            if filename != "db-snapshot.json":
                print(
                    f"  Skipping unknown file: {filename}",
                    file=sys.stderr,
                )
            skipped += 1
            continue

        source_path = file_entry.get("source_path")
        collection_method = file_entry.get("method")

        conn.execute(
            """INSERT INTO sources
               (filename, format, sha256, size, mtime,
                hostname, timezone,
                window_start_utc, window_end_utc,
                source_path, collection_method)
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

        file_data = (data_dir / filename).read_bytes()
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

    # Copy db-snapshot.json alongside the DB for review --counts-json
    _copy_db_snapshot(data_dir, db_path)

    print(f"Ingested {ingested} source(s), skipped {skipped} (dedup/metadata).")

    # Auto-fetch Beszel metrics if hub is reachable
    _try_beszel_fetch(db_path, window_start_utc, window_end_utc, timezone)


def _try_beszel_fetch(
    db_path: __import__("pathlib").Path,
    start_utc: str,
    end_utc: str,
    timezone: str,
) -> None:
    """Fetch Beszel metrics if the hub is reachable on localhost:8090.

    Requires an SSH tunnel: ``ssh -L 8090:localhost:8090 <monitor>``.
    Silently skips if the port is not open or httpx is unavailable.
    """
    if not _HAS_BESZEL:
        print("  httpx not available — skipping Beszel fetch")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(("localhost", 8090))
    finally:
        sock.close()

    if result != 0:
        print(
            "  Beszel hub not reachable on localhost:8090 "
            "(start SSH tunnel to fetch metrics)"
        )
        return

    hub = "http://localhost:8090"
    sha = hashlib.sha256(f"{hub}:{start_utc}:{end_utc}".encode()).hexdigest()

    conn = sqlite3.connect(db_path)
    existing = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (sha,)
    ).fetchone()
    if existing is not None:
        conn.close()
        print("  Beszel metrics already fetched (dedup).")
        return

    try:
        metrics = _fetch_beszel(hub, start_utc, end_utc)  # type: ignore[misc]
    except Exception as exc:
        conn.close()
        print(f"  Beszel fetch failed: {exc}")
        return

    create_schema(conn)
    conn.execute(
        """INSERT INTO sources
           (filename, format, sha256, size, mtime,
            hostname, timezone,
            window_start_utc, window_end_utc,
            source_path, collection_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "beszel-api",
            "beszel",
            sha,
            0,
            0,
            "beszel-hub",
            timezone,
            start_utc,
            end_utc,
            hub,
            "auto-fetch on ingest",
        ),
    )
    source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for m in metrics:
        conn.execute(
            """INSERT INTO beszel_metrics
               (source_id, ts_utc, cpu, mem_used,
                mem_percent, net_sent, net_recv,
                disk_read, disk_write,
                load_1, load_5, load_15)
               VALUES (?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?)""",
            (
                source_id,
                m["ts_utc"],
                m["cpu"],
                m["mem_used"],
                m["mem_percent"],
                m["net_sent"],
                m["net_recv"],
                m["disk_read"],
                m["disk_write"],
                m["load_1"],
                m["load_5"],
                m["load_15"],
            ),
        )

    conn.commit()
    conn.close()
    print(f"  Fetched {len(metrics)} Beszel metric data points")
