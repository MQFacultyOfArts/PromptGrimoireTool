"""Pre-restart flush and connection-count API endpoints.

Called by ``deploy/restart.sh`` during zero-downtime deploys to flush
in-flight CRDT state and navigate clients to a holding page before the
application process restarts.
"""

from __future__ import annotations

import hmac
import sys
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from starlette.responses import JSONResponse

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from typing import Any

    from starlette.requests import Request

    from promptgrimoire.crdt import AnnotationDocumentRegistry

logger = structlog.get_logger()


def _validate_restart_token(request: Request) -> JSONResponse | None:
    """Validate Bearer token for restart endpoints.

    Returns an error JSONResponse if validation fails, or None if valid.
    """
    secret = get_settings().admin.pre_restart_token.get_secret_value()
    if not secret:
        return JSONResponse(
            {"error": "PRE_RESTART_TOKEN not configured"}, status_code=503
        )

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    token = auth_header[len("bearer ") :]
    if not hmac.compare_digest(token, secret):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return None


def _get_annotation_state() -> tuple[dict, AnnotationDocumentRegistry | None]:
    """Lazy accessor for annotation module state.

    Avoids importing the annotation package at module level (which
    triggers NiceGUI page registration and UI element creation).
    The annotation module is only in ``sys.modules`` when the server
    is running, which is exactly when these handlers are called.
    """
    mod = sys.modules.get("promptgrimoire.pages.annotation")
    if mod is None:
        return {}, None
    return mod._workspace_presence, mod._workspace_registry


def _replace_crdt_text(text_field: Any, new_value: str, doc: Any) -> None:
    """Atomically replace a CRDT Text field's content.

    Mirrors the write pattern in ``pages/annotation/respond.py:382-391``.
    """
    current = str(text_field)
    if current == new_value:
        return
    with doc.transaction():
        current_len = len(text_field)
        if current_len > 0:
            del text_field[:current_len]
        if new_value:
            text_field += new_value


async def _flush_single_client(
    workspace_id: str,
    client_id: str,
    presence: Any,
    workspace_registry: AnnotationDocumentRegistry,
) -> None:
    """Flush one client's Milkdown editor content into the CRDT document."""
    if not presence.has_milkdown_editor:
        return
    if not presence.nicegui_client or presence.nicegui_client._deleted:
        return
    try:
        md = await presence.nicegui_client.run_javascript(
            "window._getMilkdownMarkdown()", timeout=3.0
        )
        if md is None:
            md = ""
        crdt_doc = await workspace_registry.get_or_create_for_workspace(
            UUID(workspace_id)
        )
        _replace_crdt_text(crdt_doc.response_draft_markdown, md, crdt_doc.doc)
    except Exception:
        logger.warning(
            "pre_restart_flush_failed",
            workspace_id=workspace_id,
            client_id=client_id,
            exc_info=True,
        )


async def _flush_milkdown_to_crdt() -> None:
    """Extract Milkdown editor content and write it into CRDT documents.

    Iterates all connected clients with active Milkdown editors, pulls
    the current markdown via ``window._getMilkdownMarkdown()``, and
    writes it into the workspace's CRDT ``response_draft_markdown``
    field.  Tolerates stale/disconnected clients by catching all
    exceptions per-client.
    """
    workspace_presence, workspace_registry = _get_annotation_state()
    if workspace_registry is None:
        return

    for workspace_id, clients in list(workspace_presence.items()):
        for client_id, presence in list(clients.items()):
            await _flush_single_client(
                workspace_id, client_id, presence, workspace_registry
            )


async def pre_restart_handler(request: Request) -> JSONResponse:
    """Flush CRDT state and invalidate sessions before manual restart.

    POST /api/pre-restart -- requires Bearer token matching
    ADMIN__PRE_RESTART_TOKEN.

    Does NOT navigate clients to /restarting. HAProxy's 503 maintenance
    page handles the user-facing restart UX. Previous approach navigated
    sequentially (2s timeout x N clients) and raced with HAProxy drain.
    """
    error = _validate_restart_token(request)
    if error is not None:
        return error

    import asyncio  # noqa: PLC0415

    from nicegui import Client  # noqa: PLC0415

    from promptgrimoire.crdt.persistence import get_persistence_manager  # noqa: PLC0415

    connected = [c for c in Client.instances.values() if c.has_socket_connection]
    initial_count = len(connected)

    # Flush Milkdown content to CRDT for all connected editors
    await _flush_milkdown_to_crdt()

    # Persist all dirty CRDT state to database
    await get_persistence_manager().persist_all_dirty_workspaces()

    # Invalidate all sessions so no stale auth survives the restart
    from promptgrimoire.diagnostics import _invalidate_all_sessions  # noqa: PLC0415

    await _invalidate_all_sessions()

    # Trigger a reload on connected clients so they disconnect cleanly.
    # Parallelized with a 5s global timeout — unresponsive clients are
    # logged and skipped rather than blocking the deploy for minutes.
    async def _disconnect_client(client: Client) -> None:
        try:
            await client.run_javascript(
                "window.location.reload()",
                timeout=1.0,
            )
        except Exception:
            logger.debug(
                "pre_restart_disconnect_skipped",
                client_id=client.id,
            )

    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(_disconnect_client(c) for c in connected),
                return_exceptions=True,
            ),
            timeout=5.0,
        )
    except TimeoutError:
        logger.warning(
            "pre_restart_disconnect_timeout",
            remaining=len(connected),
        )

    logger.info(
        "pre_restart_complete",
        initial_count=initial_count,
    )
    return JSONResponse({"initial_count": initial_count})


async def connection_count_handler(request: Request) -> JSONResponse:
    """Return count of connected WebSocket clients.

    GET /api/connection-count -- requires Bearer token matching
    ADMIN__PRE_RESTART_TOKEN.
    """
    error = _validate_restart_token(request)
    if error is not None:
        return error

    from nicegui import Client  # noqa: PLC0415

    count = len([c for c in Client.instances.values() if c.has_socket_connection])
    return JSONResponse({"count": count})
