"""Tab 2 (Organise) rendering for the annotation page.

Renders tag columns with highlight cards, grouped by tag. Each column has a
coloured header and contains cards for highlights assigned to that tag.
Highlights with no tag appear in a final "Untagged" column.

Cards are draggable within and between columns via SortableJS. Sort-end events
update the CRDT tags Map highlights (reorder) or move highlights between tags (reassign)
and broadcast changes to all connected clients.

This module imports TagInfo -- the tag-agnostic abstraction ensures Tab 2
rendering is decoupled from any specific tag definition.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_03.md Task 2
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_04.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.3, AC2.4, AC2.6
"""

from __future__ import annotations

import html as _html
import time
from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

from promptgrimoire.elements.sortable import Sortable
from promptgrimoire.pages.annotation.card_shared import (
    anonymise_display_author,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from nicegui.events import GenericEventArguments

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tags import TagInfo

logger = structlog.get_logger()
# Colour for the "Untagged" column header
_UNTAGGED_COLOUR = "#999999"

# Raw key for the untagged pseudo-tag (empty string in CRDT)
_UNTAGGED_RAW_KEY = ""


def _render_organise_card_html(
    *,
    tag_display: str,
    color: str,
    display_author: str,
    text: str,
    comments: list[tuple[str, str]],
) -> str:
    """Render the body of an organise card as an HTML string.

    Returns an HTML fragment for use with ``ui.html(sanitize=False)``.
    All interpolated string values are escaped via ``html.escape()``
    (defence-in-depth).

    SortableJS contract attributes (``id``, ``data-highlight-id``,
    ``data-testid``) are set on the NiceGUI wrapper element by the
    caller, not in this HTML body.

    Args:
        tag_display: Human-readable tag name.
        color: Hex colour for tag label.
        display_author: Pre-anonymised author display name.
        text: Highlighted text content.
        comments: List of (display_author, text) tuples, pre-anonymised.
    """
    esc = _html.escape
    parts: list[str] = [
        # Tag label
        f'<div style="display:flex;align-items:center;gap:4px;">'
        f'<span style="font-weight:bold;color:{esc(color)};max-width:100px;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        f"{esc(tag_display)}</span>"
        f"</div>",
        # Author
        f'<div style="font-size:0.85em;color:#666;">by {esc(display_author)}</div>',
    ]

    # Text preview with CSS overflow
    if text:
        parts.append(
            f'<div style="font-size:0.85em;white-space:pre-wrap;'
            f'max-height:4.5em;overflow:hidden;">'
            f"{esc(text)}</div>"
        )

    # Comments
    for c_author, c_text in comments:
        if not c_text:
            continue
        parts.append(
            f'<div style="border-left:2px solid #e0e0e0;padding-left:8px;'
            f'margin-top:4px;">'
            f'<span style="font-size:0.75em;color:#666;font-weight:500;">'
            f"{esc(c_author)}:</span> "
            f'<span style="font-size:0.75em;color:#555;">'
            f"{esc(c_text)}</span></div>"
        )

    return "".join(parts)


def _build_highlight_card_html(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
    state: PageState,
    on_locate: Callable[..., Any] | None = None,
) -> ui.element:
    """Render an organise card as ``ui.html()`` plus NiceGUI locate button.

    Replaces ``_build_highlight_card()`` — collapses 8-10 NiceGUI elements
    per card into 2-3 (wrapper div + html + optional locate button).

    The wrapper div carries SortableJS contract attributes:
    ``id="hl-{highlight_id}"``, ``data-highlight-id``, ``data-testid``.

    Returns the wrapper element (needed by ``_render_ordered_cards``).
    """
    highlight_id = highlight.get("id", "")
    raw_author = highlight.get("author", "Unknown")
    hl_user_id = highlight.get("user_id")
    start_char: int = int(highlight.get("start_char", 0))
    end_char: int = int(highlight.get("end_char", 0))
    full_text = highlight.get("text", "")
    comments_raw: list[dict[str, Any]] = list(highlight.get("comments", []))

    display_author = anonymise_display_author(raw_author, hl_user_id, state)

    # Pre-anonymise comment authors
    comments: list[tuple[str, str]] = []
    for comment in comments_raw:
        c_text = comment.get("text", "")
        if not c_text:
            continue
        raw_c_author = comment.get("author", "Unknown")
        c_uid = comment.get("user_id")
        display_c_author = anonymise_display_author(raw_c_author, c_uid, state)
        comments.append((display_c_author, c_text))

    html_str = _render_organise_card_html(
        tag_display=display_tag_name,
        color=tag_colour,
        display_author=display_author,
        text=full_text,
        comments=comments,
    )

    wrapper = (
        ui.element("div")
        .classes("w-full mb-2 cursor-grab")
        .style(f"border-left: 4px solid {tag_colour}; padding: 8px;")
        .props(
            f'data-testid="organise-card"'
            f' data-highlight-id="{highlight_id}"'
            f' id="hl-{highlight_id}"'
        )
    )
    with wrapper:
        ui.html(html_str, sanitize=False)
        if on_locate is not None:
            hl_doc_id = highlight.get("document_id")

            async def _do_locate(
                sc: int = start_char,
                ec: int = end_char,
                did: str | None = hl_doc_id,
            ) -> None:
                await on_locate(sc, ec, did)

            ui.button(icon="my_location", on_click=_do_locate).props(
                "flat dense size=xs"
            ).tooltip("Locate in document").classes("sortable-ignore")

    return wrapper


def _render_ordered_cards(
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
    tag_colour: str,
    tag_name: str,
    state: PageState,
    on_locate: Callable[..., Any] | None,
) -> None:
    """Render highlight cards respecting tag highlights order, then unordered remainder.

    Ordered highlights are rendered first (in tags Map sequence), followed
    by any highlights not yet in the order list. Shows an empty-state hint
    when the column has no highlights at all.

    Args:
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tags Map.
        tag_colour: Hex colour for card left borders.
        tag_name: Display name for card tag label.
        state: Page state for anonymisation context.
        on_locate: Optional locate callback for Tab 1 warp.
    """
    hl_by_id = {h.get("id", ""): h for h in highlights}
    rendered_ids: set[str] = set()

    for hid in ordered_ids:
        if hid in hl_by_id:
            _build_highlight_card_html(
                hl_by_id[hid], tag_colour, tag_name, state, on_locate
            )
            rendered_ids.add(hid)

    for hl in highlights:
        hid = hl.get("id", "")
        if hid not in rendered_ids:
            _build_highlight_card_html(hl, tag_colour, tag_name, state, on_locate)

    if not highlights:
        ui.label("No highlights").classes(
            "text-xs text-gray-400 italic p-2 sortable-ignore"
        )


def _build_tag_column(
    tag_name: str,
    tag_colour: str,
    raw_key: str,
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
    on_sort_end: Callable[[GenericEventArguments], Any] | None,
    state: PageState,
    on_locate: Callable[..., Any] | None = None,
) -> ui.column:
    """Render a single tag column with header and highlight cards.

    Cards are ordered by tags Map highlights first, with any unordered highlights
    appended at the bottom. If on_sort_end is provided, cards are wrapped
    in a SortableJS container enabling drag reorder and cross-column moves.

    Args:
        tag_name: Display name for column header.
        tag_colour: Hex colour for header background and card borders.
        raw_key: Raw tag key for CRDT operations.
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tags Map.
        on_sort_end: Callback for sort-end events (None to disable drag).
        state: Page state for anonymisation context.
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.

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
            _render_ordered_cards(
                highlights, ordered_ids, tag_colour, tag_name, state, on_locate
            )

    return column


def render_organise_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    *,
    on_sort_end: (Callable[[GenericEventArguments], Any] | None) = None,
    on_locate: Callable[..., Any] | None = None,
    state: PageState,
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
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.
        state: Page state for anonymisation context.
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

    _t0 = time.monotonic()
    card_count = 0

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
            ordered_ids = crdt_doc.get_tag_highlights(tag_info.raw_key)
            _build_tag_column(
                tag_info.name,
                tag_info.colour,
                tag_info.raw_key,
                highlights_for_tag,
                ordered_ids,
                on_sort_end,
                state,
                on_locate,
            )
            card_count += len(highlights_for_tag)

        # Untagged column (AC2.6)
        if untagged_highlights:
            ordered_ids = crdt_doc.get_tag_highlights(_UNTAGGED_RAW_KEY)
            _build_tag_column(
                "Untagged",
                _UNTAGGED_COLOUR,
                _UNTAGGED_RAW_KEY,
                untagged_highlights,
                ordered_ids,
                on_sort_end,
                state,
                on_locate,
            )
            card_count += len(untagged_highlights)

    logger.info(
        "organise_card_build",
        elapsed_ms=round((time.monotonic() - _t0) * 1000, 1),
        card_count=card_count,
    )

    # Scroll restoration is handled by callers that can await
    # (see _rebuild_organise_with_scroll in workspace.py).
