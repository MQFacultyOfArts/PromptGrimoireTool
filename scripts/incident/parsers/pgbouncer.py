"""PgBouncer log parser — pure function: bytes → list[dict].

PgBouncer log format (syslog-style with local timezone):
    2026-03-24 18:59:51.118 AEDT [2392057] LOG message text here
    2026-03-24 19:00:51.119 AEDT [2392057] WARNING some warning

Timestamps include a timezone abbreviation (AEDT, AEST, UTC, etc.)
which must be resolved using the manifest's timezone field to get
the correct UTC offset — abbreviations are ambiguous (CST = US Central
or China Standard).
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.incident.parsers import in_window, normalise_utc

# Matches: 2026-03-24 18:59:51.118 AEDT [2392057] LOG message
_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?"
    r" \w+"
    r" \[(\d+)\]"
    r" (\w+)"
    r" (.*)$"
)


def parse_pgbouncer(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
    timezone: str = "Australia/Sydney",
) -> list[dict]:
    """Parse PgBouncer log bytes.

    The *timezone* parameter is the IANA timezone from the manifest
    (e.g. ``Australia/Sydney``).  PgBouncer logs use local time with
    an abbreviated timezone label — we ignore the label and use the
    manifest timezone for conversion, since abbreviations are ambiguous.

    Returns list of dicts with keys: ``ts_utc``, ``pid``, ``level``,
    ``message``.
    """
    tz = ZoneInfo(timezone)
    results: list[dict] = []

    for line in data.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue

        m = _LINE_RE.match(line)
        if m is None:
            continue

        ts_raw, pid_str, level, message = m.groups()
        local_dt = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
        aware_dt = local_dt.replace(tzinfo=tz)
        ts_utc = normalise_utc(aware_dt)

        if not in_window(ts_utc, window_start_utc, window_end_utc):
            continue

        results.append(
            {
                "ts_utc": ts_utc,
                "pid": int(pid_str),
                "level": level,
                "message": message,
            }
        )

    return results
