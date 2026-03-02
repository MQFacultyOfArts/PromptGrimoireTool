"""Documentation generation and serving commands."""

import typer

docs_app = typer.Typer(help="Documentation generation and serving.")


@docs_app.command()
def placeholder() -> None:
    """Placeholder — will be replaced in Phase 3."""
    typer.echo("Not yet implemented.")
