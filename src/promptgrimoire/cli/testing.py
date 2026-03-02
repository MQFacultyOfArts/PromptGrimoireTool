"""Unit/integration test commands."""

import typer

test_app = typer.Typer(help="Unit and integration test commands.")


@test_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 4."""
    typer.echo("Not yet implemented.")
