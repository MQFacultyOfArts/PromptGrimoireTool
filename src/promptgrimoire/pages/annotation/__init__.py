"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT

Route: /annotation

Package structure (12 authored modules):
    __init__    Core types, globals, route definition
    broadcast   Multi-client sync and remote presence
    cards       Annotation card UI components
    content_form  Document upload/paste form
    css         CSS styles and tag toolbar
    document    Document rendering and selection wiring
    highlights  Highlight CRUD and rendering
    organise    Organise tab (tag columns, drag-and-drop)
    pdf_export  PDF export orchestration
    respond     Respond tab (reference panel, editor)
    tags        Tag definitions and colour mapping
    workspace   Workspace header, tabs, and view orchestration
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from string.templatelib import Interpolation, Template
from typing import TYPE_CHECKING, Any
from uuid import UUID

from nicegui import ui

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)

# Pre-load export package to break circular import chain:
# input_pipeline.html_input -> export.platforms -> export.__init__ ->
# export.pandoc -> export.highlight_spans -> input_pipeline.html_input.
# The monolith imported export BEFORE input_pipeline, ensuring export
# was fully loaded. We replicate that ordering here.
from promptgrimoire.export.pdf_export import (
    export_annotation_pdf as export_annotation_pdf,
)
from promptgrimoire.input_pipeline.html_input import (
    extract_text_from_html as extract_text_from_html,
)

if TYPE_CHECKING:
    import asyncio

    from nicegui import Client

    from promptgrimoire.pages.annotation.tags import TagInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WARNING: Definition-before-import ordering is CRITICAL in this file.
#
# 1. Stdlib/third-party imports (above)
# 2. Define: PageState, _RemotePresence, _RawJS, _render_js()   (this section)
#    Define: _workspace_registry, _workspace_presence, _background_tasks
# 3. Import from submodules (workspace.py etc.) -- types already exist
# 4. Define: annotation_page() -- uses imported functions
#
# Do not reorder. Types must be defined before submodule imports
# to resolve circular dependency (workspace.py imports PageState from here).
# ---------------------------------------------------------------------------

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
        Any  # Callable[[], Awaitable[None]] -- ty cannot validate closure signatures
    )
    cursor_char: int | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    has_milkdown_editor: bool = False

    async def invoke_callback(self) -> None:
        """Run the callback inside this client's NiceGUI slot context.

        Callers MUST use this method instead of calling ``callback()``
        directly.  It enters the client's context manager so that
        ``ui.run_javascript()`` and element creation resolve to the
        correct browser tab.  If the client has disconnected (weakref
        dead), the ``with`` block raises and the caller's
        ``contextlib.suppress(Exception)`` handles it.
        """
        if self.callback and self.nicegui_client:
            with self.nicegui_client:
                await self.callback()


# Track connected clients per workspace for broadcasting
# workspace_id -> {client_id -> _RemotePresence}
_workspace_presence: dict[str, dict[str, _RemotePresence]] = {}


class _RawJS:
    """Pre-serialised JavaScript literal -- bypasses ``_render_js`` escaping.

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
    # Tag info list for Tab 2 (Organise) -- populated on first visit
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


# ---------------------------------------------------------------------------
# Section 3: Submodule imports (types above are now available)
# ---------------------------------------------------------------------------

from promptgrimoire.pages.annotation.css import _setup_page_styles  # noqa: E402
from promptgrimoire.pages.annotation.workspace import (  # noqa: E402
    _create_workspace_and_redirect,
    _render_workspace_view,
)
from promptgrimoire.pages.registry import page_route  # noqa: E402


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
