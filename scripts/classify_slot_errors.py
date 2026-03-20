"""Classify slot deletion errors by our-code call chain.

Reads journal_events from incident.db, finds all seconds containing
NiceGUI slot/parent deletion errors, extracts our-code stack frames
(src/promptgrimoire/**/*.py), and groups by unique frame chain.

Usage:
    uv run scripts/classify_slot_errors.py --db incident.db

Output: sorted list of (count, chain) pairs, most frequent first.

This script was used to produce the trigger-site classification in
docs/postmortems/2026-03-20-slot-deletion-investigation-369.md.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path  # noqa: TC003 — typer evaluates annotations at runtime

import typer

app = typer.Typer()


def _classify(db_path: Path) -> dict[str, list[str]]:
    """Return {frame_chain: [ts_sec, ...]} from journal_events."""
    conn = sqlite3.connect(db_path)

    error_times = conn.execute(
        """
        SELECT DISTINCT substr(ts_utc, 1, 19) as ts_sec FROM journal_events
        WHERE message LIKE '%parent element this slot%'
           OR message LIKE '%parent slot of the element%'
        ORDER BY ts_utc
        """
    ).fetchall()

    call_chains: dict[str, list[str]] = {}

    for (ts_sec,) in error_times:
        rows = conn.execute(
            """
            SELECT message FROM journal_events
            WHERE ts_utc >= ? AND ts_utc < ? || 'Z'
            ORDER BY id
            """,
            (ts_sec, ts_sec),
        ).fetchall()

        chain_parts: list[str] = []
        for (msg,) in rows:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", msg)
            # Only our source, not .venv
            matches = re.findall(
                r"src/(promptgrimoire/\S+\.py)[,:]"
                r"\s*(?:line\s+)?(\d+)",
                clean,
            )
            for path, line in matches:
                part = f"{path}:{line}"
                # Deduplicate consecutive identical frames
                if not chain_parts or chain_parts[-1] != part:
                    chain_parts.append(part)

        chain_key = (
            " -> ".join(chain_parts) if chain_parts else "(NiceGUI-internal only)"
        )
        call_chains.setdefault(chain_key, []).append(ts_sec)

    conn.close()
    return call_chains


def _aggregate_by_file(
    call_chains: dict[str, list[str]],
) -> dict[str, int]:
    """Count error-seconds where any frame references each file.

    An error-second is counted for a file if ANY chain frame contains
    that filename. One error-second can count for multiple files if its
    chain spans multiple files.
    """
    file_counts: dict[str, set[str]] = {}
    for chain, timestamps in call_chains.items():
        # Extract unique filenames from the chain
        files = {part.rsplit(":", 1)[0] for part in chain.split(" -> ") if "/" in part}
        for fname in files:
            file_counts.setdefault(fname, set()).update(timestamps)
    return {f: len(ts) for f, ts in file_counts.items()}


@app.command()
def main(
    db: Path = typer.Option(default="incident.db", help="SQLite database path"),  # noqa: B008
    aggregate: bool = typer.Option(
        default=False,
        help="Aggregate by file instead of exact chain",
    ),
) -> None:
    """Classify slot deletion errors by our-code call chain."""
    if not db.exists():
        typer.echo(f"Error: {db} not found", err=True)
        raise typer.Exit(1)

    call_chains = _classify(db)

    total_seconds = sum(len(v) for v in call_chains.values())
    typer.echo(f"Distinct error-seconds: {total_seconds}")

    if aggregate:
        file_agg = _aggregate_by_file(call_chains)
        typer.echo(f"Distinct files referenced: {len(file_agg)}")
        for fname, count in sorted(file_agg.items(), key=lambda x: -x[1]):
            typer.echo(f"  [{count}x] {fname}")
    else:
        typer.echo(f"Distinct call chains: {len(call_chains)}")
        for chain, times in sorted(call_chains.items(), key=lambda x: -len(x[1])):
            typer.echo(f"\n  [{len(times)}x] {chain}")


if __name__ == "__main__":
    app()
