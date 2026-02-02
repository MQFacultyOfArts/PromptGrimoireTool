"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT

Route: /annotation
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from nicegui import app, ui

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.workspace_documents import (
    add_document,
    get_document,
    list_documents,
)
from promptgrimoire.db.workspaces import create_workspace, get_workspace
from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.models.case import TAG_COLORS, TAG_SHORTCUTS, BriefTag
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)

# Global registry for workspace annotation documents
_workspace_registry = AnnotationDocumentRegistry()


class _ClientState:
    """State for a connected client."""

    def __init__(self, callback: Any, color: str, name: str) -> None:
        self.callback = callback
        self.color = color
        self.name = name
        self.cursor_word: int | None = None
        self.selection_start: int | None = None
        self.selection_end: int | None = None

    def set_cursor(self, word_index: int | None) -> None:
        """Update cursor position."""
        self.cursor_word = word_index

    def set_selection(self, start: int | None, end: int | None) -> None:
        """Update selection range."""
        self.selection_start = start
        self.selection_end = end

    def to_cursor_dict(self) -> dict[str, Any]:
        """Get cursor as dict for CSS generation."""
        return {"word": self.cursor_word, "name": self.name, "color": self.color}

    def to_selection_dict(self) -> dict[str, Any]:
        """Get selection as dict for CSS generation."""
        return {
            "start_word": self.selection_start,
            "end_word": self.selection_end,
            "name": self.name,
            "color": self.color,
        }


# Track connected clients per workspace for broadcasting
# workspace_id -> {client_id -> _ClientState}
_connected_clients: dict[str, dict[str, _ClientState]] = {}

# Background tasks set - prevents garbage collection of fire-and-forget tasks
_background_tasks: set[asyncio.Task[None]] = set()

