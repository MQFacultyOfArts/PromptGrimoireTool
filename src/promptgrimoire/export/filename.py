"""Pure helpers for building safe PDF export filenames.

No database or UI dependencies. All functions are deterministic and
side-effect-free so they can be tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
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


@dataclass(frozen=True, slots=True)
class _FilenameSegments:
    """Sanitised filename segments that travel together through assembly
    and truncation. Grouped into one param object (rather than passed as
    six positional arguments) because every function in this module that
    touches one segment needs all six to reconstruct the assembled stem.
    """

    course: str
    last: str
    first: str
    activity: str
    workspace: str
    date_part: str


def _assemble_stem(segments: _FilenameSegments) -> str:
    """Join non-empty segments with underscores."""
    parts = [segments.course, segments.last, segments.first]
    if segments.activity:
        parts.append(segments.activity)
    if segments.workspace:
        parts.append(segments.workspace)
    parts.append(segments.date_part)
    return "_".join(parts)


def _truncate_for_budget(segments: _FilenameSegments) -> _FilenameSegments:
    """Return *segments* with first/activity/workspace trimmed to fit the budget.

    Truncation order:
    1. workspace (right-truncated)
    2. activity (right-truncated)
    3. first name (reduced to 1-char initial)

    course, last, and date_part are never truncated. If the assembled stem
    still exceeds the budget after workspace and activity are exhausted and
    the first name is reduced to a single character, AC3.6 allows that
    pathological overflow to stand.
    """
    budget = _MAX_FILENAME_LENGTH - len(_PDF_SUFFIX)
    first, activity, workspace = segments.first, segments.activity, segments.workspace

    def _fits(f: str, a: str, w: str) -> bool:
        candidate = replace(segments, first=f, activity=a, workspace=w)
        return len(_assemble_stem(candidate)) <= budget

    # Already fits?
    if _fits(first, activity, workspace):
        return replace(segments, first=first, activity=activity, workspace=workspace)

    # Step 1: trim workspace
    while workspace and not _fits(first, activity, workspace):
        workspace = workspace[:-1]

    if _fits(first, activity, workspace):
        return replace(segments, first=first, activity=activity, workspace=workspace)

    # Step 2: trim activity
    while activity and not _fits(first, activity, workspace):
        activity = activity[:-1]

    if _fits(first, activity, workspace):
        return replace(segments, first=first, activity=activity, workspace=workspace)

    # Step 3: trim first name to 1-char initial
    if len(first) > 1:
        first = first[0]

    # AC3.6: overflow is legal only after every trimmable segment has already
    # been exhausted and the first-name segment is down to one character.
    return replace(segments, first=first, activity=activity, workspace=workspace)


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

    segments = _FilenameSegments(
        course=course,
        last=last,
        first=first,
        activity=activity,
        workspace=workspace,
        date_part=date_part,
    )

    # Truncate to fit budget
    segments = _truncate_for_budget(segments)

    return _assemble_stem(segments)
