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
from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.db.workspace_documents import add_document, list_documents
from promptgrimoire.db.workspaces import create_workspace, get_workspace
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


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


async def _render_workspace_view(workspace_id: UUID) -> None:
    """Render the workspace content view with documents or add content form."""
    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

    # Load existing documents
    documents = await list_documents(workspace_id)

    if documents:
        # Render existing documents
        for doc in documents:
            with ui.element("div").classes(
                "document-content border p-4 rounded bg-white mt-4"
            ):
                ui.html(doc.content, sanitize=False).classes("prose")
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
    requires_auth=False,  # Will add auth requirement in Task 2
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
