"""Client registry for tracking connected NiceGUI clients per user.

Maps user_id -> set of NiceGUI Client objects, enabling real-time
disconnection when a user is banned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID

    from nicegui import Client

logger = structlog.get_logger()

# Module-level registry: user_id -> set of connected clients
_registry: dict[UUID, set[Client]] = {}


def register(user_id: UUID, client: Client) -> None:
    """Register a client connection for a user.

    Also sets up on_delete callback for automatic deregistration.
    """
    if user_id not in _registry:
        _registry[user_id] = set()
    _registry[user_id].add(client)

    # Auto-deregister on permanent disconnect
    client.on_delete(lambda: deregister(user_id, client))


def deregister(user_id: UUID, client: Client) -> None:
    """Remove a client from the user's set.

    Tolerates the client not being in the registry (stale state).
    Removes the user entry entirely if no clients remain.
    """
    clients = _registry.get(user_id)
    if clients is None:
        return
    clients.discard(client)
    if not clients:
        del _registry[user_id]


def disconnect_user(user_id: UUID) -> int:
    """Redirect all of a user's connected clients to /banned (fire-and-forget).

    Returns count of clients that were successfully sent a redirect.
    Tolerates stale/disconnected clients -- logs warning and continues.
    """
    clients = _registry.pop(user_id, set())
    redirected = 0
    for client in clients:
        try:
            client.run_javascript(
                'window.location.href = "/banned"',
                timeout=2.0,
            )
            redirected += 1
        except Exception:
            logger.warning(
                "ban_redirect_failed",
                client_id=client.id,
                exc_info=True,
            )
    return redirected
