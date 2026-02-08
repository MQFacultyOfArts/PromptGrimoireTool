"""Tab 2 (Organise) rendering for the annotation page.

Renders tag columns with highlight cards, grouped by tag. Each column has a
coloured header and contains cards for highlights assigned to that tag.
Highlights with no tag appear in a final "Untagged" column.

Cards are draggable within and between columns via SortableJS. Sort-end events
update the CRDT tag_order (reorder) or move highlights between tags (reassign)
and broadcast changes to all connected clients.

This module imports TagInfo but NOT BriefTag -- the tag-agnostic abstraction
ensures Tab 2 rendering is decoupled from the domain enum.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 2
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.3, AC2.4, AC2.6
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nicegui import ui

from promptgrimoire.elements.sortable import Sortable

if TYPE_CHECKING:
    from collections.abc import Callable

    from nicegui.events import GenericEventArguments

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation_tags import TagInfo

logger = logging.getLogger(__name__)

# Colour for the "Untagged" column header
_UNTAGGED_COLOUR = "#999999"

# Raw key for the untagged pseudo-tag (empty string in CRDT)
_UNTAGGED_RAW_KEY = ""

# Maximum characters to show in text snippet before truncation
_SNIPPET_MAX_CHARS = 100


def _build_highlight_card(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
) -> ui.card:
    """Render a single highlight card inside a tag column.

    The card's HTML id is set to ``hl-{highlight_id}`` so that SortableJS
    event handlers can identify which highlight was dragged.

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name.

    Returns:
        The created ui.card element.
    """
    highlight_id = highlight.get("id", "")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    snippet = full_text[:_SNIPPET_MAX_CHARS]
    if len(full_text) > _SNIPPET_MAX_CHARS:
        snippet += "..."
    comments: list[dict[str, Any]] = list(highlight.get("comments", []))

    card = (
        ui.card()
        .classes("w-full mb-2 cursor-grab")
        .style(f"border-left: 4px solid {tag_colour};")
        .props(
            f'data-testid="organise-card"'
            f' data-highlight-id="{highlight_id}"'
            f' id="hl-{highlight_id}"'
        )
    )
    with card:
        ui.label(display_tag_name).classes("text-xs font-bold").style(
            f"color: {tag_colour};"
        )
        ui.label(f"by {author}").classes("text-xs text-gray-500")
        if snippet:
            ui.label(f'"{snippet}"').classes("text-sm italic mt-1")
        if comments:
            ui.separator().classes("my-1")
            for comment in comments:
                comment_author = comment.get("author", "Unknown")
                comment_text = comment.get("text", "")
                with ui.row().classes("w-full gap-1 items-start"):
                    ui.label(f"{comment_author}:").classes(
                        "text-xs font-semibold text-gray-600 flex-shrink-0"
                    )
                    ui.label(comment_text).classes("text-xs text-gray-700")

    return card


def _build_tag_column(
    tag_name: str,
    tag_colour: str,
    raw_key: str,
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
    on_sort_end: Callable[[GenericEventArguments], Any] | None,
) -> ui.column:
    """Render a single tag column with header and highlight cards.

    Cards are ordered by tag_order first, with any unordered highlights
    appended at the bottom. If on_sort_end is provided, cards are wrapped
    in a SortableJS container enabling drag reorder and cross-column moves.

    Args:
        tag_name: Display name for column header.
        tag_colour: Hex colour for header background and card borders.
        raw_key: Raw tag key for CRDT operations.
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tag_order.
        on_sort_end: Callback for sort-end events (None to disable drag).

    Returns:
        The created ui.column element.
    """
    column = (
        ui.column()
        .classes("min-w-64 max-w-80 flex-shrink-0 self-stretch")
        .props(f'data-testid="tag-column" data-tag-name="{tag_name}"')
    )

    with column:
        # Coloured header
        ui.label(tag_name).classes(
            "text-white font-bold text-sm px-3 py-1 rounded-t w-full text-center"
        ).style(f"background-color: {tag_colour};")

        # Build ID-to-highlight lookup
        hl_by_id = {h.get("id", ""): h for h in highlights}

        # Create Sortable container for cards
        sortable = Sortable(
            options={
                "group": "organise-highlights",
                "animation": 150,
                "filter": ".sortable-ignore",
            },
            on_end=on_sort_end,
        )
        # Set HTML id so event handler can identify the tag
        sortable_id = f"sort-{raw_key}" if raw_key else "sort-untagged"
        sortable.props(f'id="{sortable_id}"')
        sortable.classes("w-full flex-grow min-h-24 pb-4")

        with sortable:
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

            # Empty state hint (inside sortable so column is a valid drop target)
            if not highlights:
                ui.label("No highlights").classes(
                    "text-xs text-gray-400 italic p-2 sortable-ignore"
                )

    return column


def render_organise_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    *,
    on_sort_end: (Callable[[GenericEventArguments], Any] | None) = None,
) -> None:
    """Populate the Organise tab panel with tag columns and highlight cards.

    Clears the placeholder content from the panel, then creates a
    horizontally scrollable row of tag columns. Each column shows
    highlights grouped by tag. An "Untagged" column is appended if
    any highlights have no tag.

    When on_sort_end is provided, cards are wrapped in SortableJS
    containers enabling drag reorder and cross-column moves.

    Args:
        panel: The ui.tab_panel element to populate.
        tags: List of TagInfo instances.
        crdt_doc: The CRDT annotation document.
        on_sort_end: Callback for SortableJS sort-end events.
    """
    panel.clear()

    all_highlights = crdt_doc.get_all_highlights()

    # Build raw tag value -> TagInfo lookup
    tag_raw_values: dict[str, TagInfo] = {tag.raw_key: tag for tag in tags}

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
            .classes("w-full overflow-x-auto gap-4 p-4 flex-nowrap items-stretch")
            .props('data-testid="organise-columns"')
        ),
    ):
        for tag_info in tags:
            highlights_for_tag = tagged_highlights[tag_info.name]
            ordered_ids = crdt_doc.get_tag_order(tag_info.raw_key)
            _build_tag_column(
                tag_info.name,
                tag_info.colour,
                tag_info.raw_key,
                highlights_for_tag,
                ordered_ids,
                on_sort_end,
            )

        # Untagged column (AC2.6)
        if untagged_highlights:
            ordered_ids = crdt_doc.get_tag_order(_UNTAGGED_RAW_KEY)
            _build_tag_column(
                "Untagged",
                _UNTAGGED_COLOUR,
                _UNTAGGED_RAW_KEY,
                untagged_highlights,
                ordered_ids,
                on_sort_end,
            )
