"""Document rendering and selection wiring for the annotation page.

Handles rendering a WorkspaceDocument with highlight support,
setting up JS-based text selection detection, and keyboard shortcuts.
"""

from __future__ import annotations

from html import escape
from typing import Any

from nicegui import ui

from promptgrimoire.input_pipeline.html_input import extract_text_from_html
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


def _setup_selection_handlers(state: PageState) -> None:
    """Set up JavaScript-based selection detection and event handlers.

    Note: Per Key Design Decision #5 in the phase plan, detecting browser text
    selection inherently requires JavaScript. The implementation uses
    ui.run_javascript() for this unavoidable browser API access. E2E tests
    correctly use Playwright's native mouse events to simulate user selection.
    """

    async def on_selection(e: Any) -> None:
        """Handle selection event from JavaScript."""
        state.selection_start = e.args.get("start_char")
        state.selection_end = e.args.get("end_char")
        if state.highlight_menu:
            state.highlight_menu.set_visibility(True)
        # Broadcast selection to other clients
        if state.broadcast_selection:
            await state.broadcast_selection(state.selection_start, state.selection_end)

    async def on_selection_cleared(_e: Any) -> None:
        """Handle selection cleared event."""
        state.selection_start = None
        state.selection_end = None
        if state.highlight_menu:
            state.highlight_menu.set_visibility(False)
        # Clear selection broadcast
        if state.broadcast_selection:
            await state.broadcast_selection(None, None)

    async def on_cursor_move(e: Any) -> None:
        """Handle cursor position change from JavaScript."""
        char_index = e.args.get("char")
        if state.broadcast_cursor:
            await state.broadcast_cursor(char_index)

    ui.on("selection_made", on_selection)
    ui.on("selection_cleared", on_selection_cleared)
    ui.on("cursor_move", on_cursor_move)

    # Keyboard shortcut handler (1-0 keys map to tags)
    async def on_keydown(e: Any) -> None:
        """Handle keyboard shortcut for tag selection."""
        key = e.args.get("key")
        if key and state.tag_info_list:
            key_to_index = {
                str((i + 1) % 10): i for i in range(min(10, len(state.tag_info_list)))
            }
            if key in key_to_index:
                ti = state.tag_info_list[key_to_index[key]]
                await _add_highlight(state, ti.raw_key)

    ui.on("keydown", on_keydown)

    # Selection detection is handled by setupAnnotationSelection() in the
    # init JS (loaded in _render_document_with_highlights). This remaining
    # JS handles: selection clearing on click and keyboard shortcuts.
    # Remote cursor tracking (Phase 5) will use the text walker.
    # fmt: off
    js_code = (
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
    ui.run_javascript(js_code)


def _populate_highlight_menu(state: PageState, on_tag_click: Any) -> None:
    """Populate the highlight menu card with abbreviated tag buttons.

    Clears existing content and rebuilds from ``state.tag_info_list``.
    Called on initial build and after tag list changes.
    """
    menu = state.highlight_menu
    if menu is None:
        return
    menu.clear()
    with menu:
        if state.tag_info_list:
            # Partition tags by group, preserving order
            groups: dict[str | None, list[Any]] = {}
            for ti in state.tag_info_list:
                groups.setdefault(ti.group_name, []).append(ti)

            with ui.column().classes("gap-1"):
                for members in groups.values():
                    with ui.row().classes("gap-1 items-center"):
                        for ti in members:
                            abbrev = ti.name[:6]

                            async def _apply(tag_key: str = ti.raw_key) -> None:
                                await on_tag_click(tag_key)

                            btn = ui.button(abbrev, on_click=_apply).classes(
                                "text-xs compact-btn"
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
        else:
            ui.label("No tags available").classes("text-sm text-gray-600")


def _build_highlight_menu(state: PageState, on_tag_click: Any) -> None:
    """Build the floating highlight menu card and populate it."""
    highlight_menu = (
        ui.card()
        .classes("fixed z-50 shadow-lg p-2")
        .props('data-testid="highlight-menu" id="highlight-menu"')
    )
    highlight_menu.set_visibility(False)
    state.highlight_menu = highlight_menu

    # Store callback for rebuilds triggered by _refresh_tag_state
    state._highlight_menu_tag_click = on_tag_click

    _populate_highlight_menu(state, on_tag_click)


async def _render_document_with_highlights(
    state: PageState,
    doc: Any,
    crdt_doc: Any,
    *,
    on_add_click: Any | None = None,
    on_manage_click: Any | None = None,
) -> None:
    """Render a document with highlight support."""
    state.document_id = doc.id
    state.crdt_doc = crdt_doc
    state.annotation_cards = {}

    # Extract characters from clean HTML for text extraction when highlighting
    # (char spans are injected client-side, not stored in DB)
    if doc.content:
        state.document_chars = extract_text_from_html(doc.content)

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
        )

    # Highlight creation menu (popup with abbreviated tag buttons)
    # Only built for users who can annotate
    if state.can_annotate:
        _build_highlight_menu(state, handle_tag_click)

    # Two-column layout: document (70%) + sidebar (30%)
    # Takes up 80-90% of screen width for comfortable reading
    # Add padding-top to account for fixed toolbar (approx 50px height)
    layout_wrapper = ui.element("div").style(
        "position: relative; display: flex; gap: 1.5rem; "
        "width: 90%; max-width: 1600px; margin: 0 auto; padding-top: 60px; "
        "min-height: calc(100vh - 250px);"
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
            .props('id="doc-container"')
        )
        with doc_container:
            ui.html(doc.content, sanitize=False)

        # Load annotation-highlight.js for CSS Custom Highlight API support.
        # This script provides walkTextNodes(), applyHighlights(),
        # clearHighlights(), and setupAnnotationSelection().
        #
        # add_body_html injects into the initial HTML template served on
        # full page loads.  On SPA navigations (ui.navigate.to) the script
        # tags are NOT added to the already-loaded DOM, so we also load
        # them dynamically as a fallback.
        ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')
        ui.add_body_html('<script src="/static/annotation-card-sync.js"></script>')
        ui.add_body_html(
            '<script src="/static/annotation-copy-protection.js"></script>'
        )

        # Initialise text walker, apply highlights, and set up selection
        # detection after scripts are loaded.  The dynamic loader handles
        # SPA navigations where add_body_html scripts are absent.
        highlight_json = _RawJS(_build_highlight_json(state))
        init_js = _render_js(
            t"(function() {{"
            t"  var SCRIPTS = ["
            t"    '/static/annotation-highlight.js',"
            t"    '/static/annotation-card-sync.js',"
            t"    '/static/annotation-copy-protection.js'"
            t"  ];"
            t"  function init() {{"
            t"    var c = document.getElementById('doc-container');"
            t"    if (!c) return;"
            t"    window._textNodes = walkTextNodes(c);"
            t"    applyHighlights(c, {highlight_json});"
            t"    setupAnnotationSelection('doc-container', function(sel) {{"
            t"      emitEvent('selection_made', sel);"
            t"    }});"
            t"    if (window._pendingCopyProtection) {{"
            t"      setupCopyProtection(window._pendingCopyProtection);"
            t"      delete window._pendingCopyProtection;"
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

        # Annotations sidebar (~35% of layout)
        # Needs ID for scroll-sync JavaScript positioning
        state.annotations_container = (
            ui.element("div")
            .classes("annotations-sidebar")
            .style("flex: 1; min-width: 300px; max-width: 450px;")
            .props('id="annotations-container"')
        )

    # Set up refresh function
    def refresh_annotations() -> None:
        _refresh_annotation_cards(state)

    state.refresh_annotations = refresh_annotations

    # Load existing annotations
    _refresh_annotation_cards(state)

    # Set up selection detection (viewers get read-only view)
    if state.can_annotate:
        _setup_selection_handlers(state)

    # Set up scroll-synced card positioning and hover interaction
    # (loaded from static/annotation-card-sync.js)
    ui.run_javascript(
        "setupCardPositioning('doc-container', 'annotations-container', 8)"
    )
