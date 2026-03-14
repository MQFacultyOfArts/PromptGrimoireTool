"""Shared UI utilities for annotation cards.

Functions extracted from cards.py for reuse across annotation
card modules (cards.py, organise.py, respond.py).
"""

from __future__ import annotations

import re

from nicegui import ui

_EXPANDABLE_THRESHOLD = 80


def author_initials(name: str) -> str:
    """Derive compact initials from a display name.

    Splits on whitespace and hyphens, takes first char of each segment,
    joins with dots.  "Brian Ballsun-Stanton" -> "B.B.S.", "Ada" -> "A."
    """
    segments = re.split(r"[\s\-]+", name)
    return ".".join(s[0].upper() for s in segments if s) + "."


def build_expandable_text(full_text: str) -> None:
    """Build expandable text preview for annotation card."""
    is_long = len(full_text) > _EXPANDABLE_THRESHOLD
    if is_long:
        truncated_text = full_text[:_EXPANDABLE_THRESHOLD] + "..."
        with ui.element("div").classes("mt-1 w-full overflow-hidden"):
            # Truncated view with expand icon
            with ui.row().classes(
                "items-start gap-1 cursor-pointer w-full"
            ) as truncated_row:
                ui.icon("expand_more", size="xs").classes("text-gray-400 flex-shrink-0")
                ui.label(f'"{truncated_text}"').classes("text-sm italic")

            # Full view with collapse icon
            with ui.row().classes(
                "items-start gap-1 cursor-pointer w-full"
            ) as full_row:
                ui.icon("expand_less", size="xs").classes("text-gray-400 flex-shrink-0")
                ui.label(f'"{full_text}"').classes("text-sm italic min-w-0").style(
                    "white-space: pre-wrap; overflow-wrap: break-word"
                )
            full_row.set_visibility(False)

            def toggle_expand(
                tr: ui.row = truncated_row, fr: ui.row = full_row
            ) -> None:
                tr.set_visibility(not tr.visible)
                fr.set_visibility(not fr.visible)

            truncated_row.on("click", toggle_expand)
            full_row.on("click", toggle_expand)
    else:
        ui.label(f'"{full_text}"').classes("text-sm italic mt-1")
