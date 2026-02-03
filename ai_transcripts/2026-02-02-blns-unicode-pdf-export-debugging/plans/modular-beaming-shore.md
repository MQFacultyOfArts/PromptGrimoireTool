# Plan: Add Protected Index Page with Route Links

## Summary

Create a new index page (`/`) that:
1. Requires authentication (redirects to `/login` if not logged in)
2. Shows links to all available routes in the application

## Files to Modify

1. **[src/promptgrimoire/pages/__init__.py](src/promptgrimoire/pages/__init__.py)** - Add `index` module import
2. **New file: `src/promptgrimoire/pages/index.py`** - Create the index page

## Implementation

### 1. Create `src/promptgrimoire/pages/index.py`

```python
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

    ui.link("Logout", "/logout").classes("mt-4")
```

### 2. Update `src/promptgrimoire/pages/__init__.py`

Add `index` to imports and `__all__`.

## Verification

1. Run the app: `uv run python -m promptgrimoire`
2. Navigate to `http://localhost:8080/` - should redirect to `/login`
3. Set `AUTH_MOCK=true` and login - should see index with all route links
4. Click each link to verify navigation works
