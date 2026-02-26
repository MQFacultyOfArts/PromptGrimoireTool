"""Section grouping, rendering, and append-only infinite scroll."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.auth.anonymise import (
    anonymise_author,
)  # used by _get_owner_display_name
from promptgrimoire.config import get_settings
from promptgrimoire.db.courses import get_course_by_id
from promptgrimoire.pages.navigator._cards import (
    render_unstarted_entry,
    render_workspace_entry,
)
from promptgrimoire.pages.navigator._helpers import (
    SECTION_DISPLAY_NAMES,
    SECTION_ORDER,
    group_by_owner,
    group_rows_by_section,
    group_shared_in_unit_by_course,
)

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.models import Course
    from promptgrimoire.db.navigator import NavigatorRow


# ---------------------------------------------------------------------------
# Anonymisation helper
# ---------------------------------------------------------------------------


def _get_owner_display_name(
    row: NavigatorRow,
    user_id: UUID,
    is_privileged: bool,
) -> str:
    """Resolve the display name, applying anonymisation.

    Uses the resolved anonymous_sharing flag from the SQL query
    (COALESCE of activity-level and course-level defaults).
    """
    return anonymise_author(
        author=row.owner_display_name or "Unknown",
        user_id=(str(row.owner_user_id) if row.owner_user_id else None),
        viewing_user_id=str(user_id),
        anonymous_sharing=row.anonymous_sharing,
        viewer_is_privileged=is_privileged,
        author_is_privileged=row.owner_is_privileged,
    )


# ---------------------------------------------------------------------------
# Full-render helpers (initial load + search results)
# ---------------------------------------------------------------------------


async def _render_shared_in_unit(
    shared_in_unit_rows: list[NavigatorRow],
    enrolled_course_ids: list[UUID],
    course_cache: dict[UUID, Course],
    user_id: UUID,
    is_privileged: bool,
    snippets: dict[UUID, str] | None,
    page_state: dict[str, object] | None = None,
) -> None:
    """Render shared_in_unit sections grouped by course and owner."""
    by_course = group_shared_in_unit_by_course(shared_in_unit_rows)
    for course_id in enrolled_course_ids:
        course_rows = by_course.get(course_id, [])
        if not course_rows:
            continue
        course = course_cache.get(course_id)
        course_name = (
            course.name
            if course
            else course_rows[0].course_name or get_settings().i18n.unit_label
        )
        ui.label(f"Shared in {course_name}").classes(
            "text-xl font-bold mt-6 mb-2 navigator-section-header"
        )

        by_owner_groups = group_by_owner(course_rows)
        for _owner_id, owner_rows in by_owner_groups.items():
            display_name = _get_owner_display_name(
                owner_rows[0], user_id, is_privileged
            )
            ui.label(display_name).classes(
                "text-sm font-semibold mt-3 mb-1 ml-2 text-gray-600"
            )

            placed = [r for r in owner_rows if r.activity_id is not None]
            loose = [r for r in owner_rows if r.activity_id is None]

            for row in placed:
                render_workspace_entry(
                    row, show_owner=False, snippets=snippets, page_state=page_state
                )

            if loose:
                ui.label("Unsorted").classes(
                    "text-xs font-medium mt-2 mb-1 ml-4 "
                    "text-gray-400 navigator-unsorted-label"
                )
                for row in loose:
                    render_workspace_entry(
                        row,
                        show_owner=False,
                        snippets=snippets,
                        page_state=page_state,
                    )


async def _render_simple_section(
    section_key: str,
    section_rows: list[NavigatorRow],
    user_id: UUID,
    is_privileged: bool,
    snippets: dict[UUID, str] | None,
    page_state: dict[str, object] | None = None,
) -> None:
    """Render a non-shared_in_unit section."""
    display_name = SECTION_DISPLAY_NAMES.get(section_key, section_key)
    ui.label(display_name).classes(
        "text-xl font-bold mt-6 mb-2 navigator-section-header"
    )

    for row in section_rows:
        if section_key == "unstarted":
            render_unstarted_entry(row, user_id)
        elif section_key == "shared_with_me":
            owner_label = _get_owner_display_name(row, user_id, is_privileged)
            render_workspace_entry(
                row,
                show_owner=True,
                owner_label=owner_label,
                snippets=snippets,
                page_state=page_state,
            )
        else:
            render_workspace_entry(row, snippets=snippets, page_state=page_state)


async def render_sections(
    rows: list[NavigatorRow],
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: list[UUID],
    snippets: dict[UUID, str] | None = None,
    page_state: dict[str, object] | None = None,
) -> None:
    """Render all navigator sections from the given rows.

    Groups rows by section and renders them in fixed order.
    Empty sections produce no output (AC1.7).
    """
    grouped = group_rows_by_section(rows)

    course_cache: dict[UUID, Course] = {}
    shared_rows = grouped.get("shared_in_unit", [])
    if shared_rows:
        needed = {r.course_id for r in shared_rows if r.course_id is not None}
        for cid in needed:
            if cid not in course_cache:
                course = await get_course_by_id(cid)
                if course is not None:
                    course_cache[cid] = course

    for section_key in SECTION_ORDER:
        if section_key == "shared_in_unit":
            if shared_rows:
                await _render_shared_in_unit(
                    shared_rows,
                    enrolled_course_ids,
                    course_cache,
                    user_id,
                    is_privileged,
                    snippets,
                    page_state=page_state,
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
                    page_state=page_state,
                )


# ---------------------------------------------------------------------------
# Header tracking for append-only infinite scroll
# ---------------------------------------------------------------------------


def reset_header_tracking(page_state: dict[str, object]) -> None:
    """Reset header tracking state for a full re-render."""
    page_state["rendered_sections"] = set()
    page_state["rendered_courses"] = set()
    page_state["rendered_owners"] = set()
    page_state["rendered_unsorted"] = set()


def record_rendered_headers(
    rows: list[NavigatorRow],
    page_state: dict[str, object],
) -> None:
    """Record which section/course/owner headers were rendered."""
    rendered_sections: set[str] = page_state["rendered_sections"]  # type: ignore[assignment]
    rendered_courses: set[UUID] = page_state["rendered_courses"]  # type: ignore[assignment]
    rendered_owners: set[tuple[UUID, UUID | None]] = page_state["rendered_owners"]  # type: ignore[assignment]
    rendered_unsorted: set[tuple[UUID, UUID | None]] = page_state["rendered_unsorted"]  # type: ignore[assignment]

    for row in rows:
        rendered_sections.add(row.section)
        if row.section == "shared_in_unit" and row.course_id is not None:
            rendered_courses.add(row.course_id)
            rendered_owners.add((row.course_id, row.owner_user_id))
            if row.activity_id is None:
                rendered_unsorted.add((row.course_id, row.owner_user_id))


# ---------------------------------------------------------------------------
# Append-only scroll (new rows only, preserves DOM)
# ---------------------------------------------------------------------------


async def _append_shared_in_unit(
    shared_rows: list[NavigatorRow],
    *,
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: list[UUID],
    page_state: dict[str, object],
) -> None:
    """Append shared_in_unit rows, adding course/owner headers as needed."""
    rendered_courses: set[UUID] = page_state["rendered_courses"]  # type: ignore[assignment]
    rendered_owners: set[tuple[UUID, UUID | None]] = page_state["rendered_owners"]  # type: ignore[assignment]
    rendered_unsorted: set[tuple[UUID, UUID | None]] = page_state["rendered_unsorted"]  # type: ignore[assignment]
    course_cache: dict[UUID, Course] = page_state.get("course_cache", {})  # type: ignore[assignment]

    needed = {r.course_id for r in shared_rows if r.course_id is not None}
    for cid in needed - set(course_cache.keys()):
        course = await get_course_by_id(cid)
        if course is not None:
            course_cache[cid] = course
    page_state["course_cache"] = course_cache

    by_course = group_shared_in_unit_by_course(shared_rows)
    for course_id in enrolled_course_ids:
        course_rows = by_course.get(course_id, [])
        if not course_rows:
            continue

        if course_id not in rendered_courses:
            course = course_cache.get(course_id)
            course_name = (
                course.name
                if course
                else course_rows[0].course_name or get_settings().i18n.unit_label
            )
            ui.label(f"Shared in {course_name}").classes(
                "text-xl font-bold mt-6 mb-2 navigator-section-header"
            )
            rendered_courses.add(course_id)

        by_owner_groups = group_by_owner(course_rows)
        for owner_id, owner_rows in by_owner_groups.items():
            owner_key = (course_id, owner_id)
            if owner_key not in rendered_owners:
                display_name = _get_owner_display_name(
                    owner_rows[0], user_id, is_privileged
                )
                ui.label(display_name).classes(
                    "text-sm font-semibold mt-3 mb-1 ml-2 text-gray-600"
                )
                rendered_owners.add(owner_key)

            placed = [r for r in owner_rows if r.activity_id is not None]
            loose = [r for r in owner_rows if r.activity_id is None]

            for row in placed:
                render_workspace_entry(row, show_owner=False, page_state=page_state)
            if loose:
                if owner_key not in rendered_unsorted:
                    ui.label("Unsorted").classes(
                        "text-xs font-medium mt-2 mb-1 ml-4 "
                        "text-gray-400 navigator-unsorted-label"
                    )
                    rendered_unsorted.add(owner_key)
                for row in loose:
                    render_workspace_entry(row, show_owner=False, page_state=page_state)


def _append_simple_section(
    section_key: str,
    section_rows: list[NavigatorRow],
    *,
    user_id: UUID,
    is_privileged: bool,
    page_state: dict[str, object],
) -> None:
    """Append rows for a non-shared_in_unit section, adding header if needed."""
    rendered_sections: set[str] = page_state["rendered_sections"]  # type: ignore[assignment]

    if section_key not in rendered_sections:
        display_name = SECTION_DISPLAY_NAMES.get(section_key, section_key)
        ui.label(display_name).classes(
            "text-xl font-bold mt-6 mb-2 navigator-section-header"
        )
        rendered_sections.add(section_key)

    for row in section_rows:
        if section_key == "unstarted":
            render_unstarted_entry(row, user_id)
        elif section_key == "shared_with_me":
            owner_label = _get_owner_display_name(row, user_id, is_privileged)
            render_workspace_entry(
                row, show_owner=True, owner_label=owner_label, page_state=page_state
            )
        else:
            render_workspace_entry(row, page_state=page_state)


async def append_new_rows(
    new_rows: list[NavigatorRow],
    *,
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: list[UUID],
    page_state: dict[str, object],
    sections_container: ui.column,
) -> None:
    """Append newly loaded rows to the existing sections container.

    Scroll position is preserved because existing DOM is never
    destroyed — new elements are appended at the bottom.
    """
    grouped = group_rows_by_section(new_rows)

    with sections_container:
        for section_key in SECTION_ORDER:
            if section_key == "shared_in_unit":
                shared_rows = grouped.get("shared_in_unit", [])
                if shared_rows:
                    await _append_shared_in_unit(
                        shared_rows,
                        user_id=user_id,
                        is_privileged=is_privileged,
                        enrolled_course_ids=enrolled_course_ids,
                        page_state=page_state,
                    )
            else:
                section_rows = grouped.get(section_key, [])
                if section_rows:
                    _append_simple_section(
                        section_key,
                        section_rows,
                        user_id=user_id,
                        is_privileged=is_privileged,
                        page_state=page_state,
                    )
