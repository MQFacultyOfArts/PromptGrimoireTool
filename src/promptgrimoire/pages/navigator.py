"""Workspace navigator page.

Replaces the old index page with a searchable, sectioned workspace list.
Renders all workspaces for the authenticated user across four sections:
  1. My Work -- owned workspaces
  2. Unstarted Work -- published activities not yet started
  3. Shared With Me -- workspaces shared via explicit ACL
  4. Shared in [Unit] -- peer workspaces in enrolled courses

Route: /
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.config import get_settings
from promptgrimoire.db.courses import get_course_by_id, list_user_enrollments
from promptgrimoire.db.engine import init_db
from promptgrimoire.db.navigator import NavigatorRow, load_navigator_page
from promptgrimoire.db.search import search_workspace_content
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
    get_user_workspace_for_activity,
)
from promptgrimoire.pages.layout import page_layout
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from collections.abc import Callable

    from nicegui.elements.input import Input
    from nicegui.elements.timer import Timer

    from promptgrimoire.db.models import Course
    from promptgrimoire.db.navigator import NavigatorCursor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEARCH_DEBOUNCE_SECONDS = 0.5
_SEARCH_MIN_CHARS = 3

# ---------------------------------------------------------------------------
# Section display names and render order
# ---------------------------------------------------------------------------

_SECTION_DISPLAY_NAMES: dict[str, str] = {
    "my_work": "My Work",
    "unstarted": "Unstarted Work",
    "shared_with_me": "Shared With Me",
    # shared_in_unit uses per-course names, handled separately
}

_SECTION_ORDER: list[str] = [
    "my_work",
    "unstarted",
    "shared_with_me",
    "shared_in_unit",
]

# Permission level -> action button label
_ACTION_LABELS: dict[str | None, str] = {
    "owner": "Resume",
    "editor": "Open",
    "viewer": "View",
    "peer": "View",
}

# ---------------------------------------------------------------------------
# CSS for search snippets (Phase 5, Task 3)
# ---------------------------------------------------------------------------

_SEARCH_SNIPPET_CSS = """\
.navigator-snippet {
    font-size: 0.8rem;
    line-height: 1.4;
    color: #555;
    background: #f8f9fa;
    border-radius: 4px;
    padding: 4px 8px;
    margin-top: 4px;
}
.navigator-snippet mark {
    background-color: #fff3cd;
    color: #856404;
    padding: 0 2px;
    border-radius: 2px;
    font-weight: 600;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_updated_at(row: NavigatorRow) -> str:
    """Format the updated_at timestamp for display."""
    if row.updated_at is None:
        return ""
    return row.updated_at.strftime("%d %b %Y, %H:%M")


def _breadcrumb(row: NavigatorRow) -> str:
    """Build a breadcrumb string: course > week > activity."""
    parts: list[str] = []
    if row.course_code:
        parts.append(row.course_code)
    if row.week_title:
        parts.append(row.week_title)
    if row.activity_title:
        parts.append(row.activity_title)
    return " > ".join(parts)


def _workspace_url(workspace_id: UUID) -> str:
    """Build the annotation page URL for a workspace."""
    qs = urlencode({"workspace_id": str(workspace_id)})
    return f"/annotation?{qs}"


def _group_rows_by_section(
    rows: list[NavigatorRow],
) -> dict[str, list[NavigatorRow]]:
    """Group rows by section into a dict.

    Does NOT use itertools.groupby because rows are sorted by
    recency across sections, not grouped contiguously by section.
    """
    groups: dict[str, list[NavigatorRow]] = {}
    for row in rows:
        groups.setdefault(row.section, []).append(row)
    return groups


def _group_shared_in_unit_by_course(
    rows: list[NavigatorRow],
) -> dict[UUID, list[NavigatorRow]]:
    """Sub-group shared_in_unit rows by course_id."""
    by_course: dict[UUID, list[NavigatorRow]] = {}
    for row in rows:
        if row.course_id is not None:
            by_course.setdefault(row.course_id, []).append(row)
    return by_course


def _group_by_owner(
    rows: list[NavigatorRow],
) -> dict[UUID | None, list[NavigatorRow]]:
    """Group rows by owner_user_id for sub-grouping."""
    by_owner: dict[UUID | None, list[NavigatorRow]] = {}
    for row in rows:
        by_owner.setdefault(row.owner_user_id, []).append(row)
    return by_owner


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_workspace_entry(
    row: NavigatorRow,
    *,
    show_owner: bool = False,
    owner_label: str = "",
    snippets: dict[UUID, str] | None = None,
) -> None:
    """Render a single workspace entry as a card row."""
    with (
        ui.card().classes("w-full p-3 mb-2").props("flat bordered"),
        ui.row().classes("w-full items-center gap-4"),
    ):
        # Left side: title + breadcrumb
        with ui.column().classes("flex-grow gap-0"):
            # Title row
            with ui.row().classes("items-center gap-2"):
                title = row.title or row.activity_title or "Untitled"
                if row.workspace_id is not None:
                    ui.link(
                        title,
                        _workspace_url(row.workspace_id),
                    ).classes(
                        "text-base font-medium text-primary "
                        "no-underline hover:underline "
                        "cursor-pointer"
                    ).props(f'data-workspace-id="{row.workspace_id}"')
                else:
                    ui.label(title).classes("text-base font-medium")

            # Breadcrumb
            crumb = _breadcrumb(row)
            if crumb:
                ui.label(crumb).classes("text-xs text-gray-500")

            # Owner (for shared sections)
            if show_owner and owner_label:
                ui.label(f"by {owner_label}").classes("text-xs text-gray-400")

            # Snippet (Phase 5, Task 2: render as HTML for <mark> tags)
            if (
                snippets
                and row.workspace_id is not None
                and row.workspace_id in snippets
            ):
                # sanitize=False: snippet HTML is from ts_headline with
                # HTML-stripped content (regexp_replace in search SQL).
                ui.html(snippets[row.workspace_id], sanitize=False).classes(
                    "navigator-snippet"
                )

        # Right side: date + action button
        with ui.column().classes("items-end gap-1"):
            date_str = _format_updated_at(row)
            if date_str:
                ui.label(date_str).classes("text-xs text-gray-400")

            if row.workspace_id is not None:
                action = _ACTION_LABELS.get(row.permission, "Open")
                url = _workspace_url(row.workspace_id)
                ui.button(
                    action,
                    on_click=lambda u=url: ui.navigate.to(u),
                ).props("flat dense size=sm color=primary").classes(
                    "navigator-action-btn"
                )


def _render_unstarted_entry(
    row: NavigatorRow,
    user_id: UUID,
) -> None:
    """Render an unstarted activity entry with a Start button."""
    with (
        ui.card().classes("w-full p-3 mb-2").props("flat bordered"),
        ui.row().classes("w-full items-center gap-4"),
    ):
        with ui.column().classes("flex-grow gap-0"):
            title = row.activity_title or "Untitled Activity"
            ui.label(title).classes("text-base font-medium")

            crumb = _breadcrumb(row)
            if crumb:
                ui.label(crumb).classes("text-xs text-gray-500")

        with ui.column().classes("items-end gap-1"):
            if row.activity_id is not None:

                async def _start_activity(
                    aid: UUID = row.activity_id,
                    uid: UUID = user_id,
                ) -> None:
                    """Clone template and navigate."""
                    existing = await get_user_workspace_for_activity(aid, uid)
                    if existing is not None:
                        ui.navigate.to(_workspace_url(existing.id))
                        return

                    error = await check_clone_eligibility(aid, uid)
                    if error is not None:
                        ui.notify(error, type="negative")
                        return

                    try:
                        clone, _doc_map = await clone_workspace_from_activity(aid, uid)
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        return

                    ui.navigate.to(_workspace_url(clone.id))

                ui.button("Start", on_click=_start_activity).props(
                    "flat dense size=sm color=primary"
                ).classes("navigator-start-btn")


async def _get_owner_display_name(
    row: NavigatorRow,
    user_id: UUID,
    is_privileged: bool,
    course: Course | None,
) -> str:
    """Resolve the display name, applying anonymisation."""
    author = row.owner_display_name or "Unknown"

    if course is None:
        return author

    # Use course-level default_anonymous_sharing. The NavigatorRow
    # doesn't carry the activity's anonymous_sharing override, but
    # shared_in_unit rows are already filtered by the SQL query's
    # sharing gates, so the course default is acceptable here.
    anonymous_sharing = course.default_anonymous_sharing

    return anonymise_author(
        author=author,
        user_id=(str(row.owner_user_id) if row.owner_user_id else None),
        viewing_user_id=str(user_id),
        anonymous_sharing=anonymous_sharing,
        viewer_is_privileged=is_privileged,
        author_is_privileged=False,
    )


async def _render_shared_in_unit(
    shared_in_unit_rows: list[NavigatorRow],
    enrolled_course_ids: list[UUID],
    course_cache: dict[UUID, Course],
    user_id: UUID,
    is_privileged: bool,
    snippets: dict[UUID, str] | None,
) -> None:
    """Render shared_in_unit sections grouped by course and owner."""
    by_course = _group_shared_in_unit_by_course(shared_in_unit_rows)
    for course_id in enrolled_course_ids:
        course_rows = by_course.get(course_id, [])
        if not course_rows:
            continue
        course = course_cache.get(course_id)
        course_name = course.name if course else course_rows[0].course_name or "Unit"
        ui.label(f"Shared in {course_name}").classes(
            "text-xl font-bold mt-6 mb-2 navigator-section-header"
        )

        by_owner = _group_by_owner(course_rows)
        for _owner_id, owner_rows in by_owner.items():
            display_name = await _get_owner_display_name(
                owner_rows[0], user_id, is_privileged, course
            )
            ui.label(display_name).classes(
                "text-sm font-semibold mt-3 mb-1 ml-2 text-gray-600"
            )

            placed = [r for r in owner_rows if r.activity_id is not None]
            loose = [r for r in owner_rows if r.activity_id is None]

            for row in placed:
                _render_workspace_entry(row, show_owner=False, snippets=snippets)

            if loose:
                ui.label("Unsorted").classes(
                    "text-xs font-medium mt-2 mb-1 ml-4 "
                    "text-gray-400 navigator-unsorted-label"
                )
                for row in loose:
                    _render_workspace_entry(
                        row,
                        show_owner=False,
                        snippets=snippets,
                    )


async def _render_simple_section(
    section_key: str,
    section_rows: list[NavigatorRow],
    user_id: UUID,
    is_privileged: bool,
    snippets: dict[UUID, str] | None,
) -> None:
    """Render a non-shared_in_unit section."""
    display_name = _SECTION_DISPLAY_NAMES.get(section_key, section_key)
    ui.label(display_name).classes(
        "text-xl font-bold mt-6 mb-2 navigator-section-header"
    )

    for row in section_rows:
        if section_key == "unstarted":
            _render_unstarted_entry(row, user_id)
        elif section_key == "shared_with_me":
            # Anonymise owner names for shared_with_me just like shared_in_unit.
            # Students should not see real names of workspace owners.
            # anonymous_sharing=True enables the anonymisation path;
            # viewer_is_privileged bypasses it for instructors/admins.
            owner_label = anonymise_author(
                author=row.owner_display_name or "Unknown",
                user_id=(str(row.owner_user_id) if row.owner_user_id else None),
                viewing_user_id=str(user_id),
                anonymous_sharing=True,
                viewer_is_privileged=is_privileged,
                author_is_privileged=False,
            )
            _render_workspace_entry(
                row,
                show_owner=True,
                owner_label=owner_label,
                snippets=snippets,
            )
        else:
            _render_workspace_entry(row, snippets=snippets)


async def _render_sections_impl(
    rows: list[NavigatorRow],
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: list[UUID],
    next_cursor: NavigatorCursor | None = None,  # noqa: ARG001 -- Phase 7 pagination
    snippets: dict[UUID, str] | None = None,
) -> None:
    """Render all navigator sections from the given rows.

    Groups rows by section and renders them in fixed order.
    Empty sections produce no output (AC1.7).

    Parameters
    ----------
    rows:
        All NavigatorRow objects to render.
    user_id:
        The authenticated user's UUID.
    is_privileged:
        Whether the user has instructor/admin privileges.
    enrolled_course_ids:
        Course IDs the user is enrolled in.
    next_cursor:
        Pagination cursor for more pages (Phase 7).
    snippets:
        workspace_id -> snippet HTML for search (Phase 5).
    """
    grouped = _group_rows_by_section(rows)

    # Pre-load courses for shared_in_unit anonymisation
    course_cache: dict[UUID, Course] = {}
    shared_rows = grouped.get("shared_in_unit", [])
    if shared_rows:
        needed = {r.course_id for r in shared_rows if r.course_id is not None}
        for cid in needed:
            if cid not in course_cache:
                course = await get_course_by_id(cid)
                if course is not None:
                    course_cache[cid] = course

    for section_key in _SECTION_ORDER:
        if section_key == "shared_in_unit":
            if shared_rows:
                await _render_shared_in_unit(
                    shared_rows,
                    enrolled_course_ids,
                    course_cache,
                    user_id,
                    is_privileged,
                    snippets,
                )
        else:
            section_rows = grouped.get(section_key, [])
            if section_rows:
                await _render_simple_section(
                    section_key,
                    section_rows,
                    user_id,
                    is_privileged,
                    snippets,
                )


# ---------------------------------------------------------------------------
# Search behaviour (Phase 5, Task 1)
# ---------------------------------------------------------------------------


def _setup_search(
    *,
    all_rows: list[NavigatorRow],
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: list[UUID],
    next_cursor: NavigatorCursor | None,
    render_sections_refresh: Callable[..., object],
    no_results_container: ui.column,
    search_input: Input,
) -> Callable[[object], None]:
    """Wire up debounced FTS search and return the on-change handler.

    Extracted from ``navigator_page`` to keep that function under the
    PLR0915 statement limit.

    Parameters
    ----------
    all_rows:
        The full (unfiltered) list of NavigatorRow from the initial load.
    render_sections_refresh:
        The ``.refresh()`` method on the ``@ui.refreshable`` sections.
    no_results_container:
        A ``ui.column`` where "no results" messaging is rendered.
    search_input:
        The ``ui.input`` element for clearing its value on reset.

    Returns
    -------
    The event handler to attach to the search input's
    ``update:model-value`` event.
    """
    _debounce: dict[str, Timer | None] = {"timer": None}

    def _restore_full_view() -> None:
        no_results_container.clear()
        render_sections_refresh(
            rows=all_rows,
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
            next_cursor=next_cursor,
            snippets=None,
        )

    def _clear_search() -> None:
        search_input.set_value("")
        _restore_full_view()

    async def _do_search(query: str) -> None:
        results = await search_workspace_content(query, limit=50)
        matched_ids = {r.workspace_id for r in results}
        snippets = {r.workspace_id: r.snippet for r in results}
        filtered = [r for r in all_rows if r.workspace_id in matched_ids]

        if filtered:
            no_results_container.clear()
            render_sections_refresh(
                rows=filtered,
                user_id=user_id,
                is_privileged=is_privileged,
                enrolled_course_ids=enrolled_course_ids,
                next_cursor=None,
                snippets=snippets,
            )
        else:
            render_sections_refresh(
                rows=[],
                user_id=user_id,
                is_privileged=is_privileged,
                enrolled_course_ids=enrolled_course_ids,
                next_cursor=None,
                snippets=None,
            )
            no_results_container.clear()
            with (
                no_results_container,
                ui.column().classes("w-full items-center mt-8 gap-2"),
            ):
                ui.label("No workspaces match your search.").classes(
                    "text-gray-500 navigator-no-results"
                )
                ui.button(
                    "Clear search",
                    on_click=_clear_search,
                ).props("flat color=primary").classes("navigator-clear-search-btn")

    def _on_search_change(e: object) -> None:
        if _debounce["timer"] is not None:
            _debounce["timer"].cancel()
            _debounce["timer"] = None

        # GenericEventArguments from update:model-value passes the
        # new value as ``args`` (a raw string), not ``value``.
        query = getattr(e, "args", None) or ""
        if not isinstance(query, str):
            query = ""
        query = query.strip()

        if len(query) < _SEARCH_MIN_CHARS:
            _restore_full_view()
            return

        _debounce["timer"] = ui.timer(
            _SEARCH_DEBOUNCE_SECONDS,
            lambda q=query: _do_search(q),
            once=True,
        )

    return _on_search_change


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------


@page_route("/", title="Home", icon="home", order=10)
async def navigator_page() -> None:
    """Workspace navigator page. Requires authentication."""
    user = app.storage.user.get("auth_user")

    if not user:
        ui.navigate.to("/login")
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

    enrollments = await list_user_enrollments(user_id)
    enrolled_course_ids = [e.course_id for e in enrollments]

    rows, next_cursor = await load_navigator_page(
        user_id=user_id,
        is_privileged=is_privileged,
        enrolled_course_ids=enrolled_course_ids,
    )

    # Page-level state for Phase 7 infinite scroll.  Stored in a mutable
    # container so Phase 7's scroll handler (defined in the same scope) can
    # append new rows and call _render_sections.refresh() without reloading
    # the entire page.
    page_state: dict[str, object] = {
        "rows": rows,
        "next_cursor": next_cursor,
        "user_id": user_id,
        "is_privileged": is_privileged,
        "enrolled_course_ids": enrolled_course_ids,
    }

    @ui.refreshable
    async def _render_sections(
        rows: list[NavigatorRow],
        user_id: UUID,
        is_privileged: bool,
        enrolled_course_ids: list[UUID],
        next_cursor: NavigatorCursor | None = None,
        snippets: dict[UUID, str] | None = None,
    ) -> None:
        """Refreshable section renderer.

        Wraps ``_render_sections_impl`` so Phase 5 (search) and Phase 7
        (infinite scroll) can call ``_render_sections.refresh()`` with
        updated rows without reconstructing the entire page.  ``page_state``
        (captured via closure) keeps the accumulated rows and cursor so
        Phase 7 can append before refreshing.
        """
        await _render_sections_impl(
            rows=rows,
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
            next_cursor=next_cursor,
            snippets=snippets,
        )

    with page_layout("Home"), ui.column().classes("w-full max-w-4xl mx-auto"):
        # Search snippet CSS (Phase 5, Task 3)
        ui.add_css(_SEARCH_SNIPPET_CSS)

        # Search input (Phase 5, Task 1)
        search_input = (
            ui.input(placeholder="Search titles and content...")
            .classes("w-full mb-4 navigator-search-input")
            .props("outlined dense clearable")
        )

        # Container for no-results message
        no_results_container = ui.column().classes("w-full")

        # Wire up search behaviour
        on_search_change = _setup_search(
            all_rows=rows,
            user_id=user_id,
            is_privileged=is_privileged,
            enrolled_course_ids=enrolled_course_ids,
            next_cursor=next_cursor,
            render_sections_refresh=_render_sections.refresh,
            no_results_container=no_results_container,
            search_input=search_input,
        )
        search_input.on("update:model-value", on_search_change)

        if not rows:
            ui.label("No workspaces yet.").classes("text-gray-500 mt-4")
        else:
            await _render_sections(
                rows=rows,
                user_id=user_id,
                is_privileged=is_privileged,
                enrolled_course_ids=enrolled_course_ids,
                next_cursor=next_cursor,
                snippets=None,
            )

    # Suppress unused-variable warning: page_state is intentionally kept in
    # scope for Phase 7's scroll handler to mutate.
    _ = page_state
