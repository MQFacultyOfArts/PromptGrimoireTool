"""Server-side highlight insertion into HTML.

Inserts <mark> tags into HTML based on character offsets in the text content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class HighlightSpec:
    """Specification for a highlight to insert."""

    id: str
    start: int
    end: int
    color: str
    tag: str


def insert_highlights(html: str, highlights: list[HighlightSpec]) -> str:
    """Insert highlight marks into HTML at the specified text positions.

    Walks the HTML, tracking character positions in the visible text content,
    and inserts <mark> tags at the positions corresponding to each highlight.

    Args:
        html: The HTML content.
        highlights: List of highlights with character offsets (in text content).

    Returns:
        HTML with <mark> tags inserted at the correct positions.
    """
    if not highlights:
        return html

    # Build a mapping from text position to HTML position
    # text_pos_to_html[i] = position in HTML where text character i appears
    text_pos_to_html: list[int] = []

    i = 0
    text_pos = 0
    while i < len(html):
        if html[i] == "<":
            # Skip HTML tag
            end = html.find(">", i)
            if end == -1:
                break
            i = end + 1
        elif html[i] == "&":
            # Handle HTML entities (e.g., &nbsp;, &amp;)
            match = re.match(r"&[a-zA-Z]+;|&#\d+;|&#x[0-9a-fA-F]+;", html[i:])
            if match:
                # Entity represents one text character
                text_pos_to_html.append(i)
                text_pos += 1
                i += len(match.group())
            else:
                # Bare & - treat as text
                text_pos_to_html.append(i)
                text_pos += 1
                i += 1
        else:
            # Regular text character
            text_pos_to_html.append(i)
            text_pos += 1
            i += 1

    # Add end position for convenience
    text_pos_to_html.append(len(html))

    # Sort highlights by start position descending (insert from end to start)
    sorted_highlights = sorted(highlights, key=lambda h: h.start, reverse=True)

    result = html
    for h in sorted_highlights:
        # Get HTML positions
        if h.start >= len(text_pos_to_html) or h.end > len(text_pos_to_html):
            continue

        start_html = text_pos_to_html[h.start]
        end_html = text_pos_to_html[h.end]

        # Create mark tags
        mark_open = (
            f'<mark class="case-highlight" '
            f'data-highlight-id="{h.id}" '
            f'data-tag="{h.tag}" '
            f'style="background-color: {h.color}40; '
            f'border-bottom: 2px solid {h.color}; cursor: pointer;">'
        )
        mark_close = "</mark>"

        # Insert closing tag first (at end), then opening tag (at start)
        result = result[:end_html] + mark_close + result[end_html:]
        result = result[:start_html] + mark_open + result[start_html:]

    return result
