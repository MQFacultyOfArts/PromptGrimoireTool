"""Tarball ingest orchestration -- extract, register sources, dispatch parsers."""

from __future__ import annotations

import sqlite3
import sys
import tarfile
import tempfile
from typing import TYPE_CHECKING

from scripts.incident.provenance import format_to_table, parse_manifest
from scripts.incident.schema import create_schema

if TYPE_CHECKING:
    from pathlib import Path

# Parser dispatch: format string -> callable(conn, source_id, file_path).
# Empty in Phase 2; parsers are registered in Phases 3-4.
_PARSERS: dict[str, object] = {}


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

            conn.execute(
                """INSERT INTO sources
                   (filename, format, sha256, size, mtime, hostname, timezone,
                    window_start_utc, window_end_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                ),
            )
            source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Dispatch to parser if registered (Phase 3-4 fills this in)
            parser = _PARSERS.get(fmt)
            if parser is not None:
                file_path = tmp_dir / filename
                parser(conn, source_id, file_path)  # type: ignore[operator]

            ingested += 1

        conn.commit()
        conn.close()

        print(f"Ingested {ingested} source(s), skipped {skipped} (dedup).")
