"""Development data seeding commands."""

import typer

seed_app = typer.Typer(help="Seed development data.")


@seed_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
