"""Navigator page route, UI builder, and infinite scroll handler."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from nicegui import app, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.config import get_settings
from promptgrimoire.db.courses import list_user_enrollments
from promptgrimoire.db.engine import init_db
from promptgrimoire.db.navigator import load_navigator_page
from promptgrimoire.pages.layout import page_layout
from promptgrimoire.pages.navigator._search import setup_search
from promptgrimoire.pages.navigator._sections import (
    append_new_rows,
    record_rendered_headers,
    render_sections,
    reset_header_tracking,
)
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from collections.abc import Callable

    from promptgrimoire.pages.navigator._helpers import PageState

logger = structlog.get_logger()

_CSS_FILE = Path(__file__).resolve().parent.parent.parent / "static" / "navigator.css"

# Scroll payload is [scrollTop, scrollHeight, clientHeight]; see the
# js_handler passed to scroll_container.on(...) in _build_navigator_ui.
_SCROLL_EVENT_ARG_COUNT = 3
# Fraction of scrollHeight past which we treat the user as "near the
# bottom" and prefetch the next page.
_SCROLL_NEAR_BOTTOM_RATIO = 0.9


async def _handle_scroll_event(e: object, *, page_state: PageState) -> None:
    """Load more rows when the user scrolls near the bottom.

    ``user_id``/``is_privileged``/``enrolled_course_ids`` are read from
    ``page_state`` rather than taken as separate parameters; see
    ``_build_navigator_ui`` for why.
    """
    if (
        page_state["loading"]
        or page_state["next_cursor"] is None
        or page_state["search_active"]
        or page_state["editing_active"]
    ):
        return

    event_args = getattr(e, "args", None)
    if (
        not event_args
        or not isinstance(event_args, (list, tuple))
        or len(event_args) < _SCROLL_EVENT_ARG_COUNT
    ):
        return
    scroll_top, scroll_height, client_height = event_args[:_SCROLL_EVENT_ARG_COUNT]
    if not scroll_height or client_height >= scroll_height:
        return
    if (scroll_top + client_height) / scroll_height < _SCROLL_NEAR_BOTTOM_RATIO:
        return

    page_state["loading"] = True
    try:
        accumulated_rows = page_state["rows"]
        cursor = page_state["next_cursor"]
        new_rows, new_cursor = await load_navigator_page(
            user_id=page_state["user_id"],
            is_privileged=page_state["is_privileged"],
            enrolled_course_ids=page_state["enrolled_course_ids"],
            cursor=cursor,
            limit=50,
        )
        accumulated_rows.extend(new_rows)
        page_state["next_cursor"] = new_cursor
        sections_container = page_state["sections_container"]
        await append_new_rows(
            new_rows,
            page_state=page_state,
            sections_container=sections_container,
        )
    finally:
        page_state["loading"] = False


async def _build_navigator_ui(
    *,
    page_state: PageState,
    handle_scroll: Callable[..., object],
) -> None:
    """Build the navigator page DOM.

    Uses a plain scrollable column instead of Quasar QScrollArea.
    The scroll event uses ``js_handler`` with ``emit()`` to extract
    ``scrollTop``, ``scrollHeight``, and ``clientHeight`` from the
    event target.

    ``rows`` is read from ``page_state`` rather than taken as a separate
    parameter -- it is a required key already populated by the caller, so
    passing it again would only duplicate what ``page_state`` carries.
    """
    rows = page_state["rows"]
    with page_layout("Home"):
        ui.add_css(_CSS_FILE)

        scroll_container = ui.column().classes(
            "w-full items-center navigator-scroll-area"
        )
        scroll_container.on(
            "scroll",
            handle_scroll,
            throttle=0.3,
            js_handler="(event) => emit("
            "event.target.scrollTop,"
            " event.target.scrollHeight,"
            " event.target.clientHeight)",
        )

        with (
            scroll_container,
            ui.column().classes("mx-auto q-pa-lg navigator-content-column"),
        ):
            if get_settings().features.enable_search_worker:
                search_input = (
                    ui.input(placeholder="Search titles and content...")
                    .classes("w-full mb-4 navigator-search-input")
                    .props(
                        'outlined dense clearable data-testid="navigator-search-input"'
                    )
                )

            no_results_container = ui.column().classes("w-full")
            sections_container = ui.column().classes("w-full")
            page_state["sections_container"] = sections_container

            if get_settings().features.enable_search_worker:
                on_search_change = setup_search(
                    page_state=page_state,
                    sections_container=sections_container,
                    no_results_container=no_results_container,
                    search_input=search_input,
                )
                search_input.on("update:model-value", on_search_change)

            if not rows:
                ui.label("No workspaces yet.").classes("text-gray-500 mt-4")
            else:
                reset_header_tracking(page_state)
                with sections_container:
                    await render_sections(rows=rows, page_state=page_state)
                record_rendered_headers(rows, page_state)


@page_route("/", title="Home", icon="home", order=10)
async def navigator_page() -> None:
    """Workspace navigator page. Requires authentication."""
    user = app.storage.user.get("auth_user")

    if not user:
        ui.navigate.to("/welcome")
        return

    if not get_settings().database.url:
        ui.label("Database not configured").classes("text-red-500")
        return

    await init_db()

    user_id_str = user.get("user_id")
    if not user_id_str:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    user_id = UUID(user_id_str)
    is_privileged = is_privileged_user(user)

    try:
        enrollments = await list_user_enrollments(user_id)
        enrolled_course_ids = [e.course_id for e in enrollments]

        rows, next_cursor = await load_navigator_page(
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
        )
    except Exception:
        logger.exception("navigator_load_failed", operation="load_navigator_page")
        ui.label("Failed to load workspaces. Please refresh.").classes("text-red-500")
        return

    page_state: PageState = {
        "rows": rows,
        "next_cursor": next_cursor,
        "user_id": user_id,
        "is_privileged": is_privileged,
        "enrolled_course_ids": enrolled_course_ids,
        "search_active": False,
        "loading": False,
        "editing_active": False,
    }

    handle_scroll = functools.partial(_handle_scroll_event, page_state=page_state)

    await _build_navigator_ui(
        page_state=page_state,
        handle_scroll=handle_scroll,
    )
