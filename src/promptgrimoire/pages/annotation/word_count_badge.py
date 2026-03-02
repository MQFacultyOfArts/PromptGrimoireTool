"""Word count badge formatting for annotation header.

Pure functions — no UI, no async, no side effects.
Computes badge text and CSS classes based on word count vs limits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeState:
    """Immutable badge display state."""

    text: str
    css_classes: str


# Tailwind CSS class sets for each badge style
_NEUTRAL = "text-sm text-gray-600 bg-gray-100 px-2 py-0.5 rounded"
_AMBER = "text-sm text-amber-800 bg-amber-100 px-2 py-0.5 rounded"
_RED = "text-sm text-red-800 bg-red-100 px-2 py-0.5 rounded"


def format_word_count_badge(
    count: int,
    word_minimum: int | None,
    word_limit: int | None,
) -> BadgeState:
    """Format word count badge text and style.

    Args:
        count: Current word count.
        word_minimum: Minimum word count threshold, or None.
        word_limit: Maximum word count threshold, or None.

    Returns:
        BadgeState with formatted text and CSS classes.

    Colour logic:
        - Red: over limit (count >= word_limit) or below minimum (count < word_minimum)
        - Amber: approaching limit (count >= word_limit * 0.9)
        - Neutral: within acceptable range
    """
    text = f"Words: {count:,}"
    css_classes = _NEUTRAL

    if word_limit is not None and word_minimum is not None:
        # Both min and max configured
        text += f" / {word_limit:,}"
        if count >= word_limit:
            text += " (over limit)"
            css_classes = _RED
        elif count < word_minimum:
            text += " (below minimum)"
            css_classes = _RED
        elif count >= word_limit * 0.9:
            text += " (approaching limit)"
            css_classes = _AMBER
    elif word_limit is not None:
        # Max only
        text += f" / {word_limit:,}"
        if count >= word_limit:
            text += " (over limit)"
            css_classes = _RED
        elif count >= word_limit * 0.9:
            text += " (approaching limit)"
            css_classes = _AMBER
    elif word_minimum is not None:
        # Min only
        text += f" / {word_minimum:,} minimum"
        if count < word_minimum:
            text += " (below minimum)"
            css_classes = _RED

    return BadgeState(text=text, css_classes=css_classes)
