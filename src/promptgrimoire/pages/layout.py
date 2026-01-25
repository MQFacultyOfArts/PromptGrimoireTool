"""Shared layout components for PromptGrimoire.

Provides consistent header, navigation drawer, and page structure.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from nicegui import app, ui

if TYPE_CHECKING:
    from collections.abc import Iterator


def _get_session_user() -> dict | None:
    """Get the current user from session storage."""
    return app.storage.user.get("auth_user")


def _is_admin() -> bool:
    """Check if current user is an admin."""
    user = _get_session_user()
    return bool(user and user.get("is_admin"))


def demos_enabled() -> bool:
    """Check if demo pages are enabled via feature flag.

    Returns:
        True if ENABLE_DEMO_PAGES env var is set to a truthy value.
    """
    return os.environ.get("ENABLE_DEMO_PAGES", "").lower() in ("1", "true", "yes")


def require_demo_enabled() -> bool:
    """Check if demos are enabled, show error if not.

    Use at the start of demo pages to gate access.

    Returns:
        True if demos are enabled, False otherwise.
    """
    if demos_enabled():
        return True
    ui.label("Demo pages are disabled").classes("text-h5 text-red-500")
    ui.label("Set ENABLE_DEMO_PAGES=true in your environment to enable.").classes(
        "text-body1 text-grey-7"
    )
    ui.button("Go Home", on_click=lambda: ui.navigate.to("/")).classes("mt-4")
    return False


# Alias for internal use in navigation
_demos_enabled = demos_enabled


def _nav_item(label: str, route: str, icon: str | None = None) -> None:
    """Create a navigation item in the drawer."""
    with ui.item(on_click=lambda: ui.navigate.to(route)).classes("w-full"):
        if icon:
            with ui.item_section().props("avatar"):
                ui.icon(icon)
        with ui.item_section():
            ui.item_label(label)


def _info_item(route: str) -> None:
    """Create a disabled info item showing a parameterised route."""
    with ui.item().classes("w-full opacity-50"):
        with ui.item_section().props("avatar"):
            ui.icon("info")
        with ui.item_section():
            ui.item_label(route).classes("text-xs")


def _build_all_routes_section() -> None:
    """Build the 'All Routes' section for demo mode."""
    ui.separator().classes("q-my-md")
    ui.label("All Routes").classes("text-caption q-px-md text-grey-7")
    _nav_item("Protected Test", "/protected", "lock")
    _nav_item("Login", "/login", "login")
    _nav_item("Logout", "/logout", "logout")
    _nav_item("New Course", "/courses/new", "add_circle")

    # Show parameterised routes as disabled info items
    _info_item("/courses/{id}")
    _info_item("/courses/{id}/weeks/new")
    _info_item("/courses/{id}/enrollments")
    _info_item("/auth/callback")
    _info_item("/auth/sso/callback")
    _info_item("/auth/oauth/callback")


@contextmanager
def page_layout(title: str = "PromptGrimoire") -> Iterator[None]:
    """Context manager for consistent page layout with header and nav drawer.

    Usage:
        @ui.page("/my-page")
        async def my_page():
            with page_layout("My Page"):
                ui.label("Page content here")

    Args:
        title: Page title shown in header.

    Yields:
        Context for page content.
    """
    user = _get_session_user()

    # Create header
    with ui.header().classes("bg-primary items-center q-py-xs"):
        # Menu button (toggles drawer)
        menu_btn = ui.button(icon="menu").props("flat color=white")
        ui.label(title).classes("text-h6 text-white q-ml-sm")

        # Spacer
        ui.element("div").classes("flex-grow")

        # User info
        if user:
            ui.label(user.get("email", "")).classes("text-white text-body2 q-mr-md")
            ui.button(icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                "flat color=white"
            ).tooltip("Logout")

    # Create left drawer
    with ui.left_drawer().classes("bg-grey-2") as drawer:
        ui.label("Navigation").classes("text-h6 q-pa-md")
        ui.separator()

        with ui.list().props("padding"):
            _nav_item("Home", "/", "home")
            _nav_item("Courses", "/courses", "school")
            _nav_item("Roleplay", "/roleplay", "chat")
            _nav_item("Session Logs", "/logs", "description")
            _nav_item("Case Tool", "/case-tool", "gavel")

            # Demo section (feature-flagged)
            if _demos_enabled():
                ui.separator().classes("q-my-md")
                ui.label("Demos").classes("text-caption q-px-md text-grey-7")
                _nav_item("Text Selection", "/demo/text-selection", "text_fields")
                _nav_item("CRDT Sync", "/demo/crdt-sync", "sync")
                _nav_item("Live Annotation", "/demo/live-annotation", "edit_note")

                # Dev/Debug routes - show all endpoints for development
                _build_all_routes_section()

            # Admin section
            if _is_admin():
                ui.separator().classes("q-my-md")
                ui.label("Admin").classes("text-caption q-px-md text-grey-7")
                _nav_item("Users", "/admin/users", "people")

    # Connect menu button to drawer
    menu_btn.on("click", drawer.toggle)

    # Main content area with padding
    with ui.element("div").classes("q-pa-md"):
        yield
