"""Document rendering and selection wiring for the annotation page.

Handles rendering a WorkspaceDocument with highlight support,
setting up JS-based text selection detection, and keyboard shortcuts.
"""

from __future__ import annotations

import time
from html import escape
from typing import Any

import structlog
from nicegui import ui

from promptgrimoire.input_pipeline.html_input import extract_text_from_html
from promptgrimoire.input_pipeline.paragraph_map import inject_paragraph_attributes
from promptgrimoire.pages.annotation import PageState, _RawJS, _render_js
from promptgrimoire.pages.annotation.cards import _refresh_annotation_cards
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
    state.annotation_cards = {}
    state.card_snapshots = {}

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
    ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')
    ui.add_body_html('<script src="/static/annotation-card-sync.js"></script>')
    ui.add_body_html('<script src="/static/annotation-copy-protection.js"></script>')

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
        t"    setupCardPositioning("
        t"      {state.doc_container_id}, {state.ann_container_id}, 8);"
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


async def _render_document_with_highlights(
    state: PageState,
    doc: Any,
    crdt_doc: Any,
    *,
    on_add_click: Any | None = None,
    on_manage_click: Any | None = None,
    footer: Any | None = None,
) -> None:
    """Render a document with highlight support."""
    _t_render = time.monotonic()
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
            on_add_click=on_add_click,
            on_manage_click=on_manage_click,
            footer=footer,
        )

    # Highlight creation menu (popup with abbreviated tag buttons)
    # Only built for users who can annotate
    if state.can_annotate:
        _build_highlight_menu(state, handle_tag_click, on_add_click=on_add_click)

    # Two-column layout: document (70%) + sidebar (30%)
    # Takes up 80-90% of screen width for comfortable reading
    # When using Quasar footer, q-page handles padding automatically.
    # Fallback: manual padding-bottom for fixed-position toolbar.
    pb = "" if footer is not None else "padding-bottom: 60px; "
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

        _inject_highlight_scripts(state)

        # Annotations sidebar (~35% of layout)
        # Needs ID for scroll-sync JavaScript positioning
        state.annotations_container = (
            ui.element("div")
            .classes("annotations-sidebar")
            .style("flex: 1; min-width: 300px; max-width: 450px;")
            .props(f'id="{state.ann_container_id}"')
        )

    # Set up refresh function.
    # WARNING: this closure is NOT saved/restored on tab switch — each
    # source tab render overwrites it.  It works because it reads
    # state.annotations_container dynamically at call time (restored by
    # _restore_source_tab_state).  Do NOT refactor to capture the
    # container at closure creation time — that would silently target
    # the wrong document after a tab switch.
    def refresh_annotations(*, trigger: str = "unknown") -> None:
        _refresh_annotation_cards(state, trigger=trigger)

    state.refresh_annotations = refresh_annotations

    # Load existing annotations
    _t_cards = time.monotonic()
    _refresh_annotation_cards(state, trigger="initial_load")
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
        highlight_count=len(state.annotation_cards or {}),
        document_id=str(state.document_id),
    )

    # Card positioning is set up inside init_js (see _inject_highlight_scripts)
    # to guarantee annotation-card-sync.js is loaded before the call.
    # Do NOT add a standalone ui.run_javascript("setupCardPositioning(...)") here —
    # it races with the async script fetch in deferred-load contexts.
