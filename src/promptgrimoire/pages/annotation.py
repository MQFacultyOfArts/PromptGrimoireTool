"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT

Route: /annotation

Pattern: Mixed (needs refactoring)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from string.templatelib import Interpolation, Template
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode
from uuid import UUID, uuid4

from nicegui import app, events, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.activities import list_activities_for_week
from promptgrimoire.db.courses import list_courses, list_user_enrollments
from promptgrimoire.db.weeks import list_weeks
from promptgrimoire.db.workspace_documents import (
    add_document,
    get_document,
    list_documents,
)
from promptgrimoire.db.workspaces import (
    PlacementContext,
    create_workspace,
    get_placement_context,
    get_workspace,
    make_workspace_loose,
    place_workspace_in_activity,
    place_workspace_in_course,
)
from promptgrimoire.export.pdf_export import (
    export_annotation_pdf,
    markdown_to_latex_notes,
)
from promptgrimoire.input_pipeline.html_input import (
    ContentType,
    detect_content_type,
    extract_text_from_html,
    process_input,
)
from promptgrimoire.models.case import TAG_COLORS, TAG_SHORTCUTS, BriefTag
from promptgrimoire.pages.annotation_organise import render_organise_tab
from promptgrimoire.pages.annotation_respond import render_respond_tab
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info
from promptgrimoire.pages.dialogs import show_content_type_dialog
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

    from promptgrimoire.pages.annotation_tags import TagInfo

logger = logging.getLogger(__name__)

# Global registry for workspace annotation documents
_workspace_registry = AnnotationDocumentRegistry()


@dataclass
class _RemotePresence:
    """Lightweight presence state for a connected client."""

    name: str
    color: str
    nicegui_client: (
        Any  # NiceGUI Client not publicly exported; revisit when type stubs added
    )
    callback: (
        Any  # Callable[[], Awaitable[None]] — ty cannot validate closure signatures
    )
    cursor_char: int | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    has_milkdown_editor: bool = False


# Track connected clients per workspace for broadcasting
# workspace_id -> {client_id -> _RemotePresence}
_workspace_presence: dict[str, dict[str, _RemotePresence]] = {}


class _RawJS:
    """Pre-serialised JavaScript literal — bypasses ``_render_js`` escaping.

    Use for values already serialised by ``json.dumps()`` that must appear
    as-is in the JS output (e.g. JSON objects passed to ``applyHighlights()``).
    """

    __slots__ = ("_js",)

    def __init__(self, js: str) -> None:
        self._js = js

    def __str__(self) -> str:
        return self._js


def _render_js(template: Template) -> str:
    """Render a t-string as JavaScript, escaping interpolated values.

    Strings are JSON-encoded (handles quotes, backslashes, unicode).
    Numbers pass through as literals. None becomes ``null``.
    Booleans become ``true`` / ``false``.
    ``_RawJS`` values pass through without encoding (pre-serialised JSON).
    """
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Interpolation):
            val = item.value
            if isinstance(val, _RawJS):
                parts.append(val._js)
            elif isinstance(val, bool):
                parts.append("true" if val else "false")
            elif isinstance(val, int | float):
                parts.append(str(val))
            elif val is None:
                parts.append("null")
            else:
                parts.append(json.dumps(str(val)))
    return "".join(parts)


# Background tasks set - prevents garbage collection of fire-and-forget tasks
_background_tasks: set[asyncio.Task[None]] = set()

# CSS styles for annotation interface
_PAGE_CSS = """
    /* Document container */
    .doc-container {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        line-height: 1.6 !important;
        padding: 1rem;
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        /* Allow horizontal scroll for wide content (tables) */
        overflow-x: auto;
    }

    /* Tables: proper table layout, container handles overflow */
    .doc-container table {
        border-collapse: collapse;
        margin: 1em 0;
    }
    .doc-container td,
    .doc-container th {
        vertical-align: top;
        padding: 4px 8px;
        /* Allow text to wrap in cells */
        word-wrap: break-word;
        overflow-wrap: break-word;
    }

    /* Lists: ensure proper rendering */
    .doc-container ol,
    .doc-container ul {
        margin: 0.5em 0;
        padding-left: 2em;
    }
    .doc-container ol {
        list-style-type: decimal;
    }
    .doc-container ul {
        list-style-type: disc;
    }
    .doc-container li {
        margin: 0.25em 0;
        display: list-item;
    }

    /* Paragraphs */
    .doc-container p {
        margin: 0.5em 0;
    }

    /* Normalize headings - prevent oversized inherited styles */
    .doc-container h1 {
        font-size: 1.5em;
        font-weight: bold;
        margin: 1em 0 0.5em 0;
    }
    .doc-container h2 {
        font-size: 1.3em;
        font-weight: bold;
        margin: 0.8em 0 0.4em 0;
    }
    .doc-container h3 {
        font-size: 1.15em;
        font-weight: bold;
        margin: 0.6em 0 0.3em 0;
    }
    .doc-container h4,
    .doc-container h5,
    .doc-container h6 {
        font-size: 1em;
        font-weight: bold;
        margin: 0.5em 0 0.25em 0;
    }

    /* Blockquotes */
    .doc-container blockquote {
        border-left: 3px solid #ccc;
        padding-left: 1em;
        margin: 1em 0 1em 0.5em;
        color: #444;
    }

    /* Preformatted/code blocks */
    .doc-container pre {
        background: #f5f5f5;
        border: 1px solid #ddd;
        border-radius: 3px;
        padding: 0.8em;
        overflow-x: auto;
        white-space: pre;
        font-family: "Courier New", Courier, monospace;
        font-size: 0.9em;
        line-height: 1.4 !important;
    }
    .doc-container code {
        font-family: "Courier New", Courier, monospace;
        font-size: 0.9em;
    }

    /* Speaker turn markers for chatbot exports (data-speaker attribute) */
    .doc-container [data-speaker] {
        display: block;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    .doc-container [data-speaker="user"]::before {
        content: "User:";
        display: inline-block;
        color: #1a5f7a;
        background: #e3f2fd;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: bold;
        margin-bottom: 0.3em;
    }
    .doc-container [data-speaker="assistant"]::before {
        content: "Assistant:";
        display: inline-block;
        color: #2e7d32;
        background: #e8f5e9;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: bold;
        margin-bottom: 0.3em;
    }

    /* Thinking block indicators (Claude thinking) */
    .doc-container [data-thinking] {
        color: #888;
        font-style: italic;
        font-size: 0.9em;
    }

    /* Plain text documents use monospace */
    .doc-container.source-text {
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
            "Liberation Mono", monospace;
        font-size: 11pt;
        white-space: pre-wrap;
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

    /* Remote cursor indicators */
    .remote-cursor {
        position: absolute;
        width: 2px;
        pointer-events: none;
        z-index: 20;
        transition: left 0.15s ease, top 0.15s ease;
    }
    .remote-cursor-label {
        position: absolute;
        top: -1.4em;
        left: -2px;
        font-size: 0.6rem;
        color: white;
        padding: 1px 4px;
        border-radius: 2px;
        white-space: nowrap;
        pointer-events: none;
        opacity: 0.9;
    }

"""


@dataclass
class PageState:
    """Per-page state for annotation workspace."""

    workspace_id: UUID
    client_id: str = ""  # Unique ID for this client connection
    document_id: UUID | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    user_name: str = "Anonymous"
    user_color: str = "#666"  # Client color for cursor display
    # UI elements set during page build
    highlight_style: ui.element | None = None
    highlight_menu: ui.element | None = None
    save_status: ui.label | None = None
    user_count_badge: ui.label | None = None  # Shows connected user count
    crdt_doc: AnnotationDocument | None = None
    # Annotation cards
    annotations_container: ui.element | None = None
    annotation_cards: dict[str, ui.card] | None = None
    refresh_annotations: Any | None = None  # Callable to refresh cards
    broadcast_update: Any | None = None  # Callable to broadcast to other clients
    broadcast_cursor: Any | None = None  # Callable to broadcast cursor position
    broadcast_selection: Any | None = None  # Callable to broadcast selection
    # Document content for text extraction
    document_chars: list[str] | None = None  # Characters by index
    # Guard against duplicate highlight creation
    processing_highlight: bool = False
    # Tab container references (Phase 1: three-tab UI)
    tab_panels: ui.tab_panels | None = (
        None  # Tab panels container for programmatic switching
    )
    initialised_tabs: set[str] | None = None  # Tracks which tabs have been rendered
    # Tag info list for Tab 2 (Organise) — populated on first visit
    tag_info_list: list[TagInfo] | None = None
    # Reference to the Organise tab panel element for deferred rendering
    organise_panel: ui.element | None = None
    # Callable to refresh the Organise tab from broadcast
    refresh_organise: Any | None = None  # Callable[[], None]
    # Track active tab for broadcast-triggered refresh
    active_tab: str = "Annotate"
    # Reference to the Respond tab panel element for deferred rendering
    respond_panel: ui.element | None = None
    # Whether the Milkdown editor has been initialised (for Phase 7 export)
    has_milkdown_editor: bool = False
    # Callable to refresh the Respond reference panel from tab switch / broadcast
    refresh_respond_references: Any | None = None  # Callable[[], None]
    # Async callable to sync Milkdown markdown to CRDT Text field (Phase 7)
    sync_respond_markdown: Any | None = None  # Callable[[], Awaitable[None]]


