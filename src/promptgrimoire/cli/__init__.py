"""PromptGrimoire CLI — unified development tools."""

import typer

from promptgrimoire.cli.admin import admin_app
from promptgrimoire.cli.docs import docs_app
from promptgrimoire.cli.e2e import e2e_app
from promptgrimoire.cli.export import export_app
from promptgrimoire.cli.seed import seed_app
from promptgrimoire.cli.testing import test_app

app = typer.Typer(name="grimoire", help="PromptGrimoire development tools.")
app.add_typer(test_app, name="test")
app.add_typer(e2e_app, name="e2e")
app.add_typer(admin_app, name="admin")
app.add_typer(seed_app, name="seed")
app.add_typer(export_app, name="export")
app.add_typer(docs_app, name="docs")
