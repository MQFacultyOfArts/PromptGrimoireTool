"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT

Route: /annotation
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.workspace_documents import add_document, list_documents
from promptgrimoire.db.workspaces import create_workspace, get_workspace
from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.models.case import TAG_COLORS, TAG_SHORTCUTS, BriefTag
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)

# Global registry for workspace annotation documents
_workspace_registry = AnnotationDocumentRegistry()

# CSS styles matching live_annotation_demo.py for consistent UX
_PAGE_CSS = """
    /* Document container */
    .doc-container {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        line-height: 1.6;
        padding: 1rem;
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
    }

    /* Compact tag toolbar in header */
    .tag-toolbar-compact {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        justify-content: center;
    }

    /* Compact buttons */
    .compact-btn {
        padding: 2px 8px !important;
        min-height: 24px !important;
        font-size: 11px !important;
    }

    /* Annotation sidebar - relative container for positioned cards */
    .annotations-sidebar {
        position: relative !important;
        min-height: 100%;
    }

    /* Annotation cards - absolutely positioned within sidebar */
    .ann-card-positioned {
        left: 0;
        right: 0;
        border-radius: 4px;
        padding: 8px 12px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: top 0.15s ease-out, box-shadow 0.2s;
    }
    .ann-card-positioned:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    /* Word spans for selection - smooth highlighting between words */
    .word {
        cursor: text;
        /* Extend background to cover inter-word gaps */
        padding: 0 0.15em;
        margin: 0 -0.15em;
        /* Ensure highlights blend smoothly */
        box-decoration-break: clone;
        -webkit-box-decoration-break: clone;
    }
"""


@dataclass
class PageState:
    """Per-page state for annotation workspace."""

    workspace_id: UUID
    document_id: UUID | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    user_name: str = "Anonymous"
    # UI elements set during page build
    highlight_style: ui.element | None = None
    highlight_menu: ui.element | None = None
    save_status: ui.label | None = None
    crdt_doc: AnnotationDocument | None = None
    # Annotation cards
    annotations_container: ui.element | None = None
    annotation_cards: dict[str, ui.card] | None = None
    refresh_annotations: Any | None = None  # Callable to refresh cards
    # Document content for text extraction
    document_words: list[str] | None = None  # Words by index


