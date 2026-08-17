"""Highlight CRUD, JSON serialisation, and push-to-client for annotation page.

Functions for creating, deleting, and syncing highlights between
CRDT state and the browser's CSS Custom Highlight API.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import structlog
from nicegui import ui

from promptgrimoire.annotation_core import group_highlights_by_tag
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.input_pipeline.paragraph_map import lookup_para_ref
from promptgrimoire.pages.annotation import (
    PageState,
    _RawJS,
    _render_js,
    _workspace_presence,
)
from promptgrimoire.pages.annotation.css import _build_highlight_pseudo_css

logger = structlog.get_logger()

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _resolve_warp_target_doc_id(
    document_id: str | None,
    document_tabs: Mapping[UUID, Any],
) -> str:
    """Resolve which document tab id a highlight-warp should land on.

    Prefers ``document_id`` when it names a syntactically valid UUID that
    is a key of ``document_tabs``; otherwise falls back to the first
    available tab. Caller guarantees ``document_tabs`` is non-empty.
    """
    if document_id:
        doc_uuid = UUID(document_id) if _UUID_RE.match(document_id) else None
        if doc_uuid is not None and doc_uuid in document_tabs:
            return document_id
    return str(next(iter(document_tabs)))


async def _warp_to_highlight(
    state: PageState,
    start_char: int,
    end_char: int,
    document_id: str | None = None,
) -> None:
    """Switch to the correct source tab and scroll to a highlight range.

    Stores the scroll target on ``state._pending_scroll`` and calls
    ``set_value`` to trigger the tab change handler.  The handler
    (``_handle_source_tab_switch``) executes the scroll after
    render/refresh completes — this avoids duplicating tab-switch logic
    and works for both rendered and unrendered (deferred) tabs.

    If the target tab is already active, executes the scroll directly.
    """
    # Resolve target document tab
    target_doc_id: str | None = None
    if state.tab_panels is not None and state.document_tabs:
        target_doc_id = _resolve_warp_target_doc_id(document_id, state.document_tabs)

    # Store pending scroll for the tab change handler to execute.
    state._pending_scroll = (start_char, end_char)

    if target_doc_id is not None and state.tab_panels is not None:
        if target_doc_id == state.active_tab:
            # Already on the right tab — execute scroll directly.
            _execute_pending_scroll(state)
        else:
            # Different tab — set_value triggers async _on_tab_change
            # which does save/restore/render/refresh, then executes
            # the pending scroll.
            state.tab_panels.set_value(target_doc_id)


def _execute_pending_scroll(state: PageState) -> None:
    """Execute and clear the pending scroll target.

    Called by ``_handle_source_tab_switch`` after render/refresh,
    or directly by ``_warp_to_highlight`` when already on the target tab.
    """
    scroll = state._pending_scroll
    if scroll is None:
        return
    state._pending_scroll = None
    start_char, end_char = scroll

    # Refresh before scrolling
    if state.refresh_annotations:
        state.refresh_annotations(trigger="highlight_add")
    _update_highlight_css(state)

    js = _render_js(
        t"(function(){{"
        t"  var c = document.getElementById({state.doc_container_id});"
        t"  if (!c) return;"
        t"  window._textNodes = walkTextNodes(c);"
        t"  scrollToCharOffset(window._textNodes, {start_char}, {end_char});"
        t"  throbHighlight(window._textNodes, {start_char}, {end_char}, 800);"
        t"  if (window._positionCards)"
        t"    requestAnimationFrame(window._positionCards);"
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

    return json.dumps(group_highlights_by_tag(highlights))


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
        t"  const c = document.getElementById({state.doc_container_id});"
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
    css = _build_highlight_pseudo_css(state.tag_colours())
    state.highlight_style._props["innerHTML"] = css
    state.highlight_style.update()
    _push_highlights_to_client(state)


async def _delete_highlight(
    state: PageState,
    highlight_id: str,
    card: ui.card,
) -> None:
    """Delete a highlight and clean up its NiceGUI card element.

    Legacy function retained for the slot deletion race guard test
    (test_slot_deletion_race_369.py). Production highlight deletion
    is handled by the Vue sidebar's on_delete_highlight handler in
    document.py.
    """
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
    # Guard: the card may have already been deleted (e.g. by a
    # concurrent container rebuild). Calling card.delete() on an
    # already-deleted element raises ValueError at element.py:504.
    # See postmortems/2026-03-20-slot-deletion-investigation-369.md
    if not card.is_deleted:
        card.delete()
    _update_highlight_css(state)
    if state.broadcast_update:
        await state.broadcast_update()


def _parse_selection_payload(
    selection: Mapping[str, Any] | None,
) -> tuple[int, int] | None:
    """Normalise an event-carried selection payload to ``(start, end)``.

    The payload comes from the browser (``window._annotSel`` captured by
    a ``js_handler`` at trigger time), so validate strictly: both offsets
    must be ints and the selection must be non-empty.  Returns ``None``
    for anything invalid.
    """
    if not isinstance(selection, Mapping):
        return None
    start = selection.get("start_char")
    end = selection.get("end_char")
    if not isinstance(start, int) or not isinstance(end, int) or start == end:
        return None
    return min(start, end), max(start, end)


def _validate_highlight_state(
    state: PageState, selection: tuple[int, int] | None
) -> str | None:
    """Check preconditions for adding a highlight.

    Returns an error message if invalid, or None if ready to proceed.
    """
    if selection is None:
        logger.debug("[HIGHLIGHT] No selection - returning early")
        return "No selection"
    if state.document_id is None:
        return "No document"
    if state.crdt_doc is None:
        return "CRDT not initialized"
    return None


async def _add_highlight(
    state: PageState, tag: str, selection: Mapping[str, Any] | None
) -> None:
    """Add a highlight to CRDT from the selection carried by the event.

    The offsets ride the triggering event itself (captured client-side
    at click/keydown time) rather than being read from
    ``state.selection_*``, because python-socketio dispatches events as
    concurrent tasks and the apply can be processed before its
    ``selection_made`` arrives (#502).

    Args:
        state: Page state with CRDT document.
        tag: Tag key string (UUID) for the highlight.
        selection: ``{start_char, end_char}`` payload from the
            triggering event, or ``None`` when the browser had no
            selection.
    """
    # Guard against duplicate calls (e.g., rapid keyboard events)
    if state.processing_highlight:
        logger.debug("[HIGHLIGHT] Already processing - ignoring duplicate")
        return
    state.processing_highlight = True

    parsed = _parse_selection_payload(selection)
    logger.debug(
        "[HIGHLIGHT] called: selection=%s, tag=%s",
        parsed,
        tag,
    )
    error = _validate_highlight_state(state, parsed)
    if error:
        state.processing_highlight = False
        ui.notify(error, type="warning")
        return

    # Type narrowing — _validate_highlight_state guarantees these are not None
    assert parsed is not None  # noqa: S101
    assert state.crdt_doc is not None  # noqa: S101
    start, end = parsed

    _t_pipeline = time.monotonic()
    try:
        # Update status to show saving
        if state.save_status:
            state.save_status.text = "Saving..."

        # end_char is exclusive: the JS text walker's
        # setupAnnotationSelection() returns exclusive end_char (per
        # Range API semantics), so no +1 needed.

        # Extract highlighted text from document characters
        highlighted_text = ""
        if state.document_chars:
            chars_slice = state.document_chars[start:end]
            highlighted_text = "".join(chars_slice)

        # Compute paragraph reference from the document's paragraph map
        para_ref = lookup_para_ref(state.paragraph_map, start, end)

        state.crdt_doc.add_highlight(
            start_char=start,
            end_char=end,
            tag=tag,
            text=highlighted_text,
            author=state.user_name,
            para_ref=para_ref,
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
        _t = time.monotonic()
        await pm.force_persist_workspace(state.workspace_id)
        logger.debug(
            "tag_apply_phase",
            phase="force_persist_workspace",
            elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
        )

        if state.save_status:
            state.save_status.text = "Saved"

        # Update CSS to show new highlight
        _update_highlight_css(state)

        # Refresh annotation cards to show new highlight
        _t = time.monotonic()
        if state.refresh_annotations:
            state.refresh_annotations(trigger="tag_apply")
        logger.debug(
            "tag_apply_phase",
            phase="refresh_annotation_cards",
            elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
        )

        # Broadcast to other clients
        _t = time.monotonic()
        if state.broadcast_update:
            await state.broadcast_update()
        logger.debug(
            "tag_apply_phase",
            phase="broadcast_update",
            elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
        )

        # Clear browser selection and the client-side selection capture
        # (fire-and-forget — void return, no ordering dependency on
        # subsequent server-side cleanup).  Previously awaited with 1.0s
        # timeout, causing ~3,400 TimeoutErrors when the browser could
        # not respond in time (queued behind NiceGUI element batch).
        # See #377.  window._annotSel mirrors state.selection_* so a
        # second tag click without a new selection stays a no-op (#502).
        ui.run_javascript(
            "window.getSelection().removeAllRanges(); window._annotSel = null;"
        )
    finally:
        # Always release processing lock -- prevents permanent lockout if any
        # step above raises (e.g. JS relay failure, persistence error).
        state.processing_highlight = False

        # Clear selection state and hide menu — unconditional so that a JS
        # timeout or other exception cannot leave ghost highlight_menu or
        # stale selection_start/selection_end.  Previously inside the try
        # block after the awaited removeAllRanges, so TimeoutError skipped
        # these lines.  See #377.
        state.selection_start = None
        state.selection_end = None
        if state.highlight_menu:
            state.highlight_menu.set_visibility(False)
        logger.debug(
            "tag_apply_phase",
            phase="total_pipeline",
            elapsed_ms=round((time.monotonic() - _t_pipeline) * 1000, 1),
        )
