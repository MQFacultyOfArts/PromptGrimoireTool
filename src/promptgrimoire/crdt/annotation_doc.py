"""Annotation document management for CRDT-based collaborative highlighting.

This module provides the server-side document state management for
collaborative text annotation, handling highlights, cursors, selections,
and comment threads across multiple connected clients.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pycrdt import Awareness, Doc, Map, TransactionEvent

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Async-safe storage for the origin client ID during updates.
_origin_var: ContextVar[str | None] = ContextVar("annotation_origin", default=None)

# Pre-defined colors for client cursors/selections (colorblind-friendly)
CLIENT_COLORS = [
    "#2196F3",  # Blue
    "#4CAF50",  # Green
    "#FF9800",  # Orange
    "#9C27B0",  # Purple
    "#00BCD4",  # Cyan
    "#E91E63",  # Pink
    "#795548",  # Brown
    "#607D8B",  # Blue Grey
]


class AnnotationDocument:
    """Manages a shared annotation document with CRDT-based collaboration.

    This class holds the server-side CRDT document state for collaborative
    annotation, including highlights, cursors, selections, and comments.

    Attributes:
        doc_id: Unique identifier for this document.
        doc: The pycrdt Doc instance.
        awareness: Awareness instance for cursor/selection presence.
    """

    def __init__(self, doc_id: str) -> None:
        """Initialize a new annotation document.

        Args:
            doc_id: Unique identifier for this document (e.g., case_id).
        """
        self.doc_id = doc_id
        self.doc = Doc()

        # Root-level Maps
        self.doc["highlights"] = Map()  # {highlight_id: HighlightData}
        self.doc["client_meta"] = Map()  # {client_id: {name, color}}

        # Awareness for ephemeral state (cursors, selections)
        self.awareness = Awareness(self.doc)

        # Client tracking
        self._clients: dict[str, Any] = {}
        self._next_color_index = 0
        self._broadcast_callback: Callable[[bytes, str | None], None] | None = None

        # Persistence tracking
        self._persistence_enabled = False
        self._last_editor: str | None = None

        # Set up observer to broadcast changes
        self.doc.observe(self._on_update)

    @property
    def highlights(self) -> Map:
        """Get the highlights Map."""
        return self.doc["highlights"]

    @property
    def client_meta(self) -> Map:
        """Get the client metadata Map."""
        return self.doc["client_meta"]

    def _get_next_color(self) -> str:
        """Get the next available client color."""
        color = CLIENT_COLORS[self._next_color_index % len(CLIENT_COLORS)]
        self._next_color_index += 1
        return color

    def register_client(
        self, client_id: str, name: str, client_data: Any = None
    ) -> str:
        """Register a new connected client.

        Args:
            client_id: Unique identifier for the client.
            name: Display name for the client.
            client_data: Optional data associated with the client.

        Returns:
            The assigned color for this client.
        """
        self._clients[client_id] = client_data
        color = self._get_next_color()

        # Store client metadata in CRDT for sharing
        token = _origin_var.set(client_id)
        try:
            self.client_meta[client_id] = {"name": name, "color": color}
        finally:
            _origin_var.reset(token)

        # Set awareness state
        self.awareness.set_local_state(
            {"client_id": client_id, "name": name, "color": color}
        )

        return color

    def unregister_client(self, client_id: str) -> None:
        """Unregister a disconnected client.

        Args:
            client_id: ID of the client to remove.
        """
        self._clients.pop(client_id, None)

        # Remove from client_meta
        token = _origin_var.set(client_id)
        try:
            self.client_meta.pop(client_id, None)
        finally:
            _origin_var.reset(token)

    def get_client_ids(self) -> list[str]:
        """Get list of connected client IDs."""
        return list(self._clients.keys())

    def set_broadcast_callback(
        self, callback: Callable[[bytes, str | None], None] | None
    ) -> None:
        """Set the callback for broadcasting updates to clients.

        Args:
            callback: Function that takes (update_bytes, origin_client_id)
                     and broadcasts to all clients except the origin.
        """
        self._broadcast_callback = callback

    def enable_persistence(self) -> None:
        """Enable database persistence for this document.

        When enabled, changes will be debounced and saved to the database.
        """
        self._persistence_enabled = True

    def _on_update(self, event: TransactionEvent) -> None:
        """Handle document updates and broadcast to clients."""
        if self._broadcast_callback is not None:
            origin = _origin_var.get()
            self._broadcast_callback(event.update, origin)

        # Trigger persistence if enabled
        if self._persistence_enabled:
            from promptgrimoire.crdt.persistence import get_persistence_manager

            get_persistence_manager().mark_dirty(self.doc_id, self._last_editor)

    # --- Highlight operations ---

    def add_highlight(
        self,
        start_word: int,
        end_word: int,
        tag: str,
        text: str,
        author: str,
        origin_client_id: str | None = None,
    ) -> str:
        """Add a new highlight to the document.

        Args:
            start_word: Starting word index (inclusive).
            end_word: Ending word index (exclusive).
            tag: Tag type (e.g., 'jurisdiction', 'legal_issues').
            text: The highlighted text content.
            author: Display name of the author.
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            The generated highlight ID.
        """
        highlight_id = str(uuid4())
        self._last_editor = author
        token = _origin_var.set(origin_client_id)
        try:
            # Create highlight with embedded comments Array
            highlight_data = {
                "id": highlight_id,
                "start_word": start_word,
                "end_word": end_word,
                "tag": tag,
                "text": text,
                "author": author,
                "created_at": datetime.now(UTC).isoformat(),
                "comments": [],  # Will be converted to Array by pycrdt
            }
            self.highlights[highlight_id] = highlight_data
        finally:
            _origin_var.reset(token)
        return highlight_id

    def remove_highlight(
        self, highlight_id: str, origin_client_id: str | None = None
    ) -> bool:
        """Remove a highlight from the document.

        Args:
            highlight_id: ID of the highlight to remove.
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            True if highlight was found and removed.
        """
        token = _origin_var.set(origin_client_id)
        try:
            if highlight_id in self.highlights:
                self.highlights.pop(highlight_id)
                return True
            return False
        finally:
            _origin_var.reset(token)

    def get_highlight(self, highlight_id: str) -> dict[str, Any] | None:
        """Get a highlight by ID.

        Args:
            highlight_id: ID of the highlight.

        Returns:
            Highlight data dict or None if not found.
        """
        return self.highlights.get(highlight_id)

    def get_all_highlights(self) -> list[dict[str, Any]]:
        """Get all highlights in the document.

        Returns:
            List of highlight data dicts, sorted by start_word.
        """
        highlights = list(self.highlights.values())
        return sorted(highlights, key=lambda h: h.get("start_word", 0))

    # --- Comment operations ---

    def add_comment(
        self,
        highlight_id: str,
        author: str,
        text: str,
        origin_client_id: str | None = None,
    ) -> str | None:
        """Add a comment to a highlight's thread.

        Args:
            highlight_id: ID of the highlight to comment on.
            author: Display name of the comment author.
            text: Comment text content.
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            The generated comment ID, or None if highlight not found.
        """
        highlight = self.highlights.get(highlight_id)
        if highlight is None:
            return None

        comment_id = str(uuid4())
        self._last_editor = author
        token = _origin_var.set(origin_client_id)
        try:
            comment = {
                "id": comment_id,
                "author": author,
                "text": text,
                "created_at": datetime.now(UTC).isoformat(),
            }

            # Get current comments and append
            comments = list(highlight.get("comments", []))
            comments.append(comment)

            # Update the highlight with new comments
            highlight["comments"] = comments
            self.highlights[highlight_id] = highlight
        finally:
            _origin_var.reset(token)
        return comment_id

    def delete_comment(
        self,
        highlight_id: str,
        comment_id: str,
        origin_client_id: str | None = None,
    ) -> bool:
        """Delete a comment from a highlight's thread.

        Args:
            highlight_id: ID of the highlight.
            comment_id: ID of the comment to delete.
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            True if comment was found and deleted.
        """
        highlight = self.highlights.get(highlight_id)
        if highlight is None:
            return False

        token = _origin_var.set(origin_client_id)
        try:
            comments = list(highlight.get("comments", []))
            original_len = len(comments)
            comments = [c for c in comments if c.get("id") != comment_id]

            if len(comments) < original_len:
                highlight["comments"] = comments
                self.highlights[highlight_id] = highlight
                return True
            return False
        finally:
            _origin_var.reset(token)

    # --- Cursor/Selection operations (via Awareness) ---

    def update_cursor(
        self, client_id: str, word_index: int | None, name: str, color: str
    ) -> None:
        """Update a client's cursor position.

        Args:
            client_id: ID of the client.
            word_index: Word index of cursor, or None to clear.
            name: Client display name.
            color: Client color.
        """
        state = {
            "client_id": client_id,
            "name": name,
            "color": color,
            "cursor": word_index,
            "selection": None,
        }
        self.awareness.set_local_state(state)

    def update_selection(
        self,
        client_id: str,
        start_word: int | None,
        end_word: int | None,
        name: str,
        color: str,
    ) -> None:
        """Update a client's selection range.

        Args:
            client_id: ID of the client.
            start_word: Starting word index, or None to clear.
            end_word: Ending word index, or None to clear.
            name: Client display name.
            color: Client color.
        """
        selection = None
        if start_word is not None and end_word is not None:
            selection = {"start_word": start_word, "end_word": end_word}

        state = {
            "client_id": client_id,
            "name": name,
            "color": color,
            "cursor": None,
            "selection": selection,
        }
        self.awareness.set_local_state(state)

    def clear_cursor_and_selection(self, client_id: str, name: str, color: str) -> None:
        """Clear a client's cursor and selection.

        Args:
            client_id: ID of the client.
            name: Client display name.
            color: Client color.
        """
        state = {
            "client_id": client_id,
            "name": name,
            "color": color,
            "cursor": None,
            "selection": None,
        }
        self.awareness.set_local_state(state)

    # --- Serialization ---

    def get_full_state(self) -> bytes:
        """Get the full document state for syncing to new clients."""
        return self.doc.get_update()

    def apply_update(self, update: bytes, origin_client_id: str | None = None) -> None:
        """Apply an update from a client.

        Args:
            update: Binary update from a client.
            origin_client_id: ID of the client that sent the update.
        """
        token = _origin_var.set(origin_client_id)
        try:
            self.doc.apply_update(update)
        finally:
            _origin_var.reset(token)


# Registry for managing multiple annotation documents
class AnnotationDocumentRegistry:
    """Registry for managing multiple annotation documents by ID."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._documents: dict[str, AnnotationDocument] = {}

    def get_or_create(self, doc_id: str) -> AnnotationDocument:
        """Get an existing document or create a new one (in-memory only).

        Args:
            doc_id: Document identifier.

        Returns:
            The AnnotationDocument instance.
        """
        if doc_id not in self._documents:
            self._documents[doc_id] = AnnotationDocument(doc_id)
        return self._documents[doc_id]

    async def get_or_create_with_persistence(self, doc_id: str) -> AnnotationDocument:
        """Get existing document, load from DB, or create new.

        This is the preferred method when database is available.
        Falls back to empty document if no persisted state exists.

        Args:
            doc_id: Document identifier.

        Returns:
            The AnnotationDocument instance, restored from DB if available.
        """
        if doc_id in self._documents:
            return self._documents[doc_id]

        # Try to load from database
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.annotation_state import get_state_by_case_id

        doc = AnnotationDocument(doc_id)

        try:
            state = await get_state_by_case_id(doc_id)
            if state and state.crdt_state:
                doc.apply_update(state.crdt_state)
                logger.info("Loaded document %s from database", doc_id)
        except Exception:
            logger.exception("Failed to load document %s from database", doc_id)

        self._documents[doc_id] = doc

        # Register with persistence manager
        get_persistence_manager().register_document(doc)

        return doc

    def get(self, doc_id: str) -> AnnotationDocument | None:
        """Get a document by ID if it exists.

        Args:
            doc_id: Document identifier.

        Returns:
            The AnnotationDocument or None.
        """
        return self._documents.get(doc_id)

    def remove(self, doc_id: str) -> bool:
        """Remove a document from the registry.

        Args:
            doc_id: Document identifier.

        Returns:
            True if document was found and removed.
        """
        if doc_id in self._documents:
            del self._documents[doc_id]
            return True
        return False

    def list_ids(self) -> list[str]:
        """List all document IDs in the registry."""
        return list(self._documents.keys())
