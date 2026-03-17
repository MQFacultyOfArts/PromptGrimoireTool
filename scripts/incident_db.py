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
import sqlite3
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
    start: str = typer.Option(..., help="Start time (AEDT, e.g. '2026-03-16 16:05')"),
    end: str = typer.Option(..., help="End time (AEDT, e.g. '2026-03-16 16:14')"),
    level: str | None = typer.Option(None, help="Filter by level/status"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Show cross-source timeline for a time window (times in AEDT)."""
    from scripts.incident.queries import query_timeline

    conn = sqlite3.connect(db)

    # Look up the timezone from the first ingested source.
    row = conn.execute("SELECT timezone FROM sources LIMIT 1").fetchone()
    tz_name = row[0] if row else "Australia/Sydney"

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
    start: str = typer.Option(..., help="Start time (AEDT, e.g. '2026-03-16 16:05')"),
    end: str = typer.Option(..., help="End time (AEDT, e.g. '2026-03-16 16:14')"),
    hub: str = typer.Option(
        "http://localhost:8090", help="Beszel hub URL (via SSH tunnel)"
    ),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Fetch Beszel system metrics for a time window."""
    from scripts.incident.parsers.beszel import fetch_beszel_metrics
    from scripts.incident.schema import create_schema

    conn = sqlite3.connect(db)
    create_schema(conn)

    # Look up timezone from first ingested source, default to Sydney.
    row = conn.execute("SELECT timezone FROM sources LIMIT 1").fetchone()
    tz_name = row[0] if row else "Australia/Sydney"

    start_utc = _aedt_to_utc(start, tz_name)
    end_utc = _aedt_to_utc(end, tz_name)

    if start_utc > end_utc:
        typer.echo(f"Error: --start ({start}) is after --end ({end}).", err=True)
        conn.close()
        raise SystemExit(1)

    metrics = fetch_beszel_metrics(hub, start_utc, end_utc)

    # Insert synthetic source row for FK constraint.
    sha = hashlib.sha256(f"{hub}:{start_utc}:{end_utc}".encode()).hexdigest()
    conn.execute(
        """INSERT OR IGNORE INTO sources
           (filename, format, sha256, size, mtime, hostname, timezone,
            window_start_utc, window_end_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        ),
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (sha,)
    ).fetchone()[0]

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


if __name__ == "__main__":
    app()