def _get_current_username() -> str:
    """Get the display name for the current user."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user:
        if auth_user.get("display_name"):
            return auth_user["display_name"]
        if auth_user.get("email"):
            return auth_user["email"].split("@")[0]
    return "Anonymous"


async def _warp_to_highlight(state: PageState, start_char: int, end_char: int) -> None:
    """Switch to the Annotate tab and scroll to a highlight range.

    This is the cross-tab navigation entry point: Tab 2 (Organise) and Tab 3
    (Respond) "locate" buttons call this to warp the user back to Tab 1 and
    scroll the highlighted text into view with a brief gold flash.

    Per-client only — ``set_value()`` affects only the calling client's tab
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
    await ui.run_javascript(js)


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


def _get_tag_color(tag_str: str) -> str:
    """Get hex color for a tag string."""
    try:
        tag = BriefTag(tag_str)
        return TAG_COLORS.get(tag, "#FFEB3B")
    except ValueError:
        return "#FFEB3B"


def _build_highlight_pseudo_css(tags: set[str] | None = None) -> str:
    """Generate ::highlight() pseudo-element CSS rules for annotation tags.

    Uses the CSS Custom Highlight API: each tag gets a ``::highlight(hl-<tag>)``
    rule with a semi-transparent background and underline in the tag's colour.
    The JS ``applyHighlights()`` function registers the actual highlight ranges
    in ``CSS.highlights``; this CSS just defines the visual style.

    Note: ``::highlight()`` supports only ``background-color``, ``color``,
    ``text-decoration``, and ``text-shadow``. Properties like
    ``text-decoration-thickness`` and ``text-underline-offset`` are NOT
    supported inside ``::highlight()`` rules.

    Args:
        tags: Optional set of tag strings to generate rules for.
              If None, generates rules for all BriefTag values.

    Returns:
        CSS string with ``::highlight()`` rules.
    """
    tag_strings = [t.value for t in BriefTag] if tags is None else sorted(tags)

    css_rules: list[str] = []
    for tag_str in tag_strings:
        hex_color = _get_tag_color(tag_str)
        r, g, b = (
            int(hex_color[1:3], 16),
            int(hex_color[3:5], 16),
            int(hex_color[5:7], 16),
        )
        bg_rgba = f"rgba({r}, {g}, {b}, 0.4)"
        css_rules.append(
            f"::highlight(hl-{tag_str}) {{\n"
            f"    background-color: {bg_rgba};\n"
            f"    text-decoration: underline;\n"
            f"    text-decoration-color: {hex_color};\n"
            f"}}"
        )

    # Hover and throb highlights for card interaction (Phase 4)
    css_rules.append(
        "::highlight(hl-hover) {\n    background-color: rgba(255, 215, 0, 0.3);\n}"
    )
    css_rules.append(
        "::highlight(hl-throb) {\n    background-color: rgba(255, 215, 0, 0.6);\n}"
    )

    return "\n".join(css_rules)


def _setup_page_styles() -> None:
    """Add CSS and register custom tag colors."""
    ui.add_css(_PAGE_CSS)

    # Register custom colors for tag buttons
    custom_tag_colors = {
        tag.value.replace("_", "-"): color for tag, color in TAG_COLORS.items()
    }
    ui.colors(**custom_tag_colors)


