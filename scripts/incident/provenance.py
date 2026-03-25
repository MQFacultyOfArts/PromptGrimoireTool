"""Manifest parsing and provenance helpers (pure functions, FCIS pattern)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Mapping from manifest filenames to source format strings used in the DB.
_FILENAME_TO_FORMAT: dict[str, str] = {
    "journal.json": "journal",
    "structlog.jsonl": "jsonl",
    "haproxy.log": "haproxy",
    "postgresql.log": "pglog",
    "postgresql.json": "pglog",
    "pgbouncer.log": "pgbouncer",
}

_REQUIRED_MANIFEST_KEYS = {"hostname", "timezone", "requested_window", "files"}


def parse_manifest(manifest_bytes: bytes) -> dict:
    """Parse manifest.json from bytes, validate required fields.

    Raises ``ValueError`` with a clear message if required fields are missing.
    """
    try:
        data = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is not valid JSON: {exc}") from exc

    missing = _REQUIRED_MANIFEST_KEYS - data.keys()
    if missing:
        raise ValueError(
            f"manifest.json missing required fields: {', '.join(sorted(missing))}"
        )

    window = data["requested_window"]
    for key in ("start_utc", "end_utc"):
        if key not in window:
            raise ValueError(f"manifest.json requested_window missing '{key}'")

    if not isinstance(data["files"], list):
        raise ValueError("manifest.json 'files' must be a list")

    return data


def compute_sha256(file_path: Path) -> str:
    """Compute sha256 hex digest of a file using ``hashlib.file_digest``."""
    with file_path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def format_to_table(filename: str) -> str:
    """Map a manifest filename to its source format string.

    Uses pattern matching: anything starting with ``postgresql`` and ending
    ``.log`` or ``.json`` maps to ``pglog``.  Exact matches are checked first.

    Raises ``ValueError`` for unknown filenames.
    """
    # Exact match first
    if filename in _FILENAME_TO_FORMAT:
        return _FILENAME_TO_FORMAT[filename]

    # Pattern match for rotated PG log files (e.g. postgresql-16-main.log)
    if filename.startswith("postgresql") and (
        filename.endswith(".log") or filename.endswith(".json")
    ):
        return "pglog"

    return ""  # Unknown format — caller should skip
