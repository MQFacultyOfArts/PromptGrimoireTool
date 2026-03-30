"""Annotation card UI for the annotation page.

Builds and refreshes the annotation sidebar cards that display
highlight metadata, comments, and action buttons.

Cards default to a compact header (~28px) showing essential metadata.
Clicking the expand chevron reveals the full detail section with
tag select, text preview, and comments.
"""

from __future__ import annotations

import html as _html  # stdlib — for html.escape in raw HTML rendering
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation import PageState, _render_js
from promptgrimoire.pages.annotation.card_shared import (
    anonymise_display_author,
    author_initials,
    build_expandable_text,
)
from promptgrimoire.pages.annotation.highlights import (
    _delete_highlight,
    _update_highlight_css,
)
from promptgrimoire.ui_helpers import on_submit_with_value

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


def _broadcast_cards_epoch(state: PageState) -> None:
    """Increment and broadcast the cards epoch to the client.

    Writes both the per-document map (``window.__cardEpochs``) and the
    legacy scalar (``window.__annotationCardsEpoch``) so that E2E tests
    can wait on either.
    """
    state.cards_epoch += 1
    doc_key = str(state.document_id) if state.document_id else "_default"
    ui.run_javascript(
        f"window.__cardEpochs = window.__cardEpochs || {{}}; "
        f"window.__cardEpochs['{doc_key}'] = {state.cards_epoch}; "
        f"window.__annotationCardsEpoch = {state.cards_epoch}"
    )


def _snapshot_highlight(hl: dict[str, Any]) -> dict[str, Any]:
    """Create a comparable snapshot of highlight data for change detection.

    Captures tag, para_ref, comment count, and comment text content to
    detect when a card needs rebuilding.  Any rendered field that can
    change independently of the highlight ID must be included here.
    """
    comments = hl.get("comments", [])
    return {
        "tag": hl.get("tag", ""),
        "para_ref": hl.get("para_ref", ""),
        "comment_count": len(comments),
        "comment_texts": tuple(
            c.get("text", "")
            for c in sorted(comments, key=lambda c: c.get("created_at", ""))
        ),
    }


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
    c_author = anonymise_display_author(c_author_raw, c_user_id, state)
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


def _render_compact_header_html(
    *,
    tag_display: str,
    color: str,
    initials: str,
    para_ref: str,
    comment_count: int,
) -> str:
    """Render the static parts of the compact header as raw HTML.

    Returns an HTML fragment for use with ``ui.html(sanitize=False)``.
    All interpolated string values are escaped via ``html.escape()``
    (defense-in-depth — values originate from authenticated UI but
    we never trust interpolated content in raw HTML).

    Elements rendered: colour dot, tag name, author initials,
    para ref (conditional), comment count badge (conditional), spacer.
    """
    esc = _html.escape
    parts: list[str] = [
        # Container open
        '<div style="display:flex;align-items:center;gap:0.25rem;">',
        # Colour dot
        f'<div style="width:8px;height:8px;border-radius:50%;'
        f'background-color:{esc(color)};flex-shrink:0;"></div>',
        # Tag label
        f'<span class="text-xs font-bold" style="color:{esc(color)};'
        f"max-width:100px;overflow:hidden;text-overflow:ellipsis;"
        f'white-space:nowrap;">{esc(tag_display)}</span>',
        # Author initials
        f'<span class="text-xs text-gray-500">{esc(initials)}</span>',
    ]
    # Para ref (conditional)
    if para_ref:
        parts.append(
            f'<span class="text-xs font-mono text-gray-400">{esc(para_ref)}</span>'
        )
    # Comment count badge (conditional)
    if comment_count > 0:
        parts.append(
            f'<span class="text-xs bg-blue-100 text-blue-700 rounded-full px-1"'
            f' data-testid="comment-count">{comment_count}</span>'
        )
    # Spacer
    parts.append('<div style="flex-grow:1;"></div>')
    # Container close
    parts.append("</div>")
    return "".join(parts)


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
        # Static display elements as a single HTML block (Task 5, #457).
        # Replaces 6 NiceGUI element constructors with one ui.html() call.
        html_content = _render_compact_header_html(
            tag_display=tag_display,
            color=color,
            initials=initials,
            para_ref=para_ref,
            comment_count=comment_count,
        )
        ui.html(html_content, sanitize=False).classes("flex items-center gap-1").style(
            "flex: 1; min-width: 0;"
        )

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
        build_expandable_text(full_text)

    # Comments
    _build_comments_section(state, highlight_id, comments)


