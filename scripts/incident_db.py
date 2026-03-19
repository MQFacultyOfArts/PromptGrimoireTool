#!/usr/bin/env python3
"""Incident analysis CLI -- ingest production telemetry tarballs into SQLite."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

# Ensure the project root is on sys.path so `scripts.incident` is importable
# when invoked as `uv run scripts/incident_db.py` without PYTHONPATH.
_project_root = str(_Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import hashlib
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

app = typer.Typer(
    no_args_is_help=True,
    help="Incident analysis: ingest and query production telemetry.",
)


@app.command()
def ingest(
    tarball: Path = typer.Argument(..., help="Path to telemetry tarball (.tar.gz)"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Ingest a telemetry tarball into the SQLite database."""
    from scripts.incident.ingest import run_ingest

    run_ingest(tarball, db)


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------


def _output(
    data: list[dict],
    title: str,
    *,
    json_output: bool,
    csv_output: bool,
) -> None:
    """Dispatch to the appropriate renderer."""
    from scripts.incident.queries import render_csv, render_json, render_table

    if json_output:
        render_json(data)
    elif csv_output:
        render_csv(data)
    else:
        render_table(data, title)


@app.command()
def sources(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Display provenance table for all ingested sources."""
    from scripts.incident.queries import query_sources

    conn = sqlite3.connect(db)
    data = query_sources(conn)
    conn.close()
    _output(data, "Sources", json_output=json_output, csv_output=csv_output)


def _resolve_timezone(conn: sqlite3.Connection, override: str | None) -> str:
    """Return the timezone to use for local→UTC conversion.

    Uses explicit ``--timezone`` if provided, otherwise looks up from
    the first ingested source, falling back to Australia/Sydney.

    Raises ``typer.BadParameter`` for invalid IANA timezone names.
    """
    tz_name = override
    if not tz_name:
        row = conn.execute("SELECT timezone FROM sources LIMIT 1").fetchone()
        tz_name = row[0] if row else "Australia/Sydney"
    try:
        ZoneInfo(tz_name)
    except KeyError:
        raise typer.BadParameter(
            f"Unknown timezone '{tz_name}'. Use an IANA name like 'Australia/Sydney'."
        ) from None
    return tz_name


def _aedt_to_utc(local_str: str, tz_name: str) -> str:
    """Convert a local-time string to UTC ISO-8601 for SQLite comparison.

    Accepts ``YYYY-MM-DD HH:MM`` or ``YYYY-MM-DD HH:MM:SS``.
    """
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(local_str, fmt)
            break
        except ValueError:
            continue
    else:
        msg = f"Cannot parse time '{local_str}' — expected YYYY-MM-DD HH:MM[:SS]"
        raise typer.BadParameter(msg)

    local_dt = naive.replace(tzinfo=ZoneInfo(tz_name))
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@app.command()
def timeline(
    start: str = typer.Option(..., help="Start time (local, e.g. '2026-03-16 16:05')"),
    end: str = typer.Option(..., help="End time (local, e.g. '2026-03-16 16:14')"),
    level: str | None = typer.Option(None, help="Filter by level/status"),
    timezone: str | None = typer.Option(
        None, "--timezone", "-tz", help="IANA timezone (default: from ingested sources)"
    ),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Show cross-source timeline for a time window (times in local timezone)."""
    from scripts.incident.queries import query_timeline

    conn = sqlite3.connect(db)

    tz_name = _resolve_timezone(conn, timezone)

    start_utc = _aedt_to_utc(start, tz_name)
    end_utc = _aedt_to_utc(end, tz_name)

    if start_utc > end_utc:
        typer.echo(f"Error: --start ({start}) is after --end ({end}).", err=True)
        conn.close()
        raise SystemExit(1)

    data = query_timeline(conn, start_utc, end_utc, level)
    conn.close()
    _output(data, "Timeline", json_output=json_output, csv_output=csv_output)


@app.command()
def breakdown(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Show event counts grouped by source and level/status."""
    from scripts.incident.queries import query_breakdown

    conn = sqlite3.connect(db)
    data = query_breakdown(conn)
    conn.close()
    _output(data, "Breakdown", json_output=json_output, csv_output=csv_output)


@app.command()
def beszel(
    start: str = typer.Option(..., help="Start time (local, e.g. '2026-03-16 16:05')"),
    end: str = typer.Option(..., help="End time (local, e.g. '2026-03-16 16:14')"),
    hub: str = typer.Option(
        "http://localhost:8090", help="Beszel hub URL (via SSH tunnel)"
    ),
    timezone: str | None = typer.Option(
        None, "--timezone", "-tz", help="IANA timezone"
    ),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Fetch Beszel system metrics for a time window."""
    from scripts.incident.parsers.beszel import fetch_beszel_metrics
    from scripts.incident.schema import create_schema

    conn = sqlite3.connect(db)
    create_schema(conn)

    tz_name = _resolve_timezone(conn, timezone)

    start_utc = _aedt_to_utc(start, tz_name)
    end_utc = _aedt_to_utc(end, tz_name)

    if start_utc > end_utc:
        typer.echo(f"Error: --start ({start}) is after --end ({end}).", err=True)
        conn.close()
        raise SystemExit(1)

    # Dedup check before network fetch — avoids unnecessary HTTP calls
    sha = hashlib.sha256(f"{hub}:{start_utc}:{end_utc}".encode()).hexdigest()
    existing = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (sha,)
    ).fetchone()
    if existing is not None:
        conn.close()
        typer.echo("Already fetched (dedup). 0 new data points.")
        return

    metrics = fetch_beszel_metrics(hub, start_utc, end_utc)

    conn.execute(
        """INSERT INTO sources
           (filename, format, sha256, size, mtime, hostname, timezone,
            window_start_utc, window_end_utc, source_path,
            collection_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "beszel-api",
            "beszel",
            sha,
            0,
            0,
            "beszel-hub",
            tz_name,
            start_utc,
            end_utc,
            hub,
            "pocketbase API",
        ),
    )
    source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert metrics rows.
    for m in metrics:
        conn.execute(
            """INSERT INTO beszel_metrics
               (source_id, ts_utc, cpu, mem_used, mem_percent,
                net_sent, net_recv, disk_read, disk_write,
                load_1, load_5, load_15)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                m["ts_utc"],
                m["cpu"],
                m["mem_used"],
                m["mem_percent"],
                m["net_sent"],
                m["net_recv"],
                m["disk_read"],
                m["disk_write"],
                m["load_1"],
                m["load_5"],
                m["load_15"],
            ),
        )

    conn.commit()
    conn.close()
    typer.echo(f"Fetched {len(metrics)} metric data points")


