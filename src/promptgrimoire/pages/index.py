"""Index page for PromptGrimoire."""

from nicegui import app, ui

from promptgrimoire.pages.layout import page_layout
from promptgrimoire.pages.registry import page_route


def _get_session_user() -> dict | None:
    """Get the current user from session storage."""
    return app.storage.user.get("auth_user")


@page_route("/", title="Home", icon="home", order=10)
async def index_page() -> None:
    """Index page with welcome message. Requires authentication."""
    user = _get_session_user()

    if not user:
        ui.navigate.to("/login")
        return

    with page_layout("Home"):
        ui.label("Welcome to PromptGrimoire").classes("text-2xl font-bold mb-4")
        display_name = user.get("name") or user.get("email", "").split("@")[0]
        ui.label(f"Hello, {display_name}!").classes("text-lg mb-4")

        with ui.card().classes("p-4 max-w-md"):
            ui.label("Getting Started").classes("text-lg font-semibold mb-2")
            ui.markdown("""
Use the **navigation menu** (☰) to access:

- **Units** - View and manage your unit enrollments
- **Roleplay** - AI-powered roleplay scenarios
- **Session Logs** - Review past session transcripts
- **Case Tool** - Legal case analysis (requires database)
            """)
