"""Epoch analysis queries for incident database."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

_CRASH_BOUNCE_THRESHOLD = 300  # seconds

LOGIN_EVENT_PATTERN = "Login successful%"


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


# ── Restart classification ────────────────────────────────────────

# Restart reasons, ordered from most to least concerning:
RESTART_OOM = "oom-kill"  # systemd/kernel killed the process
RESTART_CRASH = "crash"  # process exited with non-zero status
RESTART_UNKNOWN = "unknown"  # no journal evidence (hard kill? power loss?)
RESTART_MANUAL = "manual-restart"  # same commit, clean shutdown
RESTART_DEPLOY = "deploy"  # commit changed → deliberate deploy
RESTART_FIRST = "first"  # first epoch in the window (no predecessor)

_EXIT_CODE_RE = re.compile(r"Main process exited, code=(\w+), status=(\d+)(?:/\w+)?")


def enrich_restart_reasons(
    conn: sqlite3.Connection,
    epochs: list[dict],
) -> None:
    """Classify why each epoch started (deploy, crash, OOM, manual restart).

    Enriches each epoch dict in place with ``restart_reason``.
    The classification examines whether the commit changed from the
    previous epoch, and what journal messages appear in the gap
    between epochs.
    """
    for i, epoch in enumerate(epochs):
        if i == 0:
            epoch["restart_reason"] = RESTART_FIRST
            continue

        prev = epochs[i - 1]
        commit_changed = epoch["commit"] != prev["commit"]

        # Look at journal messages between previous epoch end and this epoch start
        gap_start = str(prev["end_utc"])
        gap_end = str(epoch["start_utc"])

        rows = conn.execute(
            "SELECT message FROM journal_events"
            " WHERE ts_utc >= ? AND ts_utc <= ?"
            " ORDER BY ts_utc",
            (gap_start, gap_end),
        ).fetchall()

        messages = [r[0] for r in rows if r[0]]
        reason = _classify_gap(commit_changed, messages)
        epoch["restart_reason"] = reason


def _classify_gap(commit_changed: bool, messages: list[str]) -> str:
    """Classify restart reason from commit change and journal messages."""
    abnormal = _detect_abnormal_exit(messages)
    if abnormal:
        return abnormal

    if commit_changed:
        return RESTART_DEPLOY

    if _has_clean_shutdown(messages):
        return RESTART_MANUAL

    return RESTART_UNKNOWN


def _detect_abnormal_exit(messages: list[str]) -> str | None:
    """Check messages for OOM kills or crash exit codes."""
    for msg in messages:
        lower = msg.lower()
        if "oom-kill" in lower or "out of memory" in lower:
            return RESTART_OOM

    for msg in messages:
        m = _EXIT_CODE_RE.search(msg)
        if not m:
            continue
        code, status = m.group(1), int(m.group(2))
        if code == "killed":
            return RESTART_OOM
        if status != 0:
            return RESTART_CRASH

    return None


def _has_clean_shutdown(messages: list[str]) -> bool:
    """Check if messages contain a clean systemd shutdown sequence."""
    return any("Stopping" in msg or "Stopped" in msg for msg in messages)


# ── Event normalisation ──────────────────────────────────────────

_NORMALISE_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_NORMALISE_ADDR = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)
_NORMALISE_TASK = re.compile(r"Task-\d+")
_NORMALISE_POOL_TRANSIENT = re.compile(
    r"\s*checked_in=\d+\s*checked_out=\d+\s*overflow=\d+/\d+",
)


def normalise_event(event: str) -> str:
    """Collapse variable tokens in an event string to produce a stable class key.

    Replaces UUIDs, hex addresses, asyncio task names, and transient
    pool state counters so that structurally identical events map to
    the same key regardless of runtime-specific values.
    """
    result = _NORMALISE_UUID.sub("<UUID>", event)
    result = _NORMALISE_ADDR.sub("<ADDR>", result)
    result = _NORMALISE_TASK.sub("Task-<N>", result)
    result = _NORMALISE_POOL_TRANSIENT.sub("", result)
    return result


def compute_error_landscape(
    conn: sqlite3.Connection,
    epochs: list[dict],
) -> list[dict]:
    """Compute appeared/resolved error classes per epoch.

    For each epoch, queries distinct error/warning/critical events,
    normalises them via ``normalise_event()``, then computes set
    differences against all prior epochs' classes.
    """
    all_prior_classes: set[str] = set()
    results: list[dict] = []

    for epoch in epochs:
        rows = conn.execute(
            "SELECT DISTINCT event FROM jsonl_events"
            " WHERE ts_utc >= ? AND ts_utc <= ?"
            " AND level IN ('error', 'critical', 'warning')",
            (epoch["start_utc"], epoch["end_utc"]),
        ).fetchall()

        current_classes = {normalise_event(row[0]) for row in rows}
        appeared = current_classes - all_prior_classes
        resolved = all_prior_classes - current_classes

        results.append(
            {
                "appeared": appeared,
                "resolved": resolved,
                "current": current_classes,
            }
        )
        all_prior_classes |= current_classes

    return results


# ── Restart gap enrichment ────────────────────────────────────────


def enrich_restart_gaps(epochs: list[dict]) -> None:
    """Compute downtime duration between consecutive epochs.

    Enriches each epoch dict in place with ``restart_gap_seconds``.
    First epoch gets ``None`` (no predecessor).
    """
    for i, epoch in enumerate(epochs):
        if i == 0:
            epoch["restart_gap_seconds"] = None
            continue
        prev_end = datetime.fromisoformat(str(epochs[i - 1]["end_utc"]))
        curr_start = datetime.fromisoformat(str(epoch["start_utc"]))
        epoch["restart_gap_seconds"] = (curr_start - prev_end).total_seconds()


# ── Pool configuration detection ─────────────────────────────────

_POOL_SIZE_RE = re.compile(r"size=(\d+)")
_POOL_OVERFLOW_RE = re.compile(r"overflow\s*=?\s*\d+/(\d+)")


def detect_pool_config(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> dict | None:
    """Extract SQLAlchemy pool configuration from INVALIDATE/QueuePool events.

    Queries raw (un-normalised) events to read transient pool counters.
    Returns ``{"pool_size": int, "max_overflow": int | None}`` or ``None``.
    """
    # Prefer INVALIDATE events (have size=N) over QueuePool limit (may not)
    row = conn.execute(
        "SELECT event FROM jsonl_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " AND (event LIKE '%INVALIDATE%size=%' OR event LIKE '%QueuePool limit%')"
        " ORDER BY (event LIKE '%INVALIDATE%size=%') DESC"
        " LIMIT 1",
        (start_utc, end_utc),
    ).fetchone()

    if row is None:
        return None

    event = row[0]
    size_match = _POOL_SIZE_RE.search(event)
    if not size_match:
        return None

    overflow_match = _POOL_OVERFLOW_RE.search(event)
    return {
        "pool_size": int(size_match.group(1)),
        "max_overflow": int(overflow_match.group(1)) if overflow_match else None,
    }


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
            pr_number, title, author, url = row
            epoch["pr_number"] = pr_number
            epoch["pr_title"] = title
            epoch["pr_author"] = author
            epoch["pr_url"] = url
        else:
            epoch["pr_number"] = None
            epoch["pr_title"] = "no PR"
            epoch["pr_author"] = None
            epoch["pr_url"] = None


def query_epoch_errors(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
    duration_seconds: float,
) -> list[dict]:
    """Query error/warning/critical JSONL events within an epoch window.

    Groups by level and event, calculates per-hour rate (or marks
    as crash-bounce if epoch is shorter than 300 seconds).
    """
    rows = conn.execute(
        "SELECT level, event, COUNT(*) AS count"
        " FROM jsonl_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " AND level IN ('error', 'critical', 'warning')"
        " GROUP BY level, event"
        " ORDER BY count DESC",
        (start_utc, end_utc),
    ).fetchall()

    is_crash = duration_seconds < _CRASH_BOUNCE_THRESHOLD
    result: list[dict] = []
    for level, event, count in rows:
        result.append(
            {
                "level": level,
                "event": event,
                "count": count,
                "per_hour": None if is_crash else count / (duration_seconds / 3600),
                "is_crash_bounce": is_crash,
            }
        )
    return result


def _query_nosrv_clustering(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> tuple[int, int]:
    """Count NOSRV events total and within first 60 seconds of epoch."""
    count_nosrv = conn.execute(
        "SELECT COUNT(*) FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " AND server = '<NOSRV>'",
        (start_utc, end_utc),
    ).fetchone()[0]

    if count_nosrv > 0:
        dt_start = datetime.fromisoformat(start_utc)
        cutoff_60s = (dt_start + timedelta(seconds=60)).isoformat()
        nosrv_first_60s = conn.execute(
            "SELECT COUNT(*) FROM haproxy_events"
            " WHERE ts_utc >= ? AND ts_utc <= ?"
            " AND server = '<NOSRV>'",
            (start_utc, cutoff_60s),
        ).fetchone()[0]
    else:
        nosrv_first_60s = 0

    return count_nosrv, nosrv_first_60s


def query_epoch_haproxy(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
    duration_seconds: float,
) -> dict:
    """Query HAProxy traffic stats within an epoch window.

    Returns status code distribution, request totals, 5xx rates,
    and latency percentiles (p50/p95/p99).
    """
    # Status code distribution
    status_rows = conn.execute(
        "SELECT status_code, COUNT(*) AS count"
        " FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " GROUP BY status_code"
        " ORDER BY status_code",
        (start_utc, end_utc),
    ).fetchall()
    status_codes = [{"status_code": code, "count": cnt} for code, cnt in status_rows]

    # Totals — exclude <NOSRV> (HAProxy 503s during restart, not app errors).
    # <NOSRV> means HAProxy had no backend available (app restarting).
    # These are infrastructure transients, not application errors.
    row = conn.execute(
        "SELECT COUNT(*) AS total_requests,"
        " SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS count_5xx"
        " FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " AND (server IS NULL OR server != '<NOSRV>')",
        (start_utc, end_utc),
    ).fetchone()
    total_requests = row[0]
    count_5xx = row[1] or 0

    count_nosrv, nosrv_first_60s = _query_nosrv_clustering(conn, start_utc, end_utc)

    is_crash = duration_seconds < _CRASH_BOUNCE_THRESHOLD

    # Percentiles — also exclude <NOSRV> (no meaningful response time)
    p50_ms: int | None = None
    p95_ms: int | None = None
    p99_ms: int | None = None

    sample_count_row = conn.execute(
        "SELECT COUNT(*) FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL"
        " AND (server IS NULL OR server != '<NOSRV>')",
        (start_utc, end_utc),
    ).fetchone()
    sample_count = sample_count_row[0]

    if sample_count > 0:
        for pct, attr in [(0.50, "p50_ms"), (0.95, "p95_ms"), (0.99, "p99_ms")]:
            pct_row = conn.execute(
                "SELECT ta_ms FROM haproxy_events"
                " WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL"
                " AND (server IS NULL OR server != '<NOSRV>')"
                " ORDER BY ta_ms"
                " LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * ? AS INTEGER)"
                "   FROM haproxy_events"
                "   WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL"
                "   AND (server IS NULL OR server != '<NOSRV>'))",
                (start_utc, end_utc, pct, start_utc, end_utc),
            ).fetchone()
            if pct_row:
                if attr == "p50_ms":
                    p50_ms = pct_row[0]
                elif attr == "p95_ms":
                    p95_ms = pct_row[0]
                else:
                    p99_ms = pct_row[0]

    return {
        "status_codes": status_codes,
        "total_requests": total_requests,
        "count_5xx": count_5xx,
        "rate_5xx": None if is_crash else count_5xx / (duration_seconds / 3600),
        "requests_per_minute": None
        if is_crash
        else total_requests / (duration_seconds / 60),
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "p99_ms": p99_ms,
        "sample_count": sample_count,
        "count_nosrv": count_nosrv,
        "nosrv_first_60s": nosrv_first_60s,
    }


def query_epoch_resources(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> dict:
    """Query Beszel resource metrics (CPU, memory, load) within an epoch window."""
    row = conn.execute(
        "SELECT AVG(cpu) AS mean_cpu, MAX(cpu) AS max_cpu,"
        " AVG(mem_percent) AS mean_mem, MAX(mem_percent) AS max_mem,"
        " AVG(load_1) AS mean_load, MAX(load_1) AS max_load"
        " FROM beszel_metrics"
        " WHERE ts_utc >= ? AND ts_utc <= ?",
        (start_utc, end_utc),
    ).fetchone()

    return {
        "mean_cpu": row[0],
        "max_cpu": row[1],
        "mean_mem": row[2],
        "max_mem": row[3],
        "mean_load": row[4],
        "max_load": row[5],
    }


def query_epoch_pg(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> list[dict]:
    """Query PostgreSQL events grouped by level and error type."""
    rows = conn.execute(
        "SELECT level, error_type, COUNT(*) AS count"
        " FROM pg_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " GROUP BY level, error_type"
        " ORDER BY count DESC",
        (start_utc, end_utc),
    ).fetchall()

    return [
        {"level": level, "error_type": error_type, "count": count}
        for level, error_type, count in rows
    ]


def query_epoch_journal_anomalies(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> list[dict]:
    """Query high-priority journal events (priority <= 3: emerg/alert/crit/err)."""
    rows = conn.execute(
        "SELECT ts_utc, priority, unit, message"
        " FROM journal_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?"
        " AND priority <= 3"
        " ORDER BY ts_utc",
        (start_utc, end_utc),
    ).fetchall()

    return [
        {"ts_utc": ts, "priority": pri, "unit": unit, "message": msg}
        for ts, pri, unit, msg in rows
    ]


def _user_metrics_windowed(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> dict[str, int]:
    """User metrics within a time window."""
    where = "ts_utc >= ? AND ts_utc <= ?"
    params: tuple[str, ...] = (start_utc, end_utc)
    return _user_metrics_core(conn, where, params)


def _user_metrics_all(conn: sqlite3.Connection) -> dict[str, int]:
    """User metrics across all JSONL data (no time bounds)."""
    return _user_metrics_core(conn, "1=1", ())


def _user_metrics_core(
    conn: sqlite3.Connection,
    where_clause: str,
    params: tuple[str, ...],
) -> dict[str, int]:
    """Shared implementation for user metrics queries.

    Both where_clause values are hardcoded constants from the two
    callers above — never derived from external input.
    """
    login_params = (*params, LOGIN_EVENT_PATTERN)

    unique_logins = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM jsonl_events"  # noqa: S608
        f" WHERE {where_clause}"
        " AND event LIKE ?"
        " AND user_id IS NOT NULL",
        login_params,
    ).fetchone()[0]

    active_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM jsonl_events"  # noqa: S608
        f" WHERE {where_clause}"
        " AND user_id IS NOT NULL",
        params,
    ).fetchone()[0]

    active_workspaces = conn.execute(
        "SELECT COUNT(DISTINCT workspace_id) FROM jsonl_events"  # noqa: S608
        f" WHERE {where_clause}"
        " AND workspace_id IS NOT NULL",
        params,
    ).fetchone()[0]

    workspace_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM jsonl_events"  # noqa: S608
        f" WHERE {where_clause}"
        " AND user_id IS NOT NULL"
        " AND workspace_id IS NOT NULL",
        params,
    ).fetchone()[0]

    return {
        "unique_logins": unique_logins,
        "active_users": active_users,
        "active_workspaces": active_workspaces,
        "workspace_users": workspace_users,
    }


def query_epoch_users(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
) -> dict[str, int]:
    """Query distinct user activity metrics within an epoch window."""
    return _user_metrics_windowed(conn, start_utc, end_utc)


def query_summative_users(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    """Query distinct user activity metrics across all JSONL data (no time bounds)."""
    return _user_metrics_all(conn)


def load_static_counts(counts_path: Path | None) -> dict | None:
    """Load static counts from a JSON file.

    Returns None if counts_path is None.
    Lets FileNotFoundError and json.JSONDecodeError propagate.
    """
    if counts_path is None:
        return None
    return json.loads(counts_path.read_text())


# ── Trend analysis ────────────────────────────────────────────────

_TREND_METRICS = (
    "5xx_ratio",
    "error_ratio",
    "warning_ratio",
    "memory_peak_bytes",
    "mean_cpu",
    "active_users",
    "pool_size",
)

# Anomaly detection: absolute thresholds per metric.
# A metric is flagged when the current value exceeds its floor.
_ANOMALY_FLOORS: dict[str, float] = {
    "5xx_ratio": 0.01,  # > 1% of requests returning 5xx
    "error_ratio": 0.05,  # > 5% of requests producing errors
    "memory_peak_bytes": 3_221_225_472,  # > 3 GB
    "mean_cpu": 50.0,  # > 50%
}
# warning_ratio and active_users are never flagged as anomalous


def _safe_delta(
    current: float | int | None,
    previous: float | int | None,
) -> dict:
    """Compute delta between current and previous, handling None safely."""
    if current is None or previous is None:
        return {"value": current, "previous": previous, "delta": None}
    delta = current - previous
    return {"value": current, "previous": previous, "delta": delta}


def compute_trends(epochs: list[dict]) -> list[dict]:
    """Compare consecutive non-crash-bounce epochs to detect metric trends.

    Returns a list of trend dicts, each containing the original epoch
    index, commit hash, and per-metric values with deltas. Anomalies
    are flagged when the current value exceeds an absolute threshold.
    """
    # Build list of (original_index, epoch) for non-crash-bounce epochs
    valid = [
        (i, epoch) for i, epoch in enumerate(epochs) if not epoch["is_crash_bounce"]
    ]

    trends: list[dict] = []
    for pos in range(1, len(valid)):
        idx, current = valid[pos]
        _, previous = valid[pos - 1]

        metrics: dict[str, dict] = {}
        for metric in _TREND_METRICS:
            d = _safe_delta(current.get(metric), previous.get(metric))

            if metric == "pool_size":
                # Config change: any non-zero delta is anomalous
                is_anomaly = d["delta"] is not None and d["delta"] != 0
            else:
                is_anomaly = (
                    metric in _ANOMALY_FLOORS
                    and d["value"] is not None
                    and d["value"] > _ANOMALY_FLOORS[metric]
                )

            d["is_anomaly"] = is_anomaly
            metrics[metric] = d

        trends.append(
            {
                "epoch_index": idx,
                "commit": current["commit"],
                "pr_title": current.get("pr_title", ""),
                "total_requests": current.get("total_requests", 0),
                "metrics": metrics,
            }
        )

    return trends


# ── Report rendering ──────────────────────────────────────────────


def _md_table(
    headers: list[str],
    rows: list[list[str]],
    alignments: list[str] | None = None,
) -> list[str]:
    """Generate markdown table lines from headers and row data.

    alignments: list of 'l', 'r', or 'c' per column. Defaults to left-aligned.
    """
    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")

    if alignments is None:
        alignments = ["l"] * len(headers)

    sep_parts: list[str] = []
    for align in alignments:
        if align == "r":
            sep_parts.append("---:")
        elif align == "c":
            sep_parts.append(":---:")
        else:
            sep_parts.append("---")
    lines.append("| " + " | ".join(sep_parts) + " |")

    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

    return lines


def _fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _fmt_gap_duration(seconds: float | None) -> str:
    """Format restart gap duration for the timeline table.

    None → "—", 0 → "0s", <60 → "{n}s", <3600 → "{m}m {s}s", else "{h}h {m}m".
    """
    if seconds is None:
        return "—"
    if seconds == 0.0:
        return "0s"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


def _fmt_delta(value: float | int | None) -> str:
    """Format a numeric delta with +/- sign."""
    if value is None:
        return "N/A"
    prefix = "+" if value >= 0 else ""
    if isinstance(value, float):
        return f"{prefix}{value:.1f}"
    return f"{prefix}{value}"


def _fmt_pct(value: float | None) -> str:
    """Format a percentage change with +/- sign."""
    if value is None:
        return "N/A"
    prefix = "+" if value >= 0 else ""
    return f"{prefix}{value:.1f}%"


def _fmt_val(value: object) -> str:
    """Format a value for table display, handling None."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _render_section_sources(lines: list[str], sources: list[dict]) -> None:
    """Render the Source Inventory section."""
    lines.append("## Source Inventory")
    lines.append("")
    if sources:
        headers = ["Filename", "Format", "SHA256", "Size", "Window"]
        rows: list[list[str]] = []
        for s in sources:
            sha = str(s.get("sha256", ""))[:12]
            window = f"{s.get('window_start_utc', '')} - {s.get('window_end_utc', '')}"
            rows.append(
                [
                    str(s.get("filename", "")),
                    str(s.get("format", "")),
                    sha,
                    str(s.get("size", "")),
                    window,
                ]
            )
        lines.extend(_md_table(headers, rows))
    else:
        lines.append("No sources ingested.")
    lines.append("")