def _analyse_epochs(
    conn: sqlite3.Connection,
    epochs: list[dict],
) -> list[dict]:
    """Run per-epoch queries and attach ratio metrics to each epoch dict."""
    from scripts.incident.analysis import (
        query_epoch_errors,
        query_epoch_haproxy,
        query_epoch_journal_anomalies,
        query_epoch_pg,
        query_epoch_resources,
        query_epoch_users,
    )

    epoch_analyses: list[dict] = []
    for epoch in epochs:
        start = str(epoch["start_utc"])
        end = str(epoch["end_utc"])
        dur_raw = epoch["duration_seconds"]
        dur = dur_raw if isinstance(dur_raw, float) else float(str(dur_raw))
        analysis = {
            "errors": query_epoch_errors(conn, start, end, dur),
            "haproxy": query_epoch_haproxy(conn, start, end, dur),
            "resources": query_epoch_resources(conn, start, end),
            "pg": query_epoch_pg(conn, start, end),
            "journal_anomalies": query_epoch_journal_anomalies(conn, start, end),
            "users": query_epoch_users(conn, start, end),
        }
        total_requests = analysis["haproxy"]["total_requests"]
        if epoch["is_crash_bounce"] or total_requests == 0:
            epoch["error_ratio"] = None
            epoch["warning_ratio"] = None
            epoch["5xx_ratio"] = None
        else:
            error_count = sum(
                e["count"]
                for e in analysis["errors"]
                if e["level"] in ("error", "critical")
            )
            warning_count = sum(
                e["count"] for e in analysis["errors"] if e["level"] == "warning"
            )
            epoch["error_ratio"] = error_count / total_requests
            epoch["warning_ratio"] = warning_count / total_requests
            epoch["5xx_ratio"] = analysis["haproxy"]["count_5xx"] / total_requests
        epoch["total_requests"] = total_requests
        epoch["mean_cpu"] = analysis["resources"].get("mean_cpu")
        epoch["active_users"] = analysis["users"]["active_users"]
        epoch_analyses.append(analysis)
    return epoch_analyses