def _build_tag_toolbar(
    on_tag_click: Any,  # Callable[[BriefTag], Awaitable[None]]
) -> None:
    """Build fixed tag toolbar.

    Uses a div with fixed positioning for floating toolbar behavior.
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
    ``client.run_javascript()`` — this avoids slot-stack errors when called
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
        ui.run_javascript(js)


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

    # Get tag color
    try:
        tag = BriefTag(tag_str)
        color = TAG_COLORS.get(tag, "#666")
    except ValueError:
        color = "#666"

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
            tag_options = {t.value: t.value.replace("_", " ").title() for t in BriefTag}

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
                    new_color = TAG_COLORS.get(BriefTag(new_tag), "#666")
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
        # Always release processing lock — prevents permanent lockout if any
        # step above raises (e.g. JS relay failure, persistence error).
        state.processing_highlight = False


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
    crdt_doc: AnnotationDocument,
) -> None:
    """Render a document with highlight support."""
    state.document_id = doc.id
    state.crdt_doc = crdt_doc
    state.annotation_cards = {}

    # Extract characters from clean HTML for text extraction when highlighting
    # (char spans are injected client-side, not stored in DB)
    if doc.content:
        state.document_chars = extract_text_from_html(doc.content)

    # Static ::highlight() CSS for all tags — actual highlight ranges are
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
        "width: 90%; max-width: 1600px; margin: 0 auto; padding-top: 60px;"
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
    # Uses charOffsetToRect() from annotation-highlight.js (Phase 4)
    # fmt: off
    # All DOM lookups are dynamic (getElementById on every call) because
    # NiceGUI/Vue can REPLACE the entire Annotate tab panel DOM when
    # another tab initialises (e.g. Respond tab's Milkdown editor).
    # Closured DOM references become dead after replacement.
    scroll_sync_js = (
        "(function() {\n"
        "  var MIN_GAP = 8;\n"
        "  var _obs = null;\n"
        "  var _lastAnnC = null;\n"
        "  function tn() {\n"
        "    var dc = document.getElementById('doc-container');\n"
        "    var t = window._textNodes;\n"
        "    if (!dc || !t || !t.length) return null;\n"
        "    if (!dc.contains(t[0].node)) {\n"
        "      t = walkTextNodes(dc);\n"
        "      window._textNodes = t;\n"
        "    }\n"
        "    return t;\n"
        "  }\n"
        "  function positionCards() {\n"
        "    var nodes = tn();\n"
        "    if (!nodes || !nodes.length) return;\n"
        "    var dc = document.getElementById('doc-container');\n"
        "    var ac = document.getElementById("
        "'annotations-container');\n"
        "    if (!dc || !ac) return;\n"
        "    var cards = Array.from("
        "ac.querySelectorAll('[data-start-char]'));\n"
        "    if (!cards.length) return;\n"
        "    var docRect = dc.getBoundingClientRect();\n"
        "    var annRect = ac.getBoundingClientRect();\n"
        "    var cOff = annRect.top - docRect.top;\n"
        "    var cardInfos = cards.map(function(card) {\n"
        "      var sc = parseInt(card.dataset.startChar);\n"
        "      var cr = charOffsetToRect(nodes, sc);\n"
        "      if (cr.width === 0 && cr.height === 0) return null;\n"
        "      return {card: card, startChar: sc,\n"
        "        height: card.offsetHeight,\n"
        "        targetY: (cr.top - docRect.top) - cOff};\n"
        "    }).filter(Boolean);\n"
        "    cardInfos.sort(function(a,b) {"
        " return a.startChar - b.startChar; });\n"
        "    var hH = 60, vT = hH, vB = window.innerHeight;\n"
        "    var minY = 0;\n"
        "    for (var i = 0; i < cardInfos.length; i++) {\n"
        "      var info = cardInfos[i];\n"
        "      var sc2 = info.startChar;\n"
        "      var ec2 = parseInt("
        "info.card.dataset.endChar) || sc2;\n"
        "      var sr = charOffsetToRect(nodes, sc2);\n"
        "      var er = charOffsetToRect("
        "nodes, Math.max(ec2-1, sc2));\n"
        "      var inView = er.bottom > vT && sr.top < vB;\n"
        "      info.card.style.position = 'absolute';\n"
        "      if (!inView) {"
        " info.card.style.display = 'none'; continue; }\n"
        "      info.card.style.display = '';\n"
        "      var y = Math.max(info.targetY, minY);\n"
        "      info.card.style.top = y + 'px';\n"
        "      minY = y + info.height + MIN_GAP;\n"
        "    }\n"
        "  }\n"
        "  var ticking = false;\n"
        "  function onScroll() {\n"
        "    if (!ticking) {\n"
        "      requestAnimationFrame(function() {"
        " positionCards(); ticking = false; });\n"
        "      ticking = true;\n"
        "    }\n"
        "  }\n"
        "  window._positionCards = positionCards;\n"
        "  window.addEventListener('scroll', onScroll,"
        " {passive: true});\n"
        "  // Re-attach MutationObserver on each highlights-ready\n"
        "  // because the annotations-container DOM element may have\n"
        "  // been replaced by Vue re-rendering.\n"
        "  document.addEventListener("
        "'highlights-ready', function() {\n"
        "    var ac = document.getElementById("
        "'annotations-container');\n"
        "    if (!ac) return;\n"
        "    if (ac !== _lastAnnC) {\n"
        "      if (_obs) _obs.disconnect();\n"
        "      _obs = new MutationObserver(function() {"
        " requestAnimationFrame(positionCards); });\n"
        "      _obs.observe(ac,"
        " {childList: true, subtree: true});\n"
        "      _lastAnnC = ac;\n"
        "    }\n"
        "    requestAnimationFrame(positionCards);\n"
        "  });\n"
        "  // Card hover via event delegation on document\n"
        "  // (survives DOM replacement)\n"
        "  var hoveredCard = null;\n"
        "  document.addEventListener('mouseover', function(e) {\n"
        "    var ac = document.getElementById("
        "'annotations-container');\n"
        "    if (!ac || !ac.contains(e.target)) {\n"
        "      if (hoveredCard) {"
        " clearHoverHighlight(); hoveredCard = null; }\n"
        "      return;\n"
        "    }\n"
        "    var card = e.target.closest('[data-start-char]');\n"
        "    if (card === hoveredCard) return;\n"
        "    clearHoverHighlight();\n"
        "    hoveredCard = null;\n"
        "    if (!card) return;\n"
        "    hoveredCard = card;\n"
        "    var sc = parseInt(card.dataset.startChar);\n"
        "    var ec = parseInt(card.dataset.endChar) || sc;\n"
        "    var nodes = tn();\n"
        "    if (nodes) showHoverHighlight(nodes, sc, ec);\n"
        "  });\n"
        "})();"
    )
    # fmt: on
    ui.run_javascript(scroll_sync_js)


def _get_user_color(user_name: str) -> str:
    """Generate a consistent color for a user based on their name."""
    # Simple hash-based color generation for consistency
    hash_val = sum(ord(c) for c in user_name)
    colors = [
        "#e91e63",  # pink
        "#9c27b0",  # purple
        "#673ab7",  # deep purple
        "#3f51b5",  # indigo
        "#2196f3",  # blue
        "#009688",  # teal
        "#4caf50",  # green
        "#ff9800",  # orange
        "#795548",  # brown
    ]
    return colors[hash_val % len(colors)]


def _update_user_count(state: PageState) -> None:
    """Update user count badge."""
    if state.user_count_badge is None:
        return
    workspace_key = str(state.workspace_id)
    count = len(_workspace_presence.get(workspace_key, {}))
    logger.debug(
        "USER_COUNT: ws=%s count=%d keys=%s",
        workspace_key,
        count,
        list(_workspace_presence.keys()),
    )
    label = "1 user" if count == 1 else f"{count} users"
    state.user_count_badge.set_text(label)


async def _broadcast_js_to_others(
    workspace_key: str, exclude_client_id: str, js: str
) -> None:
    """Send a JS snippet to every other client in the workspace.

    Skips clients without a ``nicegui_client`` reference and suppresses
    individual send failures so one broken connection cannot block others.
    """
    for cid, presence in _workspace_presence.get(workspace_key, {}).items():
        if cid == exclude_client_id or presence.nicegui_client is None:
            continue
        with contextlib.suppress(Exception):
            await presence.nicegui_client.run_javascript(js, timeout=2.0)


def _notify_other_clients(workspace_key: str, exclude_client_id: str) -> None:
    """Fire-and-forget notification to other clients in workspace."""
    for cid, cstate in _workspace_presence.get(workspace_key, {}).items():
        if cid != exclude_client_id and cstate.callback:
            with contextlib.suppress(Exception):
                task = asyncio.create_task(cstate.callback())
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)


def _setup_client_sync(  # noqa: PLR0915  # TODO(2026-02): refactor after Phase 7
    workspace_id: UUID,
    client: Client,
    state: PageState,
) -> None:
    """Set up client synchronization for real-time updates.

    Registers the client, creates broadcast function, and sets up disconnect handler.
    """
    client_id = str(uuid4())
    workspace_key = str(workspace_id)
    state.client_id = client_id
    state.user_color = _get_user_color(state.user_name)

    # Create broadcast function for annotation updates
    async def broadcast_update() -> None:
        for cid, cstate in _workspace_presence.get(workspace_key, {}).items():
            if cid != client_id and cstate.callback:
                with contextlib.suppress(Exception):
                    await cstate.callback()

    state.broadcast_update = broadcast_update

    # Create broadcast function for cursor updates — JS-targeted (AC3.4)
    async def broadcast_cursor(char_index: int | None) -> None:
        clients = _workspace_presence.get(workspace_key, {})
        if client_id in clients:
            clients[client_id].cursor_char = char_index
        if char_index is not None:
            name = state.user_name
            color = state.user_color
            js = _render_js(
                t"renderRemoteCursor("
                t"document.getElementById('doc-container')"
                t", {client_id}, {char_index}"
                t", {name}, {color})"
            )
        else:
            js = _render_js(t"removeRemoteCursor({client_id})")
        await _broadcast_js_to_others(workspace_key, client_id, js)

    state.broadcast_cursor = broadcast_cursor

    # Create broadcast function for selection updates — JS-targeted (AC3.4)
    async def broadcast_selection(start: int | None, end: int | None) -> None:
        clients = _workspace_presence.get(workspace_key, {})
        if client_id in clients:
            clients[client_id].selection_start = start
            clients[client_id].selection_end = end
        if start is not None and end is not None:
            name = state.user_name
            color = state.user_color
            js = _render_js(
                t"renderRemoteSelection({client_id}, {start}, {end}, {name}, {color})"
            )
        else:
            js = _render_js(t"removeRemoteSelection({client_id})")
        await _broadcast_js_to_others(workspace_key, client_id, js)

    state.broadcast_selection = broadcast_selection

    # Callback for receiving updates from other clients
    async def handle_update_from_other() -> None:
        _update_highlight_css(state)
        _update_user_count(state)
        if state.refresh_annotations:
            state.refresh_annotations()
        # Refresh Organise tab if client is currently viewing it (Phase 4)
        if state.active_tab == "Organise" and state.refresh_organise:
            state.refresh_organise()
        # Refresh Respond reference panel if client is currently viewing it
        if state.active_tab == "Respond" and state.refresh_respond_references:
            state.refresh_respond_references()

    # Register this client
    if workspace_key not in _workspace_presence:
        _workspace_presence[workspace_key] = {}
    _workspace_presence[workspace_key][client_id] = _RemotePresence(
        name=state.user_name,
        color=state.user_color,
        nicegui_client=client,
        callback=handle_update_from_other,
    )
    logger.info(
        "CLIENT_REGISTERED: ws=%s client=%s total=%d",
        workspace_key,
        client_id[:8],
        len(_workspace_presence[workspace_key]),
    )

    # Update own user count and notify others
    _update_user_count(state)
    _notify_other_clients(workspace_key, client_id)

    # Send existing remote cursors/selections to newly connected client
    for cid, presence in _workspace_presence.get(workspace_key, {}).items():
        if cid == client_id:
            continue
        if presence.cursor_char is not None:
            char = presence.cursor_char
            name = presence.name
            color = presence.color
            js = _render_js(
                t"renderRemoteCursor("
                t"document.getElementById('doc-container')"
                t", {cid}, {char}"
                t", {name}, {color})"
            )
            ui.run_javascript(js)
        if presence.selection_start is not None and presence.selection_end is not None:
            s_start = presence.selection_start
            s_end = presence.selection_end
            name = presence.name
            color = presence.color
            js = _render_js(
                t"renderRemoteSelection({cid}, {s_start}, {s_end}, {name}, {color})"
            )
            ui.run_javascript(js)

    # Disconnect handler
    async def on_disconnect() -> None:
        if workspace_key in _workspace_presence:
            _workspace_presence[workspace_key].pop(client_id, None)
            # Clean up empty workspace dict to prevent slow memory leak
            if not _workspace_presence[workspace_key]:
                del _workspace_presence[workspace_key]
            # Remove this client's cursor/selection and refresh UI for all remaining
            removal_js = _render_js(
                t"removeRemoteCursor({client_id});removeRemoteSelection({client_id})"
            )
            for _cid, presence in _workspace_presence.get(workspace_key, {}).items():
                if presence.nicegui_client is not None:
                    with contextlib.suppress(Exception):
                        await presence.nicegui_client.run_javascript(
                            removal_js, timeout=2.0
                        )
                if presence.callback:
                    with contextlib.suppress(Exception):
                        await presence.callback()
        pm = get_persistence_manager()
        await pm.force_persist_workspace(workspace_id)

    client.on_disconnect(on_disconnect)


async def _handle_pdf_export(state: PageState, workspace_id: UUID) -> None:
    """Handle PDF export with loading notification."""
    if state.crdt_doc is None or state.document_id is None:
        ui.notify("No document to export", type="warning")
        return

    # Show notification with spinner IMMEDIATELY
    notification = ui.notification(
        message="Generating PDF...",
        spinner=True,
        timeout=None,
        type="ongoing",
    )
    # Force UI update before starting async work
    await asyncio.sleep(0)

    try:
        # Get tag colours as dict[str, str]
        tag_colours = {tag.value: colour for tag, colour in TAG_COLORS.items()}

        # Get highlights for this document
        highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))

        doc = await get_document(state.document_id)
        if doc is None or not doc.content:
            notification.dismiss()
            ui.notify(
                "No document content to export. Please paste or upload content first.",
                type="warning",
            )
            return
        html_content = doc.content

        # Get response draft markdown for the General Notes section (Phase 7).
        # Primary path: JS extraction from running Milkdown editor (most accurate).
        # Fallback: CRDT Text field synced by whichever client last edited Tab 3.
        response_markdown = ""
        if state.has_milkdown_editor:
            try:
                response_markdown = await ui.run_javascript(
                    "window._getMilkdownMarkdown()", timeout=3.0
                )
                if not response_markdown:
                    response_markdown = ""
            except (TimeoutError, OSError) as exc:
                logger.debug(
                    "PDF export: JS markdown extraction failed (%s), "
                    "using CRDT fallback",
                    type(exc).__name__,
                )
                response_markdown = ""

        if not response_markdown and state.crdt_doc is not None:
            response_markdown = state.crdt_doc.get_response_draft_markdown()

        # Convert markdown to LaTeX via Pandoc (no new dependencies)
        notes_latex = ""
        if response_markdown and response_markdown.strip():
            notes_latex = await markdown_to_latex_notes(response_markdown)

        # Generate PDF
        pdf_path = await export_annotation_pdf(
            html_content=html_content,
            highlights=highlights,
            tag_colours=tag_colours,
            general_notes="",
            notes_latex=notes_latex,
            word_to_legal_para=None,
            filename=f"workspace_{workspace_id}",
        )

        notification.dismiss()

        # Trigger download
        ui.download(pdf_path)
        ui.notify("PDF exported successfully!", type="positive")
    except Exception as e:
        notification.dismiss()
        logger.exception("Failed to export PDF")
        ui.notify(f"PDF export failed: {e}", type="negative", timeout=10000)


def _detect_type_from_extension(filename: str) -> ContentType | None:
    """Detect content type from file extension.

    Returns None if extension is not recognized.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_to_type: dict[str, ContentType] = {
        "html": "html",
        "htm": "html",
        "rtf": "rtf",
        "docx": "docx",
        "pdf": "pdf",
        "txt": "text",
        "md": "text",
        "markdown": "text",
    }
    return ext_to_type.get(ext)


