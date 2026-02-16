"""Document rendering and selection wiring for the annotation page.

Handles rendering a WorkspaceDocument with highlight support,
setting up JS-based text selection detection, and keyboard shortcuts.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from promptgrimoire.input_pipeline.html_input import extract_text_from_html
from promptgrimoire.models.case import TAG_SHORTCUTS, BriefTag
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
        if key and key in TAG_SHORTCUTS:
            tag = TAG_SHORTCUTS[key]
            await _add_highlight(state, tag)

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


async def _render_document_with_highlights(
    state: PageState,
    doc: Any,
    crdt_doc: Any,
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
    initial_css = _build_highlight_pseudo_css()

    # Dynamic style element for highlights
    state.highlight_style = ui.element("style")
    state.highlight_style._props["innerHTML"] = initial_css

    # Tag toolbar handler
    async def handle_tag_click(tag: BriefTag) -> None:
        await _add_highlight(state, tag)

    # Tag toolbar - always visible above document
    _build_tag_toolbar(handle_tag_click)

    # Highlight creation menu (hidden popup for quick highlight without tag selection)
    with (
        ui.card()
        .classes("fixed z-50 shadow-lg p-2")
        .style("top: 50%; left: 50%; transform: translate(-50%, -50%);")
        .props('data-testid="highlight-menu"') as highlight_menu
    ):
        highlight_menu.set_visibility(False)
        state.highlight_menu = highlight_menu

        ui.label("Select a tag above to highlight").classes("text-sm text-gray-600")

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
        ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')
        ui.add_body_html('<script src="/static/annotation-card-sync.js"></script>')
        ui.add_body_html(
            '<script src="/static/annotation-copy-protection.js"></script>'
        )

        # Initialise text walker, apply highlights, and set up selection
        # detection after DOM is ready. Uses setTimeout to ensure the script
        # has loaded and the HTML element is rendered.
        highlight_json = _RawJS(_build_highlight_json(state))
        init_js = _render_js(
            t"setTimeout(function() {{"
            t"  const c = document.getElementById('doc-container');"
            t"  if (!c) return;"
            t"  window._textNodes = walkTextNodes(c);"
            t"  applyHighlights(c, {highlight_json});"
            t"  setupAnnotationSelection('doc-container', function(sel) {{"
            t"    emitEvent('selection_made', sel);"
            t"  }});"
            t"}}, 100);"
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

    # Set up selection detection
    _setup_selection_handlers(state)

    # Set up scroll-synced card positioning and hover interaction
    # (loaded from static/annotation-card-sync.js)
    ui.run_javascript(
        "setupCardPositioning('doc-container', 'annotations-container', 8)"
    )
