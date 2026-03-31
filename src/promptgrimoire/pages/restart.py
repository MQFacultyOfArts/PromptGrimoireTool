"""Pre-restart flush and connection-count API endpoints.

Called by ``deploy/restart.sh`` during zero-downtime deploys to flush
in-flight CRDT state and navigate clients to a holding page before the
application process restarts.
"""

from __future__ import annotations

import contextlib
import hmac
import sys
from typing import TYPE_CHECKING

import structlog
from starlette.responses import JSONResponse

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
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


async def _flush_milkdown_to_crdt() -> None:
    """Fire-and-forget flush of Milkdown editor content into CRDT documents.

    Sends ``window._flushRespondMarkdownNow()`` to every connected client
    with an active Milkdown editor (fire-and-forget — no per-client await).
    Then waits a bounded 1-second drain deadline for the resulting
    ``respond_markdown_flush`` events to arrive and be processed by each
    client's handler in ``respond.py``.

    This replaces the old per-client ``await run_javascript`` loop that
    blocked the event loop serially for every editor client.
    """
    import asyncio  # noqa: PLC0415

    workspace_presence, workspace_registry = _get_annotation_state()
    if workspace_registry is None:
        return

    flushed = 0
    for _workspace_id, clients in list(workspace_presence.items()):
        for _client_id, presence in list(clients.items()):
            if not presence.has_milkdown_editor:
                continue
            if not presence.nicegui_client or presence.nicegui_client._deleted:
                continue
            try:
                presence.nicegui_client.run_javascript(
                    "window._flushRespondMarkdownNow()"
                )
                flushed += 1
            except Exception:
                logger.warning(
                    "pre_restart_flush_fire_failed",
                    client_id=_client_id,
                    exc_info=True,
                )

    if flushed:
        # Bounded drain deadline — events arrive within milliseconds
        await asyncio.sleep(1.0)
        logger.debug("pre_restart_flush_drain", flushed_clients=flushed)


async def pre_restart_handler(request: Request) -> JSONResponse:
    """Flush CRDT state and navigate all clients to /restarting.

    POST /api/pre-restart -- requires Bearer token matching
    ADMIN__PRE_RESTART_TOKEN.
    """
    error = _validate_restart_token(request)
    if error is not None:
        return error

    from nicegui import Client  # noqa: PLC0415

    from promptgrimoire.crdt.persistence import get_persistence_manager  # noqa: PLC0415

    initial_count = len(
        [c for c in Client.instances.values() if c.has_socket_connection]
    )

    # Flush Milkdown content to CRDT for all connected editors
    await _flush_milkdown_to_crdt()

    # Persist all dirty CRDT state to database
    await get_persistence_manager().persist_all_dirty_workspaces()

    # Clear admission queue
    from promptgrimoire.admission import get_admission_state  # noqa: PLC0415

    with contextlib.suppress(RuntimeError):
        get_admission_state().clear()

    # Navigate BEFORE invalidating — clients still rendering pages will
    # hit `assert auth_user is not None` if sessions vanish mid-load.
    for client in list(Client.instances.values()):
        if not client.has_socket_connection:
            continue
        try:
            client.run_javascript(
                'window.location.href = "/restarting?return="'
                " + encodeURIComponent("
                "location.pathname + location.search + location.hash)",
                timeout=2.0,
            )
        except Exception:
            logger.warning(
                "pre_restart_navigate_failed",
                client_id=client.id,
                exc_info=True,
            )

    # Invalidate all sessions so no stale auth survives the restart
    from promptgrimoire.diagnostics import _invalidate_all_sessions  # noqa: PLC0415

    await _invalidate_all_sessions()

    logger.info("pre_restart_complete", initial_count=initial_count)
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
