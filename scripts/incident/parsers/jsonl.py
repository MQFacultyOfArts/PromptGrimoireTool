"""Structlog JSONL parser — pure function: bytes → list[dict].

Extracts structlog JSON lines into dicts matching the ``jsonl_events`` schema.
Dedicated columns: level, event, user_id, workspace_id, request_path, exc_info.
All remaining fields go into ``extra_json`` as a JSON string.
"""

from __future__ import annotations

import json
import logging

from scripts.incident.parsers import in_window

logger = logging.getLogger(__name__)


def _extract_timestamp(record: dict) -> str | None:
    """Extract and normalise the timestamp from a JSONL record.

    Returns the normalised timestamp string, or None if the record
    should be skipped (missing, non-string, or unparseable timestamp).
    """
    ts = record.get("timestamp")
    if ts is None or not isinstance(ts, str):
        logger.warning("Skipping JSONL line with missing or non-string timestamp")
        return None
    return ts.replace("+00:00", "Z") if ts.endswith("+00:00") else ts


# Fields extracted to dedicated columns (plus timestamp, which becomes ts_utc).
_COLUMN_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "event",
        "user_id",
        "workspace_id",
        "request_path",
        "exc_info",
    }
)


def _event_from_record(record: dict, ts_normalised: str) -> dict:
    """Build the ``jsonl_events`` row dict for one already-validated record."""
    # extra_json holds all keys NOT in the dedicated column set.
    extra = {k: v for k, v in record.items() if k not in _COLUMN_FIELDS}
    return {
        "ts_utc": ts_normalised,
        "level": record.get("level"),
        "event": record.get("event"),
        "user_id": record.get("user_id"),
        "workspace_id": record.get("workspace_id"),
        "request_path": record.get("request_path"),
        "exc_info": record.get("exc_info"),  # None if absent or JSON null — AC3.5
        "extra_json": json.dumps(extra) if extra else None,
    }


def _parse_line(
    line: str,
    window_start_utc: str,
    window_end_utc: str,
) -> tuple[dict | None, bool]:
    """Parse one JSONL line into ``(event, skipped)``.

    ``event`` is ``None`` when the line produced no row (blank, malformed,
    missing/unparseable timestamp, or simply outside the window). ``skipped``
    is ``True`` only for malformed/incomplete lines — blank lines and lines
    that parsed fine but fell outside the window are not counted as skipped.
    """
    if not line.strip():
        return None, False

    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("Skipping malformed JSONL line")
        return None, True

    ts_normalised = _extract_timestamp(record)
    if ts_normalised is None:
        return None, True

    try:
        if not in_window(ts_normalised, window_start_utc, window_end_utc):
            return None, False
    except ValueError, TypeError:
        logger.warning("Skipping JSONL line with unparseable timestamp")
        return None, True

    return _event_from_record(record, ts_normalised), False


def parse_jsonl(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    """Parse structlog JSONL bytes into a list of event dicts.

    Each returned dict has keys matching the ``jsonl_events`` table columns:
    ts_utc, level, event, user_id, workspace_id, request_path, exc_info, extra_json.

    Events outside ``[window_start_utc, window_end_utc]`` are discarded.
    Malformed lines and lines missing ``timestamp`` are skipped with a log warning.
    """
    results: list[dict] = []
    skipped = 0

    for line in data.decode("utf-8").split("\n"):
        event, was_skipped = _parse_line(line, window_start_utc, window_end_utc)
        skipped += was_skipped
        if event is not None:
            results.append(event)

    if skipped:
        logger.warning("Skipped %d malformed/incomplete JSONL lines", skipped)

    return results
