#!/usr/bin/env python3
"""Incident analysis CLI -- ingest production telemetry tarballs into SQLite."""

from pathlib import Path

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


if __name__ == "__main__":
    app()
