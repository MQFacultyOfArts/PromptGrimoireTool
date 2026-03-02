"""Export log inspection commands."""

import typer

export_app = typer.Typer(help="Export log inspection.")


@export_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
