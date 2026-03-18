"""Multi-client sync and remote presence for the annotation page.

Handles broadcasting updates, cursor positions, and selections
between connected clients in the same workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time as _time
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from nicegui import app, ui
from structlog.contextvars import bind_contextvars

from promptgrimoire.auth.anonymise import anonymise_author
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

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


def resolve_broadcast_label(
    *,
    sender_name: str,
    sender_user_id: str | None,
    receiver_user_id: str | None,
    is_anonymous: bool,
    receiver_is_privileged: bool,
    sender_is_privileged: bool = False,
) -> str:
    """Resolve the display label for a sender as seen by a specific receiver.

    Delegates to ``anonymise_author`` with the receiver's context.
    """
    return anonymise_author(
        author=sender_name,
        user_id=sender_user_id,
        viewing_user_id=receiver_user_id,
        anonymous_sharing=is_anonymous,
        viewer_is_privileged=receiver_is_privileged,
        author_is_privileged=sender_is_privileged,
    )


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
    for cid, presence in list(_workspace_presence.get(workspace_key, {}).items()):
        if cid == exclude_client_id or presence.nicegui_client is None:
            continue
        with contextlib.suppress(Exception):
            await presence.nicegui_client.run_javascript(js, timeout=2.0)


def _notify_other_clients(workspace_key: str, exclude_client_id: str) -> None:
    """Fire-and-forget notification to other clients in workspace."""
    for cid, cstate in list(_workspace_presence.get(workspace_key, {}).items()):
        if cid != exclude_client_id and cstate.callback:
            with contextlib.suppress(Exception):
                task = asyncio.create_task(cstate.invoke_callback())
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)


def _rebuild_tag_state_from_crdt(state: PageState) -> None:
    """Rebuild tag_info_list from CRDT maps after a remote update.

    Called by handle_update_from_other so receiving clients pick up
    tag creates, edits, and deletes broadcast by the originating client.
    """
    if state.crdt_doc is None:
        return
    from promptgrimoire.pages.annotation.tags import (  # noqa: PLC0415
        workspace_tags_from_crdt,
    )

    state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)


async def _broadcast_cursor_update(
    workspace_key: str,
    client_id: str,
    state: PageState,
    char_index: int | None,
) -> None:
    """Broadcast cursor position to all other clients in the workspace."""
    clients = _workspace_presence.get(workspace_key, {})
    if client_id in clients:
        clients[client_id].cursor_char = char_index
    if char_index is None:
        js = _render_js(t"removeRemoteCursor({client_id})")
        await _broadcast_js_to_others(workspace_key, client_id, js)
        return
    color = state.user_color
    for cid, presence in list(clients.items()):
        if cid == client_id or presence.nicegui_client is None:
            continue
        name = resolve_broadcast_label(
            sender_name=state.user_name,
            sender_user_id=state.user_id,
            receiver_user_id=presence.user_id,
            is_anonymous=state.is_anonymous,
            receiver_is_privileged=presence.viewer_is_privileged,
            sender_is_privileged=state.viewer_is_privileged,
        )
        js = _render_js(
            t"renderRemoteCursor("
            t"document.getElementById('doc-container')"
            t", {client_id}, {char_index}"
            t", {name}, {color})"
        )
        with contextlib.suppress(Exception):
            await presence.nicegui_client.run_javascript(js, timeout=2.0)


async def _broadcast_selection_update(
    workspace_key: str,
    client_id: str,
    state: PageState,
    start: int | None,
    end: int | None,
) -> None:
    """Broadcast text selection to all other clients in the workspace."""
    clients = _workspace_presence.get(workspace_key, {})
    if client_id in clients:
        clients[client_id].selection_start = start
        clients[client_id].selection_end = end
    if start is None or end is None:
        js = _render_js(t"removeRemoteSelection({client_id})")
        await _broadcast_js_to_others(workspace_key, client_id, js)
        return
    color = state.user_color
    for cid, presence in list(clients.items()):
        if cid == client_id or presence.nicegui_client is None:
            continue
        name = resolve_broadcast_label(
            sender_name=state.user_name,
            sender_user_id=state.user_id,
            receiver_user_id=presence.user_id,
            is_anonymous=state.is_anonymous,
            receiver_is_privileged=presence.viewer_is_privileged,
            sender_is_privileged=state.viewer_is_privileged,
        )
        js = _render_js(
            t"renderRemoteSelection({client_id}, {start}, {end}, {name}, {color})"
        )
        with contextlib.suppress(Exception):
            await presence.nicegui_client.run_javascript(js, timeout=2.0)


def _replay_existing_cursors(
    workspace_key: str,
    client_id: str,
    state: PageState,
) -> None:
    """Send existing remote cursors/selections to a newly connected client."""
    for cid, presence in list(_workspace_presence.get(workspace_key, {}).items()):
        if cid == client_id:
            continue
        resolved_name = resolve_broadcast_label(
            sender_name=presence.name,
            sender_user_id=presence.user_id,
            receiver_user_id=state.user_id,
            is_anonymous=state.is_anonymous,
            receiver_is_privileged=state.viewer_is_privileged,
            sender_is_privileged=presence.viewer_is_privileged,
        )
        if presence.cursor_char is not None:
            char = presence.cursor_char
            color = presence.color
            js = _render_js(
                t"renderRemoteCursor("
                t"document.getElementById('doc-container')"
                t", {cid}, {char}"
                t", {resolved_name}, {color})"
            )
            ui.run_javascript(js)
        if presence.selection_start is not None and presence.selection_end is not None:
            s_start = presence.selection_start
            s_end = presence.selection_end
            color = presence.color
            js = _render_js(
                t"renderRemoteSelection("
                t"{cid}, {s_start}, {s_end},"
                t" {resolved_name}, {color})"
            )
            ui.run_javascript(js)


async def _handle_client_delete(
    workspace_key: str,
    client_id: str,
    workspace_id: UUID,
) -> None:
    """Clean up when a client is permanently removed.

    Runs after reconnect_timeout expires with no reconnection.
    """
    t0 = _time.monotonic()
    logger.debug("DELETE[%s] ws=%s start", client_id, workspace_id)

    last_client = False
    if workspace_key in _workspace_presence:
        _workspace_presence[workspace_key].pop(client_id, None)
        if not _workspace_presence[workspace_key]:
            del _workspace_presence[workspace_key]
            last_client = True
        removal_js = _render_js(
            t"removeRemoteCursor({client_id});removeRemoteSelection({client_id})"
        )
        remaining = list(_workspace_presence.get(workspace_key, {}).items())
        for _cid, presence in remaining:
            if (
                presence.nicegui_client is not None
                and not presence.nicegui_client._deleted
            ):
                with contextlib.suppress(Exception):
                    await presence.nicegui_client.run_javascript(
                        removal_js,
                        timeout=2.0,
                    )
            if presence.on_peer_left:
                with contextlib.suppress(Exception):
                    await presence.invoke_peer_left()

    pm = get_persistence_manager()
    await pm.force_persist_workspace(workspace_id)

    if last_client:
        doc_id = f"ws-{workspace_id}"
        pm.evict_workspace(workspace_id, doc_id)
        _workspace_registry.remove(doc_id)

    logger.debug(
        "DELETE[%s] total: %.3fs last=%s",
        client_id,
        _time.monotonic() - t0,
        last_client,
    )


async def _handle_remote_update(state: PageState) -> None:
    """Process a CRDT update received from another client.

    Rebuilds tag state, CSS, toolbar, annotations, and any
    tab-specific views that are currently active.
    """
    _rebuild_tag_state_from_crdt(state)
    _update_highlight_css(state)
    if state.refresh_toolbar:
        await state.refresh_toolbar()
    _update_user_count(state)
    if state.refresh_annotations:
        state.refresh_annotations(trigger="crdt_broadcast")
    if state.active_tab == "Organise":
        if state.refresh_organise_with_scroll:
            await state.refresh_organise_with_scroll()
        elif state.refresh_organise:
            state.refresh_organise()
    if state.active_tab == "Respond" and state.refresh_respond_references:
        state.refresh_respond_references()


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
        for cid, cstate in list(_workspace_presence.get(workspace_key, {}).items()):
            if cid != client_id and cstate.callback:
                with contextlib.suppress(Exception):
                    await cstate.invoke_callback()

    state.broadcast_update = broadcast_update

    async def broadcast_cursor(char_index: int | None) -> None:
        await _broadcast_cursor_update(
            workspace_key,
            client_id,
            state,
            char_index,
        )

    state.broadcast_cursor = broadcast_cursor

    async def broadcast_selection(start: int | None, end: int | None) -> None:
        await _broadcast_selection_update(
            workspace_key,
            client_id,
            state,
            start,
            end,
        )

    state.broadcast_selection = broadcast_selection

    async def handle_update_from_other() -> None:
        await _handle_remote_update(state)

    # Register this client
    if workspace_key not in _workspace_presence:
        _workspace_presence[workspace_key] = {}

    # Resolve user_id for revocation lookup
    auth_user = app.storage.user.get("auth_user")
    client_user_id = str(auth_user.get("user_id", "")) if auth_user else None

    # Bind workspace context for structured logging
    bind_contextvars(workspace_id=str(workspace_id))

    async def handle_peer_left() -> None:
        _update_user_count(state)

    _workspace_presence[workspace_key][client_id] = _RemotePresence(
        name=state.user_name,
        color=state.user_color,
        nicegui_client=client,
        callback=handle_update_from_other,
        on_peer_left=handle_peer_left,
        user_id=client_user_id,
        viewer_is_privileged=state.viewer_is_privileged,
        is_owner=state.is_owner,
    )
    logger.debug(
        "CLIENT_REGISTERED: ws=%s client=%s total=%d",
        workspace_key,
        client_id[:8],
        len(_workspace_presence[workspace_key]),
    )

    # Update own user count and notify others
    _update_user_count(state)
    _notify_other_clients(workspace_key, client_id)

    _replay_existing_cursors(workspace_key, client_id, state)

    async def on_client_delete() -> None:
        await _handle_client_delete(
            workspace_key,
            client_id,
            workspace_id,
        )

    client.on_delete(on_client_delete)


def _broadcast_yjs_update(
    workspace_id: UUID, origin_client_id: str, b64_update: str
) -> None:
    """Relay a Yjs update from one client's Milkdown editor to all others.

    Sends ``window._applyRemoteUpdate(b64)`` to every connected client
    that has initialised the Milkdown editor, except the originating client.
    """
    ws_key = str(workspace_id)
    for cid, cstate in list(_workspace_presence.get(ws_key, {}).items()):
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
    for client_id, presence in list(_workspace_presence[workspace_key].items()):
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
