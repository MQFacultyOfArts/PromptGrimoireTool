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

    # Totals
    row = conn.execute(
        "SELECT COUNT(*) AS total_requests,"
        " SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS count_5xx"
        " FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ?",
        (start_utc, end_utc),
    ).fetchone()
    total_requests = row[0]
    count_5xx = row[1] or 0

    is_crash = duration_seconds < _CRASH_BOUNCE_THRESHOLD

    # Percentiles
    p50_ms: int | None = None
    p95_ms: int | None = None
    p99_ms: int | None = None

    sample_count_row = conn.execute(
        "SELECT COUNT(*) FROM haproxy_events"
        " WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL",
        (start_utc, end_utc),
    ).fetchone()
    sample_count = sample_count_row[0]

    if sample_count > 0:
        for pct, attr in [(0.50, "p50_ms"), (0.95, "p95_ms"), (0.99, "p99_ms")]:
            pct_row = conn.execute(
                "SELECT ta_ms FROM haproxy_events"
                " WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL"
                " ORDER BY ta_ms"
                " LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * ? AS INTEGER)"
                "   FROM haproxy_events"
                "   WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL)",
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


def _user_metrics_query(
    conn: sqlite3.Connection,
    where_clause: str,
    params: tuple[str, ...],
) -> dict[str, int]:
    """Shared implementation for epoch and summative user metrics.

    where_clause is always a hardcoded SQL fragment built by callers
    in this module -- never from external input.
    """
    unique_logins = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM jsonl_events"  # noqa: S608
        f" WHERE {where_clause}"
        f" AND event LIKE '{LOGIN_EVENT_PATTERN}'"
        " AND user_id IS NOT NULL",
        params,
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
    return _user_metrics_query(
        conn,
        "ts_utc >= ? AND ts_utc <= ?",
        (start_utc, end_utc),
    )


def query_summative_users(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    """Query distinct user activity metrics across all JSONL data (no time bounds)."""
    return _user_metrics_query(conn, "1=1", ())


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
    "error_rate",
    "rate_5xx",
    "memory_peak_bytes",
    "mean_cpu",
    "active_users",
)

# Anomaly detection thresholds (metric_name -> (pct_threshold, absolute_floor))
_ANOMALY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "error_rate": (100.0, 5.0),  # >100% increase AND current > 5/hour
    "rate_5xx": (100.0, 2.0),  # >100% increase AND current > 2/hour
    "memory_peak_bytes": (50.0, 1_073_741_824),  # >50% increase AND current > 1GB
    "mean_cpu": (100.0, 20.0),  # >100% increase AND current > 20%
}
# active_users is intentionally excluded — not an operational concern


def _safe_delta(
    current: float | int | None,
    previous: float | int | None,
) -> dict:
    """Compute delta and percentage change, handling None and zero safely."""
    if current is None or previous is None:
        return {
            "value": current,
            "previous": previous,
            "delta": None,
            "pct_change": None,
        }
    delta = current - previous
    pct = (delta / previous) * 100 if previous != 0 else None
    return {"value": current, "previous": previous, "delta": delta, "pct_change": pct}


