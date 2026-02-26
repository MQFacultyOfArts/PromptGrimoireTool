"""Search behaviour: debounced FTS search and result rendering."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.db.navigator import NavigatorRow, search_navigator
from promptgrimoire.pages.navigator._helpers import (
    SEARCH_DEBOUNCE_SECONDS,
    SEARCH_MIN_CHARS,
)
from promptgrimoire.pages.navigator._sections import (
    record_rendered_headers,
    render_sections,
    reset_header_tracking,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from nicegui.elements.input import Input
    from nicegui.elements.timer import Timer

logger = logging.getLogger(__name__)


async def rerender_all(
    rows: list[NavigatorRow],
    *,
    snippets: dict[UUID, str] | None = None,
    page_state: dict[str, object],
    sections_container: ui.column,
    no_results_container: ui.column,
) -> None:
    """Clear sections container and re-render all rows from scratch.

    Used by search (to show filtered results) and search-clear
    (to restore the full accumulated view).
    """
    no_results_container.clear()
    sections_container.clear()
    user_id: UUID = page_state["user_id"]  # type: ignore[assignment]
    is_privileged: bool = page_state["is_privileged"]  # type: ignore[assignment]
    enrolled_course_ids: list[UUID] = page_state["enrolled_course_ids"]  # type: ignore[assignment]
    reset_header_tracking(page_state)
    with sections_container:
        await render_sections(
            rows=rows,
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
            snippets=snippets,
            page_state=page_state,
        )
    record_rendered_headers(rows, page_state)


async def _do_search(
    query: str,
    *,
    page_state: dict[str, object],
    sections_container: ui.column,
    no_results_container: ui.column,
    clear_search_callback: Callable[..., Awaitable[None]],
) -> None:
    """Execute FTS search via the single combined navigator query."""
    user_id: UUID = page_state["user_id"]  # type: ignore[assignment]
    is_privileged: bool = page_state["is_privileged"]  # type: ignore[assignment]
    enrolled_course_ids: list[UUID] = page_state["enrolled_course_ids"]  # type: ignore[assignment]

    try:
        hits = await search_navigator(
            query,
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
        )
    except Exception:
        logger.exception("Search failed for query %r", query)
        ui.notify("Search failed. Try again.", type="warning")
        return

    page_state["search_active"] = True
    rows = [h.row for h in hits]
    snippets: dict[UUID, str] = {
        h.row.workspace_id: h.snippet for h in hits if h.row.workspace_id
    }

    if rows:
        await rerender_all(
            rows,
            snippets=snippets,
            page_state=page_state,
            sections_container=sections_container,
            no_results_container=no_results_container,
        )
    else:
        await rerender_all(
            [],
            page_state=page_state,
            sections_container=sections_container,
            no_results_container=no_results_container,
        )
        with (
            no_results_container,
            ui.column().classes("w-full items-center mt-8 gap-2"),
        ):
            ui.label("No workspaces match your search.").classes(
                "text-gray-500 navigator-no-results"
            )
            ui.button(
                "Clear search",
                on_click=clear_search_callback,
            ).props("flat color=primary").classes("navigator-clear-search-btn")


def setup_search(
    *,
    page_state: dict[str, object],
    sections_container: ui.column,
    no_results_container: ui.column,
    search_input: Input,
) -> Callable[..., Awaitable[None]]:
    """Wire up debounced FTS search and return the on-change handler."""
    _debounce: dict[str, Timer | None] = {"timer": None}

    async def _restore_full_view() -> None:
        all_rows: list[NavigatorRow] = page_state["rows"]  # type: ignore[assignment]
        page_state["search_active"] = False
        await rerender_all(
            all_rows,
            page_state=page_state,
            sections_container=sections_container,
            no_results_container=no_results_container,
        )

    async def _clear_search() -> None:
        search_input.set_value("")
        await _restore_full_view()

    async def _on_search_change(e: object) -> None:
        if _debounce["timer"] is not None:
            _debounce["timer"].cancel()
            _debounce["timer"] = None

        # GenericEventArguments from update:model-value passes the
        # new value as ``args`` (a raw string), not ``value``.
        query = getattr(e, "args", None) or ""
        if not isinstance(query, str):
            query = ""
        query = query.strip()

        if len(query) < SEARCH_MIN_CHARS:
            await _restore_full_view()
            return

        _debounce["timer"] = ui.timer(
            SEARCH_DEBOUNCE_SECONDS,
            lambda q=query: _do_search(
                q,
                page_state=page_state,
                sections_container=sections_container,
                no_results_container=no_results_container,
                clear_search_callback=_clear_search,
            ),
            once=True,
        )

    return _on_search_change
