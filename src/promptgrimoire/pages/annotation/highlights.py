"""Highlight CRUD, JSON serialisation, and push-to-client for annotation page.

Functions for creating, deleting, and syncing highlights between
CRDT state and the browser's CSS Custom Highlight API.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nicegui import ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation import (
    PageState,
    _RawJS,
    _render_js,
    _workspace_presence,
)
from promptgrimoire.pages.annotation.css import _build_highlight_pseudo_css

if TYPE_CHECKING:
    from promptgrimoire.models.case import BriefTag

logger = logging.getLogger(__name__)


async def _warp_to_highlight(state: PageState, start_char: int, end_char: int) -> None:
    """Switch to the Annotate tab and scroll to a highlight range.

    This is the cross-tab navigation entry point: Tab 2 (Organise) and Tab 3
    (Respond) "locate" buttons call this to warp the user back to Tab 1 and
    scroll the highlighted text into view with a brief gold flash.

    Per-client only -- ``set_value()`` affects only the calling client's tab
    state, not other connected users (AC5.4).

    Args:
        state: Page state with tab_panels and annotations.
        start_char: First character index of the highlight range.
        end_char: Last character index (exclusive) of the highlight range.
    """
    # 1. Switch tab to Annotate
    if state.tab_panels is not None:
        state.tab_panels.set_value("Annotate")
    state.active_tab = "Annotate"

    # 2. Refresh Tab 1 annotations and highlight CSS.
    # _update_highlight_css() pushes highlight ranges to the client internally,
    # so no separate _push_highlights_to_client() call is needed.
    if state.refresh_annotations:
        state.refresh_annotations()
    _update_highlight_css(state)

    # 4. Scroll to highlight and throb it. Refreshes _textNodes inline
    #    to guarantee fresh DOM references after tab switch + re-render.
    #    After scrolling, explicitly trigger positionCards via rAF to ensure
    #    annotation sidebar cards become visible (MutationObserver fires
    #    before the scroll, hiding cards that aren't yet in viewport).
    js = _render_js(
        t"(function(){{"
        t"  var c = document.getElementById('doc-container');"
        t"  if (!c) return;"
        t"  window._textNodes = walkTextNodes(c);"
        t"  scrollToCharOffset(window._textNodes, {start_char}, {end_char});"
        t"  throbHighlight(window._textNodes, {start_char}, {end_char}, 800);"
        t"  if (window._positionCards) requestAnimationFrame(window._positionCards);"
        t"}})()"
    )
    ui.run_javascript(js)


def _build_highlight_json(state: PageState) -> str:
    """Build JSON highlight data from CRDT state for ``applyHighlights()``.

    Groups highlights by tag into the format expected by the JS function:
    ``{tag: [{start_char, end_char, id}, ...], ...}``

    Returns:
        JSON string ready for injection into ``applyHighlights()`` call.
    """
    if state.crdt_doc is None:
        return "{}"

    if state.document_id is not None:
        highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))
    else:
        highlights = state.crdt_doc.get_all_highlights()

    # Group by tag
    by_tag: dict[str, list[dict[str, Any]]] = {}
    for hl in highlights:
        tag = hl.get("tag", "highlight")
        entry = {
            "start_char": hl.get("start_char", 0),
            "end_char": hl.get("end_char", 0),
            "id": hl.get("id", ""),
        }
        by_tag.setdefault(tag, []).append(entry)

    return json.dumps(by_tag)


def _push_highlights_to_client(state: PageState) -> None:
    """Push current highlight state to the client via ``applyHighlights()``.

    Rebuilds the highlight JSON from CRDT and calls the JS function to
    re-register all ``CSS.highlights`` entries. Called after any highlight
    mutation (add, delete, tag change) and on tab switch back to Annotate.

    Looks up the NiceGUI client from ``_workspace_presence`` to use
    ``client.run_javascript()`` -- this avoids slot-stack errors when called
    from background contexts (CRDT sync callbacks).
    """
    highlight_json = _RawJS(_build_highlight_json(state))
    js = _render_js(
        t"(function() {{"
        t"  const c = document.getElementById('doc-container');"
        t"  if (c) applyHighlights(c, {highlight_json});"
        t"}})()"
    )
    # Look up the NiceGUI client from the connected clients registry.
    # Using client.run_javascript() is safe in background contexts (CRDT
    # sync callbacks) where ui.run_javascript() would crash with a
    # slot-stack RuntimeError.
    workspace_key = str(state.workspace_id)
    client_state = _workspace_presence.get(workspace_key, {}).get(state.client_id)
    if client_state and client_state.nicegui_client:
        client_state.nicegui_client.run_javascript(js)
    else:
        logger.warning(
            "PUSH_HIGHLIGHTS: no client ref for client_id=%s -- skipping JS push",
            state.client_id[:8] if state.client_id else "?",
        )


def _update_highlight_css(state: PageState) -> None:
    """Update highlight CSS and push highlight ranges to the client.

    With the CSS Custom Highlight API, the ``::highlight()`` pseudo-element
    rules are static (one rule per tag). The actual highlight ranges are
    registered in ``CSS.highlights`` by JS ``applyHighlights()``. This
    function ensures both the CSS and the JS highlight state are current.
    """
    if state.highlight_style is None or state.crdt_doc is None:
        return

    # CSS is invariant (fixed TAG_COLORS palette) but cheap to regenerate.
    # Re-setting it here keeps this function as a single "sync everything"
    # call site, which is simpler than caching the string.
    css = _build_highlight_pseudo_css()
    state.highlight_style._props["innerHTML"] = css
    state.highlight_style.update()

    # Push updated highlight ranges to the client
    _push_highlights_to_client(state)


async def _delete_highlight(
    state: PageState,
    highlight_id: str,
    card: ui.card,
) -> None:
    """Delete a highlight and its card."""
    if state.crdt_doc:
        state.crdt_doc.remove_highlight(highlight_id)
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )
        await pm.force_persist_workspace(state.workspace_id)
        if state.save_status:
            state.save_status.text = "Saved"
    card.delete()
    if state.annotation_cards and highlight_id in state.annotation_cards:
        del state.annotation_cards[highlight_id]
    _update_highlight_css(state)
    # Broadcast to other clients
    if state.broadcast_update:
        await state.broadcast_update()


async def _add_highlight(state: PageState, tag: BriefTag | None = None) -> None:
    """Add a highlight from current selection to CRDT.

    Args:
        state: Page state with selection and CRDT document.
        tag: Optional BriefTag for the highlight. Defaults to "highlight".
    """
    # Guard against duplicate calls (e.g., rapid keyboard events)
    if state.processing_highlight:
        logger.debug("[HIGHLIGHT] Already processing - ignoring duplicate")
        return
    state.processing_highlight = True

    logger.debug(
        "[HIGHLIGHT] called: start=%s, end=%s, tag=%s",
        state.selection_start,
        state.selection_end,
        tag,
    )
    if state.selection_start is None or state.selection_end is None:
        logger.debug("[HIGHLIGHT] No selection - returning early")
        state.processing_highlight = False
        ui.notify("No selection", type="warning")
        return

    if state.document_id is None:
        state.processing_highlight = False
        ui.notify("No document", type="warning")
        return

    if state.crdt_doc is None:
        state.processing_highlight = False
        ui.notify("CRDT not initialized", type="warning")
        return

    try:
        # Update status to show saving
        if state.save_status:
            state.save_status.text = "Saving..."

        # Add highlight to CRDT (end_char is exclusive).
        # The JS text walker's setupAnnotationSelection() already returns
        # exclusive end_char (per Range API semantics), so no +1 needed.
        start = min(state.selection_start, state.selection_end)
        end = max(state.selection_start, state.selection_end)

        # Use tag value if provided, otherwise default to "highlight"
        tag_value = tag.value if tag else "highlight"

        # Extract highlighted text from document characters
        highlighted_text = ""
        if state.document_chars:
            chars_slice = state.document_chars[start:end]
            highlighted_text = "".join(chars_slice)

        state.crdt_doc.add_highlight(
            start_char=start,
            end_char=end,
            tag=tag_value,
            text=highlighted_text,
            author=state.user_name,
            document_id=str(state.document_id),
            user_id=state.user_id,
        )

        # Schedule persistence
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )

        # Force immediate save for test observability
        await pm.force_persist_workspace(state.workspace_id)

        if state.save_status:
            state.save_status.text = "Saved"

        # Update CSS to show new highlight
        _update_highlight_css(state)

        # Refresh annotation cards to show new highlight
        if state.refresh_annotations:
            state.refresh_annotations()

        # Broadcast to other clients
        if state.broadcast_update:
            await state.broadcast_update()

        # Clear browser selection first to prevent re-triggering on next mouseup
        await ui.run_javascript("window.getSelection().removeAllRanges();")

        # Clear selection state and hide menu
        state.selection_start = None
        state.selection_end = None
        if state.highlight_menu:
            state.highlight_menu.set_visibility(False)
    finally:
        # Always release processing lock -- prevents permanent lockout if any
        # step above raises (e.g. JS relay failure, persistence error).
        state.processing_highlight = False
