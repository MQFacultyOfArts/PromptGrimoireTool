"""Annotation card UI for the annotation page.

Builds and refreshes the annotation sidebar cards that display
highlight metadata, comments, and action buttons.

Cards default to a compact header (~28px) showing essential metadata.
Clicking the expand chevron reveals the full detail section with
tag select, text preview, and comments.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation import PageState, _render_js
from promptgrimoire.pages.annotation.highlights import (
    _delete_highlight,
    _update_highlight_css,
)
from promptgrimoire.ui_helpers import on_submit_with_value

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

_EXPANDABLE_THRESHOLD = 80


def _author_initials(name: str) -> str:
    """Derive compact initials from a display name.

    Splits on whitespace and hyphens, takes first char of each segment,
    joins with dots.  "Brian Ballsun-Stanton" -> "B.B.S.", "Ada" -> "A."
    """
    segments = re.split(r"[\s\-]+", name)
    return ".".join(s[0].upper() for s in segments if s) + "."


def _build_expandable_text(full_text: str) -> None:
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


def _build_comment_delete_btn(
    state: PageState,
    highlight_id: str,
    comment_id: str,
) -> None:
    """Build a delete button for a comment.

    Shown for comment owner, workspace owner, or privileged users.
    """

    async def do_delete(
        hid: str = highlight_id,
        cid: str = comment_id,
    ) -> None:
        if state.crdt_doc is None:
            return
        deleted = state.crdt_doc.delete_comment(
            hid,
            cid,
            requesting_user_id=state.user_id,
            is_privileged=state.viewer_is_privileged,
        )
        if not deleted:
            return

        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )
        await pm.force_persist_workspace(state.workspace_id)

        if state.save_status:
            state.save_status.text = "Saved"
        if state.refresh_annotations:
            state.refresh_annotations(trigger="highlight_delete")
        if state.broadcast_update:
            await state.broadcast_update()

    ui.button(icon="close", on_click=do_delete).props(
        'flat dense size=xs data-testid="comment-delete"'
    ).tooltip("Delete comment")


def _build_single_comment(
    state: PageState,
    highlight_id: str,
    comment: dict[str, Any],
) -> None:
    """Build a single comment display within a card."""
    c_author_raw = comment.get("author", "Unknown")
    c_text = comment.get("text", "")
    c_user_id = comment.get("user_id")
    c_id = comment.get("id", "")
    c_author = anonymise_author(
        author=c_author_raw,
        user_id=c_user_id,
        viewing_user_id=state.user_id,
        anonymous_sharing=state.is_anonymous,
        viewer_is_privileged=state.viewer_is_privileged,
        author_is_privileged=(
            c_user_id is not None and c_user_id in state.privileged_user_ids
        ),
    )
    with (
        ui.element("div")
        .classes("bg-gray-100 p-2 rounded mt-1")
        .props('data-testid="comment"')
    ):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(c_author).classes("text-xs font-bold").props(
                'data-testid="comment-author"'
            )
            if state.can_delete_content(c_user_id):
                _build_comment_delete_btn(state, highlight_id, c_id)
        ui.label(c_text).classes("text-sm")


def _make_add_comment_handler(
    state: PageState,
    highlight_id: str,
    comment_input: ui.input,
) -> Callable[[str], Any]:
    """Create an async handler for posting a new comment.

    Returns a callable that accepts the comment text (captured
    client-side by ``on_submit_with_value``) rather than reading
    ``comment_input.value``, which may be stale due to concurrent
    event dispatch.  See value-capture-hardening design doc.
    """

    async def add_comment(
        text: str,
        hid: str = highlight_id,
        inp: ui.input = comment_input,
    ) -> None:
        if text and text.strip() and state.crdt_doc:
            state.crdt_doc.add_comment(
                hid,
                state.user_name,
                text.strip(),
                user_id=state.user_id,
            )
            inp.value = ""

            pm = get_persistence_manager()
            pm.mark_dirty_workspace(
                state.workspace_id,
                state.crdt_doc.doc_id,
                last_editor=state.user_name,
            )
            await pm.force_persist_workspace(state.workspace_id)

            if state.save_status:
                state.save_status.text = "Saved"
            if state.refresh_annotations:
                state.refresh_annotations(trigger="comment_save")
            if state.broadcast_update:
                await state.broadcast_update()

    return add_comment


def _build_comments_section(
    state: PageState,
    highlight_id: str,
    comments: list[dict[str, Any]],
) -> None:
    """Build comments display and input for an annotation card."""
    if comments:
        ui.separator()
        sorted_comments = sorted(comments, key=lambda c: c.get("created_at", ""))
        for comment in sorted_comments:
            _build_single_comment(state, highlight_id, comment)

    if state.can_annotate:
        comment_input = (
            ui.input(placeholder="Add comment...")
            .props('dense data-testid="comment-input"')
            .classes("w-full mt-2")
        )
        add_comment = _make_add_comment_handler(state, highlight_id, comment_input)
        post_btn = (
            ui.button("Post")
            .props('dense size=sm data-testid="post-comment-btn"')
            .classes("mt-1")
        )
        on_submit_with_value(post_btn, comment_input, add_comment)


def _build_para_ref_editor(
    state: PageState,
    highlight_id: str,
    para_ref: str,
) -> None:
    """Build a click-to-edit para_ref display.

    Default state shows a static label. Clicking switches to an inline
    input. On blur or Enter the new value is saved to CRDT, persisted,
    and the display swaps back to the label.
    """
    # Mutable container so finish_edit always falls back to the most recently
    # saved value, not the stale value captured at construction time.
    current: list[str] = [para_ref]

    # Container holds label and input; only one visible at a time
    label = (
        ui.label(para_ref)
        .classes("text-xs font-mono text-gray-400 cursor-pointer")
        .props('data-testid="para-ref-label"')
    )
    inp = (
        ui.input(value=para_ref)
        .props('dense data-testid="para-ref-input"')
        .classes("text-xs font-mono")
        .style("max-width: 80px;")
    )
    inp.set_visibility(False)

    def start_edit(
        lbl: ui.label = label,
        field: ui.input = inp,
    ) -> None:
        lbl.set_visibility(False)
        field.set_visibility(True)

    async def finish_edit(
        lbl: ui.label = label,
        field: ui.input = inp,
        hid: str = highlight_id,
    ) -> None:
        new_value = (field.value or "").strip()
        lbl.text = new_value if new_value else current[0]
        lbl.set_visibility(True)
        field.set_visibility(False)

        # Only persist if value actually changed
        if new_value and new_value != current[0] and state.crdt_doc is not None:
            state.crdt_doc.update_highlight_para_ref(hid, new_value)
            current[0] = new_value  # Track latest saved value for future edits
            pm = get_persistence_manager()
            pm.mark_dirty_workspace(
                state.workspace_id,
                state.crdt_doc.doc_id,
                last_editor=state.user_name,
            )
            await pm.force_persist_workspace(state.workspace_id)
            if state.save_status:
                state.save_status.text = "Saved"
            if state.broadcast_update:
                await state.broadcast_update()

    label.on("click", start_edit)
    inp.on("blur", finish_edit)
    inp.on("keydown.enter", finish_edit)


def _make_tag_change_handler(
    state: PageState,
    highlight_id: str,
    tag_str: str,
    card: ui.card,
) -> Any:
    """Create an async handler for tag dropdown changes."""

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
            new_color = state.tag_colours().get(new_tag, "#999999")
            crd.style(f"border-left: 4px solid {new_color};")
            if state.broadcast_update:
                await state.broadcast_update()

    return on_tag_change


def _build_compact_header(
    state: PageState,
    *,
    tag_display: str,
    color: str,
    initials: str,
    para_ref: str,
    comment_count: int,
    start_char: int,
    end_char: int,
    highlight_id: str,
    highlight_user_id: str | None,
    card: ui.card,
) -> tuple[ui.row, ui.button]:
    """Build the always-visible compact card header.

    Returns (header_row, chevron) for wiring toggle logic.
    The entire row is clickable; the chevron provides the visual indicator.
    """
    header_row = (
        ui.row()
        .classes("w-full items-center gap-1 cursor-pointer")
        .style("min-height: 20px; padding: 4px 8px;")
    )
    with header_row:
        # Colour dot
        ui.element("div").style(
            f"width: 8px; height: 8px; border-radius: 50%; "
            f"background-color: {color}; flex-shrink: 0;"
        )
        # Tag name (static label)
        ui.label(tag_display).classes("text-xs font-bold truncate").style(
            f"color: {color}; max-width: 100px;"
        )
        # Author initials
        ui.label(initials).classes("text-xs text-gray-500")
        # Para ref
        if para_ref:
            ui.label(para_ref).classes("text-xs font-mono text-gray-400")
        # Comment count badge
        if comment_count > 0:
            ui.label(str(comment_count)).classes(
                "text-xs bg-blue-100 text-blue-700 rounded-full px-1"
            ).props('data-testid="comment-count"')
        # Spacer pushes buttons to the right
        ui.element("div").style("flex-grow: 1;")

        # Expand/collapse chevron
        chevron = (
            ui.button(icon="expand_more")
            .props('flat dense size=xs data-testid="card-expand-btn"')
            .tooltip("Expand card")
        )

        # Locate button (available to all)
        def goto_highlight(sc: int = start_char, ec: int = end_char) -> None:
            js = _render_js(
                t"scrollToCharOffset(window._textNodes, {sc}, {ec});"
                t"throbHighlight(window._textNodes, {sc}, {ec}, 800);"
            )
            # Fire-and-forget — scroll/throb are visual-only, void return.
            # See #377.
            ui.run_javascript(js)

        ui.button(icon="my_location", on_click=goto_highlight).props(
            "flat dense size=xs"
        ).tooltip("Go to highlight")

        # Delete button (if permitted)
        if state.can_delete_content(highlight_user_id):

            async def do_delete(
                hid: str = highlight_id,
                c: ui.card = card,
            ) -> None:
                await _delete_highlight(state, hid, c)

            ui.button(icon="close", on_click=do_delete).props(
                "flat dense size=xs"
            ).tooltip("Delete highlight")

    return header_row, chevron


def _build_detail_section(
    state: PageState,
    *,
    highlight_id: str,
    tag_str: str,
    color: str,
    display_author: str,
    para_ref: str,
    full_text: str,
    comments: list[dict[str, Any]],
    card: ui.card,
) -> None:
    """Build the expandable detail section of an annotation card."""
    # Tag select (annotators only)
    if state.can_annotate:
        tag_options = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}
        # Defensive: if the highlight references a tag not in options
        # (e.g. deleted tag group), add a recovery entry so ui.select
        # doesn't raise ValueError.
        if tag_str and tag_str not in tag_options:
            tag_options[tag_str] = "\u26a0 recovered"
        on_change = _make_tag_change_handler(state, highlight_id, tag_str, card)
        ui.select(
            tag_options,
            value=tag_str,
            on_change=on_change,
        ).props('dense borderless data-testid="tag-select"').classes(
            "text-sm font-bold"
        ).style(f"color: {color}; min-width: 120px;")

    # Full author and editable para_ref
    with ui.row().classes("gap-2 items-center"):
        ui.label(f"by {display_author}").classes("text-xs text-gray-500")
        if para_ref:
            _build_para_ref_editor(state, highlight_id, para_ref)

    # Highlighted text preview
    if full_text:
        _build_expandable_text(full_text)

    # Comments
    _build_comments_section(state, highlight_id, comments)


def _build_annotation_card(
    state: PageState,
    highlight: dict[str, Any],
) -> ui.card:
    """Build an annotation card with compact header and expandable detail."""
    highlight_id = highlight.get("id", "")
    tag_str = highlight.get("tag", "highlight")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    start_char = int(highlight.get("start_char", 0))
    end_char = int(highlight.get("end_char", start_char))
    para_ref = highlight.get("para_ref", "")
    comments: list[dict[str, Any]] = highlight.get("comments", [])

    tag_colours = state.tag_colours()
    color = tag_colours.get(tag_str, "#999999")

    # Derive display values — look up human-readable name from tag info
    tag_display = tag_str.replace("_", " ").title()
    if state.tag_info_list:
        for ti in state.tag_info_list:
            if ti.raw_key == tag_str:
                tag_display = ti.name
                break
    hl_user_id = highlight.get("user_id")
    display_author = anonymise_author(
        author=author,
        user_id=hl_user_id,
        viewing_user_id=state.user_id,
        anonymous_sharing=state.is_anonymous,
        viewer_is_privileged=state.viewer_is_privileged,
        author_is_privileged=(
            hl_user_id is not None and hl_user_id in state.privileged_user_ids
        ),
    )
    initials = _author_initials(display_author)

    card = (
        ui.card()
        .classes("ann-card-positioned")
        .style(f"border-left: 4px solid {color};")
        .props(
            f'data-testid="annotation-card" '
            f'data-highlight-id="{highlight_id}" '
            f'data-start-char="{start_char}" '
            f'data-end-char="{end_char}"'
        )
    )

    with card:
        # Compact header (always visible)
        header_row, chevron = _build_compact_header(
            state,
            tag_display=tag_display,
            color=color,
            initials=initials,
            para_ref=para_ref,
            comment_count=len(comments),
            start_char=start_char,
            end_char=end_char,
            highlight_id=highlight_id,
            highlight_user_id=hl_user_id,
            card=card,
        )

        # Detail section (collapsed by default, carries its own padding)
        detail = (
            ui.element("div")
            .classes("w-full")
            .props('data-testid="card-detail"')
            .style("padding: 0 8px 8px 8px;")
        )
        detail.set_visibility(False)

        with detail:
            _build_detail_section(
                state,
                highlight_id=highlight_id,
                tag_str=tag_str,
                color=color,
                display_author=display_author,
                para_ref=para_ref,
                full_text=full_text,
                comments=comments,
                card=card,
            )

        # Restore expansion state from previous render cycle
        if highlight_id in state.expanded_cards:
            detail.set_visibility(True)
            chevron.props('icon="expand_less"')

        # Wire expand/collapse toggle — click anywhere on header row
        def toggle_detail(
            d: ui.element = detail,
            ch: ui.button = chevron,
            hid: str = highlight_id,
        ) -> None:
            if d.visible:
                d.set_visibility(False)
                ch.props('icon="expand_more"')
                state.expanded_cards.discard(hid)
            else:
                d.set_visibility(True)
                ch.props('icon="expand_less"')
                state.expanded_cards.add(hid)
            # Fire-and-forget — rAF returns an unused int ID, and the
            # MutationObserver already triggers positionCards on visibility
            # change.  Previously awaited with 1.0s timeout, causing ~2,100
            # TimeoutErrors when the browser could not respond in time
            # (queued behind NiceGUI element batch).  See #377.
            ui.run_javascript(
                "if (window._positionCards)"
                " requestAnimationFrame(window._positionCards)"
            )

        header_row.on("click", toggle_detail)

    return card


def _refresh_annotation_cards(state: PageState, *, trigger: str = "unknown") -> None:
    """Refresh all annotation cards from CRDT state."""
    logger.debug(
        "card_rebuild",
        trigger=trigger,
        cards_epoch=state.cards_epoch,
        container_exists=state.annotations_container is not None,
        crdt_doc_exists=state.crdt_doc is not None,
    )
    if state.annotations_container is None or state.crdt_doc is None:
        return

    _t0 = time.monotonic()

    if state.annotation_cards is None:
        state.annotation_cards = {}

    # Wrap the entire rebuild in ``with container`` so that every
    # ``ui.run_javascript`` call resolves the NiceGUI client through the
    # container's slot — not the caller's slot, whose parent element may
    # have been destroyed by a prior ``container.clear()``.
    with state.annotations_container:
        state.annotations_container.clear()

        # Get highlights for this document
        if state.document_id is not None:
            highlights = state.crdt_doc.get_highlights_for_document(
                str(state.document_id),
            )
        else:
            highlights = state.crdt_doc.get_all_highlights()

        logger.debug(
            "[CARDS] Found %d highlights for doc_id=%s",
            len(highlights),
            state.document_id,
        )

        # Create cards for each highlight
        for hl in highlights:
            hl_id = hl.get("id", "")
            logger.debug("[CARDS] Creating card for highlight %s", hl_id[:8])
            card = _build_annotation_card(state, hl)
            state.annotation_cards[hl_id] = card

        state.cards_epoch += 1
        ui.run_javascript(f"window.__annotationCardsEpoch = {state.cards_epoch}")

    logger.debug(
        "render_phase",
        phase="refresh_annotation_cards",
        elapsed_ms=round((time.monotonic() - _t0) * 1000, 1),
        trigger=trigger,
        highlight_count=len(highlights),
    )
