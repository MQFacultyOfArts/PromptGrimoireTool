"""Tests for tarball ingest orchestration.

Verifies:
- AC2.1: sources table has one row per file after ingest
- AC2.5: re-ingesting same tarball is a no-op (sha256 dedup)
- AC2.6: tarball without manifest.json prints error and exits non-zero
"""

from __future__ import annotations

import json
import sqlite3
import tarfile
from typing import TYPE_CHECKING

import pytest
from scripts.incident.ingest import run_ingest
from scripts.incident.provenance import compute_sha256, format_to_table, parse_manifest

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    files: list[dict],
    *,
    hostname: str = "grimoire.drbbs.org",
    timezone: str = "Australia/Sydney",
) -> bytes:
    """Build a minimal manifest.json as bytes."""
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
    """Create a .tar.gz in tmp_path containing manifest.json and given files."""
    tarball_path = tmp_path / "telemetry.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        # Add manifest.json
        import io

        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest)
        tar.addfile(manifest_info, io.BytesIO(manifest))

        # Add each file
        for name, content in file_contents.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

    return tarball_path


# ---------------------------------------------------------------------------
# Provenance unit tests
# ---------------------------------------------------------------------------


class TestParseManifest:
    def test_valid_manifest(self) -> None:
        manifest = _make_manifest(
            files=[
                {
                    "filename": "journal.json",
                    "sha256": "abc",
                    "size": 100,
                    "mtime": 1000,
                }
            ]
        )
        result = parse_manifest(manifest)
        assert result["hostname"] == "grimoire.drbbs.org"
        assert len(result["files"]) == 1

    def test_missing_required_field(self) -> None:
        bad = json.dumps({"hostname": "test", "timezone": "UTC"}).encode()
        with pytest.raises(ValueError, match="missing required fields"):
            parse_manifest(bad)

    def test_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_manifest(b"not json{{{")

    def test_missing_window_fields(self) -> None:
        bad = json.dumps(
            {
                "hostname": "test",
                "timezone": "UTC",
                "requested_window": {"start_utc": "x"},
                "files": [],
            }
        ).encode()
        with pytest.raises(ValueError, match="end_utc"):
            parse_manifest(bad)


class TestFormatToTable:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("journal.json", "journal"),
            ("structlog.jsonl", "jsonl"),
            ("haproxy.log", "haproxy"),
            ("postgresql.log", "pglog"),
        ],
    )
    def test_known_formats(self, filename: str, expected: str) -> None:
        assert format_to_table(filename) == expected

    def test_unknown_filename(self) -> None:
        with pytest.raises(ValueError, match="Unknown source filename"):
            format_to_table("mystery.txt")


class TestComputeSha256:
    def test_computes_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        digest = compute_sha256(f)
        assert len(digest) == 64
        assert (
            digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )


# ---------------------------------------------------------------------------
# Ingest integration tests
# ---------------------------------------------------------------------------

_DUMMY_JOURNAL = b'{"__REALTIME_TIMESTAMP":"1710568200000000","MESSAGE":"test"}\n'
_DUMMY_JSONL = b'{"timestamp":"2026-03-16T04:00:00Z","level":"info","event":"test"}\n'
_DUMMY_HAPROXY = b"Mar 16 15:00:00 grimoire haproxy[123]: 1.2.3.4:5678 test\n"
_DUMMY_PGLOG = b"2026-03-16 04:00:00.000 UTC [123] LOG:  test\n"

_FILE_CONTENTS = {
    "journal.json": _DUMMY_JOURNAL,
    "structlog.jsonl": _DUMMY_JSONL,
    "haproxy.log": _DUMMY_HAPROXY,
    "postgresql.log": _DUMMY_PGLOG,
}


def _file_entries_for_contents(
    tmp_path: Path, file_contents: dict[str, bytes]
) -> list[dict]:
    """Build manifest file entries with real sha256 for the given contents."""
    entries = []
    for name, content in file_contents.items():
        # Write to tmp so we can hash
        p = tmp_path / name
        p.write_bytes(content)
        entries.append(
            {
                "filename": name,
                "sha256": compute_sha256(p),
                "size": len(content),
                "mtime": 1710568200,
            }
        )
    return entries


class TestRunIngest:
    """AC2.1: sources table has one row per file after ingest."""

    def test_ingest_populates_sources(self, tmp_path: Path) -> None:
        entries = _file_entries_for_contents(tmp_path, _FILE_CONTENTS)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, _FILE_CONTENTS, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT filename, format, hostname FROM sources ORDER BY filename"
        ).fetchall()
        assert len(rows) == 4
        filenames = [r[0] for r in rows]
        assert "journal.json" in filenames
        assert "structlog.jsonl" in filenames
        assert "haproxy.log" in filenames
        assert "postgresql.log" in filenames

        # Check format mapping
        fmt_map = {r[0]: r[1] for r in rows}
        assert fmt_map["journal.json"] == "journal"
        assert fmt_map["structlog.jsonl"] == "jsonl"
        assert fmt_map["haproxy.log"] == "haproxy"
        assert fmt_map["postgresql.log"] == "pglog"

        # Check hostname from manifest
        assert all(r[2] == "grimoire.drbbs.org" for r in rows)
        conn.close()


class TestRunIngestDedup:
    """AC2.5: re-ingesting same tarball is a no-op."""

    def test_reingest_is_noop(self, tmp_path: Path) -> None:
        entries = _file_entries_for_contents(tmp_path, _FILE_CONTENTS)
        manifest = _make_manifest(files=entries)
        tarball = _make_tarball(tmp_path, _FILE_CONTENTS, manifest)
        db_path = tmp_path / "test.db"

        run_ingest(tarball, db_path)
        run_ingest(tarball, db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        assert count == 4  # No duplicates
        conn.close()


class TestRunIngestNoManifest:
    """AC2.6: tarball without manifest.json prints error and exits non-zero."""

    def test_missing_manifest_exits(self, tmp_path: Path) -> None:
        # Create a tarball with no manifest.json
        tarball_path = tmp_path / "bad.tar.gz"
        with tarfile.open(tarball_path, "w:gz") as tar:
            import io

            info = tarfile.TarInfo(name="random.txt")
            content = b"no manifest here"
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        db_path = tmp_path / "test.db"

        with pytest.raises(SystemExit) as exc_info:
            run_ingest(tarball_path, db_path)
        assert exc_info.value.code == 1
