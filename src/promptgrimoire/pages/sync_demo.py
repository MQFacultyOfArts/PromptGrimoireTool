"""CRDT sync demo page.

Demonstrates real-time text synchronization between multiple browser
tabs using pycrdt CRDTs over NiceGUI WebSockets.

Route: /demo/crdt-sync
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.crdt import SharedDocument
from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui.elements.input import Input
    from nicegui.elements.label import Label

# Server-side shared document (single instance for all clients).
# NOTE: This singleton pattern is intentional for demo purposes.
# Production requires document-per-conversation isolation.
# See: docs/pycrdt/nicegui-integration.md and future spike for DocumentRegistry.
shared_doc = SharedDocument()

# Track connected clients: client_id -> (label_element, input_element)
_connected_clients: dict[str, tuple[Label, Input]] = {}


def _broadcast_to_other_clients(origin_client_id: str | None) -> None:
    """Update UI elements for all clients except the origin."""
    content = shared_doc.get_content()
    for client_id, (label, input_elem) in _connected_clients.items():
        if client_id != origin_client_id:
            # Update the label and input for this client
            try:
                label.text = content
                input_elem.value = content
                # Force update to push changes over WebSocket
                label.update()
                input_elem.update()
            except Exception:
                # Client may have disconnected
                pass


@page_route(
    "/demo/crdt-sync",
    title="CRDT Sync",
    icon="sync",
    category="demo",
    requires_demo=True,
    order=20,
)
async def crdt_sync_demo_page() -> None:
    """Demo page: Real-time CRDT text synchronization."""
    if not require_demo_enabled():
        return
    # Wait for WebSocket connection
    await ui.context.client.connected()

    # Get client reference
    client = ui.context.client
    client_id = str(id(client))

    # Register client in shared document
    shared_doc.register_client(client_id)

    # Create UI elements
    ui.label("CRDT Real-Time Sync Demo").classes("text-h5")

    # Display area for synced text
    synced_label = ui.label(shared_doc.get_content()).props('data-testid="synced-text"')

    # Input field for editing
    def on_input_change(e) -> None:
        """Handle input changes and sync to document."""
        new_value = e.value if e.value is not None else ""
        # Update the shared document
        shared_doc.set_text(new_value, origin_client_id=client_id)
        # Update our own display
        synced_label.text = shared_doc.get_content()
        # Broadcast to other clients
        _broadcast_to_other_clients(client_id)

    input_field = ui.input(
        label="Edit text",
        value=shared_doc.get_content(),
        on_change=on_input_change,
    ).classes("w-full")

    # Store references to UI elements for this client
    _connected_clients[client_id] = (synced_label, input_field)

    # Cleanup on disconnect
    def on_disconnect() -> None:
        shared_doc.unregister_client(client_id)
        _connected_clients.pop(client_id, None)

    client.on_disconnect(on_disconnect)

    # Show connection info
    ui.label(f"Client ID: {client_id[:8]}...").classes("text-caption text-grey")
