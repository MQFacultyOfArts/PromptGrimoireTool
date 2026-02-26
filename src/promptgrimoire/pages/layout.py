"""Shared layout components for PromptGrimoire.

Provides consistent header, navigation drawer, and page structure.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from nicegui import app, ui

from promptgrimoire.config import get_settings
from promptgrimoire.pages.registry import get_pages_by_category

if TYPE_CHECKING:
    from collections.abc import Iterator


def _get_session_user() -> dict | None:
    """Get the current user from session storage."""
    return app.storage.user.get("auth_user")


def demos_enabled() -> bool:
    """Check if demo pages are enabled via feature flag.

    Returns:
        True if DEV__ENABLE_DEMO_PAGES is set to true.
    """
    return get_settings().dev.enable_demo_pages


def roleplay_enabled() -> bool:
    """Check if roleplay is enabled via feature flag.

    Returns:
        True if FEATURES__ENABLE_ROLEPLAY is set to true.
    """
    return get_settings().features.enable_roleplay


def require_demo_enabled() -> bool:
    """Check if demos are enabled, show error if not.

    Use at the start of demo pages to gate access.

    Returns:
        True if demos are enabled, False otherwise.
    """
    if demos_enabled():
        return True
    ui.label("Demo pages are disabled").classes("text-h5 text-red-500")
    ui.label("Set DEV__ENABLE_DEMO_PAGES=true in your environment to enable.").classes(
        "text-body1 text-grey-7"
    )
    ui.button("Go Home", on_click=lambda: ui.navigate.to("/")).classes("mt-4")
    return False


def require_roleplay_enabled() -> bool:
    """Check if roleplay is enabled, show error if not.

    Use at the start of roleplay pages to gate access.

    Returns:
        True if roleplay is enabled, False otherwise.
    """
    if roleplay_enabled():
        return True
    ui.label("Roleplay is disabled").classes("text-h5 text-red-500")
    ui.label(
        "Set FEATURES__ENABLE_ROLEPLAY=true in your environment to enable."
    ).classes("text-body1 text-grey-7")
    ui.button("Go Home", on_click=lambda: ui.navigate.to("/")).classes("mt-4")
    return False


def _nav_item(label: str, route: str, icon: str | None = None) -> None:
    """Create a navigation item in the drawer."""
    with ui.item(on_click=lambda: ui.navigate.to(route)).classes("w-full"):
        if icon:
            with ui.item_section().props("avatar"):
                ui.icon(icon)
        with ui.item_section():
            ui.item_label(label)


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
            # Build navigation dynamically from page registry
            pages_by_cat = get_pages_by_category(
                user, demos_enabled(), roleplay_enabled()
            )

            # Category display config
            category_labels = {
                "main": None,  # No header for main section
                "demo": "Demos",
                "admin": "Admin",
            }

            for category in ["main", "demo", "admin"]:
                pages = pages_by_cat.get(category, [])
                if not pages:
                    continue

                # Add section header (except for main)
                label = category_labels.get(category)
                if label:
                    ui.separator().classes("q-my-md")
                    ui.label(label).classes("text-caption q-px-md text-grey-7")

                for page in pages:
                    _nav_item(page.title, page.route, page.icon)

    # Connect menu button to drawer
    menu_btn.on("click", drawer.toggle)

    # Main content area with padding
    with ui.element("div").classes("q-pa-md"):
        yield