# CSS styles for annotation interface
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

    /* Character spans for selection */
    .char {
        cursor: text;
    }

    /* Hover highlight effect when card is hovered */
    .char.card-hover-highlight {
        outline: 2px solid #FFD700 !important;
        outline-offset: 1px;
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
    cursor_style: ui.element | None = None  # CSS for remote cursors
    selection_style: ui.element | None = None  # CSS for remote selections
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


def _process_text_to_char_spans(text: str) -> tuple[str, list[str]]:
    """Convert plain text to HTML with character-level spans.

    Each character (including whitespace) gets a span with data-char-index
    attribute for annotation targeting. Newlines create paragraph breaks
    but do not get indices.

    Args:
        text: Plain text to process.

    Returns:
        Tuple of (html_string, char_list) where char_list contains
        all indexed characters in order.
    """
    if not text:
        return "", []

    lines = text.split("\n")
    html_parts: list[str] = []
    chars: list[str] = []
    char_index = 0

    for line_num, line in enumerate(lines):
        if line:  # Non-empty line
            line_spans: list[str] = []
            for char in line:
                escaped = html.escape(char)
                span = (
                    f'<span class="char" data-char-index="{char_index}">'
                    f"{escaped}</span>"
                )
                line_spans.append(span)
                chars.append(char)
                char_index += 1
            html_parts.append(f'<p data-para="{line_num}">{"".join(line_spans)}</p>')
        else:  # Empty line
            html_parts.append(f'<p data-para="{line_num}">&nbsp;</p>')

    return "\n".join(html_parts), chars


def _get_tag_color(tag_str: str) -> str:
    """Get hex color for a tag string."""
    try:
        tag = BriefTag(tag_str)
        return TAG_COLORS.get(tag, "#FFEB3B")
    except ValueError:
        return "#FFEB3B"


def _build_highlight_css(highlights: list[dict[str, Any]]) -> str:
    """Generate CSS rules for highlighting characters with tag-specific colors.

    Uses stacked underlines to show overlapping highlights (matching latex.py):
    - 1 highlight: background + 1pt underline
    - 2 highlights: blended background + 2pt outer + 1pt inner underlines
    - 3+ highlights: blended background + 4pt thick underline

    Args:
        highlights: List of highlight dicts with start_word, end_word, tag.

    Returns:
        CSS string with background-color and underline rules.
    """
    # Build char -> list of (highlight_index, tag_color) mapping
    char_highlights: dict[int, list[str]] = {}
    for hl in highlights:
        start = int(hl.get("start_word", 0))
        end = int(hl.get("end_word", 0))
        hex_color = _get_tag_color(hl.get("tag", "highlight"))
        for i in range(start, end):
            if i not in char_highlights:
                char_highlights[i] = []
            char_highlights[i].append(hex_color)

    css_rules: list[str] = []
    for char_idx, colors in char_highlights.items():
        # Background: use first highlight's color with transparency
        first_color = colors[0]
        r, g, b = (
            int(first_color[1:3], 16),
            int(first_color[3:5], 16),
            int(first_color[5:7], 16),
        )
        bg_rgba = f"rgba({r}, {g}, {b}, 0.4)"

        overlap_count = len(colors)
        underline_color = first_color if overlap_count < 3 else "#333"
        thickness = f"{min(overlap_count, 3)}px"

        # Main character styling
        css_rules.append(
            f'[data-char-index="{char_idx}"] {{ '
            f"background-color: {bg_rgba}; "
            f"text-decoration: underline; "
            f"text-decoration-color: {underline_color}; "
            f"text-decoration-thickness: {thickness}; "
            f"text-underline-offset: 2px; }}"
        )

        # ::after pseudo-element to extend background through space
        # Only add if next character is also highlighted (check char_highlights)
        if (char_idx + 1) in char_highlights:
            css_rules.append(
                f"[data-char-index=\"{char_idx}\"]::after {{ content: ' '; }}"
            )

    return "\n".join(css_rules)


def _build_remote_cursor_css(
    cursors: dict[str, dict[str, Any]], exclude_client_id: str
) -> str:
    """Build CSS rules for remote users' cursors."""
    rules = []
    for cid, cursor in cursors.items():
        if cid == exclude_client_id:
            continue
        word = cursor.get("word")
        color = cursor.get("color", "#2196f3")
        name = cursor.get("name", "User")
        if word is None:
            continue
        # Cursor indicator using box-shadow (no layout shift)
        rules.append(
            f'[data-char-index="{word}"] {{ '
            f"position: relative; "
            f"box-shadow: inset 2px 0 0 0 {color}; }}"
        )
        # Floating name label
        rules.append(
            f'[data-char-index="{word}"]::before {{ '
            f'content: "{name}"; position: absolute; top: -1.2em; left: 0; '
            f"font-size: 0.6rem; background: {color}; color: white; "
            f"padding: 1px 3px; border-radius: 2px; white-space: nowrap; "
            f"z-index: 20; pointer-events: none; }}"
        )
    return "\n".join(rules)


def _build_remote_selection_css(
    selections: dict[str, dict[str, Any]], exclude_client_id: str
) -> str:
    """Build CSS rules for remote users' selections."""
    rules = []
    for cid, sel in selections.items():
        if cid == exclude_client_id:
            continue
        start = sel.get("start_word")
        end = sel.get("end_word")
        color = sel.get("color", "#ffeb3b")
        name = sel.get("name", "User")
        if start is None or end is None:
            continue
        if start > end:
            start, end = end, start
        # Selection highlight for all characters in range
        selectors = [f'[data-char-index="{i}"]' for i in range(start, end + 1)]
        if selectors:
            selector_str = ", ".join(selectors)
            rules.append(
                f"{selector_str} {{ background-color: {color}30 !important; "
                f"box-shadow: 0.3em 0 0 {color}30; }}"
            )
            rules.append(
                f'[data-char-index="{end}"] {{ box-shadow: none !important; }}'
            )
            # Name label on first character
            rules.append(f'[data-char-index="{start}"] {{ position: relative; }}')
            rules.append(
                f'[data-char-index="{start}"]::before {{ '
                f'content: "{name}"; position: absolute; top: -1.2em; left: 0; '
                f"font-size: 0.65rem; background: {color}; color: white; "
                f"padding: 1px 4px; border-radius: 2px; white-space: nowrap; "
                f"z-index: 10; pointer-events: none; }}"
            )
    return "\n".join(rules)


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

    # Get word positions for scroll-sync positioning
    start_word = highlight.get("start_word", 0)
    end_word = highlight.get("end_word", start_word)

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
            f'data-start-word="{start_word}" data-end-word="{end_word}"'
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

    # Update status to show saving
    if state.save_status:
        state.save_status.text = "Saving..."

    # Add highlight to CRDT (end_word is exclusive)
    start = min(state.selection_start, state.selection_end)
    end = max(state.selection_start, state.selection_end) + 1

    # Use tag value if provided, otherwise default to "highlight"
    tag_value = tag.value if tag else "highlight"

    # Extract highlighted text from document characters
    highlighted_text = ""
    if state.document_chars:
        chars_slice = state.document_chars[start:end]
        highlighted_text = "".join(chars_slice)

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

    # Release processing lock
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
        state.selection_start = e.args.get("start")
        state.selection_end = e.args.get("end")
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
        word_index = e.args.get("word")
        if state.broadcast_cursor:
            await state.broadcast_cursor(word_index)

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

        // Track cursor position over word spans for remote cursor display
        let lastCursorWord = null;
        const docC = document.getElementById('doc-container');
        if (docC) {
            docC.addEventListener('mouseover', function(e) {
                const word = e.target.closest('[data-word-index]');
                const wordIdx = word ? parseInt(word.dataset.wordIndex) : null;
                if (wordIdx !== lastCursorWord) {
                    lastCursorWord = wordIdx;
                    emitEvent('cursor_move', { word: wordIdx });
                }
            });
            docC.addEventListener('mouseleave', function() {
                if (lastCursorWord !== null) {
                    lastCursorWord = null;
                    emitEvent('cursor_move', { word: null });
                }
            });
        }
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

    # Extract characters from raw_content for text extraction when highlighting
    if hasattr(doc, "raw_content") and doc.raw_content:
        _, state.document_chars = _process_text_to_char_spans(doc.raw_content)

    # Load existing highlights and build initial CSS
    highlights = crdt_doc.get_highlights_for_document(str(doc.id))
    initial_css = _build_highlight_css(highlights)

    # Dynamic style element for highlights
    state.highlight_style = ui.element("style")
    state.highlight_style._props["innerHTML"] = initial_css

    # Dynamic style elements for remote cursors and selections
    state.cursor_style = ui.element("style")
    state.cursor_style._props["innerHTML"] = ""
    state.selection_style = ui.element("style")
    state.selection_style._props["innerHTML"] = ""

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

    # Set up scroll-synced card positioning
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
        "  // Card hover -> highlight corresponding words\n"
        "  let hoveredCard = null;\n"
        "  function clearHover() {\n"
        "    if (!hoveredCard) return;\n"
        "    const sw = parseInt(hoveredCard.dataset.startWord);\n"
        "    const ew = parseInt(hoveredCard.dataset.endWord) || sw;\n"
        "    for (let i = sw; i < ew; i++) {\n"
        "      const w = docC.querySelector('[data-word-index=\"'+i+'\"]');\n"
        "      if (w) w.classList.remove('card-hover-highlight');\n"
        "    }\n"
        "    hoveredCard = null;\n"
        "  }\n"
        "  annC.addEventListener('mouseover', function(e) {\n"
        "    const card = e.target.closest('[data-start-word]');\n"
        "    if (card === hoveredCard) return;\n"
        "    clearHover();\n"
        "    if (!card) return;\n"
        "    hoveredCard = card;\n"
        "    const sw = parseInt(card.dataset.startWord);\n"
        "    const ew = parseInt(card.dataset.endWord) || sw;\n"
        "    for (let i = sw; i < ew; i++) {\n"
        "      const w = docC.querySelector('[data-word-index=\"'+i+'\"]');\n"
        "      if (w) w.classList.add('card-hover-highlight');\n"
        "    }\n"
        "  });\n"
        "  annC.addEventListener('mouseleave', function() {\n"
        "    clearHover();\n"
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


def _update_cursor_css(state: PageState) -> None:
    """Update cursor CSS for remote users."""
    if state.cursor_style is None:
        return
    workspace_key = str(state.workspace_id)
    clients = _connected_clients.get(workspace_key, {})
    cursors = {cid: cs.to_cursor_dict() for cid, cs in clients.items()}
    css = _build_remote_cursor_css(cursors, state.client_id)
    state.cursor_style._props["innerHTML"] = css
    state.cursor_style.update()


def _update_selection_css(state: PageState) -> None:
    """Update selection CSS for remote users."""
    if state.selection_style is None:
        return
    workspace_key = str(state.workspace_id)
    clients = _connected_clients.get(workspace_key, {})
    selections = {cid: cs.to_selection_dict() for cid, cs in clients.items()}
    css = _build_remote_selection_css(selections, state.client_id)
    state.selection_style._props["innerHTML"] = css
    state.selection_style.update()


def _update_user_count(state: PageState) -> None:
    """Update user count badge."""
    if state.user_count_badge is None:
        return
    workspace_key = str(state.workspace_id)
    count = len(_connected_clients.get(workspace_key, {}))
    logger.debug(
        "USER_COUNT: ws=%s count=%d keys=%s",
        workspace_key,
        count,
        list(_connected_clients.keys()),
    )
    label = "1 user" if count == 1 else f"{count} users"
    state.user_count_badge.set_text(label)


def _notify_other_clients(workspace_key: str, exclude_client_id: str) -> None:
    """Fire-and-forget notification to other clients in workspace."""
    for cid, cstate in _connected_clients.get(workspace_key, {}).items():
        if cid != exclude_client_id and cstate.callback:
            with contextlib.suppress(Exception):
                task = asyncio.create_task(cstate.callback())
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)


