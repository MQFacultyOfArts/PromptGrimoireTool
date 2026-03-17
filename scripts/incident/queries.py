"""Query functions and output renderers for incident analysis CLI."""

from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    import sqlite3


# ---------------------------------------------------------------------------
# Query functions (pure: connection in, data out)
# ---------------------------------------------------------------------------


def query_sources(conn: sqlite3.Connection) -> list[dict]:
    """Return provenance summary for all ingested sources.

    Uses the ``timeline`` view for per-source stats so we don't need to
    route to format-specific tables.  LEFT JOIN ensures sources with zero
    parsed events still appear.
    """
    sql = """\
SELECT s.id, s.filename, s.format, substr(s.sha256, 1, 12) AS sha256_prefix,
       s.timezone, s.size, s.source_path, s.collection_method,
       MIN(t.ts_utc) AS first_ts,
       MAX(t.ts_utc) AS last_ts,
       COUNT(t.source_id) AS event_count
FROM sources s
LEFT JOIN timeline t ON t.source_id = s.id
GROUP BY s.id
ORDER BY s.id
"""
    conn.row_factory = _dict_factory
    return conn.execute(sql).fetchall()


def query_timeline(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
    level_filter: str | None = None,
) -> list[dict]:
    """Return cross-source timeline events within a UTC time window."""
    # Normalise bounds to canonical microsecond format matching stored ts_utc.
    # Without this, '...00Z' vs '...00.000000Z' string comparison fails.
    start_norm = _normalise_bound(start_utc)
    end_norm = _normalise_bound(end_utc)
    sql = "SELECT * FROM timeline WHERE ts_utc >= ? AND ts_utc <= ?"
    params: list[str] = [start_norm, end_norm]

    if level_filter is not None:
        sql += " AND level_or_status = ?"
        params.append(level_filter)

    sql += " ORDER BY ts_utc"
    conn.row_factory = _dict_factory
    return conn.execute(sql, params).fetchall()


def query_breakdown(conn: sqlite3.Connection) -> list[dict]:
    """Return event counts grouped by source and level/status."""
    sql = """\
SELECT source, level_or_status, COUNT(*) AS count
FROM timeline
GROUP BY source, level_or_status
ORDER BY count DESC
"""
    conn.row_factory = _dict_factory
    return conn.execute(sql).fetchall()


# ---------------------------------------------------------------------------
# Output renderers
# ---------------------------------------------------------------------------


def render_table(data: list[dict], title: str) -> None:
    """Print *data* as a Rich table to stdout."""
    if not data:
        Console().print(f"[dim]No results for {title}.[/dim]")
        return

    console = Console()
    table = Table(title=title)
    for key in data[0]:
        table.add_column(key)
    for row in data:
        table.add_row(*(str(v) if v is not None else "" for v in row.values()))
    console.print(table)


def render_json(data: list[dict]) -> None:
    """Print *data* as a JSON array to stdout."""
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def render_csv(data: list[dict]) -> None:
    """Print *data* as CSV to stdout."""
    if not data:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_bound(ts: str) -> str:
    """Pad a UTC timestamp to microsecond precision for SQLite string comparison.

    Stored ts_utc values use ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (from normalise_utc).
    Query bounds may arrive as ``...SSZ`` (no microseconds).  Without padding,
    ``'...00.000000Z' >= '...00Z'`` evaluates false because ``'.' < 'Z'``.
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    utc = dt.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dict_factory(
    cursor: object,  # sqlite3.Cursor
    row: tuple,
) -> dict:
    """sqlite3 row_factory that returns dicts keyed by column name."""
    # cursor.description is available on sqlite3.Cursor
    description = cursor.description  # type: ignore[union-attr]
    return {col[0]: row[idx] for idx, col in enumerate(description)}
