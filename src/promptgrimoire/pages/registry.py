"""Page registration system for data-driven navigation.

Provides a decorator for registering pages with metadata, enabling
automatic navigation generation based on user permissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from nicegui import ui

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class PageMeta:
    """Metadata for a registered page."""

    route: str
    title: str
    icon: str
    category: Literal["main", "demo", "admin", "auth", "hidden"] = "main"
    requires_auth: bool = True
    requires_admin: bool = False
    requires_demo: bool = False
    requires_roleplay: bool = False
    order: int = field(default=100)


# Global registry of all pages
_page_registry: dict[str, PageMeta] = {}


def page_route(
    route: str,
    *,
    title: str,
    icon: str,
    category: Literal["main", "demo", "admin", "auth", "hidden"] = "main",
    requires_auth: bool = True,
    requires_admin: bool = False,
    requires_demo: bool = False,
    requires_roleplay: bool = False,
    order: int = 100,
) -> Callable:
    """Decorator to register a page with navigation metadata.

    Usage:
        @page_route("/courses", title="Courses", icon="school", order=20)
        async def courses_page():
            ...

    Args:
        route: URL path for the page.
        title: Display title in navigation.
        icon: Material icon name.
        category: Navigation section (main, demo, admin, auth, hidden).
        requires_auth: Whether page requires authentication.
        requires_admin: Whether page requires admin role.
        requires_demo: Whether page requires ENABLE_DEMO_PAGES flag.
        order: Sort order within category (lower = higher).

    Returns:
        Decorated function registered with NiceGUI and the page registry.
    """

    def decorator(func: Callable) -> Callable:
        meta = PageMeta(
            route=route,
            title=title,
            icon=icon,
            category=category,
            requires_auth=requires_auth,
            requires_admin=requires_admin,
            requires_demo=requires_demo,
            requires_roleplay=requires_roleplay,
            order=order,
        )
        _page_registry[route] = meta
        return ui.page(route)(func)

    return decorator


def get_visible_pages(
    user: dict | None,
    demos_enabled: bool,
    roleplay_enabled: bool = True,
) -> list[PageMeta]:
    """Get pages visible to the current user, sorted by category and order.

    Args:
        user: Current user dict from session, or None if not authenticated.
        demos_enabled: Whether ENABLE_DEMO_PAGES flag is set.
        roleplay_enabled: Whether FEATURES__ENABLE_ROLEPLAY flag is set.

    Returns:
        List of PageMeta for pages the user can access.
    """
    is_admin = bool(user and user.get("is_admin"))
    is_authenticated = user is not None

    visible = []
    for meta in _page_registry.values():
        # Skip hidden pages
        if meta.category == "hidden":
            continue

        # Check auth requirement
        if meta.requires_auth and not is_authenticated:
            continue

        # Check admin requirement
        if meta.requires_admin and not is_admin:
            continue

        # Check demo requirement
        if meta.requires_demo and not demos_enabled:
            continue

        # Check roleplay requirement
        if meta.requires_roleplay and not roleplay_enabled:
            continue

        visible.append(meta)

    # Sort by category order, then by order field
    category_order = {"main": 0, "demo": 1, "admin": 2, "auth": 3}
    visible.sort(key=lambda p: (category_order.get(p.category, 99), p.order))

    return visible


def get_pages_by_category(
    user: dict | None,
    demos_enabled: bool,
    roleplay_enabled: bool = True,
) -> dict[str, list[PageMeta]]:
    """Get visible pages grouped by category.

    Args:
        user: Current user dict from session, or None if not authenticated.
        demos_enabled: Whether ENABLE_DEMO_PAGES flag is set.
        roleplay_enabled: Whether FEATURES__ENABLE_ROLEPLAY flag is set.

    Returns:
        Dict mapping category names to lists of PageMeta.
    """
    pages = get_visible_pages(user, demos_enabled, roleplay_enabled)
    by_category: dict[str, list[PageMeta]] = {}

    for page in pages:
        if page.category not in by_category:
            by_category[page.category] = []
        by_category[page.category].append(page)

    return by_category
