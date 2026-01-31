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
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.workspace_documents import add_document, list_documents
from promptgrimoire.db.workspaces import create_workspace, get_workspace
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)

# Global registry for workspace annotation documents
_workspace_registry = AnnotationDocumentRegistry()


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


def _get_current_user_id() -> UUID | None:
    """Get the current authenticated user's ID from session."""
    auth_user = app.storage.user.get("auth_user")
    if not auth_user:
        return None
    user_id_str = auth_user.get("user_id")
    if not user_id_str:
        return None
    try:
        return UUID(user_id_str)
    except ValueError:
        return None


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

    Requires authenticated user with user_id in session.
    """
    user_id = _get_current_user_id()
    if not user_id:
        ui.notify("Please log in to create a workspace", type="warning")
        ui.navigate.to("/login")
        return

    try:
        workspace = await create_workspace(created_by=user_id)
        logger.info("Created workspace %s for user %s", workspace.id, user_id)
        ui.navigate.to(f"/annotation?workspace_id={workspace.id}")
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
    """Generate CSS rules for highlighting words.

    Args:
        highlights: List of highlight dicts with start_word, end_word.

    Returns:
        CSS string with background-color rules for highlighted words.
    """
    css_rules: list[str] = []
    for hl in highlights:
        start = int(hl.get("start_word", 0))
        end = int(hl.get("end_word", 0))
        # Use yellow highlight color (rgba(255, 235, 59, 0.5))
        for i in range(start, end):
            css_rules.append(
                f'[data-word-index="{i}"] {{ '
                f"background-color: rgba(255, 235, 59, 0.5); "
                f"}}"
            )
    return "\n".join(css_rules)


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


async def _add_highlight(state: PageState) -> None:
    """Add a highlight from current selection to CRDT."""
    if state.selection_start is None or state.selection_end is None:
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

    state.crdt_doc.add_highlight(
        start_word=start,
        end_word=end,
        tag="highlight",
        text="",  # Could extract from DOM if needed
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

    # JavaScript to detect text selection on mouseup
    js_code = """
    document.addEventListener('mouseup', function(event) {
        // Small delay to let selection complete
        setTimeout(function() {
            const selection = window.getSelection();
            if (selection.rangeCount > 0 && !selection.isCollapsed) {
                const range = selection.getRangeAt(0);

                // Find word spans in the selection
                let startEl = range.startContainer;
                if (startEl.nodeType === Node.TEXT_NODE) {
                    startEl = startEl.parentElement;
                }
                startEl = startEl.closest('[data-word-index]');

                let endEl = range.endContainer;
                if (endEl.nodeType === Node.TEXT_NODE) {
                    endEl = endEl.parentElement;
                }
                endEl = endEl.closest('[data-word-index]');

                if (startEl && endEl) {
                    const start = parseInt(startEl.dataset.wordIndex);
                    const end = parseInt(endEl.dataset.wordIndex);
                    emitEvent('selection_made', {
                        start: Math.min(start, end),
                        end: Math.max(start, end)
                    });
                }
            }
        }, 10);
    });

    // Clear selection on click (but not drag)
    let mouseDownPos = null;
    document.addEventListener('mousedown', function(e) {
        mouseDownPos = {x: e.clientX, y: e.clientY};
    });
    document.addEventListener('click', function(e) {
        if (mouseDownPos) {
            const dx = Math.abs(e.clientX - mouseDownPos.x);
            const dy = Math.abs(e.clientY - mouseDownPos.y);
            // Only clear if it's a click, not a drag
            if (dx < 5 && dy < 5) {
                const selection = window.getSelection();
                if (selection.isCollapsed) {
                    emitEvent('selection_cleared', {});
                }
            }
        }
    });
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

    # Load existing highlights and build initial CSS
    highlights = crdt_doc.get_highlights_for_document(str(doc.id))
    initial_css = _build_highlight_css(highlights)

    # Dynamic style element for highlights
    state.highlight_style = ui.element("style")
    state.highlight_style._props["innerHTML"] = initial_css

    # Highlight creation menu (hidden by default)
    with (
        ui.card()
        .classes("fixed z-50 shadow-lg")
        .style("top: 50%; left: 50%; transform: translate(-50%, -50%);")
        .props('data-testid="highlight-menu"') as highlight_menu
    ):
        highlight_menu.set_visibility(False)
        state.highlight_menu = highlight_menu

        async def handle_highlight_click() -> None:
            await _add_highlight(state)

        ui.button(
            "Highlight",
            on_click=handle_highlight_click,
        ).classes("bg-yellow-400 text-black")

    # Document content container
    with ui.element("div").classes("document-content border p-4 rounded bg-white mt-4"):
        ui.html(doc.content, sanitize=False).classes("prose selection:bg-blue-200")

    # Set up selection detection
    _setup_selection_handlers(state)


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

    # Save status indicator (for E2E test observability)
    state.save_status = (
        ui.label("").classes("text-sm text-gray-500").props('data-testid="save-status"')
    )

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
                ui.navigate.to(f"/annotation?workspace_id={workspace_id}")
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
    # Get workspace_id from query params if present
    workspace_id_str = client.request.query_params.get("workspace_id")
    workspace_id: UUID | None = None

    if workspace_id_str:
        try:
            workspace_id = UUID(workspace_id_str)
        except ValueError:
            ui.notify("Invalid workspace ID", type="negative")

    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
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
