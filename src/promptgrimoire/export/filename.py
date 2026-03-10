"""Pure helpers for building safe PDF export filenames.

No database or UI dependencies. All functions are deterministic and
side-effect-free so they can be tested in isolation.
"""

from __future__ import annotations

import re

from slugify import slugify


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