def _setup_client_sync(
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
        for cid, cstate in _connected_clients.get(workspace_key, {}).items():
            if cid != client_id and cstate.callback:
                with contextlib.suppress(Exception):
                    await cstate.callback()

    state.broadcast_update = broadcast_update

    # Create broadcast function for cursor updates
    async def broadcast_cursor(word_index: int | None) -> None:
        clients = _connected_clients.get(workspace_key, {})
        if client_id in clients:
            clients[client_id].set_cursor(word_index)
        # Notify other clients to refresh cursor CSS
        for cid, cstate in clients.items():
            if cid != client_id and cstate.callback:
                with contextlib.suppress(Exception):
                    await cstate.callback()

    state.broadcast_cursor = broadcast_cursor

    # Create broadcast function for selection updates
    async def broadcast_selection(start: int | None, end: int | None) -> None:
        clients = _connected_clients.get(workspace_key, {})
        if client_id in clients:
            clients[client_id].set_selection(start, end)
        # Notify other clients to refresh selection CSS
        for cid, cstate in clients.items():
            if cid != client_id and cstate.callback:
                with contextlib.suppress(Exception):
                    await cstate.callback()

    state.broadcast_selection = broadcast_selection

    # Callback for receiving updates from other clients
    async def handle_update_from_other() -> None:
        _update_highlight_css(state)
        _update_cursor_css(state)
        _update_selection_css(state)
        _update_user_count(state)
        if state.refresh_annotations:
            state.refresh_annotations()

    # Register this client
    if workspace_key not in _connected_clients:
        _connected_clients[workspace_key] = {}
    _connected_clients[workspace_key][client_id] = _ClientState(
        callback=handle_update_from_other,
        color=state.user_color,
        name=state.user_name,
    )
    logger.info(
        "CLIENT_REGISTERED: ws=%s client=%s total=%d",
        workspace_key,
        client_id[:8],
        len(_connected_clients[workspace_key]),
    )

    # Update own user count and notify others
    _update_user_count(state)
    _notify_other_clients(workspace_key, client_id)

    # Disconnect handler
    async def on_disconnect() -> None:
        if workspace_key in _connected_clients:
            _connected_clients[workspace_key].pop(client_id, None)
            # Broadcast to update cursors/selections (remove this client's)
            for _cid, cstate in _connected_clients.get(workspace_key, {}).items():
                if cstate.callback:
                    with contextlib.suppress(Exception):
                        await cstate.callback()
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

        # Get document's original raw_content (preserves newlines)
        doc = await get_document(state.document_id)
        raw_content = doc.raw_content if doc else ""

        # DEBUG: Log raw_content to see if newlines are present
        logger.info(
            "[PDF DEBUG] raw_content length=%d, newlines=%d, first 200 chars: %r",
            len(raw_content),
            raw_content.count("\n"),
            raw_content[:200],
        )

        # Generate PDF
        pdf_path = await export_annotation_pdf(
            html_content=raw_content,
            highlights=highlights,
            tag_colours=tag_colours,
            general_notes="",
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


async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:
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

    # Set up client synchronization
    _setup_client_sync(workspace_id, client, state)

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

    # Header row with save status and export button
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
                html_content, _ = _process_text_to_char_spans(
                    content_input.value.strip()
                )
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
