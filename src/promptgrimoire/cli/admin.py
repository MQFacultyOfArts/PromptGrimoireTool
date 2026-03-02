"""User and role management commands."""

import typer

admin_app = typer.Typer(help="User, role, and course enrollment management.")


@admin_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 2."""
    typer.echo("Not yet implemented.")