def _get_file_preview(
    content_bytes: bytes, detected_type: ContentType, filename: str
) -> str:
    """Get preview text for file content."""
    try:
        if detected_type in ("html", "text"):
            return content_bytes.decode("utf-8")[:500]
        return f"[Binary file: {filename}]"
    except UnicodeDecodeError:
        return f"[Binary file: {filename}]"


def _render_add_content_form(workspace_id: UUID) -> None:
    """Render the add content form with editor and file upload.

    Extracted from _render_workspace_view to reduce function complexity.
    """
    ui.label("Add content to annotate:").classes("mt-4 font-semibold")

    # HTML-aware editor for paste support (Quasar QEditor)
    content_input = (
        ui.editor(placeholder="Paste HTML content or type plain text here...")
        .classes("w-full min-h-32")
        .props("toolbar=[]")
    )  # Hide toolbar for minimal UI

    # Intercept paste, strip CSS client-side, store cleaned HTML.
    # Browsers include computed CSS (2.7MB for 32KB text). Strip it here.
    paste_var = f"_pastedHtml_{content_input.id}"
    platform_var = f"_platformHint_{content_input.id}"
    ui.add_body_html(f"""
    <script>
        window.{paste_var} = null;
        window.{platform_var} = null;
        document.addEventListener('DOMContentLoaded', function() {{
            const sel = '[id="c{content_input.id}"] .q-editor__content';
            const tryAttach = () => {{
                const editorEl = document.querySelector(sel);
                if (!editorEl) {{
                    setTimeout(tryAttach, 50);
                    return;
                }}
                console.log('[PASTE-INIT] Editor found, attaching handler');
                editorEl.addEventListener('paste', function(e) {{
                    let html = e.clipboardData.getData('text/html');
                    const text = e.clipboardData.getData('text/plain');
                    if (!html && !text) return;

                    e.preventDefault();
                    e.stopPropagation();

                    let cleaned = text || '';
                    const origSize = (html || text).length;

                    if (html) {{
                        // Inject speaker labels into raw HTML
                        // BEFORE stripping (attrs needed for
                        // detection get stripped later)
                        const mk = (role) =>
                            '<div data-speaker="' +
                            role + '"></div>';
                        const sp = {{}};
                        // Build attr/class regex helpers
                        const ar = (a) =>
                            '(<[^>]*' + a + '[^>]*>)';
                        const cr = (c) =>
                            '(<[^>]*class="[^"]*'
                            + c + '[^"]*"[^>]*>)';
                        if (/font-user-message/.test(html)) {{
                            window.{platform_var} = 'claude';
                            sp.u = new RegExp(
                                ar('data-testid="user-message"'),
                                'gi');
                            // Match ONLY the primary response
                            // container (class starts with
                            // font-claude-response). Exclude:
                            // - font-claude-response-body (per-para)
                            // - secondary divs where font-claude-
                            //   response appears mid-class (these
                            //   are UI chrome, not content)
                            sp.a = new RegExp(
                                '(<[^>]*class="'
                                + 'font-claude-response'
                                + '(?!-)[^"]*"[^>]*>)', 'gi');
                        }} else if (/conversation-turn/.test(html)) {{
                            // OpenAI already has "You said:"/"ChatGPT said:"
                            // labels in content — don't inject duplicates
                            window.{platform_var} = 'openai';
                        }} else if (/chat-turn-container/.test(html)) {{
                            // AI Studio has "User"/"Model" text
                            // labels in content — don't inject
                            // duplicates (same as OpenAI)
                            window.{platform_var} = 'aistudio';
                        }} else if (/message-actions/.test(html)) {{
                            window.{platform_var} = 'gemini';
                            // Match only exact tags, not
                            // user-query-content etc.
                            // Negative lookahead (?!-) prevents
                            // matching user-query-content.
                            sp.u = new RegExp(
                                '(<user-query(?!-)(?:\\\\s[^>]*)?>)',
                                'gi');
                            sp.a = new RegExp(
                                '(<model-response(?!-)(?:\\\\s[^>]*)?>)',
                                'gi');
                        }} else if (/headroom/.test(html)) {{
                            window.{platform_var} = 'scienceos';
                            sp.u = new RegExp(
                                cr('_prompt_'), 'gi');
                            sp.a = new RegExp(
                                cr('_markdown_'), 'gi');
                        }} else if (/mw-parser-output|mw-body-content/.test(html)) {{
                            window.{platform_var} = 'wikimedia';
                            // No speaker labels — wiki content
                            // has no user/assistant turns
                        }}
                        if (sp.u) {{
                            html = html.replace(
                                sp.u, mk('user') + '$1');
                            html = html.replace(
                                sp.a, mk('assistant') + '$1');
                        }}
                        console.log('[PASTE] Platform:',
                            window.{platform_var});

                        // Parse HTML in hidden iframe
                        const iframe = document.createElement('iframe');
                        iframe.style.cssText = 'position:absolute;left:-9999px;';
                        document.body.appendChild(iframe);

                        iframe.contentDocument.open();
                        iframe.contentDocument.write(html);
                        iframe.contentDocument.close();

                        // P2: Collapse Claude thinking blocks
                        // BEFORE stripping classes — we need them
                        // to identify thinking containers.
                        if (window.{platform_var} === 'claude') {{
                            // Find the thinking toggle div by
                            // its text content and class
                            const iDoc = iframe.contentDocument;
                            iDoc.querySelectorAll('div').forEach(
                                el => {{
                                const cls = el.className || '';
                                const txt = el.textContent.trim();
                                // The toggle container has
                                // "Thought process" as text.
                                // It also contains time (18s)
                                // and an SVG icon.
                                if (/^Thought process/i.test(txt)
                                    && txt.length < 200) {{
                                    // Extract just "Thought process"
                                    // and time if present
                                    const timeM = txt.match(
                                        /(\\d+s)/);
                                    const label = 'Thought process'
                                        + (timeM
                                            ? ' ' + timeM[1] : '');
                                    const p = iDoc.createElement(
                                        'p');
                                    // Use data-thinking attr to
                                    // survive style stripping;
                                    // CSS handles presentation
                                    p.setAttribute(
                                        'data-thinking', 'true');
                                    p.textContent = '[' + label
                                        + ']';
                                    el.replaceWith(p);
                                }}
                            }});
                            // Also remove thinking CONTENT divs
                            // Claude wraps thinking text in divs
                            // with class containing "grid-cols"
                            // directly after the toggle
                        }}

                        // P4: Flatten KaTeX/MathML to plain text
                        // BEFORE stripping classes — we need
                        // .katex/.katex-display selectors.
                        {{
                            const iDoc = iframe.contentDocument;
                            iDoc.querySelectorAll(
                                '.katex, .katex-display'
                            ).forEach(el => {{
                                const ann = el.querySelector(
                                    'annotation[encoding='
                                    + '"application/x-tex"]'
                                );
                                const txt = ann
                                    ? ann.textContent
                                    : el.textContent;
                                const span =
                                    iDoc.createElement('span');
                                span.textContent = txt;
                                el.replaceWith(span);
                            }});
                            // Also handle bare <math> elements
                            iDoc.querySelectorAll('math')
                                .forEach(el => {{
                                const span =
                                    iDoc.createElement('span');
                                span.textContent = el.textContent;
                                el.replaceWith(span);
                            }});
                        }}

                        // Properties to preserve from inline styles
                        const keepStyleProps = ['margin-left', 'margin-right',
                            'margin-top', 'margin-bottom', 'text-indent',
                            'padding-left', 'padding-right'];
                        // Also handle margin/padding shorthand
                        const shorthandProps = ['margin', 'padding'];

                        // Strip style/script/img tags
                        iframe.contentDocument.querySelectorAll('style, script, img')
                            .forEach(el => el.remove());

                        // Strip MediaWiki chrome (if wikimedia platform)
                        if (window.{platform_var} === 'wikimedia') {{
                            const mwChrome = [
                                'nav', '.vector-header-container',
                                '.vector-main-menu-landmark',
                                '.vector-main-menu-container',
                                '.vector-sidebar', '.mw-portlet',
                                '#footer', '.mw-footer',
                                '.mw-editsection', '#toc', '.toc',
                                '#catlinks', '.vector-column-start',
                                '.vector-column-end', '#mw-navigation',
                                '.vector-page-toolbar',
                                '.vector-page-titlebar',
                                '.vector-sitenotice-container',
                                '.vector-dropdown',
                                '.vector-sticky-header',
                                '#p-search', '.vector-search-box',
                                '.vector-user-links',
                                '.mw-jump-link',
                                '#mw-aria-live-region',
                            ];
                            const iDoc = iframe.contentDocument;
                            for (const sel of mwChrome) {{
                                iDoc.querySelectorAll(sel)
                                    .forEach(el => el.remove());
                            }}
                        }}

                        // Unwrap hyperlinks: replace <a href="url">text</a>
                        // with text [url] — links are not interactive in
                        // the annotation view and interfere with selection
                        iframe.contentDocument.querySelectorAll('a[href]')
                            .forEach(a => {{
                                const href = a.getAttribute('href') || '';
                                const text = a.textContent || '';
                                // Skip anchors that are just fragment links
                                // or have no meaningful href
                                if (!href || href.startsWith('#')) {{
                                    // Just unwrap, keep text
                                    a.replaceWith(text);
                                    return;
                                }}
                                // Show URL after link text
                                const suffix = ' [' + href + ']';
                                a.replaceWith(text + suffix);
                            }});

                        // Process all elements - preserve important inline styles
                        iframe.contentDocument.querySelectorAll('*').forEach(el => {{
                            const existingStyle = el.getAttribute('style') || '';
                            const keptStyles = [];

                            // Parse inline style for important properties
                            for (const prop of keepStyleProps) {{
                                const pat = prop + '\\\\s*:\\\\s*([^;]+)';
                                const m = existingStyle.match(
                                    new RegExp(pat, 'i'));
                                if (m) {{
                                    keptStyles.push(
                                        prop + ':' + m[1].trim());
                                }}
                            }}
                            // Expand margin/padding shorthand
                            for (const sh of shorthandProps) {{
                                const pat = '(?:^|;)\\\\s*' + sh
                                    + '\\\\s*:\\\\s*([^;]+)';
                                const m = existingStyle.match(
                                    new RegExp(pat, 'i'));
                                if (m) {{
                                    const vals = m[1].trim().split(
                                        /\\s+/);
                                    const t = vals[0] || '0';
                                    const r = vals[1] || t;
                                    const b = vals[2] || t;
                                    const l = vals[3] || r;
                                    // Only keep non-zero values
                                    if (l !== '0' && l !== '0px')
                                        keptStyles.push(
                                            sh + '-left:' + l);
                                    if (r !== '0' && r !== '0px')
                                        keptStyles.push(
                                            sh + '-right:' + r);
                                }}
                            }}

                            // Apply preserved styles or remove style attr
                            if (keptStyles.length > 0) {{
                                el.setAttribute('style', keptStyles.join(';'));
                            }} else {{
                                el.removeAttribute('style');
                            }}

                            // Remove class attributes
                            el.removeAttribute('class');

                            // Remove data-* attrs except
                            // data-speaker and data-thinking
                            const dataAttrs = [];
                            const keepData = new Set([
                                'data-speaker',
                                'data-thinking']);
                            for (const attr of el.attributes) {{
                                if (attr.name.startsWith('data-')
                                    && !keepData.has(attr.name)) {{
                                    dataAttrs.push(attr.name);
                                }}
                            }}
                            dataAttrs.forEach(
                                n => el.removeAttribute(n));
                        }});

                        // Remove empty containers that only have <br> tags
                        const removeEmpty = () => {{
                            let removed = 0;
                            iframe.contentDocument.querySelectorAll('p, div, span')
                                .forEach(el => {{
                                // Preserve speaker marker divs
                                // and thinking indicators
                                if (el.hasAttribute('data-speaker')
                                    || el.hasAttribute(
                                        'data-thinking')) return;
                                const text = el.textContent?.trim();
                                const noBr = el.innerHTML.replace(/<br\\s*\\/?>/gi, '');
                                const htmlNoBr = noBr.trim();
                                if (!text && !htmlNoBr) {{
                                    el.remove();
                                    removed++;
                                }}
                            }});
                            return removed;
                        }};
                        while (removeEmpty() > 0) {{}}

                        // Clean up empty table elements
                        const removeEmptyTable = () => {{
                            let removed = 0;
                            const doc = iframe.contentDocument;
                            doc.querySelectorAll('td, tr, table, col').forEach(el => {{
                                if (!el.textContent?.trim()) {{
                                    el.remove();
                                    removed++;
                                }}
                            }});
                            return removed;
                        }};
                        while (removeEmptyTable() > 0) {{}}

                        // Strip nav elements and empty list items
                        const doc = iframe.contentDocument;
                        doc.querySelectorAll('nav').forEach(
                            el => el.remove());
                        doc.querySelectorAll('li').forEach(el => {{
                            if (!el.textContent?.trim())
                                el.remove();
                        }});

                        // P5: Flatten <pre> blocks to preserve
                        // whitespace. OpenAI wraps code in
                        // <pre><div>...<div><code><span>...
                        // After class stripping, the intermediate
                        // divs and spans break formatting.
                        // Fix: replace <pre> content with plain
                        // text from the <code> element.
                        doc.querySelectorAll('pre').forEach(
                            pre => {{
                            const code = pre.querySelector(
                                'code');
                            if (code) {{
                                // Preserve the text content
                                // (includes literal newlines)
                                const txt = code.textContent;
                                // Replace pre content with
                                // just <code>text</code>
                                const newCode =
                                    doc.createElement('code');
                                newCode.textContent = txt;
                                pre.textContent = '';
                                pre.appendChild(newCode);
                            }} else {{
                                // No <code> child — flatten
                                // all children to text
                                const txt = pre.textContent;
                                pre.textContent = txt;
                            }}
                        }});

                        // (P4 KaTeX flatten moved above,
                        // before attribute stripping)

                        // (P2 thinking collapse moved above,
                        // before attribute stripping)

                        // P1: Deduplicate speaker labels
                        // Two rules:
                        // (a) Same-role consecutive: always remove
                        //     the earlier one (nesting artefact)
                        // (b) Different-role consecutive with no
                        //     real text between: remove earlier
                        //     (null/empty round)
                        const FOLLOWING = Node
                            .DOCUMENT_POSITION_FOLLOWING;
                        const PRECEDING = Node
                            .DOCUMENT_POSITION_PRECEDING;
                        const allSp = Array.from(
                            doc.querySelectorAll('[data-speaker]'));
                        const spSet = new Set(allSp);
                        const toRemove = [];
                        for (let i = 0; i < allSp.length - 1;
                                i++) {{
                            const cur = allSp[i];
                            const nxt = allSp[i + 1];
                            const curRole = cur.getAttribute(
                                'data-speaker');
                            const nxtRole = nxt.getAttribute(
                                'data-speaker');
                            // (a) Same role = always duplicate
                            if (curRole === nxtRole) {{
                                toRemove.push(cur);
                                continue;
                            }}
                            // (b) Different role: check for text
                            // between the two speaker divs.
                            // Use compareDocumentPosition to
                            // find text nodes between cur & nxt
                            // (speaker divs are empty, so
                            // contains() won't find children).
                            const tw = doc.createTreeWalker(
                                doc.body,
                                NodeFilter.SHOW_TEXT,
                                null);
                            let hasContent = false;
                            while (tw.nextNode()) {{
                                const n = tw.currentNode;
                                // Is n after cur?
                                const afterCur = cur
                                    .compareDocumentPosition(n)
                                    & FOLLOWING;
                                if (!afterCur) continue;
                                // Is n before nxt?
                                const beforeNxt = nxt
                                    .compareDocumentPosition(n)
                                    & PRECEDING;
                                if (!beforeNxt) break;
                                // Skip text inside other speakers
                                let inSpeaker = false;
                                for (const s of spSet) {{
                                    if (s !== cur && s !== nxt
                                        && s.contains(n)) {{
                                        inSpeaker = true;
                                        break;
                                    }}
                                }}
                                if (inSpeaker) continue;
                                const t = n.textContent.trim();
                                if (t.length > 2) {{
                                    hasContent = true;
                                    break;
                                }}
                            }}
                            if (!hasContent) toRemove.push(cur);
                        }}
                        toRemove.forEach(el => el.remove());

                        cleaned = iframe.contentDocument.body.innerHTML;
                        document.body.removeChild(iframe);
                        console.log('[PASTE] Cleaned:', cleaned.length, 'bytes');
                    }}

                    window.{paste_var} = cleaned;
                    const newSize = cleaned.length;
                    console.log('[PASTE] Stripped:', origSize, '->', newSize,
                        '(' + Math.round(100 - newSize*100/origSize) + '% reduction)');

                    // Show placeholder with size info
                    const p = document.createElement('p');
                    p.style.cssText = 'color:#666;font-style:italic;';
                    p.textContent = '✓ Content pasted (' +
                        Math.round(newSize/1024) + ' KB after cleanup). ' +
                        'Click "Add Document" to process.';
                    editorEl.replaceChildren(p);
                }});
            }};
            tryAttach();
        }});
    </script>
    """)

    async def handle_add_document() -> None:
        """Process input and add document to workspace."""
        # Try to get pasted content from JS storage (bypasses websocket limit)
        stored = await ui.run_javascript(f"window.{paste_var}")
        platform_hint = await ui.run_javascript(f"window.{platform_var}")
        content = stored if stored else content_input.value
        from_paste = bool(stored)

        if not content or not content.strip():
            ui.notify("Please enter or paste some content", type="warning")
            return

        # Skip dialog if HTML was captured from paste - we know it's HTML
        confirmed_type: ContentType | None = (
            "html"
            if from_paste
            else (
                await show_content_type_dialog(
                    detect_content_type(content), content[:500]
                )
            )
        )
        if confirmed_type is None:
            return  # User cancelled

        try:
            processed_html = await process_input(
                content=content,
                source_type=confirmed_type,
                platform_hint=platform_hint,
            )
            await add_document(
                workspace_id=workspace_id,
                type="source",
                content=processed_html,
                source_type=confirmed_type,
                title=None,
            )
            content_input.value = ""
            ui.notify("Document added successfully", type="positive")
            ui.navigate.to(
                f"/annotation?{urlencode({'workspace_id': str(workspace_id)})}"
            )
        except Exception as exc:
            logger.exception("Failed to add document")
            ui.notify(f"Failed to add document: {exc}", type="negative")

    ui.button("Add Document", on_click=handle_add_document).classes(
        "bg-green-500 text-white mt-2"
    )

    async def handle_file_upload(upload_event: events.UploadEventArguments) -> None:
        """Handle file upload through HTML pipeline."""
        # Access file via .file attribute (FileUpload dataclass)
        # ty cannot resolve this type due to TYPE_CHECKING import in nicegui
        filename: str = upload_event.file.name  # pyright: ignore[reportAttributeAccessIssue]
        content_bytes = await upload_event.file.read()  # pyright: ignore[reportAttributeAccessIssue]

        # Detect type from extension, fall back to content detection
        detected_type = _detect_type_from_extension(filename)
        if detected_type is None:
            detected_type = detect_content_type(content_bytes)

        preview = _get_file_preview(content_bytes, detected_type, filename)
        confirmed_type = await show_content_type_dialog(
            detected_type=detected_type,
            preview=preview,
        )

        if confirmed_type is None:
            ui.notify("Upload cancelled", type="info")
            return

        try:
            processed_html = await process_input(
                content=content_bytes,
                source_type=confirmed_type,
                platform_hint=None,
            )
            await add_document(
                workspace_id=workspace_id,
                type="source",
                content=processed_html,
                source_type=confirmed_type,
                title=filename,
            )
            ui.notify(f"Uploaded: {filename}", type="positive")
            ui.navigate.to(
                f"/annotation?{urlencode({'workspace_id': str(workspace_id)})}"
            )
        except NotImplementedError as not_impl_err:
            ui.notify(f"Format not yet supported: {not_impl_err}", type="warning")
        except Exception as exc:
            logger.exception("Failed to process uploaded file")
            ui.notify(f"Failed to process file: {exc}", type="negative")

    # File upload for HTML, RTF, DOCX, PDF, TXT, Markdown files
    ui.upload(
        label="Or upload a file",
        on_upload=handle_file_upload,
        auto_upload=True,
        max_file_size=10 * 1024 * 1024,  # 10 MB limit
    ).props('accept=".html,.htm,.rtf,.docx,.pdf,.txt,.md,.markdown"').classes("w-full")


