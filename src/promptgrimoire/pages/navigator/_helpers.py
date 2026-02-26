"""Constants and pure formatting helpers for the navigator page.

Styles are in static/navigator.css (not Python strings).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.navigator import NavigatorRow


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_DEBOUNCE_SECONDS = 0.5
SEARCH_MIN_CHARS = 3

SECTION_DISPLAY_NAMES: dict[str, str] = {
    "my_work": "My Work",
    "unstarted": "Unstarted Work",
    "shared_with_me": "Shared With Me",
    # shared_in_unit uses per-course names, handled separately
}

SECTION_ORDER: list[str] = [
    "my_work",
    "unstarted",
    "shared_with_me",
    "shared_in_unit",
]

ACTION_LABELS: dict[str | None, str] = {
    "owner": "Resume",
    "editor": "Open",
    "viewer": "View",
    "peer": "View",
}

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def format_updated_at(row: NavigatorRow) -> str:
    """Format the updated_at timestamp for display."""
    if row.updated_at is None:
        return ""
    return row.updated_at.strftime("%d %b %Y, %H:%M")


def breadcrumb(row: NavigatorRow) -> str:
    """Build a breadcrumb string: course > week > activity."""
    parts: list[str] = []
    if row.course_code:
        parts.append(row.course_code)
    if row.week_title:
        parts.append(row.week_title)
    if row.activity_title:
        parts.append(row.activity_title)
    return " > ".join(parts)


def workspace_url(workspace_id: UUID) -> str:
    """Build the annotation page URL for a workspace."""
    qs = urlencode({"workspace_id": str(workspace_id)})
    return f"/annotation?{qs}"


def group_rows_by_section(
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


def group_shared_in_unit_by_course(
    rows: list[NavigatorRow],
) -> dict[UUID, list[NavigatorRow]]:
    """Sub-group shared_in_unit rows by course_id."""
    by_course: dict[UUID, list[NavigatorRow]] = {}
    for row in rows:
        if row.course_id is not None:
            by_course.setdefault(row.course_id, []).append(row)
    return by_course


def group_by_owner(
    rows: list[NavigatorRow],
) -> dict[UUID | None, list[NavigatorRow]]:
    """Group rows by owner_user_id for sub-grouping."""
    by_owner: dict[UUID | None, list[NavigatorRow]] = {}
    for row in rows:
        by_owner.setdefault(row.owner_user_id, []).append(row)
    return by_owner