def _detect_github_repo() -> str:
    """Extract owner/repo from git remote origin URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise typer.BadParameter(
            "Cannot detect repo: no git remote 'origin'. Use --repo."
        )
    url = result.stdout.strip()
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not match:
        raise typer.BadParameter(f"Cannot parse GitHub repo from remote URL: {url}")
    return match.group(1)


@app.command()
def github(
    start: str = typer.Option(..., help="Window start (local time, YYYY-MM-DD HH:MM)"),
    end: str = typer.Option(..., help="Window end (local time, YYYY-MM-DD HH:MM)"),
    repo: str = typer.Option(
        "", help="GitHub repo (owner/repo). Auto-detects from git remote if empty."
    ),
    token: str = typer.Option(
        "", help="GitHub token. Falls back to GITHUB_TOKEN env, then gh auth token."
    ),
    force: bool = typer.Option(
        False, help="Re-fetch even if window was previously ingested (bypass dedup)."
    ),
    timezone: str | None = typer.Option(None, help="IANA timezone override"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Fetch GitHub PR data for a time window."""
    from scripts.incident.parsers.github import fetch_github_prs, resolve_github_token
    from scripts.incident.schema import create_schema

    conn = sqlite3.connect(db)
    create_schema(conn)

    tz_name = _resolve_timezone(conn, timezone)

    start_utc = _aedt_to_utc(start, tz_name)
    end_utc = _aedt_to_utc(end, tz_name)

    if start_utc > end_utc:
        typer.echo(f"Error: --start ({start}) is after --end ({end}).", err=True)
        conn.close()
        raise SystemExit(1)

    # Resolve token
    try:
        resolved_token = resolve_github_token(token or None)
    except RuntimeError as exc:
        conn.close()
        raise typer.BadParameter(str(exc)) from None

    # Auto-detect repo if not provided
    if not repo:
        repo = _detect_github_repo()

    # Dedup check
    sha = hashlib.sha256(f"github:{repo}:{start_utc}:{end_utc}".encode()).hexdigest()
    existing = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (sha,)
    ).fetchone()
    if existing is not None:
        if not force:
            conn.close()
            typer.echo("Already fetched (dedup). 0 new PRs.")
            return
        # --force: delete existing source and its events
        conn.execute("DELETE FROM github_events WHERE source_id = ?", (existing[0],))
        conn.execute("DELETE FROM sources WHERE id = ?", (existing[0],))
        conn.commit()

    prs = fetch_github_prs(repo, start_utc, end_utc, resolved_token)

    conn.execute(
        """INSERT INTO sources
           (filename, format, sha256, size, mtime, hostname, timezone,
            window_start_utc, window_end_utc, source_path,
            collection_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            repo,
            "github",
            sha,
            0,
            0,
            "github.com",
            tz_name,
            start_utc,
            end_utc,
            f"https://github.com/{repo}",
            "REST API",
        ),
    )
    source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for pr in prs:
        conn.execute(
            """INSERT INTO github_events
               (source_id, ts_utc, pr_number, title, author, commit_oid, url)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                pr["ts_utc"],
                pr["pr_number"],
                pr["title"],
                pr["author"],
                pr["commit_oid"],
                pr["url"],
            ),
        )

    conn.commit()
    conn.close()
    typer.echo(f"Fetched {len(prs)} PRs")


@app.command()
def review(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    counts_json: Path | None = typer.Option(
        None, help="JSON file with static DB counts"
    ),
    output: Path | None = typer.Option(None, help="Output file (stdout if omitted)"),
) -> None:
    """Generate operational review report."""
    from scripts.incident.analysis import (
        compute_trends,
        enrich_epochs_github,
        enrich_epochs_journal,
        enrich_restart_reasons,
        extract_epochs,
        load_static_counts,
        query_summative_users,
        render_review_report,
    )
    from scripts.incident.queries import query_sources
    from scripts.incident.schema import create_schema

    conn = sqlite3.connect(db)
    create_schema(conn)

    sources_data = query_sources(conn)
    conn.row_factory = None  # reset after query_sources sets _dict_factory
    epochs = extract_epochs(conn)

    if not epochs:
        typer.echo("No epochs found. Is the database populated with JSONL events?")
        conn.close()
        return

    enrich_restart_reasons(conn, epochs)
    enrich_epochs_journal(conn, epochs)
    enrich_epochs_github(conn, epochs)

    epoch_analyses = _analyse_epochs(conn, epochs)

    summative = query_summative_users(conn)
    conn.close()

    trends_data = compute_trends(epochs)

    static_counts = None
    if counts_json:
        try:
            static_counts = load_static_counts(counts_json)
        except FileNotFoundError:
            typer.echo(
                f"Warning: counts file '{counts_json}' not found, "
                "skipping static counts.",
                err=True,
            )

    report = render_review_report(
        sources_data,
        epochs,
        epoch_analyses,
        summative,
        trends_data,
        static_counts=static_counts,
    )

    if output:
        output.write_text(report)
        typer.echo(f"Report written to {output}", err=True)
    else:
        typer.echo(report)


if __name__ == "__main__":
    app()
