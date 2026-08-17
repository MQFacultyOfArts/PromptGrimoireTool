"""Document rendering and selection wiring for the annotation page.

Handles rendering a WorkspaceDocument with highlight support,
setting up JS-based text selection detection, and keyboard shortcuts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib.parse import urlencode

import structlog
from nicegui import ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.input_pipeline.html_input import extract_text_from_html
from promptgrimoire.input_pipeline.paragraph_map import inject_paragraph_attributes
from promptgrimoire.pages.annotation import PageState, _RawJS, _render_js
from promptgrimoire.pages.annotation.css import (
    _build_highlight_pseudo_css,
    _build_tag_toolbar,
)
from promptgrimoire.pages.annotation.highlights import (
    _add_highlight,
    _build_highlight_json,
)

logger = structlog.get_logger()


def _handle_selection(state: PageState, e: Any) -> None:
    """Handle selection event from JavaScript."""
    state.selection_start = e.args.get("start_char")
    state.selection_end = e.args.get("end_char")
    if state.highlight_menu:
        state.highlight_menu.set_visibility(True)
    if state.broadcast_selection:
        state.broadcast_selection(state.selection_start, state.selection_end)


def _handle_selection_cleared(state: PageState, _e: Any) -> None:
    """Handle selection cleared event."""
    state.selection_start = None
    state.selection_end = None
    if state.highlight_menu:
        state.highlight_menu.set_visibility(False)
    if state.broadcast_selection:
        state.broadcast_selection(None, None)


def _handle_cursor_move(state: PageState, e: Any) -> None:
    """Handle cursor position change from JavaScript."""
    char_index = e.args.get("char")
    if state.broadcast_cursor:
        state.broadcast_cursor(char_index)


async def _handle_keydown(state: PageState, e: Any) -> None:
    """Handle keyboard shortcut for tag selection (1-0 keys map to tags)."""
    key = e.args.get("key")
    if not key or not state.tag_info_list:
        return
    key_to_index = {
        str((i + 1) % 10): i for i in range(min(10, len(state.tag_info_list)))
    }
    if key in key_to_index:
        ti = state.tag_info_list[key_to_index[key]]
        await _add_highlight(state, ti.raw_key)


# fmt: off
_SELECTION_CLICK_AND_KEYBOARD_JS = (
    "setTimeout(function() {"
    "  document.addEventListener('click', function(e) {"
    "    if (e.target.closest('[data-testid=\"tag-toolbar\"]')) return;"
    "    setTimeout(function() {"
    "      var s = window.getSelection();"
    "      if (!s || s.isCollapsed) emitEvent('selection_cleared', {});"
    "    }, 50);"
    "  });"
    "  var lastKeyTime = 0;"
    "  document.addEventListener('keydown', function(e) {"
    "    if (e.repeat) return;"
    "    var tag = e.target.tagName;"
    "    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'"
    "        || e.target.isContentEditable) return;"
    "    var now = Date.now();"
    "    if (now - lastKeyTime < 300) return;"
    "    lastKeyTime = now;"
    "    if ('1234567890'.indexOf(e.key) >= 0) {"
    "      emitEvent('keydown', {key: e.key});"
    "    }"
    "  });"
    "}, 100);"
)
# fmt: on


def _setup_selection_handlers(state: PageState) -> None:
    """Set up JavaScript-based selection detection and event handlers.

    Note: Per Key Design Decision #5 in the phase plan, detecting browser text
    selection inherently requires JavaScript. The implementation uses
    ui.run_javascript() for this unavoidable browser API access. E2E tests
    correctly use Playwright's native mouse events to simulate user selection.
    """
    ui.on("selection_made", lambda e: _handle_selection(state, e))
    ui.on("selection_cleared", lambda e: _handle_selection_cleared(state, e))
    ui.on("cursor_move", lambda e: _handle_cursor_move(state, e))
    ui.on("keydown", lambda e: _handle_keydown(state, e))
    ui.run_javascript(_SELECTION_CLICK_AND_KEYBOARD_JS)


def _render_new_tag_button(on_add_click: Any) -> None:
    """Render the '+ New' tag creation button in the current NiceGUI context."""
    ui.button("+ New", on_click=on_add_click).props(
        'flat dense color=grey-7 data-testid="highlight-menu-new-tag"'
    ).classes("text-sm").tooltip("Create a new tag and apply it to your selection")


def _render_highlight_menu_tag_button(ti: Any, on_tag_click: Any) -> None:
    """Render a single abbreviated tag button inside the floating highlight menu."""
    abbrev = ti.name[:6]

    async def _apply(tag_key: str = ti.raw_key) -> None:
        await on_tag_click(tag_key)

    btn = (
        ui.button(abbrev, on_click=_apply)
        .classes("text-xs compact-btn")
        .props('data-testid="highlight-menu-tag-btn"')
    )
    btn.style(
        f"background-color: {ti.colour} !important; "
        "color: white !important; "
        "padding: 1px 4px !important; "
        "min-height: 20px !important;"
    )
    if ti.description:
        with btn, ui.element("q-tooltip"):
            ui.html(
                f"<b>{escape(ti.name)}</b><br>{escape(ti.description)}",
                sanitize=False,
            )
    else:
        btn.tooltip(ti.name)


def _render_tag_groups(
    tag_info_list: list[Any], on_tag_click: Any, on_add_click: Any | None
) -> None:
    """Render tag buttons grouped by tag group, with optional '+ New' button."""
    groups: dict[str | None, list[Any]] = {}
    for ti in tag_info_list:
        groups.setdefault(ti.group_name, []).append(ti)

    with ui.column().classes("gap-1"):
        for members in groups.values():
            with ui.row().classes("gap-1 items-center"):
                for ti in members:
                    _render_highlight_menu_tag_button(ti, on_tag_click)

        if on_add_click is not None:
            _render_new_tag_button(on_add_click)


def _render_empty_tag_state(on_add_click: Any | None) -> None:
    """Render the empty-tag fallback: '+ New' button or 'No tags available' label."""
    if on_add_click is not None:
        _render_new_tag_button(on_add_click)
    else:
        ui.label("No tags available").classes("text-sm text-gray-600").props(
            'data-testid="no-tags-label"'
        ).tooltip("Ask your instructor to add tags to this activity")


def _populate_highlight_menu(
    state: PageState, on_tag_click: Any, *, on_add_click: Any | None = None
) -> None:
    """Populate the highlight menu card with abbreviated tag buttons.

    Clears existing content and rebuilds from ``state.tag_info_list``.
    Called on initial build and after tag list changes.

    When *on_add_click* is provided (user has tag creation permission),
    a "+ New" button is appended after all tag groups.  When no tags
    exist and *on_add_click* is ``None``, the "No tags available" label
    is shown with a tooltip directing the user to ask their instructor.
    """
    menu = state.highlight_menu
    if menu is None:
        return
    menu.clear()
    with menu:
        if state.tag_info_list:
            _render_tag_groups(state.tag_info_list, on_tag_click, on_add_click)
        else:
            _render_empty_tag_state(on_add_click)


def _build_highlight_menu(
    state: PageState, on_tag_click: Any, *, on_add_click: Any | None = None
) -> None:
    """Build the floating highlight menu card and populate it."""
    highlight_menu = (
        ui.card()
        .classes("fixed z-[110] shadow-lg p-2")
        .props(f'data-testid="highlight-menu" id="{state.highlight_menu_id}"')
    )
    highlight_menu.set_visibility(False)
    state.highlight_menu = highlight_menu

    # Store callbacks for rebuilds triggered by _refresh_tag_state.
    # WARNING: these are NOT saved/restored on tab switch — they hold
    # the callback from the last-rendered tab.  It works because
    # on_tag_click calls _add_highlight(state, key) which reads
    # state.document_id dynamically.  Do NOT refactor to capture
    # document_id at callback creation time.
    state._highlight_menu_tag_click = on_tag_click
    state._highlight_menu_on_add_click = on_add_click

    _populate_highlight_menu(state, on_tag_click, on_add_click=on_add_click)


def _init_document_state(state: PageState, doc: Any, crdt_doc: Any) -> None:
    """Populate PageState fields for a new document render."""
    state.document_id = doc.id
    state.doc_container_id = f"doc-container-{doc.id}"
    state.ann_container_id = f"ann-container-{doc.id}"
    state.highlight_menu_id = f"hl-menu-{doc.id}"
    state.crdt_doc = crdt_doc

    # Extract characters from clean HTML for text extraction when highlighting
    # (char spans are injected client-side, not stored in DB)
    if doc.content:
        _t = time.monotonic()
        state.document_chars = extract_text_from_html(doc.content)
        logger.debug(
            "render_phase",
            phase="extract_text_from_html",
            elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
            content_len=len(doc.content),
        )
        # paragraph_map is only meaningful when content is present
        state.paragraph_map = doc.paragraph_map
        # Store raw content and auto-number mode for paragraph toggle re-render
        state.document_content = doc.content
        state.auto_number_paragraphs = getattr(doc, "auto_number_paragraphs", True)


def _inject_highlight_scripts(state: PageState) -> None:
    """Load annotation JS and initialise text walker + highlight API.

    Injects script tags via ``add_body_html`` for full page loads, plus a
    dynamic loader for SPA navigations where ``add_body_html`` scripts are
    absent.
    """
    from urllib.parse import quote  # noqa: PLC0415

    from promptgrimoire import get_version_string  # noqa: PLC0415

    # Version query busts browser caches on deploy: an unversioned URL
    # leaves clients running stale annotation JS across fixes.
    v = quote(get_version_string())
    ui.add_body_html(f'<script src="/static/annotation-highlight.js?v={v}"></script>')
    ui.add_body_html(f'<script src="/static/annotation-card-sync.js?v={v}"></script>')
    ui.add_body_html(
        f'<script src="/static/annotation-copy-protection.js?v={v}"></script>'
    )

    highlight_json = _RawJS(_build_highlight_json(state))
    init_js = _render_js(
        t"(function() {{"
        t"  var SCRIPTS = ["
        t"    '/static/annotation-highlight.js',"
        t"    '/static/annotation-card-sync.js',"
        t"    '/static/annotation-copy-protection.js'"
        t"  ];"
        t"  function init() {{"
        t"    var c = document.getElementById({state.doc_container_id});"
        t"    if (!c) return;"
        t"    window._textNodes = walkTextNodes(c);"
        t"    applyHighlights(c, {highlight_json});"
        t"    setupAnnotationSelection({state.doc_container_id}, function(sel) {{"
        t"      emitEvent('selection_made', sel);"
        t"    }}, {state.highlight_menu_id});"
        t"    if (window._pendingCopyProtection) {{"
        t"      setupCopyProtection(window._pendingCopyProtection);"
        t"      delete window._pendingCopyProtection;"
        t"    }}"
        t"    if (typeof initToolbarObserver === 'function') {{"
        t"      initToolbarObserver();"
        t"    }}"
        t"  }}"
        t"  if (typeof walkTextNodes === 'function') {{ init(); return; }}"
        t"  var loaded = 0;"
        t"  SCRIPTS.forEach(function(src) {{"
        t"    var s = document.createElement('script');"
        t"    s.src = src;"
        t"    s.onload = function() {{"
        t"      if (++loaded === SCRIPTS.length) init();"
        t"    }};"
        t"    document.body.appendChild(s);"
        t"  }});"
        t"}})();"
    )
    ui.run_javascript(init_js)


def _arm_snapshot_container(state: PageState) -> None:
    """Arm the skeleton doc container for declarative snapshot delivery.

    Mints the bundle token and exposes it as ``data-snapshot-*``
    attributes on the container.  annotation-snapshot-bootstrap.js
    (added to the initial page HTML by ``annotation_page``) discovers
    armed containers via an initial scan plus a MutationObserver and
    mounts the bundle — no JavaScript is constructed in Python.
    See docs/design-notes/2026-08-16-initial-snapshot-delivery.md.
    """
    from promptgrimoire.config import get_settings  # noqa: PLC0415, I001 -- lazy: matches sibling render helpers
    from promptgrimoire.snapshot import (  # noqa: PLC0415 -- keep annotation import light
        SnapshotClaims,
        mint_snapshot_token,
    )

    settings = get_settings()
    claims = SnapshotClaims(
        workspace_id=str(state.workspace_id),
        document_id=str(state.document_id),
        user_id=state.user_id,
        viewer_is_privileged=state.viewer_is_privileged,
        can_annotate=state.can_annotate,
        anonymous_sharing=state.is_anonymous,
    )
    token = mint_snapshot_token(
        claims, secret=settings.app.storage_secret.get_secret_value()
    )
    bundle_url = f"{settings.snapshot.base_url}/snapshot?{urlencode({'t': token})}"

    if state.doc_container is None:  # pragma: no cover -- caller sets it just above
        msg = "snapshot container armed before doc_container was created"
        raise RuntimeError(msg)
    state.doc_container.props(
        f'data-snapshot-url="{bundle_url}" '
        f'data-snapshot-menu-id="{state.highlight_menu_id}"'
    )


async def _persist_and_broadcast(
    state: PageState,
    *,
    trigger: str,
) -> None:
    """Persist CRDT changes, update status, refresh sidebar, broadcast."""
    if state.crdt_doc is None:
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
        state.refresh_annotations(trigger=trigger)
    if state.broadcast_update:
        await state.broadcast_update()


def _on_toggle_expand(state: PageState, payload: dict[str, Any]) -> None:
    hid = payload.get("id", "")
    if hid in state.expanded_cards:
        state.expanded_cards.discard(hid)
    else:
        state.expanded_cards.add(hid)


async def _on_change_tag(state: PageState, payload: dict[str, Any]) -> None:
    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
        _update_highlight_css,
    )

    hid = payload.get("id", "")
    new_tag = payload.get("new_tag", "")
    if state.crdt_doc and new_tag:
        state.crdt_doc.update_highlight_tag(hid, new_tag)
        _update_highlight_css(state)
        await _persist_and_broadcast(state, trigger="tag_change")


async def _on_submit_comment(state: PageState, payload: dict[str, Any]) -> None:
    hid = payload.get("id", "")
    text = (payload.get("text") or "").strip()
    if text and state.crdt_doc:
        state.crdt_doc.add_comment(
            hid,
            state.user_name,
            text,
            user_id=state.user_id,
        )
        await _persist_and_broadcast(state, trigger="comment_save")


async def _on_delete_comment(state: PageState, payload: dict[str, Any]) -> None:
    hid = payload.get("highlight_id", "")
    cid = payload.get("comment_id", "")
    if state.crdt_doc:
        deleted = state.crdt_doc.delete_comment(
            hid,
            cid,
            requesting_user_id=state.user_id,
            is_privileged=state.viewer_is_privileged,
        )
        if deleted:
            await _persist_and_broadcast(state, trigger="comment_delete")


async def _on_delete_highlight(state: PageState, payload: dict[str, Any]) -> None:
    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
        _update_highlight_css,
    )

    hid = payload.get("id", "")
    if state.crdt_doc:
        state.crdt_doc.remove_highlight(hid)
        _update_highlight_css(state)
        await _persist_and_broadcast(state, trigger="highlight_delete")


async def _on_edit_para_ref(state: PageState, payload: dict[str, Any]) -> None:
    hid = payload.get("id", "")
    new_ref = (payload.get("value") or "").strip()
    if new_ref and state.crdt_doc:
        state.crdt_doc.update_highlight_para_ref(hid, new_ref)
        await _persist_and_broadcast(state, trigger="para_ref_edit")


def _on_locate_highlight(state: PageState, payload: dict[str, Any]) -> None:
    sc = payload.get("start_char", 0)
    ec = payload.get("end_char", sc)
    js = _render_js(
        t"(function(){{"
        t"  var c = document.getElementById("
        t"    {state.doc_container_id});"
        t"  if (!c) return;"
        t"  window._textNodes = walkTextNodes(c);"
        t"  scrollToCharOffset("
        t"    window._textNodes, {sc}, {ec});"
        t"  throbHighlight("
        t"    window._textNodes, {sc}, {ec}, 800);"
        t"}})();"
    )
    ui.run_javascript(js)


def _make_sidebar_handlers(
    state: PageState,
) -> dict[str, Any]:
    """Build event handler closures for the Vue annotation sidebar."""
    return {
        "on_toggle_expand": lambda p: _on_toggle_expand(state, p),
        "on_change_tag": lambda p: _on_change_tag(state, p),
        "on_submit_comment": lambda p: _on_submit_comment(state, p),
        "on_delete_comment": lambda p: _on_delete_comment(state, p),
        "on_delete_highlight": lambda p: _on_delete_highlight(state, p),
        "on_edit_para_ref": lambda p: _on_edit_para_ref(state, p),
        "on_locate_highlight": lambda p: _on_locate_highlight(state, p),
    }


def _create_annotation_sidebar(state: PageState) -> Any:
    """Create an AnnotationSidebar with CRDT mutation handlers."""
    from promptgrimoire.pages.annotation.sidebar import (  # noqa: PLC0415
        AnnotationSidebar,
    )

    handlers = _make_sidebar_handlers(state)
    return AnnotationSidebar(
        doc_container_id=state.doc_container_id,
        **handlers,
    )


@dataclass(frozen=True, slots=True)
class DocumentRenderCallbacks:
    """Optional toolbar/menu callbacks and footer for document rendering."""

    on_add_click: Any | None = None
    on_manage_click: Any | None = None
    footer: Any | None = None


def _render_document_content(doc: Any) -> None:
    """Emit the paragraph-injected document HTML into the current slot.

    Non-snapshot path: the full document payload rides the NiceGUI
    element tree.
    """
    # Inject data-para attributes for paragraph number margin display.
    # paragraph_map comes from WorkspaceDocument; empty map is a no-op.
    para_map = getattr(doc, "paragraph_map", None) or {}
    _t = time.monotonic()
    rendered_html = inject_paragraph_attributes(doc.content, para_map)
    logger.debug(
        "render_phase",
        phase="inject_paragraph_attributes",
        elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
        content_len=len(doc.content),
        para_map_size=len(para_map),
    )
    _t = time.monotonic()
    ui.html(rendered_html, sanitize=False)
    logger.debug(
        "render_phase",
        phase="ui_html",
        elapsed_ms=round((time.monotonic() - _t) * 1000, 1),
        html_len=len(rendered_html),
    )


def _build_doc_container(state: PageState, doc: Any, *, use_snapshot: bool) -> None:
    """Build the document container: real content, or a snapshot skeleton.

    In snapshot mode the NiceGUI element tree never carries the document
    payload — the container is armed with data attributes and the
    standalone service delivers the bundle to the bootstrap JS.
    """
    container_classes = "doc-container"
    if hasattr(doc, "source_type") and doc.source_type == "text":
        container_classes += " source-text"
    doc_container = (
        ui.element("div")
        .classes(container_classes)
        .style("flex: 2; min-width: 600px; max-width: 900px;")
        .props(f'id="{state.doc_container_id}" data-testid="doc-container"')
    )
    state.doc_container = doc_container
    with doc_container:
        if use_snapshot:
            ui.label("Loading document…").props(
                'data-testid="snapshot-loading"'
            ).classes("text-gray-500")
        else:
            _render_document_content(doc)

    if use_snapshot:
        _arm_snapshot_container(state)
    else:
        _inject_highlight_scripts(state)


async def _render_document_with_highlights(
    state: PageState,
    doc: Any,
    crdt_doc: Any,
    callbacks: DocumentRenderCallbacks | None = None,
) -> None:
    """Render a document with highlight support."""
    from promptgrimoire.config import get_settings  # noqa: PLC0415, I001 -- lazy: matches sibling render helpers

    cb = callbacks or DocumentRenderCallbacks()
    _t_render = time.monotonic()
    use_snapshot = get_settings().snapshot.enabled
    _init_document_state(state, doc, crdt_doc)

    # Static ::highlight() CSS for all tags -- actual highlight ranges are
    # registered in CSS.highlights by JS applyHighlights()
    initial_css = _build_highlight_pseudo_css(state.tag_colours())

    # Dynamic style element for highlights
    state.highlight_style = ui.element("style")
    state.highlight_style._props["innerHTML"] = initial_css

    # Tag toolbar handler
    async def handle_tag_click(tag_key: str) -> None:
        await _add_highlight(state, tag_key)

    # Tag toolbar — only for users who can annotate
    if state.can_annotate:
        state.toolbar_container = _build_tag_toolbar(
            state.tag_info_list or [],
            handle_tag_click,
            on_add_click=cb.on_add_click,
            on_manage_click=cb.on_manage_click,
            footer=cb.footer,
        )

    # Highlight creation menu (popup with abbreviated tag buttons)
    # Only built for users who can annotate
    if state.can_annotate:
        _build_highlight_menu(state, handle_tag_click, on_add_click=cb.on_add_click)

    # Two-column layout: document (70%) + sidebar (30%)
    # Takes up 80-90% of screen width for comfortable reading
    # When using Quasar footer, q-page handles padding automatically.
    # Fallback: manual padding-bottom for fixed-position toolbar.
    pb = "" if cb.footer is not None else "padding-bottom: 60px; "
    layout_wrapper = (
        ui.element("div")
        .props(f'id="ann-layout-{doc.id}"')
        .classes("annotation-layout-wrapper")
        .style(
            "position: relative; display: flex; gap: 1.5rem; "
            f"width: 90%; max-width: 1600px; margin: 0 auto; {pb}"
            "min-height: calc(100vh - 250px);"
        )
    )
    with layout_wrapper:
        # Document content - proper readable width (~65% of layout)
        # Needs ID for scroll-sync JavaScript positioning
        # Add source-text class for monospace rendering of plain text
        _build_doc_container(state, doc, use_snapshot=use_snapshot)

        # Annotations sidebar (~35% of layout) — Vue component
        state.annotations_container = (
            ui.element("div")
            .classes("annotations-sidebar")
            .style("flex: 1; min-width: 300px; max-width: 450px;")
            .props(f'id="{state.ann_container_id}"')
        )
        with state.annotations_container:
            sidebar = _create_annotation_sidebar(state)

    # Set up refresh function via the Vue sidebar.
    # WARNING: this closure is NOT saved/restored on tab switch —
    # each source tab render overwrites it. It works because
    # sidebar.refresh_from_state reads state dynamically.
    def refresh_annotations(*, trigger: str = "unknown") -> None:
        logger.debug("refresh_annotations", trigger=trigger)
        sidebar.refresh_from_state(state)

    state.refresh_annotations = refresh_annotations

    # Push initial items to the Vue sidebar.  In snapshot mode the bundle
    # carries the initial items; the first genuine server push (any later
    # refresh) then becomes authoritative in the component.
    _t_cards = time.monotonic()
    if not use_snapshot:
        sidebar.refresh_from_state(state)
    _t_cards_done = time.monotonic()

    # Set up selection detection (viewers get read-only view)
    if state.can_annotate:
        _setup_selection_handlers(state)

    _t_render_done = time.monotonic()
    _ms = round((_t_render_done - _t_render) * 1000, 1)
    _pre_cards_ms = round((_t_cards - _t_render) * 1000, 1)
    _cards_ms = round((_t_cards_done - _t_cards) * 1000, 1)
    _post_cards_ms = round((_t_render_done - _t_cards_done) * 1000, 1)
    logger.info(
        "document_render_profile",
        total_ms=_ms,
        pre_cards_ms=_pre_cards_ms,
        cards_ms=_cards_ms,
        post_cards_ms=_post_cards_ms,
        document_id=str(state.document_id),
    )
