"""HAProxy access-log parser — pure function: bytes → (list[dict], int).

Parses rsyslog-prefixed HAProxy HTTP-mode log lines into dicts matching the
``haproxy_events`` schema.  The rsyslog ISO 8601 prefix is used for the
timestamp (not the inner ``[%tr]`` field).  Unparseable lines are counted
and returned as the second element of the tuple (AC3.4).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from scripts.incident.parsers import in_window, normalise_utc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex for rsyslog-prefixed HAProxy HTTP-mode log lines
# ---------------------------------------------------------------------------
# Groups:
#  1: rsyslog ISO 8601 timestamp  (e.g. 2026-03-16T16:06:45+11:00)
#  2: client IP
#  3: client port
#  4: inner [%tr] timestamp       (skipped)
#  5: frontend name
#  6: backend name
#  7: server name
#  8-12: TR/Tw/Tc/Tr/Ta timing fields
#  13: status code
#  14: bytes read
#  15: request line content       (inside quotes)

_LINE_RE = re.compile(
    r"^(\S+)"  # 1: rsyslog timestamp
    r" \S+ haproxy\[\d+\]: "  #    hostname + haproxy[pid]:
    r"(.+?)"  # 2: client IP (IPv4 or IPv6)
    r":(\d+)"  # 3: client port (last colon before space+[)
    r" \[[^\]]+\]"  #    [%tr] inner timestamp (skip)
    r" (\S+)"  # 4: frontend
    r" (\S+)/(\S+)"  # 5: backend / 6: server
    r" (-?\d+)/(-?\d+)/(-?\d+)/(-?\d+)/(-?\d+)"  # 7-11: TR/Tw/Tc/Tr/Ta
    r" (\d+)"  # 12: status code
    r" (\d+)"  # 13: bytes read
    r" .+?"  #    cookie/cache/termination/connections/queues/headers
    r' "(\S+) (\S+) \S+"'  # 14: method, 15: path (from request line)
    r"$",
)


def parse_haproxy(
    data: bytes,
    window_start_utc: str,
    window_end_utc: str,
    timezone: str,  # noqa: ARG001 — contract requires param; rsyslog prefix carries offset
) -> tuple[list[dict], int]:
    """Parse HAProxy log bytes into event dicts.

    Parameters
    ----------
    data:
        Raw bytes of the HAProxy log file.
    window_start_utc:
        ISO 8601 UTC string for the start of the analysis window.
    window_end_utc:
        ISO 8601 UTC string for the end of the analysis window.
    timezone:
        IANA timezone name from manifest.json (e.g. ``"Australia/Sydney"``).
        Not used directly — the rsyslog prefix already carries the UTC offset.

    Returns
    -------
    tuple[list[dict], int]
        ``(events, unparseable_count)``.  Each event dict has keys:
        ``ts_utc``, ``client_ip``, ``status_code``, ``tr_ms``, ``tw_ms``,
        ``tc_ms``, ``tr_resp_ms``, ``ta_ms``, ``backend``, ``server``,
        ``method``, ``path``, ``bytes_read``.
    """
    text = data.decode("utf-8")
    events: list[dict] = []
    unparseable_count = 0

    for line in text.splitlines():
        if not line.strip():
            continue

        m = _LINE_RE.match(line)
        if m is None:
            unparseable_count += 1
            continue

        # Parse rsyslog ISO 8601 prefix and convert to canonical UTC
        ts_local = datetime.fromisoformat(m.group(1))
        ts_utc = normalise_utc(ts_local)

        if not in_window(ts_utc, window_start_utc, window_end_utc):
            continue

        events.append(
            {
                "ts_utc": ts_utc,
                "client_ip": m.group(2),
                "status_code": int(m.group(12)),
                "tr_ms": int(m.group(7)),
                "tw_ms": int(m.group(8)),
                "tc_ms": int(m.group(9)),
                "tr_resp_ms": int(m.group(10)),
                "ta_ms": int(m.group(11)),
                "backend": m.group(5),
                "server": m.group(6),
                "method": m.group(14),
                "path": m.group(15),
                "bytes_read": int(m.group(13)),
            }
        )

    if unparseable_count:
        logger.warning("Skipped %d unparseable HAProxy lines", unparseable_count)

    return events, unparseable_count