def _render_section_timeline(lines: list[str], epochs: list[dict]) -> None:
    """Render the Epoch Timeline section."""
    lines.append("## Epoch Timeline")
    lines.append("")
    lines.append("> Each row is one epoch. **Restart** shows why the epoch started:")
    lines.append(
        "> `deploy` (commit changed), `manual-restart` (same commit, clean shutdown),"
    )
    lines.append("> `crash` (non-zero exit), `oom-kill` (killed by kernel/systemd), or")
    lines.append(
        "> `unknown` (no journal evidence). ⚡ marks crash-bounce epochs (< 5 min)."
    )
    lines.append(
        "> Non-deploy restarts are the highest-severity signal in this report."
    )
    lines.append("")
    if not epochs:
        lines.append("No epochs detected.")
        lines.append("")
        return
    headers = [
        "#",
        "Commit",
        "PR",
        "Start",
        "End",
        "Duration",
        "Gap",
        "Events",
        "Memory",
        "CPU",
        "Restart",
    ]
    rows: list[list[str]] = []
    for i, e in enumerate(epochs):
        reason = str(e.get("restart_reason", ""))
        if e.get("is_crash_bounce"):
            reason = f"⚡ {reason}"
        pr_info = str(e.get("pr_title", "")) or ""
        pr_num = e.get("pr_number")
        if pr_num is not None:
            pr_info = f"#{pr_num} {pr_info}"
        duration = _fmt_duration(float(e.get("duration_seconds", 0)))
        gap = _fmt_gap_duration(e.get("restart_gap_seconds"))
        rows.append(
            [
                str(i + 1),
                str(e.get("commit", "")),
                pr_info,
                str(e.get("start_utc", "")),
                str(e.get("end_utc", "")),
                duration,
                gap,
                str(e.get("event_count", "")),
                str(e.get("memory_peak", "N/A")),
                str(e.get("cpu_consumed", "N/A")),
                reason,
            ]
        )
    lines.extend(_md_table(headers, rows))
    lines.append("")


