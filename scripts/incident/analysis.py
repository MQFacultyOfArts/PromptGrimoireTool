"""Epoch analysis queries for incident database."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

_CRASH_BOUNCE_THRESHOLD = 300  # seconds


def extract_epochs(
    conn: sqlite3.Connection,
) -> list[dict[str, object]]:
    """Detect epoch boundaries from commit hash transitions.

    Scans JSONL events ordered by timestamp, grouping contiguous
    runs of the same commit hash into epochs.  Each epoch records
    its commit, time window, event count, duration, and whether
    the short duration suggests a crash-bounce restart.
    """
    rows = conn.execute(
        "SELECT ts_utc, json_extract(extra_json, '$.commit')"
        " FROM jsonl_events"
        " WHERE extra_json IS NOT NULL"
        " ORDER BY ts_utc",
    ).fetchall()

    if not rows:
        return []

    epochs: list[dict[str, object]] = []
    current_commit = rows[0][1]
    start_utc = rows[0][0]
    end_utc = rows[0][0]
    count = 1

    for ts_utc, commit in rows[1:]:
        if commit != current_commit:
            # Close current epoch
            _append_epoch(
                epochs,
                current_commit,
                start_utc,
                end_utc,
                count,
            )
            current_commit = commit
            start_utc = ts_utc
            end_utc = ts_utc
            count = 1
        else:
            end_utc = ts_utc
            count += 1

    # Close final epoch
    _append_epoch(epochs, current_commit, start_utc, end_utc, count)

    return epochs


def _append_epoch(
    epochs: list[dict[str, object]],
    commit: str,
    start_utc: str,
    end_utc: str,
    event_count: int,
) -> None:
    dt_start = datetime.fromisoformat(start_utc)
    dt_end = datetime.fromisoformat(end_utc)
    duration = (dt_end - dt_start).total_seconds()
    epochs.append(
        {
            "commit": commit,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "event_count": event_count,
            "duration_seconds": duration,
            "is_crash_bounce": duration < _CRASH_BOUNCE_THRESHOLD,
        }
    )


_CONSUMED_RE = re.compile(
    r"Consumed (.+?) CPU time,"
    r" (.+?) memory peak,"
    r" (.+?) memory swap peak",
)

_UNIT_MULTIPLIERS: dict[str, int] = {
    "B": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
}


def _parse_memory_bytes(size_str: str) -> int | None:
    """Parse systemd memory strings like '2.7G', '366.5M', '0B'.

    Uses binary units: B=1, K=1024, M=1024^2, G=1024^3.
    """
    if size_str == "0B":
        return 0
    # Match number + optional suffix
    m = re.match(r"^([0-9.]+)([BKMG])$", size_str)
    if not m:
        return None
    value = float(m.group(1))
    suffix = m.group(2)
    return int(value * _UNIT_MULTIPLIERS[suffix])


def enrich_epochs_journal(
    conn: sqlite3.Connection,
    epochs: list[dict[str, object]],
) -> None:
    """Enrich epochs in place with journal Consumed message data.

    For each epoch, searches journal_events near the epoch end
    for systemd resource-consumption messages and parses CPU time,
    memory peak, and swap peak values.  If the journal timestamp
    is later than the epoch end, the epoch end is corrected.
    """
    for epoch in epochs:
        end_utc = str(epoch["end_utc"])
        dt_end = datetime.fromisoformat(end_utc)

        window_lo = (dt_end - timedelta(seconds=60)).isoformat()
        window_hi = (dt_end + timedelta(seconds=60)).isoformat()

        row = conn.execute(
            "SELECT ts_utc, message FROM journal_events"
            " WHERE message LIKE '%Consumed%'"
            " AND ts_utc >= ? AND ts_utc <= ?"
            " ORDER BY ts_utc DESC LIMIT 1",
            (window_lo, window_hi),
        ).fetchone()

        if row is None:
            epoch["cpu_consumed"] = None
            epoch["memory_peak"] = None
            epoch["swap_peak"] = None
            epoch["memory_peak_bytes"] = None
            continue

        journal_ts, message = row
        m = _CONSUMED_RE.search(message)
        if not m:
            epoch["cpu_consumed"] = None
            epoch["memory_peak"] = None
            epoch["swap_peak"] = None
            epoch["memory_peak_bytes"] = None
            continue

        epoch["cpu_consumed"] = m.group(1)
        epoch["memory_peak"] = m.group(2)
        epoch["swap_peak"] = m.group(3)
        epoch["memory_peak_bytes"] = _parse_memory_bytes(
            m.group(2),
        )

        # Epoch end correction: if journal ts is later, update
        dt_journal = datetime.fromisoformat(journal_ts)
        if dt_journal > dt_end:
            epoch["end_utc"] = journal_ts
            dt_start = datetime.fromisoformat(
                str(epoch["start_utc"]),
            )
            duration = (dt_journal - dt_start).total_seconds()
            epoch["duration_seconds"] = duration
            epoch["is_crash_bounce"] = duration < _CRASH_BOUNCE_THRESHOLD


def enrich_epochs_github(
    conn: sqlite3.Connection,
    epochs: list[dict[str, object]],
) -> None:
    """Enrich epochs in place with GitHub PR metadata.

    Matches epoch commit hashes (short prefixes) against
    full commit OIDs in github_events.
    """
    for epoch in epochs:
        commit = str(epoch["commit"])
        row = conn.execute(
            "SELECT pr_number, title, author, url"
            " FROM github_events"
            " WHERE commit_oid LIKE ? || '%'"
            " LIMIT 1",
            (commit,),
        ).fetchone()

        if row:
            epoch["pr_number"] = row[0]
            epoch["pr_title"] = row[1]
            epoch["pr_author"] = row[2]
            epoch["pr_url"] = row[3]
        else:
            epoch["pr_number"] = None
            epoch["pr_title"] = "no PR"
            epoch["pr_author"] = None
            epoch["pr_url"] = None
