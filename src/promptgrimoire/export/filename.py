"""Pure helpers for building safe PDF export filenames.

No database or UI dependencies. All functions are deterministic and
side-effect-free so they can be tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from slugify import slugify

if TYPE_CHECKING:
    # `date` is used only as an annotation on PdfExportFilenameContext.
    # Callers construct the dataclass and pass it in, so no runtime import
    # is needed here — the actual `date` instance arrives from the caller.
    from datetime import date

_MAX_FILENAME_LENGTH = 100
_PDF_SUFFIX = ".pdf"
_FALLBACK_COURSE = "Unplaced"
_FALLBACK_ACTIVITY = "Loose Work"
_FALLBACK_WORKSPACE = "Workspace"
_FALLBACK_OWNER = "Unknown Unknown"


@dataclass(frozen=True)
class PdfExportFilenameContext:
    """Context for building a PDF export filename."""

    course_code: str | None
    activity_title: str | None
    workspace_title: str | None
    owner_display_name: str | None
    export_date: date


def _split_owner_display_name(display_name: str | None) -> tuple[str, str]:
    """Return (last_name, first_name) using first-token / last-token heuristic."""
    if not display_name or not display_name.strip():
        return ("Unknown", "Unknown")

    tokens = display_name.split()
    if len(tokens) == 1:
        return (tokens[0], tokens[0])

    return (tokens[-1], tokens[0])


def _safe_segment(value: str) -> str:
    """ASCII-safe filename segment using python-slugify + underscore cleanup.

    Post-processing collapses repeated underscores and strips leading/trailing
    underscores. This is intentional defense-in-depth even though
    slugify(..., separator="_") already normalises most separators.
    """
    result = slugify(value, separator="_", lowercase=False)
    result = re.sub(r"_+", "_", result)
    result = result.strip("_")
    return result


def _assemble_stem(
    course: str,
    last: str,
    first: str,
    activity: str,
    workspace: str,
    date_part: str,
) -> str:
    """Join non-empty segments with underscores."""
    parts = [course, last, first]
    if activity:
        parts.append(activity)
    if workspace:
        parts.append(workspace)
    parts.append(date_part)
    return "_".join(parts)


def _truncate_for_budget(
    course: str,
    last: str,
    first: str,
    activity: str,
    workspace: str,
    date_part: str,
) -> tuple[str, str, str]:
    """Return trimmed (first, activity, workspace) to fit budget.

    Truncation order:
    1. workspace (right-truncated)
    2. activity (right-truncated)
    3. first name (reduced to 1-char initial)

    course, last, and date_part are never truncated.
    """
    budget = _MAX_FILENAME_LENGTH - len(_PDF_SUFFIX)

    def _current_len(f: str, a: str, w: str) -> int:
        return len(_assemble_stem(course, last, f, a, w, date_part))

    # Already fits?
    if _current_len(first, activity, workspace) <= budget:
        return (first, activity, workspace)

    # Step 1: trim workspace
    while workspace and _current_len(first, activity, workspace) > budget:
        workspace = workspace[:-1]

    if _current_len(first, activity, workspace) <= budget:
        return (first, activity, workspace)

    # Step 2: trim activity
    while activity and _current_len(first, activity, workspace) > budget:
        activity = activity[:-1]

    if _current_len(first, activity, workspace) <= budget:
        return (first, activity, workspace)

    # Step 3: trim first name to 1-char initial
    if len(first) > 1:
        first = first[0]

    return (first, activity, workspace)


def build_pdf_export_stem(ctx: PdfExportFilenameContext) -> str:
    """Return the export stem for a PDF filename."""
    # Resolve raw values with fallbacks
    raw_course = ctx.course_code or _FALLBACK_COURSE
    raw_activity = ctx.activity_title or _FALLBACK_ACTIVITY
    raw_workspace = ctx.workspace_title or _FALLBACK_WORKSPACE
    raw_owner = ctx.owner_display_name or _FALLBACK_OWNER

    # Split and sanitise
    last_raw, first_raw = _split_owner_display_name(raw_owner)
    course = _safe_segment(raw_course) or _FALLBACK_COURSE
    activity = _safe_segment(raw_activity) or "Loose_Work"
    workspace = _safe_segment(raw_workspace) or _FALLBACK_WORKSPACE
    last = _safe_segment(last_raw) or "Unknown"
    first = _safe_segment(first_raw) or "Unknown"
    date_part = ctx.export_date.strftime("%Y%m%d")

    # Suppress workspace segment when its raw title is literally the same as
    # the activity title (the default when workspaces are cloned). Compare raw
    # values, not sanitised segments, so that "José" vs "Jose" stays distinct.
    if ctx.workspace_title and ctx.workspace_title == ctx.activity_title:
        workspace = ""

    # Truncate to fit budget
    first, activity, workspace = _truncate_for_budget(
        course,
        last,
        first,
        activity,
        workspace,
        date_part,
    )

    return _assemble_stem(
        course,
        last,
        first,
        activity,
        workspace,
        date_part,
    )