def _render_epoch_analysis(
    lines: list[str],
    index: int,
    epoch: dict,
    analysis: dict,
) -> None:
    """Render a single epoch's analysis subsection."""
    commit = epoch.get("commit", "unknown")
    lines.append(f"### Epoch {index + 1}: {commit}")
    lines.append("")

    _render_epoch_errors(lines, analysis.get("errors", []))
    _render_epoch_error_landscape(lines, analysis.get("error_landscape"))
    _render_epoch_haproxy(lines, analysis.get("haproxy", {}))
    _render_epoch_pool_config(lines, analysis.get("pool_config"))
    _render_epoch_resources_section(lines, analysis.get("resources", {}))
    _render_epoch_pg_section(lines, analysis.get("pg", []))
    _render_epoch_journal(lines, analysis.get("journal_anomalies", []))
    _render_epoch_user_activity(lines, analysis.get("users", {}))


def _render_epoch_errors(lines: list[str], errors: list[dict]) -> None:
    if not errors:
        return
    lines.append("**Errors/Warnings:**")
    lines.append("")
    headers = ["Level", "Event", "Count", "Per Hour"]
    rows: list[list[str]] = []
    for err in errors:
        rows.append(
            [
                str(err.get("level", "")),
                str(err.get("event", "")),
                str(err.get("count", "")),
                _fmt_val(err.get("per_hour")),
            ]
        )
    lines.extend(_md_table(headers, rows))
    lines.append("")


