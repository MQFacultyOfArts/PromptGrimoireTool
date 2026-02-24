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

from pycrdt import Array, Awareness, Doc, Map, Text, TransactionEvent, XmlFragment

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

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
        self.doc["general_notes"] = Text()  # Collaborative text for general notes
        self.doc["tag_order"] = Map()  # {tag_name: Array([highlight_id, ...])}
        self.doc["response_draft"] = XmlFragment()  # Milkdown/ProseMirror document
        self.doc["response_draft_markdown"] = Text()  # Plain markdown mirror

        # Awareness for ephemeral state (cursors, selections)
        self.awareness = Awareness(self.doc)

        # Client tracking
        self._clients: dict[str, Any] = {}
        self._next_color_index = 0
        self._broadcast_callback: Callable[[bytes, str | None], None] | None = None

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

    @property
    def general_notes(self) -> Text:
        """Get the general notes Text object."""
        return self.doc["general_notes"]

    @property
    def tag_order(self) -> Map:
        """Get the tag_order Map."""
        return self.doc["tag_order"]

    @property
    def response_draft(self) -> XmlFragment:
        """Get the response_draft XmlFragment."""
        return self.doc["response_draft"]

    @property
    def response_draft_markdown(self) -> Text:
        """Get the response_draft_markdown Text."""
        return self.doc["response_draft_markdown"]

    def get_general_notes(self) -> str:
        """Get the current general notes content.

        Returns:
            The general notes as a string.
        """
        return str(self.general_notes)

    def get_response_draft_markdown(self) -> str:
        """Get the current response draft markdown content."""
        return str(self.response_draft_markdown)

    def set_general_notes(
        self, content: str, origin_client_id: str | None = None
    ) -> None:
        """Set the general notes content, replacing existing content.

        Args:
            content: The new notes content.
            origin_client_id: Client making the change (for echo prevention).
        """
        token = _origin_var.set(origin_client_id)
        try:
            # Clear existing content and set new
            notes = self.general_notes
            current_len = len(notes)
            if current_len > 0:
                del notes[:current_len]
            notes += content
        finally:
            _origin_var.reset(token)

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

    def _on_update(self, event: TransactionEvent) -> None:
        """Handle document updates and broadcast to clients."""
        if self._broadcast_callback is not None:
            origin = _origin_var.get()
            self._broadcast_callback(event.update, origin)

    # --- Highlight operations ---

    def add_highlight(
        self,
        start_char: int,
        end_char: int,
        tag: str,
        text: str,
        author: str,
        para_ref: str = "",
        origin_client_id: str | None = None,
        document_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Add a new highlight to the document.

        Args:
            start_char: Starting character index (inclusive).
            end_char: Ending character index (exclusive).
            tag: Tag type (e.g., 'jurisdiction', 'legal_issues').
            text: The highlighted text content.
            author: Display name of the author.
            para_ref: Paragraph reference string (e.g., "[3]", "[3]-[4]").
            origin_client_id: Client making the change (for echo prevention).
            document_id: Optional workspace document UUID for multi-document workspaces.
            user_id: Stytch user ID of the author (None for legacy/anonymous).

        Returns:
            The generated highlight ID.
        """
        highlight_id = str(uuid4())
        token = _origin_var.set(origin_client_id)
        try:
            # Create highlight with embedded comments Array
            highlight_data = {
                "id": highlight_id,
                "document_id": document_id,  # Can be None for backward compat
                "start_char": start_char,
                "end_char": end_char,
                "tag": tag,
                "text": text,
                "author": author,
                "user_id": user_id,
                "para_ref": para_ref,
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

    def update_highlight_tag(
        self, highlight_id: str, new_tag: str, origin_client_id: str | None = None
    ) -> bool:
        """Update a highlight's tag.

        Args:
            highlight_id: ID of the highlight to update.
            new_tag: New tag value.
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            True if highlight was found and updated.
        """
        token = _origin_var.set(origin_client_id)
        try:
            if highlight_id in self.highlights:
                hl_data = dict(self.highlights[highlight_id])
                hl_data["tag"] = new_tag
                self.highlights[highlight_id] = hl_data
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
            List of highlight data dicts, sorted by start_char.
        """
        highlights = list(self.highlights.values())
        return sorted(highlights, key=lambda h: h.get("start_char", 0))

    def get_highlights_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """Get all highlights for a specific document.

        Args:
            document_id: The document UUID to filter by.

        Returns:
            List of highlight data dicts for that document, sorted by start_char.
        """
        highlights = [
            h for h in self.highlights.values() if h.get("document_id") == document_id
        ]
        return sorted(highlights, key=lambda h: h.get("start_char", 0))

    # --- Tag order operations ---

    def get_tag_order(self, tag: str) -> list[str]:
        """Return the ordered list of highlight IDs for a given tag.

        Args:
            tag: The tag name to look up.

        Returns:
            Ordered list of highlight IDs, or empty list if tag has no ordering.
        """
        arr = self.tag_order.get(tag)
        if arr is None:
            return []
        return list(arr)

    def set_tag_order(
        self,
        tag: str,
        highlight_ids: list[str],
        origin_client_id: str | None = None,
    ) -> None:
        """Replace the ordered list of highlight IDs for a tag.

        Args:
            tag: The tag name.
            highlight_ids: Ordered list of highlight IDs.
            origin_client_id: Client making the change (for echo prevention).
        """
        token = _origin_var.set(origin_client_id)
        try:
            self.tag_order[tag] = Array(highlight_ids)
        finally:
            _origin_var.reset(token)

    def move_highlight_to_tag(
        self,
        highlight_id: str,
        from_tag: str | None,
        to_tag: str,
        position: int = -1,
        origin_client_id: str | None = None,
    ) -> bool:
        """Move a highlight from one tag's order to another.

        Removes ``highlight_id`` from ``from_tag``'s order (if present and
        ``from_tag`` is not None), then inserts it into ``to_tag``'s order at
        ``position`` (-1 means append). Also updates the highlight's tag field.

        Args:
            highlight_id: ID of the highlight to move.
            from_tag: Tag to remove from (None to skip removal).
            to_tag: Tag to add to.
            position: Insertion index in target order (-1 to append).
            origin_client_id: Client making the change (for echo prevention).

        Returns:
            True if the highlight exists and was moved.
        """
        if highlight_id not in self.highlights:
            return False

        token = _origin_var.set(origin_client_id)
        try:
            # Remove from source tag order
            if from_tag is not None:
                source_ids = self.get_tag_order(from_tag)
                if highlight_id in source_ids:
                    source_ids.remove(highlight_id)
                    self.tag_order[from_tag] = Array(source_ids)

            # Insert into target tag order
            target_ids = self.get_tag_order(to_tag)
            if position == -1:
                target_ids.append(highlight_id)
            else:
                target_ids.insert(position, highlight_id)
            self.tag_order[to_tag] = Array(target_ids)

            # Update the highlight's tag field
            hl_data = dict(self.highlights[highlight_id])
            hl_data["tag"] = to_tag
            self.highlights[highlight_id] = hl_data
        finally:
            _origin_var.reset(token)

        return True

    # --- Comment operations ---

    def add_comment(
        self,
        highlight_id: str,
        author: str,
        text: str,
        origin_client_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        """Add a comment to a highlight's thread.

        Args:
            highlight_id: ID of the highlight to comment on.
            author: Display name of the comment author.
            text: Comment text content.
            origin_client_id: Client making the change (for echo prevention).
            user_id: Stytch user ID of the comment author (None for legacy/anonymous).

        Returns:
            The generated comment ID, or None if highlight not found.
        """
        highlight = self.highlights.get(highlight_id)
        if highlight is None:
            return None

        comment_id = str(uuid4())
        token = _origin_var.set(origin_client_id)
        try:
            comment = {
                "id": comment_id,
                "author": author,
                "user_id": user_id,
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
        requesting_user_id: str | None = None,
        is_privileged: bool = False,
        origin_client_id: str | None = None,
    ) -> bool:
        """Delete a comment from a highlight's thread.

        Enforces ownership: only the comment creator or a privileged
        user (instructor/admin) may delete.  Workspace owners who are
        not privileged may only delete their own comments.

        Args:
            highlight_id: ID of the highlight.
            comment_id: ID of the comment to delete.
            requesting_user_id: Stytch user ID of the requester.
            is_privileged: Whether the requester is instructor/admin.
            origin_client_id: Client making the change (echo prevention).

        Returns:
            True if comment was authorised and deleted.
        """
        highlight = self.highlights.get(highlight_id)
        if highlight is None:
            return False

        # Find the target comment for authorisation check
        comments = list(highlight.get("comments", []))
        target = next((c for c in comments if c.get("id") == comment_id), None)
        if target is None:
            return False

        # Authorisation guard
        if not is_privileged:
            comment_owner = target.get("user_id")
            if (
                requesting_user_id is None
                or comment_owner is None
                or comment_owner != requesting_user_id
            ):
                return False

        token = _origin_var.set(origin_client_id)
        try:
            remaining = [c for c in comments if c.get("id") != comment_id]
            highlight["comments"] = remaining
            self.highlights[highlight_id] = highlight
            return True
        finally:
            _origin_var.reset(token)

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

    async def get_or_create_for_workspace(
        self, workspace_id: UUID
    ) -> AnnotationDocument:
        """Get existing document for workspace, load from DB, or create new.

        Loads CRDT state from Workspace.crdt_state.

        Args:
            workspace_id: The workspace UUID.

        Returns:
            The AnnotationDocument instance, restored from DB if available.
        """
        # Use workspace_id as doc_id key for caching
        doc_id = f"ws-{workspace_id}"

        if doc_id in self._documents:
            return self._documents[doc_id]

        # Try to load from Workspace
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.workspaces import get_workspace

        doc = AnnotationDocument(doc_id)

        try:
            workspace = await get_workspace(workspace_id)
            if workspace and workspace.crdt_state:
                doc.apply_update(workspace.crdt_state)
                logger.info("Loaded workspace %s from database", workspace_id)
        except Exception:
            logger.exception("Failed to load workspace %s from database", workspace_id)

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
        return self._documents.pop(doc_id, None) is not None

    def list_ids(self) -> list[str]:
        """List all document IDs in the registry."""
        return list(self._documents.keys())

    def clear_all(self) -> int:
        """Remove all documents from the registry.

        This is primarily for testing to reset state between test runs.

        Returns:
            Number of documents that were cleared.
        """
        count = len(self._documents)
        self._documents.clear()
        return count
