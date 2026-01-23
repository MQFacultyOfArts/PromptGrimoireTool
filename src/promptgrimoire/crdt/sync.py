"""Shared document management for CRDT synchronization.

This module provides the server-side document state management,
handling multiple connected clients and broadcasting updates.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from pycrdt import Doc, Text, TransactionEvent

if TYPE_CHECKING:
    from collections.abc import Callable

# Async-safe storage for the origin client ID during updates.
# Using ContextVar ensures concurrent async operations don't interfere.
_origin_var: ContextVar[str | None] = ContextVar("origin", default=None)


class SharedDocument:
    """Manages a shared pycrdt document with connected clients.

    This class holds the server-side CRDT document state and provides
    methods for syncing with multiple connected clients.
    """

    def __init__(self) -> None:
        """Initialize a new shared document with an empty Text field."""
        self.doc = Doc()
        self.doc["text"] = Text()
        # Client data is intentionally Any to allow flexibility in what callers store.
        # sync_demo.py stores (Label, Input) tuples; other uses may differ.
        # TODO: Consider Generic[T] pattern if type safety becomes important.
        self._clients: dict[str, Any] = {}
        self._broadcast_callback: Callable[[bytes, str | None], None] | None = None

        # Set up observer to broadcast changes
        self.doc.observe(self._on_update)

    @property
    def text(self) -> Text:
        """Get the shared text object."""
        return self.doc["text"]

    def get_full_state(self) -> bytes:
        """Get the full document state for syncing to new clients."""
        return self.doc.get_update()

    def apply_update(self, update: bytes, origin_client_id: str | None = None) -> None:
        """Apply an update from a client.

        Args:
            update: Binary update from a client
            origin_client_id: ID of the client that sent the update
                (for echo prevention)
        """
        token = _origin_var.set(origin_client_id)
        try:
            self.doc.apply_update(update)
        finally:
            _origin_var.reset(token)

    def set_text(self, content: str, origin_client_id: str | None = None) -> None:
        """Set the text content, replacing any existing content.

        Args:
            content: New text content
            origin_client_id: ID of the client making the change
        """
        token = _origin_var.set(origin_client_id)
        try:
            text = self.text
            text.clear()
            if content:
                text += content
        finally:
            _origin_var.reset(token)

    def insert_at(
        self, position: int, content: str, origin_client_id: str | None = None
    ) -> None:
        """Insert text at a specific position.

        Args:
            position: Character index to insert at
            content: Text to insert
            origin_client_id: ID of the client making the change
        """
        token = _origin_var.set(origin_client_id)
        try:
            self.text.insert(position, content)
        finally:
            _origin_var.reset(token)

    def delete_range(
        self, start: int, end: int, origin_client_id: str | None = None
    ) -> None:
        """Delete text in a range.

        Args:
            start: Start index (inclusive)
            end: End index (exclusive)
            origin_client_id: ID of the client making the change
        """
        token = _origin_var.set(origin_client_id)
        try:
            del self.text[start:end]
        finally:
            _origin_var.reset(token)

    def register_client(self, client_id: str, client_data: Any = None) -> None:
        """Register a new connected client.

        Args:
            client_id: Unique identifier for the client
            client_data: Optional data associated with the client
        """
        self._clients[client_id] = client_data

    def unregister_client(self, client_id: str) -> None:
        """Unregister a disconnected client.

        Args:
            client_id: ID of the client to remove
        """
        self._clients.pop(client_id, None)

    def get_client_ids(self) -> list[str]:
        """Get list of connected client IDs."""
        return list(self._clients.keys())

    def set_broadcast_callback(
        self, callback: Callable[[bytes, str | None], None] | None
    ) -> None:
        """Set the callback for broadcasting updates to clients.

        Args:
            callback: Function that takes (update_bytes, origin_client_id)
                     and broadcasts to all clients except the origin
        """
        self._broadcast_callback = callback

    def _on_update(self, event: TransactionEvent) -> None:
        """Handle document updates and broadcast to clients."""
        if self._broadcast_callback is not None:
            origin = _origin_var.get()
            self._broadcast_callback(event.update, origin)

    def get_content(self) -> str:
        """Get the current text content as a string."""
        return str(self.text)