def _render_epoch_error_landscape(lines: list[str], landscape: dict | None) -> None:
    """Render appeared/resolved error classes for an epoch."""
    if landscape is None:
        return
    appeared = landscape.get("appeared", set())
    resolved = landscape.get("resolved", set())
    if not appeared and not resolved:
        lines.append("**Error Landscape:** No errors")
        lines.append("")
        return
    lines.append("**Error Landscape:**")
    lines.append("")
    if appeared:
        lines.append("Appeared:")
        for cls in sorted(appeared):
            lines.append(f"- {cls}")
    else:
        lines.append("Appeared: none")
    if resolved:
        lines.append("Resolved:")
        for cls in sorted(resolved):
            lines.append(f"- {cls}")
    else:
        lines.append("Resolved: none")
    lines.append("")


def _render_epoch_pool_config(lines: list[str], pool_config: dict | None) -> None:
    """Render pool configuration for an epoch."""
    if pool_config is not None:
        pool_size = pool_config["pool_size"]
        max_overflow = pool_config.get("max_overflow")
        if max_overflow is not None:
            lines.append(f"**Pool:** size={pool_size}, overflow={max_overflow}")
        else:
            lines.append(f"**Pool:** size={pool_size}")
    else:
        lines.append("**Pool:** not observed")
    lines.append("")


