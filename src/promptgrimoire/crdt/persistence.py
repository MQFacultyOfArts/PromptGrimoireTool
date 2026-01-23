"""CRDT persistence manager for debounced database writes.

Coordinates saving CRDT document state to PostgreSQL with debouncing
to avoid overwhelming the database during rapid edits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument

logger = logging.getLogger(__name__)

# Debounce interval in seconds
DEBOUNCE_SECONDS = 5.0


class PersistenceManager:
    """Manages debounced persistence of CRDT documents to database.

    Attributes:
        _pending_saves: Dict of doc_id -> asyncio.Task for pending debounced saves.
        _dirty_docs: Set of doc_ids that have unsaved changes.
        _doc_registry: Dict of doc_id -> AnnotationDocument for accessing documents.
    """

    def __init__(self) -> None:
        """Initialize the persistence manager."""
        self._pending_saves: dict[str, asyncio.Task[None]] = {}
        self._dirty_docs: set[str] = set()
        self._doc_registry: dict[str, AnnotationDocument] = {}
        self._last_editors: dict[str, str | None] = {}

    def register_document(self, doc: AnnotationDocument) -> None:
        """Register a document for persistence tracking.

        Args:
            doc: The AnnotationDocument to track.
        """
        self._doc_registry[doc.doc_id] = doc

    def unregister_document(self, doc_id: str) -> None:
        """Unregister a document, canceling any pending save.

        Args:
            doc_id: ID of the document to unregister.
        """
        self._doc_registry.pop(doc_id, None)
        self._last_editors.pop(doc_id, None)
        self._cancel_pending_save(doc_id)

    def mark_dirty(self, doc_id: str, last_editor: str | None = None) -> None:
        """Mark a document as having unsaved changes, schedule debounced save.

        Args:
            doc_id: ID of the document that changed.
            last_editor: Display name of the user who made the change.
        """
        self._dirty_docs.add(doc_id)
        if last_editor:
            self._last_editors[doc_id] = last_editor
        self._schedule_debounced_save(doc_id)

    def _schedule_debounced_save(self, doc_id: str) -> None:
        """Schedule or reschedule a debounced save."""
        self._cancel_pending_save(doc_id)

        async def debounced_save() -> None:
            await asyncio.sleep(DEBOUNCE_SECONDS)
            await self._persist_document(doc_id)

        self._pending_saves[doc_id] = asyncio.create_task(debounced_save())

    def _cancel_pending_save(self, doc_id: str) -> None:
        """Cancel a pending debounced save if exists."""
        task = self._pending_saves.pop(doc_id, None)
        if task and not task.done():
            task.cancel()

    async def _persist_document(self, doc_id: str) -> None:
        """Actually persist the document to database."""
        from promptgrimoire.db.annotation_state import save_state

        doc = self._doc_registry.get(doc_id)
        if not doc:
            logger.warning(
                "Document %s not found in registry, skipping persist", doc_id
            )
            return

        try:
            crdt_state = doc.get_full_state()
            highlight_count = len(doc.get_all_highlights())
            last_editor = self._last_editors.get(doc_id)

            await save_state(
                case_id=doc_id,
                crdt_state=crdt_state,
                highlight_count=highlight_count,
                last_editor=last_editor,
            )

            self._dirty_docs.discard(doc_id)
            self._pending_saves.pop(doc_id, None)
            logger.info(
                "Persisted document %s (%d highlights)", doc_id, highlight_count
            )

        except Exception:
            logger.exception("Failed to persist document %s", doc_id)

    async def force_persist(self, doc_id: str) -> None:
        """Immediately persist a document (e.g., on last client disconnect).

        Args:
            doc_id: ID of the document to persist.
        """
        self._cancel_pending_save(doc_id)
        if doc_id in self._dirty_docs:
            await self._persist_document(doc_id)

    async def persist_all_dirty(self) -> None:
        """Persist all dirty documents (e.g., on shutdown)."""
        for doc_id in list(self._dirty_docs):
            await self.force_persist(doc_id)


# Global singleton instance
_persistence_manager: PersistenceManager | None = None


def get_persistence_manager() -> PersistenceManager:
    """Get the global persistence manager instance."""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = PersistenceManager()
    return _persistence_manager