def compute_trends(epochs: list[dict]) -> list[dict]:
    """Compare consecutive non-crash-bounce epochs to detect metric trends.

    Returns a list of trend dicts, each containing the original epoch
    index, commit hash, and per-metric deltas with anomaly flags.
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

            is_anomaly = False
            if (
                metric in _ANOMALY_THRESHOLDS
                and d["pct_change"] is not None
                and d["value"] is not None
            ):
                pct_threshold, absolute_floor = _ANOMALY_THRESHOLDS[metric]
                if d["pct_change"] > pct_threshold and d["value"] > absolute_floor:
                    is_anomaly = True

            d["is_anomaly"] = is_anomaly
            metrics[metric] = d

        trends.append(
            {
                "epoch_index": idx,
                "commit": current["commit"],
                "metrics": metrics,
            }
        )

    return trends


# ── Report rendering ──────────────────────────────────────────────


def _fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


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
        lines.append("| Filename | Format | SHA256 | Size | Window |")
        lines.append("|----------|--------|--------|------|--------|")
        for s in sources:
            sha = str(s.get("sha256", ""))[:12]
            window = f"{s.get('window_start_utc', '')} - {s.get('window_end_utc', '')}"
            lines.append(
                f"| {s.get('filename', '')} | {s.get('format', '')} "
                f"| {sha} | {s.get('size', '')} | {window} |"
            )
    else:
        lines.append("No sources ingested.")
    lines.append("")


def _render_section_timeline(lines: list[str], epochs: list[dict]) -> None:
    """Render the Epoch Timeline section."""
    lines.append("## Epoch Timeline")
    lines.append("")
    if not epochs:
        lines.append("No epochs detected.")
        lines.append("")
        return
    lines.append(
        "| # | Commit | PR | Start | End | Duration | Events | Memory | CPU | Crash |"
    )
    lines.append(
        "|---|--------|----|-------|-----|----------|--------|--------|-----|-------|"
    )
    for i, e in enumerate(epochs):
        crash_marker = "CRASH" if e.get("is_crash_bounce") else ""
        pr_info = str(e.get("pr_title", "")) or ""
        pr_num = e.get("pr_number")
        if pr_num is not None:
            pr_info = f"#{pr_num} {pr_info}"
        duration = _fmt_duration(float(e.get("duration_seconds", 0)))
        lines.append(
            f"| {i + 1} | {e.get('commit', '')}"
            f" | {pr_info}"
            f" | {e.get('start_utc', '')}"
            f" | {e.get('end_utc', '')}"
            f" | {duration}"
            f" | {e.get('event_count', '')}"
            f" | {e.get('memory_peak', 'N/A')}"
            f" | {e.get('cpu_consumed', 'N/A')}"
            f" | {crash_marker} |"
        )
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
    _render_epoch_haproxy(lines, analysis.get("haproxy", {}))
    _render_epoch_resources_section(lines, analysis.get("resources", {}))
    _render_epoch_pg_section(lines, analysis.get("pg", []))
    _render_epoch_journal(lines, analysis.get("journal_anomalies", []))
    _render_epoch_user_activity(lines, analysis.get("users", {}))


def _render_epoch_errors(lines: list[str], errors: list[dict]) -> None:
    if not errors:
        return
    lines.append("**Errors/Warnings:**")
    lines.append("")
    lines.append("| Level | Event | Count | Per Hour |")
    lines.append("|-------|-------|-------|----------|")
    for err in errors:
        per_hour = _fmt_val(err.get("per_hour"))
        lines.append(
            f"| {err.get('level', '')} | {err.get('event', '')}"
            f" | {err.get('count', '')} | {per_hour} |"
        )
    lines.append("")


def _render_epoch_haproxy(lines: list[str], haproxy: dict) -> None:
    if not haproxy:
        return
    lines.append("**HAProxy Traffic:**")
    lines.append("")
    lines.append(f"- Total requests: {haproxy.get('total_requests', 'N/A')}")
    lines.append(f"- 5xx count: {haproxy.get('count_5xx', 'N/A')}")
    lines.append(f"- 5xx rate/hr: {_fmt_val(haproxy.get('rate_5xx'))}")
    lines.append(f"- Requests/min: {_fmt_val(haproxy.get('requests_per_minute'))}")
    lines.append(f"- p50: {_fmt_val(haproxy.get('p50_ms'))} ms")
    lines.append(f"- p95: {_fmt_val(haproxy.get('p95_ms'))} ms")
    lines.append(f"- p99: {_fmt_val(haproxy.get('p99_ms'))} ms")

    status_codes = haproxy.get("status_codes", [])
    if status_codes:
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        for sc in status_codes:
            lines.append(f"| {sc.get('status_code', '')} | {sc.get('count', '')} |")
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
    lines.append("| Level | Error Type | Count |")
    lines.append("|-------|------------|-------|")
    for pg in pg_events:
        lines.append(
            f"| {pg.get('level', '')} | {pg.get('error_type', '')}"
            f" | {pg.get('count', '')} |"
        )
    lines.append("")


def _render_epoch_journal(lines: list[str], anomalies: list[dict]) -> None:
    if not anomalies:
        return
    lines.append("**Journal Anomalies:**")
    lines.append("")
    lines.append("| Timestamp | Priority | Unit | Message |")
    lines.append("|-----------|----------|------|---------|")
    for a in anomalies:
        lines.append(
            f"| {a.get('ts_utc', '')} | {a.get('priority', '')}"
            f" | {a.get('unit', '')} | {a.get('message', '')} |"
        )
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
    lines.append(f"- Unique logins: {summative_users.get('unique_logins', 0)}")
    lines.append(f"- Active users: {summative_users.get('active_users', 0)}")
    lines.append(f"- Active workspaces: {summative_users.get('active_workspaces', 0)}")
    lines.append(f"- Workspace users: {summative_users.get('workspace_users', 0)}")
    lines.append("")


def _render_section_trends(lines: list[str], trends: list[dict]) -> None:
    """Render the Trend Analysis section."""
    lines.append("## Trend Analysis")
    lines.append("")
    if not trends:
        lines.append("No trend data (fewer than 2 non-crash-bounce epochs).")
        lines.append("")
        return
    lines.append(
        "| Epoch | Commit | Metric | Value | Previous | Delta | Change | Anomaly |"
    )
    lines.append(
        "|-------|--------|--------|-------|----------|-------|--------|---------|"
    )
    for t in trends:
        commit = t.get("commit", "")
        epoch_idx = t.get("epoch_index", "")
        for metric_name, m in t.get("metrics", {}).items():
            anomaly = "!!!" if m.get("is_anomaly") else ""
            lines.append(
                f"| {epoch_idx} | {commit}"
                f" | {metric_name}"
                f" | {_fmt_val(m.get('value'))}"
                f" | {_fmt_val(m.get('previous'))}"
                f" | {_fmt_delta(m.get('delta'))}"
                f" | {_fmt_pct(m.get('pct_change'))}"
                f" | {anomaly} |"
            )
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

    _render_section_sources(lines, sources)

    if static_counts is not None:
        lines.append("## Static DB Counts")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, value in static_counts.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

    _render_section_timeline(lines, epochs)

    lines.append("## Per-Epoch Analysis")
    lines.append("")
    for i, (epoch, analysis) in enumerate(
        zip(epochs, epoch_analyses, strict=False),
    ):
        _render_epoch_analysis(lines, i, epoch, analysis)

    _render_section_users(lines, summative_users)
    _render_section_trends(lines, trends)

    return "\n".join(lines)