def _render_epoch_haproxy(lines: list[str], haproxy: dict) -> None:
    if not haproxy:
        return
    lines.append("**HAProxy Traffic:**")
    lines.append("")
    lines.append(f"- Total requests: {haproxy.get('total_requests', 'N/A')}")
    lines.append(f"- 5xx count: {haproxy.get('count_5xx', 'N/A')}")
    count_nosrv = haproxy.get("count_nosrv", 0)
    if count_nosrv > 0:
        nosrv_60s = haproxy.get("nosrv_first_60s", 0)
        lines.append(
            f"- Restart 503s (NOSRV): {count_nosrv} ({nosrv_60s} in first 60s)"
        )
    lines.append(f"- 5xx rate/hr: {_fmt_val(haproxy.get('rate_5xx'))}")
    lines.append(f"- Requests/min: {_fmt_val(haproxy.get('requests_per_minute'))}")
    lines.append(f"- p50: {_fmt_val(haproxy.get('p50_ms'))} ms")
    lines.append(f"- p95: {_fmt_val(haproxy.get('p95_ms'))} ms")
    lines.append(f"- p99: {_fmt_val(haproxy.get('p99_ms'))} ms")

    status_codes = haproxy.get("status_codes", [])
    if status_codes:
        lines.append("")
        sc_rows: list[list[str]] = [
            [str(sc.get("status_code", "")), str(sc.get("count", ""))]
            for sc in status_codes
        ]
        lines.extend(_md_table(["Status", "Count"], sc_rows, alignments=["l", "r"]))
    lines.append("")


