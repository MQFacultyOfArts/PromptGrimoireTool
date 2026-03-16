"""Page registration system for data-driven navigation.

Provides a decorator for registering pages with metadata, enabling
automatic navigation generation based on user permissions.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import structlog
from nicegui import app, ui
from structlog.contextvars import bind_contextvars, clear_contextvars

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.config import get_settings

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID


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


def _has_roleplay_page_access(
    user: dict[str, object] | None,
    roleplay_enabled: bool,
) -> bool:
    """Return whether the current user can access roleplay-gated pages."""
    if not roleplay_enabled:
        return False
    if not get_settings().features.roleplay_require_privileged:
        return user is not None
    return is_privileged_user(user)


def _is_page_visible(
    meta: PageMeta,
    user: dict[str, object] | None,
    *,
    demos_enabled: bool,
    roleplay_enabled: bool,
) -> bool:
    """Centralize page visibility checks behind a single capability seam."""
    is_authenticated = user is not None
    is_admin = bool(user and user.get("is_admin"))
    return all(
        (
            meta.category != "hidden",
            not meta.requires_auth or is_authenticated,
            not meta.requires_admin or is_admin,
            not meta.requires_demo or demos_enabled,
            not meta.requires_roleplay
            or _has_roleplay_page_access(user, roleplay_enabled),
        )
    )


async def _check_ban(user_id: UUID, route: str) -> bool:
    """Return True (and redirect) if the user is banned."""
    from promptgrimoire.db.users import is_user_banned  # noqa: PLC0415, I001 -- inline to avoid circular import (registry -> db)

    if await is_user_banned(user_id):
        logger.warning("banned_user_redirected", user_id=user_id, route=route)
        ui.navigate.to("/banned")
        return True
    return False


def _register_client(user_id: UUID) -> None:
    """Register the current NiceGUI client for real-time ban kick."""
    from uuid import UUID as _UUID  # noqa: PLC0415

    from promptgrimoire.auth import client_registry  # noqa: PLC0415

    client_registry.register(_UUID(str(user_id)), ui.context.client)


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

        @functools.wraps(func)
        async def _with_log_context(*args: object, **kwargs: object) -> None:
            clear_contextvars()
            user_id = None
            try:
                auth_user = app.storage.user.get("auth_user")
                user_id = auth_user.get("user_id") if auth_user else None
            except RuntimeError:
                logger.debug("storage_unavailable", route=route)
            bind_contextvars(user_id=user_id, request_path=route)

            # Ban check: redirect banned users to suspension page
            if requires_auth and user_id and await _check_ban(user_id, route):
                return

            # Register client for real-time ban kick
            if user_id:
                _register_client(user_id)

            await func(*args, **kwargs)

        return ui.page(route)(_with_log_context)

    return decorator


def get_visible_pages(
    user: dict[str, object] | None,
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
    visible = [
        meta
        for meta in _page_registry.values()
        if _is_page_visible(
            meta,
            user,
            demos_enabled=demos_enabled,
            roleplay_enabled=roleplay_enabled,
        )
    ]

    # Sort by category order, then by order field
    category_order = {"main": 0, "demo": 1, "admin": 2, "auth": 3}
    visible.sort(key=lambda p: (category_order.get(p.category, 99), p.order))

    return visible


def get_pages_by_category(
    user: dict[str, object] | None,
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