def _get_current_username() -> str:
    """Get the display name for the current user."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user:
        if auth_user.get("display_name"):
            return auth_user["display_name"]
        if auth_user.get("email"):
            return auth_user["email"].split("@")[0]
    return "Anonymous"


async def _create_workspace_and_redirect() -> None:
    """Create a new workspace and redirect to it.

    Requires authenticated user (auth check only, no user ID stored on workspace).
    """
    auth_user = app.storage.user.get("auth_user")
    if not auth_user:
        ui.notify("Please log in to create a workspace", type="warning")
        ui.navigate.to("/login")
        return

    try:
        workspace = await create_workspace()
        logger.info("Created workspace %s", workspace.id)
        ui.navigate.to(f"/annotation?{urlencode({'workspace_id': str(workspace.id)})}")
    except Exception:
        logger.exception("Failed to create workspace")
        ui.notify("Failed to create workspace", type="negative")


def _process_text_to_word_spans(text: str) -> str:
    """Convert plain text to HTML with word-level spans.

    Each word gets a span with data-word-index attribute for annotation targeting.
    """
    lines = text.split("\n")
    html_parts = []
    word_index = 0

    for line_num, line in enumerate(lines):
        if line.strip():
            words = line.split()
            line_spans = []
            for word in words:
                escaped = html.escape(word)
                span = (
                    f'<span class="word" data-word-index="{word_index}">'
                    f"{escaped}</span>"
                )
                line_spans.append(span)
                word_index += 1
            html_parts.append(f'<p data-para="{line_num}">{" ".join(line_spans)}</p>')
        else:
            html_parts.append(f'<p data-para="{line_num}">&nbsp;</p>')

    return "\n".join(html_parts)


def _build_highlight_css(highlights: list[dict[str, Any]]) -> str:
    """Generate CSS rules for highlighting words with tag-specific colors.

    Args:
        highlights: List of highlight dicts with start_word, end_word, tag.

    Returns:
        CSS string with background-color rules for highlighted words.
    """
    css_rules: list[str] = []
    for hl in highlights:
        start = int(hl.get("start_word", 0))
        end = int(hl.get("end_word", 0))
        tag_str = hl.get("tag", "highlight")

        # Get color for tag - try BriefTag first, fall back to yellow
        try:
            tag = BriefTag(tag_str)
            hex_color = TAG_COLORS.get(tag, "#FFEB3B")
        except ValueError:
            hex_color = "#FFEB3B"  # Default yellow for non-BriefTag tags

        # Convert hex to rgba with 40% opacity
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        rgba = f"rgba({r}, {g}, {b}, 0.4)"

        for i in range(start, end):
            css_rules.append(f'[data-word-index="{i}"] {{ background-color: {rgba}; }}')

    return "\n".join(css_rules)


def _setup_page_styles() -> None:
    """Add CSS and register custom tag colors."""
    ui.add_css(_PAGE_CSS)

    # Register custom colors for tag buttons (matching live_annotation_demo.py)
    custom_tag_colors = {
        tag.value.replace("_", "-"): color for tag, color in TAG_COLORS.items()
    }
    ui.colors(**custom_tag_colors)


def _build_tag_toolbar(
    on_tag_click: Any,  # Callable[[BriefTag], Awaitable[None]]
) -> None:
    """Build fixed tag toolbar.

    Ported from live_annotation_demo.py - uses fixed position for floating toolbar.
    Uses a div with fixed positioning instead of ui.header() to allow nesting.
    """
    with (
        ui.element("div")
        .classes("bg-gray-100 py-2 px-4")
        .style(
            "position: fixed; top: 0; left: 0; right: 0; z-index: 100; "
            "box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
        ),
        ui.row()
        .classes("tag-toolbar-compact w-full")
        .props('data-testid="tag-toolbar"'),
    ):
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}"

            # Create handler with tag bound
            async def apply_tag(t: BriefTag = tag) -> None:
                await on_tag_click(t)

            # Use registered color name (tag.value with underscores replaced by dashes)
            color_name = tag.value.replace("_", "-")
            ui.button(label, on_click=apply_tag, color=color_name).classes(
                "text-xs compact-btn"
            )


def _update_highlight_css(state: PageState) -> None:
    """Update the highlight CSS based on current CRDT state."""
    if state.highlight_style is None or state.crdt_doc is None:
        return

    if state.document_id is not None:
        highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))
    else:
        highlights = state.crdt_doc.get_all_highlights()

    css = _build_highlight_css(highlights)
    state.highlight_style._props["innerHTML"] = css
    state.highlight_style.update()


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
    text = highlight.get("text", "")[:80]
    if len(highlight.get("text", "")) > 80:
        text += "..."

    # Get word positions for scroll-sync positioning
    start_word = highlight.get("start_word", 0)
    end_word = highlight.get("end_word", start_word)

    # Get para_ref if stored
    para_ref = highlight.get("para_ref", "")

    # Get tag color
    try:
        tag = BriefTag(tag_str)
        color = TAG_COLORS.get(tag, "#666")
        tag_name = tag.value.replace("_", " ").title()
    except ValueError:
        color = "#666"
        tag_name = tag_str.replace("_", " ").title()

    # Use ann-card-positioned for scroll-sync positioning (like live_annotation_demo)
    card = (
        ui.card()
        .classes("ann-card-positioned")
        .style(f"border-left: 4px solid {color};")
        .props(
            f'data-testid="annotation-card" data-highlight-id="{highlight_id}" '
            f'data-start-word="{start_word}" data-end-word="{end_word}"'
        )
    )

    with card:
        # Header with tag name and action buttons
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(tag_name).classes("text-sm font-bold").style(f"color: {color};")

            with ui.row().classes("gap-1"):
                # Go-to-highlight button - scrolls to highlight and flashes it
                async def goto_highlight(
                    sw: int = start_word, ew: int = end_word
                ) -> None:
                    # fmt: off
                    # Flash ALL words in the highlight range, not just start
                    js = (
                        f"(function(){{"
                        f"const sw={sw},ew={ew};"
                        f"const words=[];"
                        f"for(let i=sw;i<ew;i++){{"
                        f"const w=document.querySelector("
                        f"'[data-word-index=\"'+i+'\"]');"
                        f"if(w)words.push(w);"
                        f"}}"
                        f"if(words.length===0)return;"
                        f"words[0].scrollIntoView({{behavior:'smooth',block:'center'}});"
                        f"const origColors=words.map(w=>w.style.backgroundColor);"
                        f"words.forEach(w=>{{"
                        f"w.style.transition='background-color 0.2s';"
                        f"w.style.backgroundColor='#FFD700';"
                        f"}});"
                        f"setTimeout(()=>{{"
                        f"words.forEach((w,i)=>{{w.style.backgroundColor=origColors[i];}});"
                        f"}},800);"
                        f"}})()"
                    )
                    # fmt: on
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

        # Highlighted text preview
        if text:
            ui.label(f'"{text}"').classes("text-sm italic mt-1")

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


async def _add_highlight(state: PageState, tag: BriefTag | None = None) -> None:
    """Add a highlight from current selection to CRDT.

    Args:
        state: Page state with selection and CRDT document.
        tag: Optional BriefTag for the highlight. Defaults to "highlight".
    """
    logger.debug(
        "[HIGHLIGHT] called: start=%s, end=%s, tag=%s",
        state.selection_start,
        state.selection_end,
        tag,
    )
    if state.selection_start is None or state.selection_end is None:
        logger.debug("[HIGHLIGHT] No selection - returning early")
        ui.notify("No selection", type="warning")
        return

    if state.document_id is None:
        ui.notify("No document", type="warning")
        return

    if state.crdt_doc is None:
        ui.notify("CRDT not initialized", type="warning")
        return

    # Update status to show saving
    if state.save_status:
        state.save_status.text = "Saving..."

    # Add highlight to CRDT (end_word is exclusive)
    start = min(state.selection_start, state.selection_end)
    end = max(state.selection_start, state.selection_end) + 1

    # Use tag value if provided, otherwise default to "highlight"
    tag_value = tag.value if tag else "highlight"

    # Extract highlighted text from document words
    highlighted_text = ""
    if state.document_words:
        words_slice = state.document_words[start:end]
        highlighted_text = " ".join(words_slice)

    state.crdt_doc.add_highlight(
        start_word=start,
        end_word=end,
        tag=tag_value,
        text=highlighted_text,
        author=state.user_name,
        document_id=str(state.document_id),
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

    # Clear browser selection first to prevent re-triggering on next mouseup
    await ui.run_javascript("window.getSelection().removeAllRanges();")

    # Clear selection state and hide menu
    state.selection_start = None
    state.selection_end = None
    if state.highlight_menu:
        state.highlight_menu.set_visibility(False)


def _setup_selection_handlers(state: PageState) -> None:
    """Set up JavaScript-based selection detection and event handlers.

    Note: Per Key Design Decision #5 in the phase plan, detecting browser text
    selection inherently requires JavaScript. The implementation uses
    ui.run_javascript() for this unavoidable browser API access. E2E tests
    correctly use Playwright's native mouse events to simulate user selection.
    """

    async def on_selection(e: Any) -> None:
        """Handle selection event from JavaScript."""
        state.selection_start = e.args.get("start")
        state.selection_end = e.args.get("end")
        if state.highlight_menu:
            state.highlight_menu.set_visibility(True)

    async def on_selection_cleared(_e: Any) -> None:
        """Handle selection cleared event."""
        state.selection_start = None
        state.selection_end = None
        if state.highlight_menu:
            state.highlight_menu.set_visibility(False)

    ui.on("selection_made", on_selection)
    ui.on("selection_cleared", on_selection_cleared)

    # Keyboard shortcut handler (1-0 keys map to tags)
    async def on_keydown(e: Any) -> None:
        """Handle keyboard shortcut for tag selection."""
        key = e.args.get("key")
        if key and key in TAG_SHORTCUTS:
            tag = TAG_SHORTCUTS[key]
            await _add_highlight(state, tag)

    ui.on("keydown", on_keydown)

    # JavaScript to detect text selection via selectionchange and mouseup
    # Wrapped in setTimeout to ensure DOM is ready and emitEvent is available
    js_code = """
    setTimeout(function() {
        function processSelection() {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
                return;
            }

            const range = selection.getRangeAt(0);

            // Find all word spans that intersect with the selection
            // This is more robust than checking start/end containers
            const allWordSpans = document.querySelectorAll('[data-word-index]');
            let minWord = Infinity;
            let maxWord = -Infinity;

            for (const span of allWordSpans) {
                if (range.intersectsNode(span)) {
                    const wordIdx = parseInt(span.dataset.wordIndex);
                    minWord = Math.min(minWord, wordIdx);
                    maxWord = Math.max(maxWord, wordIdx);
                }
            }

            if (minWord !== Infinity && maxWord !== -Infinity) {
                emitEvent('selection_made', {
                    start: minWord,
                    end: maxWord
                });
            }
        }

        // Listen for selectionchange (handles click+shift+click)
        document.addEventListener('selectionchange', function() {
            const selection = window.getSelection();
            if (selection && !selection.isCollapsed) {
                processSelection();
            }
        });

        // Also listen for mouseup (handles drag selection)
        document.addEventListener('mouseup', function() {
            setTimeout(processSelection, 10);
        });

        // Clear selection on click (but not on toolbar)
        document.addEventListener('click', function(e) {
            // Don't clear selection when clicking toolbar buttons
            if (e.target.closest('[data-testid="tag-toolbar"]')) {
                return;
            }
            // Small delay to check if selection was cleared by this click
            setTimeout(function() {
                const selection = window.getSelection();
                if (!selection || selection.isCollapsed) {
                    emitEvent('selection_cleared', {});
                }
            }, 50);
        });

        // Keyboard shortcuts (1-0 keys for tags)
        // Debounce to prevent duplicate events
        let lastKeyTime = 0;
        document.addEventListener('keydown', function(e) {
            // Ignore held keys and rapid repeats
            if (e.repeat) return;
            const now = Date.now();
            if (now - lastKeyTime < 300) return;
            lastKeyTime = now;
            if (['1','2','3','4','5','6','7','8','9','0'].includes(e.key)) {
                emitEvent('keydown', { key: e.key });
            }
        });
    }, 100);
    """
    ui.run_javascript(js_code)


async def _render_document_with_highlights(
    state: PageState,
    doc: Any,
    crdt_doc: AnnotationDocument,
) -> None:
    """Render a document with highlight support."""
    state.document_id = doc.id
    state.crdt_doc = crdt_doc
    state.annotation_cards = {}

    # Extract words from raw_content for text extraction when highlighting
    if hasattr(doc, "raw_content") and doc.raw_content:
        state.document_words = doc.raw_content.split()

    # Load existing highlights and build initial CSS
    highlights = crdt_doc.get_highlights_for_document(str(doc.id))
    initial_css = _build_highlight_css(highlights)

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
        "width: 90%; max-width: 1600px; margin: 0 auto; padding-top: 60px;"
    )
    with layout_wrapper:
        # Document content - proper readable width (~65% of layout)
        # Needs ID for scroll-sync JavaScript positioning
        doc_container = (
            ui.element("div")
            .classes("doc-container")
            .style("flex: 2; min-width: 600px; max-width: 900px;")
            .props('id="doc-container"')
        )
        with doc_container:
            ui.html(doc.content, sanitize=False)

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

    # Set up scroll-synced card positioning (adapted from live-annotation.js)
    # fmt: off
    scroll_sync_js = (
        "(function() {\n"
        "  const docC = document.getElementById('doc-container');\n"
        "  const annC = document.getElementById('annotations-container');\n"
        "  if (!docC || !annC) return;\n"
        "  const MIN_GAP = 8;\n"
        "  function positionCards() {\n"
        "    const cards = Array.from(annC.querySelectorAll('[data-start-word]'));\n"
        "    if (cards.length === 0) return;\n"
        "    const docRect = docC.getBoundingClientRect();\n"
        "    const annRect = annC.getBoundingClientRect();\n"
        "    const containerOffset = annRect.top - docRect.top;\n"
        "    const cardInfos = cards.map(card => {\n"
        "      const sw = parseInt(card.dataset.startWord);\n"
        "      const ws = docC.querySelector('[data-word-index=\"'+sw+'\"]');\n"
        "      if (!ws) return null;\n"
        "      const wr = ws.getBoundingClientRect();\n"
        "      return { card, startWord: sw, height: card.offsetHeight,\n"
        "               targetY: (wr.top-docRect.top)-containerOffset };\n"
        "    }).filter(Boolean);\n"
        "    cardInfos.sort((a, b) => a.startWord - b.startWord);\n"
        "    const headerHeight = 60;\n"
        "    const viewportTop = headerHeight;\n"
        "    const viewportBottom = window.innerHeight;\n"
        "    let minY = 0;\n"
        "    for (const info of cardInfos) {\n"
        "      const sw = info.startWord;\n"
        "      const ew = parseInt(info.card.dataset.endWord) || sw;\n"
        "      var qs='[data-word-index=\"'+sw+'\"]';\n"
        "      const startWS = docC.querySelector(qs);\n"
        "      var qe='[data-word-index=\"'+(ew-1)+'\"]';\n"
        "      const endWS = docC.querySelector(qe)||startWS;\n"
        "      if (!startWS || !endWS) continue;\n"
        "      const sr = startWS.getBoundingClientRect();\n"
        "      const er = endWS.getBoundingClientRect();\n"
        "      const inView = er.bottom > viewportTop && sr.top < viewportBottom;\n"
        "      info.card.style.position = 'absolute';\n"
        "      if (!inView) { info.card.style.display = 'none'; continue; }\n"
        "      info.card.style.display = '';\n"
        "      const y = Math.max(info.targetY, minY);\n"
        "      info.card.style.top = y + 'px';\n"
        "      minY = y + info.height + MIN_GAP;\n"
        "    }\n"
        "  }\n"
        "  let ticking = false;\n"
        "  function onScroll() {\n"
        "    if (!ticking) {\n"
        "      requestAnimationFrame(() => { positionCards(); ticking = false; });\n"
        "      ticking = true;\n"
        "    }\n"
        "  }\n"
        "  window.addEventListener('scroll', onScroll, { passive: true });\n"
        "  requestAnimationFrame(positionCards);\n"
        "  var rePos = () => requestAnimationFrame(positionCards);\n"
        "  const obs = new MutationObserver(rePos);\n"
        "  obs.observe(annC, { childList: true, subtree: true });\n"
        "})();"
    )
    # fmt: on
    ui.run_javascript(scroll_sync_js)


async def _render_workspace_view(workspace_id: UUID) -> None:
    """Render the workspace content view with documents or add content form."""
    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    # Create page state
    state = PageState(
        workspace_id=workspace_id,
        user_name=_get_current_username(),
    )

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

    # Header row with save status and export button
    with ui.row().classes("gap-4 items-center"):
        # Save status indicator (for E2E test observability)
        state.save_status = (
            ui.label("")
            .classes("text-sm text-gray-500")
            .props('data-testid="save-status"')
        )

        # Export PDF button (handler defined after state is populated)
        async def handle_export_pdf() -> None:
            if state.crdt_doc is None or state.document_id is None:
                ui.notify("No document to export", type="warning")
                return

            ui.notify("Generating PDF...", type="info")
            try:
                # Get tag colours as dict[str, str]
                tag_colours = {tag.value: colour for tag, colour in TAG_COLORS.items()}

                # Get highlights for this document
                highlights = state.crdt_doc.get_highlights_for_document(
                    str(state.document_id)
                )

                # Get document content (use raw_content if available)
                raw_content = ""
                if state.document_words:
                    raw_content = " ".join(state.document_words)

                # Generate PDF
                pdf_path = await export_annotation_pdf(
                    html_content=raw_content,
                    highlights=highlights,
                    tag_colours=tag_colours,
                    general_notes="",
                    word_to_legal_para=None,
                    filename=f"workspace_{workspace_id}",
                )

                # Trigger download
                ui.download(pdf_path)
                ui.notify("PDF generated!", type="positive")
            except Exception:
                logger.exception("Failed to export PDF")
                ui.notify("Failed to generate PDF", type="negative")

        ui.button(
            "Export PDF", icon="picture_as_pdf", on_click=handle_export_pdf
        ).props("color=primary")

    # Load CRDT document for this workspace
    crdt_doc = await _workspace_registry.get_or_create_for_workspace(workspace_id)

    # Load existing documents
    documents = await list_documents(workspace_id)

    if documents:
        # Render first document with highlight support
        doc = documents[0]
        await _render_document_with_highlights(state, doc, crdt_doc)
    else:
        # Show add content form
        ui.label("Add content to annotate:").classes("mt-4 font-semibold")

        content_input = ui.textarea(
            placeholder="Paste or type your content here..."
        ).classes("w-full min-h-32")

        async def handle_add_document() -> None:
            if not content_input.value or not content_input.value.strip():
                ui.notify("Please enter some content", type="warning")
                return

            try:
                html_content = _process_text_to_word_spans(content_input.value.strip())
                await add_document(
                    workspace_id=workspace_id,
                    type="source",
                    content=html_content,
                    raw_content=content_input.value.strip(),
                    title=None,
                )
                # Reload page to show document
                ui.navigate.to(
                    f"/annotation?{urlencode({'workspace_id': str(workspace_id)})}"
                )
            except Exception:
                logger.exception("Failed to add document")
                ui.notify("Failed to add document", type="negative")

        ui.button("Add Document", on_click=handle_add_document).classes(
            "bg-green-500 text-white mt-2"
        )


@page_route(
    "/annotation",
    title="Annotation Workspace",
    icon="edit_note",
    category="main",
    requires_auth=False,
    order=30,
)
async def annotation_page(client: Client) -> None:
    """Annotation workspace page.

    Query params:
        workspace_id: UUID of existing workspace to load
    """
    # Set up CSS and colors (matching live_annotation_demo.py)
    _setup_page_styles()

    # Get workspace_id from query params if present
    workspace_id_str = client.request.query_params.get("workspace_id")
    workspace_id: UUID | None = None

    if workspace_id_str:
        try:
            workspace_id = UUID(workspace_id_str)
        except ValueError:
            ui.notify("Invalid workspace ID", type="negative")

    with ui.column().classes("w-full p-4"):
        ui.label("Annotation Workspace").classes("text-2xl font-bold mb-4")

        if workspace_id:
            await _render_workspace_view(workspace_id)
        else:
            # Show create workspace form
            ui.label("No workspace selected. Create a new one:").classes("mb-2")
            ui.button(
                "Create Workspace",
                on_click=_create_workspace_and_redirect,
            ).classes("bg-blue-500 text-white")