def _get_placement_chip_style(ctx: PlacementContext) -> tuple[str, str, str]:
    """Return (label, color, icon) for a placement context chip."""
    if ctx.is_template and ctx.placement_type == "activity":
        return f"Template: {ctx.display_label}", "purple", "lock"
    if ctx.placement_type == "activity":
        return ctx.display_label, "blue", "assignment"
    if ctx.placement_type == "course":
        return ctx.display_label, "green", "folder"
    return "Unplaced", "grey", "help_outline"


def _get_current_user_id() -> UUID | None:
    """Get the local User UUID from session storage, if authenticated."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user and auth_user.get("user_id"):
        return UUID(auth_user["user_id"])
    return None


async def _load_enrolled_course_options(
    user_id: UUID,
) -> dict[str, str]:
    """Load course select options for courses the user is enrolled in."""
    enrollments = await list_user_enrollments(user_id)
    course_ids = {e.course_id for e in enrollments}
    # TODO(Seam-D): Replace with single JOIN query if course count grows
    courses_list = await list_courses()
    return {
        str(c.id): f"{c.code} - {c.name}" for c in courses_list if c.id in course_ids
    }


def _build_activity_cascade(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build the Course -> Week -> Activity cascading selects.

    Renders UI elements in the current NiceGUI context.
    Stores selected IDs into ``selected`` dict under keys
    "course", "week", "activity".
    """
    course_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course"')
    )
    week_select = (
        ui.select(options={}, label="Week")
        .classes("w-full")
        .props('data-testid="placement-week"')
    )
    week_select.disable()
    activity_select = (
        ui.select(options={}, label="Activity")
        .classes("w-full")
        .props('data-testid="placement-activity"')
    )
    activity_select.disable()

    async def on_course_change(e: events.ValueChangeEventArguments) -> None:
        week_select.options = {}
        week_select.value = None
        week_select.disable()
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["course"] = selected["week"] = selected["activity"] = None
        if e.value:
            try:
                cid = UUID(e.value)
                selected["course"] = cid
                weeks = await list_weeks(cid)
                week_select.options = {
                    str(w.id): f"Week {w.week_number}: {w.title}" for w in weeks
                }
                week_select.update()
                if weeks:
                    week_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    course_select.on_value_change(on_course_change)

    async def on_week_change(e: events.ValueChangeEventArguments) -> None:
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["week"] = selected["activity"] = None
        if e.value:
            try:
                wid = UUID(e.value)
                selected["week"] = wid
                activities = await list_activities_for_week(wid)
                activity_select.options = {str(a.id): a.title for a in activities}
                activity_select.update()
                if activities:
                    activity_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    week_select.on_value_change(on_week_change)

    def on_activity_change(e: events.ValueChangeEventArguments) -> None:
        selected["activity"] = UUID(e.value) if e.value else None

    activity_select.on_value_change(on_activity_change)