def _render_epoch_resources_section(lines: list[str], resources: dict) -> None:
    if not resources:
        return
    lines.append("**Resources:**")
    lines.append("")
    lines.append(
        f"- CPU: mean {_fmt_val(resources.get('mean_cpu'))}%,"
        f" max {_fmt_val(resources.get('max_cpu'))}%"
    )
    lines.append(
        f"- Memory: mean {_fmt_val(resources.get('mean_mem'))}%,"
        f" max {_fmt_val(resources.get('max_mem'))}%"
    )
    lines.append(
        f"- Load: mean {_fmt_val(resources.get('mean_load'))},"
        f" max {_fmt_val(resources.get('max_load'))}"
    )
    lines.append("")


def _render_epoch_pg_section(lines: list[str], pg_events: list[dict]) -> None:
    if not pg_events:
        return
    lines.append("**PostgreSQL:**")
    lines.append("")
    headers = ["Level", "Error Type", "Count"]
    rows: list[list[str]] = [
        [
            str(pg.get("level", "")),
            str(pg.get("error_type", "")),
            str(pg.get("count", "")),
        ]
        for pg in pg_events
    ]
    lines.extend(_md_table(headers, rows))
    lines.append("")


def _render_epoch_journal(lines: list[str], anomalies: list[dict]) -> None:
    if not anomalies:
        return
    lines.append("**Journal Anomalies:**")
    lines.append("")
    headers = ["Timestamp", "Priority", "Unit", "Message"]
    rows: list[list[str]] = [
        [
            str(a.get("ts_utc", "")),
            str(a.get("priority", "")),
            str(a.get("unit", "")),
            str(a.get("message", "")),
        ]
        for a in anomalies
    ]
    lines.extend(_md_table(headers, rows))
    lines.append("")