def _ensure_detail_built(
    state: PageState,
    detail: ui.element,
    highlight: dict[str, Any],
    card: ui.card,
) -> None:
    """Build the detail section lazily on first expand.

    Idempotent — returns immediately if already built.  Must be called
    within the card's NiceGUI slot context (the caller's ``with card:``
    is sufficient; this function uses ``with detail:`` internally).
    """
    highlight_id = highlight.get("id", "")
    if highlight_id in state.detail_built_cards:
        return
    tag_str = highlight.get("tag", "highlight")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    para_ref = highlight.get("para_ref", "")
    comments: list[dict[str, Any]] = highlight.get("comments", [])
    tag_colours = state.tag_colours()
    color = tag_colours.get(tag_str, "#999999")
    hl_user_id = highlight.get("user_id")
    display_author = anonymise_display_author(author, hl_user_id, state)

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
    state.detail_built_cards.add(highlight_id)


def _build_annotation_card(
    state: PageState,
    highlight: dict[str, Any],
) -> ui.card:
    """Build an annotation card with compact header and expandable detail."""
    highlight_id = highlight.get("id", "")
    tag_str = highlight.get("tag", "highlight")
    author = highlight.get("author", "Unknown")
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
    display_author = anonymise_display_author(author, hl_user_id, state)
    initials = author_initials(display_author)

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

        # Restore expansion state from previous render cycle —
        # pre-expanded cards must have detail built eagerly (AC1.3)
        if highlight_id in state.expanded_cards:
            _ensure_detail_built(state, detail, highlight, card)
            detail.set_visibility(True)
            chevron.props('icon="expand_less"')

        # Wire expand/collapse toggle — click anywhere on header row
        def toggle_detail(
            d: ui.element = detail,
            ch: ui.button = chevron,
            hid: str = highlight_id,
            hl: dict[str, Any] = highlight,
            crd: ui.card = card,
        ) -> None:
            if d.visible:
                d.set_visibility(False)
                ch.props('icon="expand_more"')
                state.expanded_cards.discard(hid)
            else:
                _ensure_detail_built(state, d, hl, crd)
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


def _get_highlights(state: PageState) -> list[dict[str, Any]]:
    """Get highlights for the current document from CRDT state.

    Caller must ensure ``state.crdt_doc is not None`` before calling.
    """
    if state.crdt_doc is None:  # pragma: no cover — guarded by callers
        return []
    if state.document_id is not None:
        return state.crdt_doc.get_highlights_for_document(
            str(state.document_id),
        )
    return state.crdt_doc.get_all_highlights()


# ---------------------------------------------------------------------------
# Card diff helpers (shared by sync and async variants)
# ---------------------------------------------------------------------------


@dataclass
class _CardDiff:
    """Pre-computed diff between CRDT highlights and current card registry."""

    crdt_map: dict[str, dict[str, Any]]
    sorted_hl_ids: list[str]
    removed_ids: set[str]
    added_in_order: list[str]
    common_ids: set[str]
    highlight_count: int
    changed: bool = False


def _compute_card_diff(
    state: PageState,
    highlights: list[dict[str, Any]],
) -> _CardDiff:
    """Compute the diff between CRDT highlights and current cards.

    Callers must verify ``state.annotation_cards is not None`` before
    calling.
    """
    crdt_map = {hl["id"]: hl for hl in highlights}
    crdt_ids = set(crdt_map.keys())
    # Callers' guard clauses guarantee annotation_cards is not None
    cards = state.annotation_cards
    if cards is None:
        raise ValueError("_compute_card_diff called with annotation_cards=None")
    registry_ids = set(cards.keys())

    removed_ids = registry_ids - crdt_ids
    added_ids = crdt_ids - registry_ids

    sorted_hl_ids = [hl["id"] for hl in highlights]
    added_in_order = [hid for hid in sorted_hl_ids if hid in added_ids]

    return _CardDiff(
        crdt_map=crdt_map,
        sorted_hl_ids=sorted_hl_ids,
        removed_ids=removed_ids,
        added_in_order=added_in_order,
        common_ids=crdt_ids & registry_ids,
        highlight_count=len(highlights),
    )


def _diff_remove_cards(state: PageState, removed_ids: set[str]) -> bool:
    """Remove cards for highlights no longer in CRDT.

    Callers guarantee ``state.annotation_cards is not None``.
    """
    cards = state.annotation_cards
    if cards is None:
        return False
    changed = False
    for removed_id in removed_ids:
        card = cards.pop(removed_id)
        card.delete()
        state.expanded_cards.discard(removed_id)
        state.detail_built_cards.discard(removed_id)
        state.card_snapshots.pop(removed_id, None)
        changed = True
    return changed


