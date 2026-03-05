"""Shared access checks for standalone roleplay pages."""

from __future__ import annotations

from nicegui import app, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.config import get_settings


def _get_session_user() -> dict[str, object] | None:
    """Get the current auth user from session storage."""
    return app.storage.user.get("auth_user")


def require_roleplay_page_access() -> bool:
    """Check if the current user can access standalone roleplay pages."""
    auth_user = _get_session_user()
    if auth_user is None:
        ui.navigate.to("/login")
        return False
    if not get_settings().features.roleplay_require_privileged:
        return True
    if is_privileged_user(auth_user):
        return True
    ui.notify("Roleplay is restricted", type="negative")
    return False
