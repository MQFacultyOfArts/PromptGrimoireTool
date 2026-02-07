"""Tab 2 (Organise) rendering for the annotation page.

Renders tag columns with highlight cards, grouped by tag. Each column has a
coloured header and contains cards for highlights assigned to that tag.
Highlights with no tag appear in a final "Untagged" column.

This module imports TagInfo but NOT BriefTag -- the tag-agnostic abstraction
ensures Tab 2 rendering is decoupled from the domain enum.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.6
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nicegui import ui

if TYPE_CHECKING:
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation_tags import TagInfo

logger = logging.getLogger(__name__)

# Colour for the "Untagged" column header
_UNTAGGED_COLOUR = "#999999"

# Maximum characters to show in text snippet before truncation
_SNIPPET_MAX_CHARS = 100


def _build_highlight_card(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
) -> None:
    """Render a single highlight card inside a tag column.

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name (e.g. "Jurisdiction" or "Untagged").
    """
    highlight_id = highlight.get("id", "")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    snippet = full_text[:_SNIPPET_MAX_CHARS]
    if len(full_text) > _SNIPPET_MAX_CHARS:
        snippet += "..."

    with (
        ui.card()
        .classes("w-full mb-2")
        .style(f"border-left: 4px solid {tag_colour};")
        .props(f'data-testid="organise-card" data-highlight-id="{highlight_id}"')
    ):
        # Tag name label
        ui.label(display_tag_name).classes("text-xs font-bold").style(
            f"color: {tag_colour};"
        )
        # Author
        ui.label(f"by {author}").classes("text-xs text-gray-500")
        # Text snippet
        if snippet:
            ui.label(f'"{snippet}"').classes("text-sm italic mt-1")


def _build_tag_column(
    tag_name: str,
    tag_colour: str,
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
) -> None:
    """Render a single tag column with header and highlight cards.

    Cards are ordered by tag_order first, with any unordered highlights
    appended at the bottom.

    Args:
        tag_name: Display name for column header.
        tag_colour: Hex colour for header background and card borders.
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tag_order.
    """
    with (
        ui.column()
        .classes("min-w-64 max-w-80 flex-shrink-0")
        .props(f'data-testid="tag-column" data-tag-name="{tag_name}"')
    ):
        # Coloured header
        ui.label(tag_name).classes(
            "text-white font-bold text-sm px-3 py-1 rounded-t w-full text-center"
        ).style(f"background-color: {tag_colour};")

        # Build ID-to-highlight lookup
        hl_by_id = {h.get("id", ""): h for h in highlights}

        # Render ordered highlights first
        rendered_ids: set[str] = set()
        for hid in ordered_ids:
            if hid in hl_by_id:
                _build_highlight_card(hl_by_id[hid], tag_colour, tag_name)
                rendered_ids.add(hid)

        # Append unordered highlights
        for hl in highlights:
            hid = hl.get("id", "")
            if hid not in rendered_ids:
                _build_highlight_card(hl, tag_colour, tag_name)

        # Empty state message
        if not highlights:
            ui.label("No highlights").classes("text-xs text-gray-400 italic p-2")


def render_organise_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
) -> None:
    """Populate the Organise tab panel with tag columns and highlight cards.

    Clears the placeholder content from the panel, then creates a horizontally
    scrollable row of tag columns. Each column shows highlights grouped by tag.
    An "Untagged" column is appended if any highlights have no tag.

    Args:
        panel: The ui.tab_panel element to populate.
        tags: List of TagInfo instances (from brief_tags_to_tag_info()).
        crdt_doc: The CRDT annotation document containing highlights and tag_order.
    """
    # Clear placeholder content
    panel.clear()

    all_highlights = crdt_doc.get_all_highlights()

    # Build tag-name -> tag value lookup (reverse of title-case transform)
    # TagInfo.name is title-cased display; highlight["tag"] is the raw enum value.
    # We need to match highlights by their raw tag value.
    tag_name_to_info: dict[str, TagInfo] = {}
    tag_raw_values: dict[str, TagInfo] = {}
    for tag_info in tags:
        # Reverse the title-case transform to get the raw enum value
        raw_value = tag_info.name.lower().replace(" ", "_")
        tag_raw_values[raw_value] = tag_info
        tag_name_to_info[tag_info.name] = tag_info

    # Group highlights by tag
    tagged_highlights: dict[str, list[dict[str, Any]]] = {
        tag_info.name: [] for tag_info in tags
    }
    untagged_highlights: list[dict[str, Any]] = []

    for hl in all_highlights:
        raw_tag = hl.get("tag", "")
        if raw_tag and raw_tag in tag_raw_values:
            display_name = tag_raw_values[raw_tag].name
            tagged_highlights[display_name].append(hl)
        else:
            untagged_highlights.append(hl)

    with (
        panel,
        (
            ui.row()
            .classes("w-full overflow-x-auto gap-4 p-4")
            .props('data-testid="organise-columns"')
        ),
    ):
        # Render one column per tag
        for tag_info in tags:
            highlights_for_tag = tagged_highlights[tag_info.name]
            # Get tag_order using raw enum value
            raw_value = tag_info.name.lower().replace(" ", "_")
            ordered_ids = crdt_doc.get_tag_order(raw_value)
            _build_tag_column(
                tag_info.name,
                tag_info.colour,
                highlights_for_tag,
                ordered_ids,
            )

        # Untagged column (AC2.6) -- only if there are untagged highlights
        if untagged_highlights:
            ordered_ids = crdt_doc.get_tag_order("")
            _build_tag_column(
                "Untagged",
                _UNTAGGED_COLOUR,
                untagged_highlights,
                ordered_ids,
            )
