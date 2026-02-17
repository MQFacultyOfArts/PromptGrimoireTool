"""Multi-client sync and remote presence for the annotation page.

Handles broadcasting updates, cursor positions, and selections
between connected clients in the same workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from nicegui import app, ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation import (
    PageState,
    _background_tasks,
    _RemotePresence,
    _render_js,
    _workspace_presence,
    _workspace_registry,
)
from promptgrimoire.pages.annotation.highlights import _update_highlight_css

if TYPE_CHECKING:
    from uuid import UUID

    from nicegui import Client

logger = logging.getLogger(__name__)


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
                task = asyncio.create_task(cstate.invoke_callback())
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
                    await cstate.invoke_callback()

    state.broadcast_update = broadcast_update

    # Create broadcast function for cursor updates -- JS-targeted (AC3.4)
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

    # Create broadcast function for selection updates -- JS-targeted (AC3.4)
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

    # Resolve user_id for revocation lookup
    auth_user = app.storage.user.get("auth_user")
    client_user_id = str(auth_user.get("user_id", "")) if auth_user else None

    _workspace_presence[workspace_key][client_id] = _RemotePresence(
        name=state.user_name,
        color=state.user_color,
        nicegui_client=client,
        callback=handle_update_from_other,
        user_id=client_user_id,
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
        last_client = False
        if workspace_key in _workspace_presence:
            _workspace_presence[workspace_key].pop(client_id, None)
            # Clean up empty workspace dict to prevent slow memory leak
            if not _workspace_presence[workspace_key]:
                del _workspace_presence[workspace_key]
                last_client = True
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
                        await presence.invoke_callback()
        pm = get_persistence_manager()
        await pm.force_persist_workspace(workspace_id)

        # Evict CRDT doc from registries when last client leaves.
        # This prevents unbounded memory growth from accumulated pycrdt
        # documents. The doc is re-loaded from DB on the next visit.
        if last_client:
            doc_id = f"ws-{workspace_id}"
            pm.evict_workspace(workspace_id, doc_id)
            _workspace_registry.remove(doc_id)
            logger.info(
                "Last client left workspace %s — evicted CRDT doc", workspace_id
            )

    client.on_disconnect(on_disconnect)


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


async def revoke_and_redirect(workspace_id: UUID, user_id: UUID) -> int:
    """Revoke access and redirect the user if they are connected.

    Finds all connected clients for this user in this workspace's presence
    registry, sends a toast notification and redirect via run_javascript()
    on the remote client.

    Note: run_javascript() is necessary here because we are pushing to a
    different client (the revoked user), not the current client. NiceGUI's
    ui.notify()/ui.navigate.to() only work in the current client context.

    Parameters
    ----------
    workspace_id : UUID
        The workspace UUID.
    user_id : UUID
        The user UUID whose access was revoked.

    Returns
    -------
    int
        Number of connected clients that were notified.
    """
    workspace_key = str(workspace_id)
    notified = 0

    if workspace_key not in _workspace_presence:
        return 0

    # Find clients belonging to this user
    clients_to_remove: list[str] = []
    for client_id, presence in _workspace_presence[workspace_key].items():
        if presence.user_id == str(user_id):
            clients_to_remove.append(client_id)

    for client_id in clients_to_remove:
        presence = _workspace_presence[workspace_key].get(client_id)
        if presence and presence.nicegui_client is not None:
            with contextlib.suppress(Exception):
                await presence.nicegui_client.run_javascript(
                    'Quasar.Notify.create({type: "negative", '
                    'message: "Your access has been revoked"}); '
                    'window.location.href = "/courses";',
                    timeout=2.0,
                )
                notified += 1

        # Remove from registry
        _workspace_presence[workspace_key].pop(client_id, None)

    # Clean up empty workspace dict
    if workspace_key in _workspace_presence and not _workspace_presence[workspace_key]:
        del _workspace_presence[workspace_key]

    return notified