def _render_epoch_user_activity(lines: list[str], users: dict) -> None:
    if not users:
        return
    lines.append("**User Activity:**")
    lines.append("")
    lines.append(f"- Unique logins: {users.get('unique_logins', 0)}")
    lines.append(f"- Active users: {users.get('active_users', 0)}")
    lines.append(f"- Active workspaces: {users.get('active_workspaces', 0)}")
    lines.append(f"- Workspace users: {users.get('workspace_users', 0)}")
    lines.append("")


def _render_section_users(lines: list[str], summative_users: dict) -> None:
    """Render the User Activity Summary section."""
    lines.append("## User Activity Summary")
    lines.append("")
    lines.append(
        "> Summative counts across the entire review window. Users active in multiple"
    )
    lines.append(
        "> epochs are counted once (union, not sum). Compare with static DB counts"
    )
    lines.append("> (if provided) to gauge what fraction of the user base was active.")
    lines.append("")
    lines.append(f"- Unique logins: {summative_users.get('unique_logins', 0)}")
    lines.append(f"- Active users: {summative_users.get('active_users', 0)}")
    lines.append(f"- Active workspaces: {summative_users.get('active_workspaces', 0)}")
    lines.append(f"- Workspace users: {summative_users.get('workspace_users', 0)}")
    lines.append("")


def _render_section_trends(lines: list[str], trends: list[dict]) -> None:
    """Render the Trend Analysis section.

    One row per epoch showing rate/hr for each metric with delta from
    previous epoch. Anomalous values (exceeding absolute thresholds)
    are flagged.
    """
    lines.append("## Trend Analysis")
    lines.append("")
    lines.append(
        "> Cross-epoch comparison normalised by HTTP request volume. Each ratio ="
    )
    lines.append(
        "> (count / total served requests). Delta shows absolute change in percentage"
    )
    lines.append("> points (pp) from the previous non-crash-bounce epoch.")
    lines.append(">")
    lines.append("> **Metrics:**")
    lines.append(
        "> - **5xx Ratio**: server errors / requests. Excludes `<NOSRV>` 503s (HAProxy"
    )
    lines.append(
        ">   returning errors while the app restarts"
        " — infrastructure, not application)."
    )
    lines.append(
        "> - **Error Ratio**: application error+critical log events / requests."
    )
    lines.append(
        "> - **Warning Ratio**: business logic warnings / requests"
        " (expected, not alarming)."
    )
    lines.append(
        "> - **⚠ flag**: value exceeds absolute threshold (5xx > 1%, errors > 5%,"
    )
    lines.append(">   memory > 3GB, CPU > 50%).")
    lines.append("")
    if not trends:
        lines.append("No trend data (fewer than 2 non-crash-bounce epochs).")
        lines.append("")
        return
    headers = [
        "#",
        "Commit",
        "PR",
        "5xx Ratio",
        "Error Ratio",
        "Warning Ratio",
        "Mem Peak",
        "CPU %",
        "Users",
        "Pool",
        "Requests",
    ]
    alignments = ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r"]
    rows: list[list[str]] = []
    for t in trends:
        commit = t.get("commit", "")[:8]
        epoch_idx = str(t.get("epoch_index", ""))
        pr_title = str(t.get("pr_title", ""))
        m = t.get("metrics", {})
        row: list[str] = [epoch_idx, commit, pr_title]
        for key in (
            "5xx_ratio",
            "error_ratio",
            "warning_ratio",
            "memory_peak_bytes",
            "mean_cpu",
            "active_users",
            "pool_size",
        ):
            md = m.get(key, {})
            row.append(_fmt_trend_cell(key, md))
        # total_requests is context, not trended
        total_reqs = t.get("total_requests", "—")
        row.append(str(total_reqs))
        rows.append(row)
    lines.extend(_md_table(headers, rows, alignments=alignments))
    lines.append("")


_RATIO_METRICS = {"5xx_ratio", "error_ratio", "warning_ratio"}


def _fmt_trend_cell(metric: str, md: dict) -> str:
    """Format a single trend cell: value (delta) with anomaly marker."""
    val = md.get("value")
    delta = md.get("delta")
    is_anomaly = md.get("is_anomaly", False)

    if val is None:
        return "—"

    if metric in _RATIO_METRICS:
        val_str = f"{val * 100:.2f}%"
        delta_str = f" ({_fmt_ratio_delta(delta)})" if delta is not None else ""
    elif metric == "memory_peak_bytes":
        val_str = _fmt_bytes(val)
        delta_str = f" ({_fmt_bytes_delta(delta)})" if delta is not None else ""
    elif metric in ("active_users", "pool_size"):
        val_str = str(int(val))
        delta_str = f" ({_fmt_delta(delta)})" if delta is not None else ""
    else:
        val_str = f"{val:.1f}"
        delta_str = f" ({_fmt_delta(delta)})" if delta is not None else ""

    flag = " ⚠" if is_anomaly else ""
    return f"{val_str}{delta_str}{flag}"


def _fmt_ratio_delta(n: float) -> str:
    """Format a ratio delta as percentage points with sign."""
    pct = n * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}pp"