def _diff_add_one_card(state: PageState, diff: _CardDiff, add_id: str) -> None:
    """Build and position a single new card.

    Callers guarantee ``state.annotation_cards is not None``.
    """
    hl = diff.crdt_map[add_id]
    card = _build_annotation_card(state, hl)
    cards = state.annotation_cards
    if cards is None:
        return
    cards[add_id] = card
    state.card_snapshots[add_id] = _snapshot_highlight(hl)
    position = diff.sorted_hl_ids.index(add_id)
    card.move(
        target_container=state.annotations_container,
        target_index=position,
    )


def _diff_update_changed_cards(state: PageState, diff: _CardDiff) -> bool:
    """Replace cards whose highlight data changed.

    Callers guarantee both container and cards are not None.
    Returns True if any card was replaced.
    """
    container = state.annotations_container
    cards = state.annotation_cards
    if container is None or cards is None:
        return False
    changed = False
    with container:
        for hl_id in diff.common_ids:
            hl = diff.crdt_map[hl_id]
            new_snap = _snapshot_highlight(hl)
            old_snap = state.card_snapshots.get(hl_id)
            if old_snap != new_snap:
                old_card = cards[hl_id]
                old_card.delete()
                state.detail_built_cards.discard(hl_id)
                new_card = _build_annotation_card(state, hl)
                cards[hl_id] = new_card
                state.card_snapshots[hl_id] = new_snap
                position = diff.sorted_hl_ids.index(hl_id)
                new_card.move(
                    target_container=container,
                    target_index=position,
                )
                changed = True
    return changed


def _diff_finish(
    state: PageState,
    diff: _CardDiff,
    t_start: float,
    *,
    phase: str = "sync",
) -> None:
    """Broadcast epoch and log timing if anything changed."""
    container = state.annotations_container
    if container is None:
        return
    elapsed = round((time.monotonic() - t_start) * 1000, 1)
    if diff.changed:
        with container:
            _broadcast_cards_epoch(state)
    if elapsed > 10:
        logger.info(
            "card_diff_total",
            phase=f"diff_annotation_cards_{phase}",
            elapsed_ms=elapsed,
            highlight_count=diff.highlight_count,
            added=len(diff.added_in_order),
            removed=len(diff.removed_ids),
        )


# ---------------------------------------------------------------------------
# Sync diff (incremental updates: 1-2 cards per call)
# ---------------------------------------------------------------------------


def _diff_annotation_cards(state: PageState) -> None:
    """Update annotation cards by diffing CRDT state against current cards.

    Instead of clearing and rebuilding the entire container, this function:
    - Removes cards for highlights that no longer exist in the CRDT
    - Adds cards for new highlights at the correct sorted position
    - Leaves unchanged cards untouched (preserving expansion state, input
      focus, and DOM event handlers)

    Only called when ``state.annotation_cards`` is already populated
    (i.e. after the first full build).
    """
    if state.annotations_container is None or state.crdt_doc is None:
        return
    if state.annotation_cards is None:
        return

    _t_diff = time.monotonic()
    highlights = _get_highlights(state)
    diff = _compute_card_diff(state, highlights)

    diff.changed = _diff_remove_cards(state, diff.removed_ids)

    if diff.added_in_order:
        _t_add = time.monotonic()
        with state.annotations_container:
            for add_id in diff.added_in_order:
                _diff_add_one_card(state, diff, add_id)
                diff.changed = True
        logger.info(
            "card_diff_add",
            phase="diff_add_cards",
            added_count=len(diff.added_in_order),
            elapsed_ms=round((time.monotonic() - _t_add) * 1000, 1),
            trigger="diff",
        )

    diff.changed |= _diff_update_changed_cards(state, diff)
    _diff_finish(state, diff, _t_diff)


def _refresh_annotation_cards(state: PageState, *, trigger: str = "unknown") -> None:
    """Refresh annotation cards from CRDT state.

    First call (``annotation_cards is None``): full build -- clears the
    container and creates all cards from scratch.

    Subsequent calls: diff-based update via ``_diff_annotation_cards`` —
    only adds/removes individual cards that changed, preserving the rest.
    """
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

    if state.annotation_cards is not None:
        # Subsequent render — diff
        _diff_annotation_cards(state)
        return

    # First render — full build
    state.annotation_cards = {}
    state.detail_built_cards.clear()

    # Wrap the entire rebuild in ``with container`` so that every
    # ``ui.run_javascript`` call resolves the NiceGUI client through the
    # container's slot — not the caller's slot, whose parent element may
    # have been destroyed by a prior ``container.clear()``.
    with state.annotations_container:
        state.annotations_container.clear()

        highlights = _get_highlights(state)

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
            state.card_snapshots[hl_id] = _snapshot_highlight(hl)

        _broadcast_cards_epoch(state)

    logger.debug(
        "render_phase",
        phase="refresh_annotation_cards",
        elapsed_ms=round((time.monotonic() - _t0) * 1000, 1),
        trigger=trigger,
        highlight_count=len(highlights),
    )
