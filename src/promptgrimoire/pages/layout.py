"""Shared layout components for PromptGrimoire.

Provides consistent header, navigation drawer, and page structure.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING

from nicegui import app, ui

from promptgrimoire.config import get_settings
from promptgrimoire.pages.registry import get_pages_by_category

if TYPE_CHECKING:
    from collections.abc import Iterator

    from promptgrimoire.config import HelpConfig


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
    slug = label.lower().replace(" ", "-")
    with (
        ui.item(on_click=lambda: ui.navigate.to(route))
        .classes("w-full")
        .props(f'data-testid="nav-{slug}"')
    ):
        if icon:
            with ui.item_section().props("avatar"):
                ui.icon(icon)
        with ui.item_section():
            ui.item_label(label)


def _render_nav_category(
    category: str,
    pages_by_cat: dict,
    category_labels: dict,
) -> None:
    """Render a single navigation category section."""
    pages = pages_by_cat.get(category, [])
    if not pages:
        return
    label = category_labels.get(category)
    if label:
        ui.separator().classes("q-my-md")
        ui.label(label).classes("text-caption q-px-md text-grey-7")
    for page in pages:
        _nav_item(page.title, page.route, page.icon)


def _render_nav_drawer(user: dict | None, drawer_open: bool) -> ui.left_drawer:
    """Build the left navigation drawer from the page registry."""
    drawer = ui.left_drawer(value=drawer_open).classes("bg-grey-2")
    with drawer:
        ui.label("Navigation").classes("text-h6 q-pa-md")
        ui.separator()

        category_labels = {"main": None, "demo": "Demos", "admin": "Admin"}
        pages_by_cat = get_pages_by_category(user, demos_enabled(), roleplay_enabled())

        with ui.list().props("padding"):
            for category in ["main", "demo", "admin"]:
                _render_nav_category(category, pages_by_cat, category_labels)

    return drawer


def _render_algolia_help(help_config: HelpConfig) -> None:
    """Render help button that opens DocSearch modal."""
    ui.add_head_html(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@docsearch/css@4" />'
    )
    ui.add_head_html(
        '<script src="https://cdn.jsdelivr.net/npm/@docsearch/js@4"></script>'
    )

    ui.html('<div id="docsearch-container" style="display:none"></div>')

    ui.add_head_html(f"""<script>
    document.addEventListener('DOMContentLoaded', function() {{
        if (typeof docsearch !== 'undefined') {{
            docsearch({{
                container: '#docsearch-container',
                appId: {json.dumps(help_config.algolia_app_id)},
                indexName: {json.dumps(help_config.algolia_index_name)},
                apiKey: {json.dumps(help_config.algolia_search_api_key)},
            }});
        }}
    }});
    </script>""")

    ui.button(
        icon="help_outline",
        on_click=lambda: ui.run_javascript(
            "document.dispatchEvent("
            "new KeyboardEvent('keydown', "
            "{key: 'k', metaKey: true, ctrlKey: true}))"
        ),
    ).props('flat color=white data-testid="help-btn"').tooltip("Search help")


def _render_mkdocs_help() -> None:
    """Render help button that opens docs site in an iframe dialog."""
    docs_url = get_settings().help.docs_url

    with ui.dialog() as help_dialog, ui.card().classes("w-full max-w-4xl h-[80vh]"):
        with ui.row().classes("w-full justify-between items-center q-pb-sm"):
            ui.label("Help").classes("text-h6")
            ui.button(
                icon="open_in_new",
                on_click=lambda url=docs_url: ui.navigate.to(url, new_tab=True),
            ).props("flat dense").tooltip("Open in new tab")
        ui.element("iframe").props(f'src="{docs_url}" frameborder="0"').classes(
            "w-full flex-grow"
        ).style("height: calc(80vh - 60px)")

    ui.button(
        icon="help_outline",
        on_click=help_dialog.open,
    ).props('flat color=white data-testid="help-btn"').tooltip("Help documentation")


def _render_help_button() -> None:
    """Render help button in header if help is enabled.

    With ``help_backend="algolia"``, injects DocSearch CDN assets and
    opens the DocSearch modal on click. With ``help_backend="mkdocs"``,
    opens the docs site in a new tab.
    """
    help_config = get_settings().help
    if not help_config.help_enabled:
        return

    if help_config.help_backend == "algolia":
        _render_algolia_help(help_config)
    else:
        _render_mkdocs_help()


def _render_header(title: str, user: dict | None) -> ui.button:
    """Build the header bar. Returns the menu button for drawer wiring."""
    with ui.header().classes("bg-primary items-center q-py-xs"):
        menu_btn = ui.button(icon="menu").props("flat color=white")
        ui.label(title).classes("text-h6 text-white q-ml-sm").props(
            'data-testid="page-header-title"'
        )
        ui.element("div").classes("flex-grow")
        _render_help_button()
        if user:
            ui.label(user.get("email", "")).classes("text-white text-body2 q-mr-md")
            ui.button(icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                "flat color=white"
            ).tooltip("Logout")
    return menu_btn


@contextmanager
def page_layout(
    title: str = "PromptGrimoire",
    *,
    drawer_open: bool = True,
    footer: bool = False,
) -> Iterator[ui.element | None]:
    """Context manager for consistent page layout with header and nav drawer.

    Usage::

        @ui.page("/my-page")
        async def my_page():
            with page_layout("My Page") as footer_el:
                ui.label("Page content here")

    When ``footer=True``, a Quasar ``q-footer`` is created and yielded.
    The caller can populate it later with ``with footer_el:``.  The footer
    integrates with Quasar's layout system, so ``q-page`` automatically
    adds padding-bottom — no manual ``position: fixed`` needed.

    Args:
        title: Page title shown in header.
        drawer_open: Whether the nav drawer starts open.
        footer: Whether to create a Quasar footer element.

    Yields:
        The footer element when ``footer=True``, otherwise ``None``.
    """
    user = _get_session_user()
    menu_btn = _render_header(title, user)

    footer_el: ui.element | None = None
    if footer:
        footer_el = (
            ui.footer()
            .classes("bg-gray-100 py-1 px-4")
            .props('id="tag-toolbar-wrapper"')
            .style("box-shadow: 0 -2px 4px rgba(0,0,0,0.1);")
        )

    drawer = _render_nav_drawer(user, drawer_open)
    menu_btn.on("click", drawer.toggle)

    yield footer_el
