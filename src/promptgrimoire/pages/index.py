"""Index page for PromptGrimoire."""

from nicegui import app, ui


def _get_session_user() -> dict | None:
    """Get the current user from session storage."""
    return app.storage.user.get("auth_user")


@ui.page("/")
async def index_page() -> None:
    """Index page with links to all routes. Requires authentication."""
    user = _get_session_user()

    if not user:
        ui.navigate.to("/login")
        return

    ui.label("PromptGrimoire").classes("text-2xl font-bold mb-4")
    ui.label(f"Welcome, {user['email']}").classes("text-lg mb-4")

    with ui.card().classes("p-4"):
        ui.label("Available Pages").classes("text-lg font-semibold mb-2")

        with ui.column().classes("gap-2"):
            ui.link("Roleplay", "/roleplay")
            ui.link("Session Logs", "/logs")
            ui.link("Text Selection Demo", "/demo/text-selection")
            ui.link("CRDT Sync Demo", "/demo/crdt-sync")
            ui.link("Session Info", "/protected")

    ui.link("Logout", "/logout").classes("mt-4")
