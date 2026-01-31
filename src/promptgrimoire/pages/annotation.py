"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT

Route: /annotation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import ui

from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


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
            # Show workspace view (to be implemented in Task 3+)
            ui.label(f"Workspace: {workspace_id}").classes("text-gray-600")
            ui.label("Workspace content will appear here...")
        else:
            # Show create workspace form
            ui.label("No workspace selected. Create a new one:").classes("mb-2")
            ui.button(
                "Create Workspace",
                on_click=lambda: ui.notify("TODO: implement in Task 2"),
            ).classes("bg-blue-500 text-white")
