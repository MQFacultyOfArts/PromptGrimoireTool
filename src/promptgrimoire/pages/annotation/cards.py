"""Annotation card UI for the annotation page.

Builds and refreshes the annotation sidebar cards that display
highlight metadata, comments, and action buttons.
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation import PageState, _render_js
from promptgrimoire.pages.annotation.highlights import (
    _delete_highlight,
    _update_highlight_css,
)

logger = logging.getLogger(__name__)


def _build_expandable_text(full_text: str) -> None:
    """Build expandable text preview for annotation card.

    Args:
        full_text: The full highlighted text.
    """
    is_long = len(full_text) > 80
    if is_long:
        truncated_text = full_text[:80] + "..."
        with ui.element("div").classes("mt-1"):
            # Truncated view with expand icon
            with ui.row().classes("items-start gap-1 cursor-pointer") as truncated_row:
                ui.icon("expand_more", size="xs").classes("text-gray-400")
                ui.label(f'"{truncated_text}"').classes("text-sm italic")

            # Full view with collapse icon
            with ui.row().classes("items-start gap-1 cursor-pointer") as full_row:
                ui.icon("expand_less", size="xs").classes("text-gray-400")
                ui.label(f'"{full_text}"').classes("text-sm italic")
            full_row.set_visibility(False)

            def toggle_expand(
                tr: ui.row = truncated_row, fr: ui.row = full_row
            ) -> None:
                if tr.visible:
                    tr.set_visibility(False)
                    fr.set_visibility(True)
                else:
                    tr.set_visibility(True)
                    fr.set_visibility(False)

            truncated_row.on("click", toggle_expand)
            full_row.on("click", toggle_expand)
    else:
        ui.label(f'"{full_text}"').classes("text-sm italic mt-1")


def _build_comments_section(
    state: PageState,
    highlight_id: str,
    comments: list[dict[str, Any]],
) -> None:
    """Build comments display and input for an annotation card.

    Args:
        state: Page state with CRDT and persistence info.
        highlight_id: ID of the highlight to add comments to.
        comments: Existing comments list from highlight.
    """
    # Display existing comments
    if comments:
        ui.separator()
        for comment in comments:
            c_author = comment.get("author", "Unknown")
            c_text = comment.get("text", "")
            with ui.element("div").classes("bg-gray-100 p-2 rounded mt-1"):
                ui.label(c_author).classes("text-xs font-bold")
                ui.label(c_text).classes("text-sm")

    # Comment input
    comment_input = (
        ui.input(placeholder="Add comment...").props("dense").classes("w-full mt-2")
    )

    async def add_comment(
        hid: str = highlight_id,
        inp: ui.input = comment_input,
    ) -> None:
        if inp.value and inp.value.strip() and state.crdt_doc:
            state.crdt_doc.add_comment(hid, state.user_name, inp.value.strip())
            inp.value = ""

            # Persist
            pm = get_persistence_manager()
            pm.mark_dirty_workspace(
                state.workspace_id,
                state.crdt_doc.doc_id,
                last_editor=state.user_name,
            )
            await pm.force_persist_workspace(state.workspace_id)

            if state.save_status:
                state.save_status.text = "Saved"

            # Refresh cards to show new comment
            if state.refresh_annotations:
                state.refresh_annotations()

            # Broadcast to other clients
            if state.broadcast_update:
                await state.broadcast_update()

    ui.button("Post", on_click=add_comment).props("dense size=sm").classes("mt-1")


def _build_annotation_card(
    state: PageState,
    highlight: dict[str, Any],
) -> ui.card:
    """Build an annotation card for a highlight.

    Args:
        state: Page state with CRDT and containers.
        highlight: Highlight dict from CRDT.

    Returns:
        The created card element.
    """
    highlight_id = highlight.get("id", "")
    tag_str = highlight.get("tag", "highlight")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")

    # Get char positions for scroll-sync positioning
    start_char = highlight.get("start_char", 0)
    end_char = highlight.get("end_char", start_char)

    # Get para_ref if stored
    para_ref = highlight.get("para_ref", "")

    # Get tag color from workspace tag info
    tag_colours = state.tag_colours()
    color = tag_colours.get(tag_str, "#999999")

    # Use ann-card-positioned for scroll-sync positioning
    card = (
        ui.card()
        .classes("ann-card-positioned")
        .style(f"border-left: 4px solid {color};")
        .props(
            f'data-testid="annotation-card" data-highlight-id="{highlight_id}" '
            f'data-start-char="{start_char}" data-end-char="{end_char}"'
        )
    )

    with card:
        # Header with tag dropdown and action buttons
        with ui.row().classes("w-full justify-between items-center"):
            # Tag dropdown for changing tag type
            tag_options = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}

            async def on_tag_change(
                e: Any,
                hid: str = highlight_id,
                crd: ui.card = card,
            ) -> None:
                new_tag = e.value
                if state.crdt_doc and new_tag != tag_str:
                    state.crdt_doc.update_highlight_tag(hid, new_tag)
                    pm = get_persistence_manager()
                    pm.mark_dirty_workspace(
                        state.workspace_id,
                        state.crdt_doc.doc_id,
                        last_editor=state.user_name,
                    )
                    await pm.force_persist_workspace(state.workspace_id)
                    if state.save_status:
                        state.save_status.text = "Saved"
                    _update_highlight_css(state)
                    # Update card border color
                    new_color = state.tag_colours().get(new_tag, "#999999")
                    crd.style(f"border-left: 4px solid {new_color};")
                    if state.broadcast_update:
                        await state.broadcast_update()

            ui.select(
                tag_options,
                value=tag_str,
                on_change=on_tag_change,
            ).props("dense borderless").classes("text-sm font-bold").style(
                f"color: {color}; min-width: 120px;"
            )

            with ui.row().classes("gap-1"):
                # Go-to-highlight button - scrolls to highlight and throbs it
                async def goto_highlight(
                    sc: int = start_char, ec: int = end_char
                ) -> None:
                    js = _render_js(
                        t"scrollToCharOffset(window._textNodes, {sc}, {ec});"
                        t"throbHighlight(window._textNodes, {sc}, {ec}, 800);"
                    )
                    await ui.run_javascript(js)

                ui.button(icon="my_location", on_click=goto_highlight).props(
                    "flat dense size=xs"
                ).tooltip("Go to highlight")

                # Delete button - uses extracted _delete_highlight function
                async def do_delete(hid: str = highlight_id, c: ui.card = card) -> None:
                    await _delete_highlight(state, hid, c)

                ui.button(icon="close", on_click=do_delete).props(
                    "flat dense size=xs"
                ).tooltip("Delete highlight")

        # Author and para_ref on same line
        with ui.row().classes("gap-2 items-center"):
            ui.label(f"by {author}").classes("text-xs text-gray-500")
            if para_ref:
                ui.label(para_ref).classes("text-xs font-mono text-gray-400")

        # Highlighted text preview - expandable if long
        if full_text:
            _build_expandable_text(full_text)

        # Comments section (extracted to reduce statement count)
        _build_comments_section(state, highlight_id, highlight.get("comments", []))

    return card


def _refresh_annotation_cards(state: PageState) -> None:
    """Refresh all annotation cards from CRDT state."""
    logger.debug(
        "[CARDS] _refresh called: container=%s, crdt_doc=%s",
        state.annotations_container is not None,
        state.crdt_doc is not None,
    )
    if state.annotations_container is None or state.crdt_doc is None:
        return

    if state.annotation_cards is None:
        state.annotation_cards = {}

    # Clear existing cards
    state.annotations_container.clear()

    # Get highlights for this document
    if state.document_id is not None:
        highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))
    else:
        highlights = state.crdt_doc.get_all_highlights()

    logger.debug(
        "[CARDS] Found %d highlights for doc_id=%s", len(highlights), state.document_id
    )

    # Create cards for each highlight
    with state.annotations_container:
        for hl in highlights:
            hl_id = hl.get("id", "")
            logger.debug("[CARDS] Creating card for highlight %s", hl_id[:8])
            card = _build_annotation_card(state, hl)
            state.annotation_cards[hl_id] = card