def _fmt_bytes(n: float | int) -> str:
    """Format bytes as human-readable (e.g. 2.7G, 366M)."""
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f}G"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.0f}M"
    return f"{n:.0f}B"


def _fmt_bytes_delta(n: float | int) -> str:
    """Format a byte delta with sign."""
    sign = "+" if n > 0 else ""
    return f"{sign}{_fmt_bytes(abs(n))}" if n != 0 else "±0"


def _render_section_methodology(lines: list[str]) -> None:
    """Render the Methodology section explaining report semantics."""
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "> **Epochs.** Server uptime is segmented into epochs — contiguous runs of"
    )
    lines.append(
        "> the same git commit hash in JSONL events. A new commit hash marks a new"
    )
    lines.append("> epoch. Each epoch runs a single deployed version.")
    lines.append(">")
    lines.append(
        "> **Restart classification.** Each epoch's start is classified by examining"
    )
    lines.append(
        "> journal messages in the gap between epochs: `deploy` (commit changed),"
    )
    lines.append("> `crash` (non-zero exit), `oom-kill` (killed by kernel/systemd),")
    lines.append(
        "> `manual-restart` (same commit, clean shutdown), `unknown` (no journal"
    )
    lines.append(
        "> evidence), `first` (first epoch in window). Non-deploy restarts are the"
    )
    lines.append("> highest-severity signal in this report.")
    lines.append(">")
    lines.append(
        "> **Request-normalised ratios.** Error and 5xx counts are divided by total"
    )
    lines.append(
        "> served requests (not time), enabling fair comparison across epochs with"
    )
    lines.append(
        "> different traffic levels. See Google SRE Workbook ch. 2 (SLOs and Error"
    )
    lines.append("> Budgets) for methodology.")
    lines.append(">")
    lines.append(
        "> **NOSRV exclusion.** `<NOSRV>` 503s are HAProxy responses when no backend"
    )
    lines.append(
        "> was available (app restarting). These are infrastructure transients, not"
    )
    lines.append(
        "> application errors — excluded from the 5xx ratio. Reported separately"
    )
    lines.append("> with first-60s clustering to show restart impact.")
    lines.append(">")
    lines.append(
        "> **Error landscape.** Event strings are normalised (hex addresses → `<ADDR>`,"
    )
    lines.append(
        "> UUIDs → `<UUID>`, task names → `Task-<N>`) to produce stable class keys."
    )
    lines.append('> "Appeared" = class present now, absent in ALL prior epochs.')
    lines.append('> "Resolved" = class present in prior epochs, absent now.')
    lines.append(">")
    lines.append("> **Anomaly thresholds.** ⚠ flags: 5xx ratio > 1%, error ratio > 5%,")
    lines.append(
        "> memory peak > 3 GB, mean CPU > 50%. Pool size changes are always flagged."
    )
    lines.append(">")
    lines.append(
        "> See `docs/postmortems/incident-analysis-playbook.md` for the operational"
    )
    lines.append("> playbook that drives this report.")
    lines.append("")


def render_review_report(
    sources: list[dict],
    epochs: list[dict],
    epoch_analyses: list[dict],
    summative_users: dict,
    trends: list[dict],
    static_counts: dict | None = None,
) -> str:
    """Assemble a markdown operational review report.

    Combines source inventory, epoch timeline, per-epoch analysis,
    user activity summary, and trend analysis into a single markdown
    document suitable for review.
    """
    lines: list[str] = []
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Window range from epochs
    if epochs:
        window_start = min(str(e["start_utc"]) for e in epochs)
        window_end = max(str(e["end_utc"]) for e in epochs)
        window_str = f"{window_start} to {window_end}"
    else:
        window_str = "No data"

    lines.append("# Operational Review Report")
    lines.append("")
    lines.append(f"Generated: {generated}")
    lines.append(f"Window: {window_str}")
    lines.append("")
    _render_section_methodology(lines)

    _render_section_sources(lines, sources)

    if static_counts is not None:
        lines.append("## Static DB Counts")
        lines.append("")
        sc_rows: list[list[str]] = [
            [str(key), str(value)] for key, value in static_counts.items()
        ]
        lines.extend(_md_table(["Metric", "Value"], sc_rows))
        lines.append("")

    _render_section_timeline(lines, epochs)

    lines.append("## Per-Epoch Analysis")
    lines.append("")
    lines.append(
        "> Detailed breakdown of each epoch's errors, HTTP traffic, resource usage,"
    )
    lines.append(
        "> and user activity. Error counts are shown with per-hour rates for context."
    )
    lines.append(
        "> For cross-epoch comparison, use the Trend Analysis table below which"
    )
    lines.append("> normalises by request volume.")
    lines.append("")
    for i, (epoch, analysis) in enumerate(
        zip(epochs, epoch_analyses, strict=False),
    ):
        _render_epoch_analysis(lines, i, epoch, analysis)

    _render_section_users(lines, summative_users)
    _render_section_trends(lines, trends)

    return "\n".join(lines)