def _build_course_only_select(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build a single Course select for course-level placement.

    Stores the selected course ID into ``selected["course_only"]``.
    """
    course_only_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course-only"')
    )

    def on_change(e: events.ValueChangeEventArguments) -> None:
        selected["course_only"] = UUID(e.value) if e.value else None

    course_only_select.on_value_change(on_change)


async def _apply_placement(
    mode_value: str,
    workspace_id: UUID,
    selected: dict[str, UUID | None],
) -> bool:
    """Apply the placement based on the selected mode.

    Returns True on success, False if validation failed.
    """
    if mode_value == "loose":
        await make_workspace_loose(workspace_id)
        ui.notify("Workspace unplaced", type="positive")
        return True
    if mode_value == "activity":
        aid = selected.get("activity")
        if aid is None:
            ui.notify(
                "Please select a course, week, and activity",
                type="warning",
            )
            return False
        await place_workspace_in_activity(workspace_id, aid)
        ui.notify("Workspace placed in activity", type="positive")
        return True
    if mode_value == "course":
        cid = selected.get("course_only")
        if cid is None:
            ui.notify("Please select a course", type="warning")
            return False
        await place_workspace_in_course(workspace_id, cid)
        ui.notify("Workspace associated with course", type="positive")
        return True
    return False


async def _show_placement_dialog(
    workspace_id: UUID,
    current_ctx: PlacementContext,
    on_changed: Any,
) -> None:
    """Open the placement dialog for changing workspace placement.

    Args:
        workspace_id: The workspace to place.
        current_ctx: Current placement context (for pre-selecting state).
        on_changed: Async callable to invoke after placement changes.
    """
    user_id = _get_current_user_id()
    if user_id is None:
        ui.notify("Please log in to change placement", type="warning")
        return

    initial_mode = current_ctx.placement_type
    if initial_mode not in {"activity", "course"}:
        initial_mode = "loose"

    course_options = await _load_enrolled_course_options(user_id)
    selected: dict[str, UUID | None] = {}

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Change Workspace Placement").classes("text-lg font-bold mb-2")
        mode = ui.radio(
            options={
                "loose": "Unplaced",
                "activity": "Place in Activity",
                "course": "Associate with Course",
            },
            value=initial_mode,
        ).props('data-testid="placement-mode"')

        activity_container = ui.column().classes("w-full gap-2")
        course_container = ui.column().classes("w-full gap-2")

        with activity_container:
            _build_activity_cascade(course_options, selected)
        with course_container:
            _build_course_only_select(course_options, selected)

        def update_visibility() -> None:
            activity_container.set_visibility(mode.value == "activity")
            course_container.set_visibility(mode.value == "course")

        mode.on_value_change(lambda _: update_visibility())
        update_visibility()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):

            async def on_confirm() -> None:
                try:
                    ok = await _apply_placement(
                        cast("str", mode.value), workspace_id, selected
                    )
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                if ok:
                    dialog.close()
                    await on_changed()

            ui.button("Confirm", on_click=on_confirm).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()


async def _render_workspace_header(
    state: PageState,
    workspace_id: UUID,
    protect: bool = False,
) -> None:
    """Render the header row with save status, user count, and export button.

    Extracted from _render_workspace_view to keep statement count manageable.

    Args:
        state: Page state to populate with header element references.
        workspace_id: Workspace UUID for export.
        protect: Whether copy protection is active for this workspace.
    """
    with ui.row().classes("gap-4 items-center"):
        # Save status indicator (for E2E test observability)
        state.save_status = (
            ui.label("")
            .classes("text-sm text-gray-500")
            .props('data-testid="save-status"')
        )

        # User count badge
        state.user_count_badge = (
            ui.label("1 user")
            .classes("text-sm text-blue-600 bg-blue-100 px-2 py-0.5 rounded")
            .props('data-testid="user-count"')
        )
        # Update with actual count now that badge exists
        _update_user_count(state)

        # Export PDF button with loading state
        export_btn = ui.button(
            "Export PDF",
            icon="picture_as_pdf",
        ).props("color=primary")

        async def on_export_click() -> None:
            export_btn.disable()
            export_btn.props("loading")
            try:
                await _handle_pdf_export(state, workspace_id)
            finally:
                export_btn.props(remove="loading")
                export_btn.enable()

        export_btn.on_click(on_export_click)

        # Placement status chip (refreshable)
        @ui.refreshable
        async def placement_chip() -> None:
            ctx = await get_placement_context(workspace_id)
            label, color, icon = _get_placement_chip_style(ctx)
            is_authenticated = _get_current_user_id() is not None

            async def open_dialog() -> None:
                await _show_placement_dialog(workspace_id, ctx, placement_chip.refresh)

            # Template workspaces have locked placement
            clickable = is_authenticated and not ctx.is_template
            props_str = 'data-testid="placement-chip" outline'
            if not clickable:
                props_str += " disable"
            chip = ui.chip(
                text=label,
                icon=icon,
                color=color,
                on_click=open_dialog if clickable else None,
            ).props(props_str)
            if ctx.is_template:
                chip.tooltip("Template placement is managed by the Activity")
            elif not is_authenticated:
                chip.tooltip("Log in to change placement")

        await placement_chip()

        # Copy protection lock icon chip (Phase 4)
        if protect:
            ui.chip(
                "Protected",
                icon="lock",
                color="amber-7",
                text_color="white",
            ).props(
                'dense aria-label="Copy protection is enabled for this activity"'
            ).tooltip("Copy protection is enabled for this activity")


def _parse_sort_end_args(
    args: dict[str, Any],
) -> tuple[str, str, str, int]:
    """Parse SortableJS sort-end event args into highlight ID and tag keys.

    Extracts and normalizes IDs from SortableJS event args:
    - ``item``: Card HTML ID (format: ``hl-{highlight_id}``)
    - ``from``: Source container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``to``: Target container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``newIndex``: Position in target container (0-indexed)

    Returns tuple: (highlight_id, source_tag_raw_key, target_tag_raw_key,
    new_index)

    The ``hl-`` and ``sort-`` prefixes are stripped. The special key
    ``sort-untagged`` is mapped to an empty string (CRDT convention).

    Args:
        args: Event args dict from SortableJS sort-end event.

    Returns:
        Tuple of (highlight_id, source_tag, target_tag, new_index).
        Empty strings or -1 indicate missing/invalid values.
    """
    item_id: str = args.get("item", "")
    from_id: str = args.get("from", "")
    to_id: str = args.get("to", "")
    new_index: int = args.get("newIndex", -1)

    # Parse IDs: "hl-{highlight_id}" and "sort-{raw_key}"
    highlight_id = item_id.removeprefix("hl-")
    source_tag = from_id.removeprefix("sort-")
    target_tag = to_id.removeprefix("sort-")

    # "sort-untagged" → empty string (CRDT convention)
    if source_tag == "untagged":
        source_tag = ""
    if target_tag == "untagged":
        target_tag = ""

    return highlight_id, source_tag, target_tag, new_index


def _setup_organise_drag(state: PageState) -> None:
    """Set up SortableJS sort-end handler and Organise tab refresh.

    Wires the on_sort_end callback to CRDT operations and stores a
    refresh_organise callable on state for broadcast-triggered re-renders.

    Must be called after state is created but before _on_tab_change is
    defined, since the tab change handler calls state.refresh_organise.
    """

    async def _on_organise_sort_end(e: events.GenericEventArguments) -> None:
        """Handle a SortableJS sort-end event from Tab 2.

        Parses source/target tag from Sortable container HTML IDs
        (``sort-{raw_key}``) and highlight_id from card HTML ID
        (``hl-{highlight_id}``). Same-column reorders within the tag;
        cross-column moves reassign the highlight's tag. Both mutate
        CRDT and broadcast.
        """
        if state.crdt_doc is None:
            return

        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(e.args)

        if not highlight_id:
            logger.warning("Sort-end event with no item ID: %s", e.args)
            return

        if source_tag == target_tag:
            # Same-column reorder: SortableJS gives us the exact newIndex.
            current_order = state.crdt_doc.get_tag_order(target_tag)
            if highlight_id in current_order:
                current_order.remove(highlight_id)
            current_order.insert(new_index, highlight_id)
            state.crdt_doc.set_tag_order(
                target_tag, current_order, origin_client_id=state.client_id
            )
            ui.notify("Reordered", type="info", position="bottom")
        else:
            # Cross-column move: reassign tag and update orders
            state.crdt_doc.move_highlight_to_tag(
                highlight_id,
                from_tag=source_tag,
                to_tag=target_tag,
                position=new_index,
                origin_client_id=state.client_id,
            )
            ui.notify(
                f"Moved to {target_tag or 'Untagged'}",
                type="positive",
                position="bottom",
            )
            # Re-render to update card tag labels and colours
            _render_organise_now()

        # Persist to database
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )
        await pm.force_persist_workspace(state.workspace_id)

        # Broadcast to other clients for CRDT sync.
        if state.broadcast_update:
            await state.broadcast_update()

    async def _on_locate(start_char: int, end_char: int) -> None:
        """Warp to a highlight in Tab 1 from Tab 2 or Tab 3."""
        await _warp_to_highlight(state, start_char, end_char)

    def _render_organise_now() -> None:
        """Re-render the Organise tab with current CRDT state."""
        if not (state.organise_panel and state.crdt_doc):
            return
        if state.tag_info_list is None:
            state.tag_info_list = brief_tags_to_tag_info()
        render_organise_tab(
            state.organise_panel,
            state.tag_info_list,
            state.crdt_doc,
            on_sort_end=_on_organise_sort_end,
            on_locate=_on_locate,
        )

    state.refresh_organise = _render_organise_now


def _broadcast_yjs_update(
    workspace_id: UUID, origin_client_id: str, b64_update: str
) -> None:
    """Relay a Yjs update from one client's Milkdown editor to all others.

    Sends ``window._applyRemoteUpdate(b64)`` to every connected client
    that has initialised the Milkdown editor, except the originating client.
    """
    ws_key = str(workspace_id)
    for cid, cstate in _workspace_presence.get(ws_key, {}).items():
        if cid == origin_client_id:
            continue
        if cstate.has_milkdown_editor and cstate.nicegui_client:
            cstate.nicegui_client.run_javascript(
                f"window._applyRemoteUpdate('{b64_update}')"
            )
            logger.debug(
                "YJS_RELAY ws=%s from=%s to=%s",
                ws_key,
                origin_client_id[:8],
                cid[:8],
            )


async def _initialise_respond_tab(state: PageState, workspace_id: UUID) -> None:
    """Initialise the Respond tab with Milkdown editor and reference panel.

    Called once on first visit to the Respond tab (deferred rendering).
    Sets up the editor, CRDT relay, and marks the client for Yjs broadcast.
    """
    if not (state.respond_panel and state.crdt_doc):
        return

    tags = state.tag_info_list or brief_tags_to_tag_info()

    def _on_broadcast(b64_update: str, origin_client_id: str) -> None:
        _broadcast_yjs_update(workspace_id, origin_client_id, b64_update)

    async def _on_respond_locate(start_char: int, end_char: int) -> None:
        await _warp_to_highlight(state, start_char, end_char)

    (
        state.refresh_respond_references,
        state.sync_respond_markdown,
    ) = await render_respond_tab(
        panel=state.respond_panel,
        tags=tags,
        crdt_doc=state.crdt_doc,
        workspace_key=str(workspace_id),
        workspace_id=workspace_id,
        client_id=state.client_id,
        on_yjs_update_broadcast=_on_broadcast,
        on_locate=_on_respond_locate,
    )
    state.has_milkdown_editor = True
    # Mark this client as having a Milkdown editor for Yjs relay
    ws_key = str(workspace_id)
    clients = _workspace_presence.get(ws_key, {})
    if state.client_id in clients:
        clients[state.client_id].has_milkdown_editor = True


# -- Copy protection JS injection (Phase 4) ----------------------------------

_COPY_PROTECTION_JS = """
(function() {
  var PROTECTED = '#doc-container, ' +
    '[data-testid="organise-columns"], ' +
    '[data-testid="respond-reference-panel"]';

  function isProtected(e) {
    return e.target.closest && e.target.closest(PROTECTED);
  }

  function showToast() {
    Quasar.Notify.create({
      message: 'Copying is disabled for this activity.',
      type: 'warning',
      position: 'top-right',
      timeout: 3000,
      icon: 'content_copy',
      group: 'copy-protection'
    });
  }

  ['copy', 'cut', 'contextmenu', 'dragstart'].forEach(function(evt) {
    document.addEventListener(evt, function(e) {
      if (isProtected(e)) { e.preventDefault(); showToast(); }
    }, true);
  });

  document.addEventListener('paste', function(e) {
    if (e.target.closest && e.target.closest('#milkdown-respond-editor')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      showToast();
    }
  }, true);

  // Ctrl+P / Cmd+P print intercept
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
      e.preventDefault();
      showToast();
    }
  }, true);
})();
""".strip()


_COPY_PROTECTION_PRINT_CSS = """
@media print {
  .q-tab-panels { display: none !important; }
  .copy-protection-print-message { display: block !important; }
}
.copy-protection-print-message { display: none; }
""".strip()

_COPY_PROTECTION_PRINT_MESSAGE = (
    '<div class="copy-protection-print-message" '
    'style="display:none; padding: 2rem; text-align: center; font-size: 1.5rem;">'
    "Printing is disabled for this activity.</div>"
)


def _inject_copy_protection() -> None:
    """Inject client-side JS and CSS to block copy/cut/paste/drag/print.

    Called once during page construction when ``protect=True``. Uses event
    delegation from protected selectors so Milkdown copy (student's own
    writing) is unaffected. Paste is blocked on the Milkdown editor in
    capture phase before ProseMirror sees the event. Ctrl+P/Cmd+P is
    intercepted via keydown handler. CSS ``@media print`` hides tab panels
    and shows a "Printing is disabled" message instead.
    """
    ui.run_javascript(_COPY_PROTECTION_JS)
    ui.add_css(_COPY_PROTECTION_PRINT_CSS)
    ui.html(_COPY_PROTECTION_PRINT_MESSAGE, sanitize=False)


async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:  # noqa: PLR0915  # TODO(2026-02): refactor after Phase 7 — extract tab setup into helpers
    """Render the workspace content view with documents or add content form."""
    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    # Compute copy protection flag (Phase 3 — consumed by Phase 4 JS injection)
    auth_user = app.storage.user.get("auth_user")
    ctx = await get_placement_context(workspace_id)
    protect = ctx.copy_protection and not is_privileged_user(auth_user)

    # Create page state
    state = PageState(
        workspace_id=workspace_id,
        user_name=_get_current_username(),
    )

    # Set up client synchronization
    _setup_client_sync(workspace_id, client, state)

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    await _render_workspace_header(state, workspace_id, protect=protect)

    # Pre-load the Milkdown JS bundle so it's available when Tab 3 (Respond)
    # is first visited. Must be added during page construction — dynamically
    # injected <script> tags via ui.add_body_html after page load don't execute.
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Three-tab container (Phase 1: three-tab UI)
    state.initialised_tabs = {"Annotate"}

    with ui.tabs().classes("w-full") as tabs:
        ui.tab("Annotate")
        ui.tab("Organise")
        ui.tab("Respond")

    # Set up Tab 2 drag-and-drop and tab change handler (Phase 4)
    _setup_organise_drag(state)

    async def _on_tab_change(e: events.ValueChangeEventArguments) -> None:
        """Handle tab switching with deferred rendering and refresh."""
        assert state.initialised_tabs is not None
        tab_name = str(e.value)
        prev_tab = state.active_tab
        state.active_tab = tab_name

        # Sync markdown to CRDT when leaving the Respond tab (Phase 7).
        # Wrapped in try/except: sync failure must not block tab switch,
        # otherwise the Annotate refresh never runs and cards disappear.
        if prev_tab == "Respond" and state.sync_respond_markdown:
            try:
                await state.sync_respond_markdown()
            except Exception:
                logger.debug(
                    "RESPOND_MD_SYNC failed on tab leave, continuing",
                    exc_info=True,
                )

        if tab_name == "Organise" and state.organise_panel and state.crdt_doc:
            # Always re-render Organise tab to show current highlights
            state.initialised_tabs.add(tab_name)
            if state.refresh_organise:
                state.refresh_organise()
            return

        if tab_name == "Annotate":
            # Rebuild text node map and re-apply highlights. The text walker
            # does not modify the DOM (unlike char span injection) so this
            # is safe to call on every tab switch.
            _push_highlights_to_client(state)
            if state.refresh_annotations:
                state.refresh_annotations()
            _update_highlight_css(state)
            return

        if tab_name == "Respond":
            if tab_name not in state.initialised_tabs:
                state.initialised_tabs.add(tab_name)
                await _initialise_respond_tab(state, workspace_id)
            elif state.refresh_respond_references:
                state.refresh_respond_references()
            return

        if tab_name not in state.initialised_tabs:
            state.initialised_tabs.add(tab_name)

    with ui.tab_panels(tabs, value="Annotate", on_change=_on_tab_change).classes(
        "w-full"
    ) as panels:
        state.tab_panels = panels

        with ui.tab_panel("Annotate"):
            # Load CRDT document for this workspace
            crdt_doc = await _workspace_registry.get_or_create_for_workspace(
                workspace_id
            )

            # Load existing documents
            documents = await list_documents(workspace_id)

            if documents:
                # Render first document with highlight support
                doc = documents[0]
                await _render_document_with_highlights(state, doc, crdt_doc)
            else:
                # Show add content form (extracted to reduce function complexity)
                _render_add_content_form(workspace_id)

        with ui.tab_panel("Organise") as organise_panel:
            state.organise_panel = organise_panel
            ui.label("Organise tab content will appear here.").classes("text-gray-400")

        with ui.tab_panel("Respond") as respond_panel:
            state.respond_panel = respond_panel
            ui.label("Respond tab content will appear here.").classes("text-gray-400")

    # Inject copy protection JS after tab container is built (Phase 4)
    if protect:
        _inject_copy_protection()


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
    # Set up CSS and colors
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
            await _render_workspace_view(workspace_id, client)
        else:
            # Show create workspace form
            ui.label("No workspace selected. Create a new one:").classes("mb-2")
            ui.button(
                "Create Workspace",
                on_click=_create_workspace_and_redirect,
            ).classes("bg-blue-500 text-white")
