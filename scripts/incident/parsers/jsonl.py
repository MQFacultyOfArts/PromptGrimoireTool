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
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            logger.warning("Skipping malformed JSONL line")
            continue

        ts = record.get("timestamp")
        if ts is None or not isinstance(ts, str):
            skipped += 1
            logger.warning("Skipping JSONL line with missing or non-string timestamp")
            continue

        # Normalise to canonical Z suffix for consistent string sorting
        ts_normalised = ts.replace("+00:00", "Z") if ts.endswith("+00:00") else ts

        if not in_window(ts_normalised, window_start_utc, window_end_utc):
            continue

        # Build extra_json from all keys NOT in the dedicated column set.
        extra = {k: v for k, v in record.items() if k not in _COLUMN_FIELDS}
        extra_json = json.dumps(extra) if extra else None

        results.append(
            {
                "ts_utc": ts_normalised,
                "level": record.get("level"),
                "event": record.get("event"),
                "user_id": record.get("user_id"),
                "workspace_id": record.get("workspace_id"),
                "request_path": record.get("request_path"),
                "exc_info": record.get(
                    "exc_info"
                ),  # None if absent or JSON null — AC3.5
                "extra_json": extra_json,
            }
        )

    if skipped:
        logger.warning("Skipped %d malformed/incomplete JSONL lines", skipped)

    return results
