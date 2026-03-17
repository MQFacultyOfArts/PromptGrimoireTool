"""PostgreSQL log parsers — pure functions: bytes → list[dict].

Two parsers for different PG log formats:
- ``parse_pglog_text``: text format (``log_line_prefix = '%t [%p] '``)
- ``parse_pglog_json``: PostgreSQL 15+ jsonlog format

Both return dicts matching the ``pglog_events`` schema:
ts_utc, pid, level, error_type, detail, statement, message.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from scripts.incident.parsers import in_window

logger = logging.getLogger(__name__)

# Matches PG log_line_prefix = '%t [%p] ' (Ubuntu/Debian default for PG 16):
# 2026-03-14 13:19:49.544 UTC [2482047] LOG:  checkpoint starting: time
# Also handles without milliseconds: 2026-03-16 04:32:52 UTC [1234] ERROR:  msg
_TEXT_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)? \w+"
    r" \[(\d+)\] (\w+):\s+(.*)$"
)

# Continuation severity levels that merge into the previous entry.
_CONTINUATION_LEVELS = frozenset({"DETAIL", "STATEMENT", "HINT", "CONTEXT"})


def _flush_entry(
    buf: dict,
    window_start: str,
    window_end: str,
    results: list[dict],
) -> None:
    """Flush a buffered entry into *results* if it passes the window."""
    if not buf:
        return
    if not in_window(buf["ts_utc"], window_start, window_end):
        return
    results.append(buf)


def parse_pglog_text(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    """Parse PostgreSQL text-format log bytes.

    Groups multi-line entries (ERROR + DETAIL + STATEMENT with
    the same PID and timestamp) into a single event dict.

    PG text timestamps are already UTC — stored as-is.

    Returns list of dicts with keys: ``ts_utc``, ``pid``,
    ``level``, ``error_type``, ``detail``, ``statement``,
    ``message``.
    """
    results: list[dict] = []
    current: dict = {}

    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue

        m = _TEXT_LINE_RE.match(line)
        if m is None:
            # Unprefixed continuation line — append to message.
            if current:
                current["message"] += "\n" + line
            continue

        ts_raw, pid_str, level, text = m.groups()
        pid = int(pid_str)
        # Convert "2026-03-16 04:32:52" to ISO with UTC tz.
        ts_utc = ts_raw.replace(" ", "T", 1) + "+00:00"

        # Is this a continuation of the current buffer?
        if (
            current
            and level in _CONTINUATION_LEVELS
            and current["pid"] == pid
            and current["ts_utc"] == ts_utc
        ):
            low = level.lower()
            current[low] = text
            current["message"] += "\n" + text
            continue

        # New entry — flush the previous one.
        _flush_entry(current, window_start_utc, window_end_utc, results)

        current = {
            "ts_utc": ts_utc,
            "pid": pid,
            "level": level,
            "error_type": text,
            "detail": None,
            "statement": None,
            "message": text,
        }

    # Flush the last buffered entry.
    _flush_entry(current, window_start_utc, window_end_utc, results)

    return results


def _parse_pg_json_timestamp(raw: str) -> str:
    """Convert PG jsonlog timestamp to ISO 8601 UTC.

    Input format: ``"2026-03-16 04:32:52.000 GMT"``
    Output: ``"2026-03-16T04:32:52+00:00"``
    """
    # Strip the trailing timezone label and parse.
    raw = raw.strip()
    if raw.endswith(" GMT") or raw.endswith(" UTC"):
        raw = raw[:-4]
    dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
    dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def parse_pglog_json(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    """Parse PostgreSQL jsonlog format (one JSON object per line).

    Returns list of dicts with the same schema as
    ``parse_pglog_text``.
    """
    results: list[dict] = []

    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed PG JSON line")
            continue

        raw_ts = record.get("timestamp")
        if raw_ts is None:
            logger.warning("Skipping PG JSON line without timestamp")
            continue

        ts_utc = _parse_pg_json_timestamp(raw_ts)

        if not in_window(ts_utc, window_start_utc, window_end_utc):
            continue

        msg = record.get("message", "")
        detail = record.get("detail")
        statement = record.get("statement")

        # Build full message like the text parser does.
        parts = [msg]
        if detail:
            parts.append(detail)
        if statement:
            parts.append(statement)
        full_message = "\n".join(parts)

        results.append(
            {
                "ts_utc": ts_utc,
                "pid": record.get("pid"),
                "level": record.get("error_severity"),
                "error_type": msg,
                "detail": detail,
                "statement": statement,
                "message": full_message,
            }
        )

    return results


def parse_pglog_auto(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    """Auto-detect PG log format and delegate to the right parser.

    Sniffs the first non-empty line: if it starts with ``{``, use
    ``parse_pglog_json``; otherwise use ``parse_pglog_text``.
    """
    text = data.decode("utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            if stripped.startswith("{"):
                return parse_pglog_json(data, window_start_utc, window_end_utc)
            return parse_pglog_text(data, window_start_utc, window_end_utc)
    # Empty input.
    return []
