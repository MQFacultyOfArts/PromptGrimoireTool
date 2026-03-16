"""Systemd journal JSON parser (pure function, FCIS pattern).

Parses journal JSON export (one JSON object per line) into dicts suitable
for insertion into the ``journal_events`` table.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from scripts.incident.parsers import in_window

logger = logging.getLogger(__name__)


def parse_journal(
    data: bytes, window_start_utc: str, window_end_utc: str
) -> list[dict]:
    """Parse systemd journal JSON lines into event dicts.

    Parameters
    ----------
    data:
        Raw bytes of the journal JSON file (one JSON object per line).
    window_start_utc:
        ISO 8601 UTC string for the start of the analysis window.
    window_end_utc:
        ISO 8601 UTC string for the end of the analysis window.

    Returns
    -------
    list[dict]
        Each dict has keys: ``ts_utc``, ``priority``, ``pid``, ``unit``,
        ``message``, ``raw_json``.
    """
    text = data.decode("utf-8")
    events: list[dict] = []

    for line in text.splitlines():
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSON line")
            continue

        ts_str = record.get("__REALTIME_TIMESTAMP")
        if ts_str is None:
            logger.warning("Skipping journal line without __REALTIME_TIMESTAMP")
            continue

        # Convert microsecond epoch to ISO 8601 UTC
        epoch_s = int(ts_str) / 1_000_000
        ts_utc = datetime.fromtimestamp(epoch_s, tz=UTC).isoformat()

        if not in_window(ts_utc, window_start_utc, window_end_utc):
            continue

        priority_str = record.get("PRIORITY")
        pid_str = record.get("_PID")

        events.append(
            {
                "ts_utc": ts_utc,
                "priority": int(priority_str) if priority_str is not None else None,
                "pid": int(pid_str) if pid_str is not None else None,
                "unit": record.get("_SYSTEMD_UNIT"),
                "message": record.get("MESSAGE"),
                "raw_json": line,
            }
        )

    return events
