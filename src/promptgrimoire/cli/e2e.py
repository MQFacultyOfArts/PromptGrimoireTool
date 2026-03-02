"""E2E test commands."""

import typer

e2e_app = typer.Typer(help="End-to-end test commands.")


@e2e_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 5."""
    typer.echo("Not yet implemented.")
