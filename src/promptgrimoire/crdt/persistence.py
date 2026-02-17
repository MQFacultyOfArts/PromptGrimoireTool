"""CRDT persistence manager for debounced database writes.

Coordinates saving CRDT document state to PostgreSQL with debouncing
to avoid overwhelming the database during rapid edits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Manages debounced persistence of CRDT documents to database.

    Attributes:
        debounce_seconds: Delay before persisting (class attr, override in tests).
        _doc_registry: Dict of doc_id -> AnnotationDocument for accessing documents.
    """

    # Debounce interval - override in tests for faster execution
    debounce_seconds: float = 5.0

    def __init__(self) -> None:
        """Initialize the persistence manager."""
        self._doc_registry: dict[str, AnnotationDocument] = {}

        # Workspace-based persistence
        self._workspace_dirty: dict[UUID, str] = {}  # workspace_id -> doc_id
        self._workspace_pending_saves: dict[UUID, asyncio.Task[None]] = {}
        self._workspace_last_editors: dict[UUID, str | None] = {}

    def register_document(self, doc: AnnotationDocument) -> None:
        """Register a document for persistence tracking.

        Args:
            doc: The AnnotationDocument to track.
        """
        self._doc_registry[doc.doc_id] = doc

    def unregister_document(self, doc_id: str) -> None:
        """Unregister a document.

        Args:
            doc_id: ID of the document to unregister.
        """
        self._doc_registry.pop(doc_id, None)

    # --- Workspace-aware persistence methods ---

    def mark_dirty_workspace(
        self,
        workspace_id: UUID,
        doc_id: str,
        last_editor: str | None = None,
    ) -> None:
        """Mark a workspace's CRDT state as needing persistence.

        Args:
            workspace_id: The workspace UUID.
            doc_id: The document ID in the registry.
            last_editor: Display name of last editor.
        """
        from uuid import UUID as UUIDType

        # Handle string UUIDs gracefully
        if isinstance(workspace_id, str):
            workspace_id = UUIDType(workspace_id)

        self._workspace_dirty[workspace_id] = doc_id
        self._workspace_last_editors[workspace_id] = last_editor
        self._schedule_debounced_workspace_save(workspace_id)

    def _schedule_debounced_workspace_save(self, workspace_id: UUID) -> None:
        """Schedule a debounced save for a workspace."""
        from uuid import UUID as UUIDType

        # Handle string UUIDs gracefully
        if isinstance(workspace_id, str):
            workspace_id = UUIDType(workspace_id)

        # Cancel any existing pending save
        if workspace_id in self._workspace_pending_saves:
            self._workspace_pending_saves[workspace_id].cancel()

        # Schedule new save
        task = asyncio.create_task(self._debounced_workspace_save(workspace_id))
        self._workspace_pending_saves[workspace_id] = task

    async def _debounced_workspace_save(self, workspace_id: UUID) -> None:
        """Wait for debounce period then persist workspace."""
        try:
            await asyncio.sleep(self.debounce_seconds)
            await self._persist_workspace(workspace_id)
        except asyncio.CancelledError:
            pass  # Save was superseded by a newer one

    async def _persist_workspace(self, workspace_id: UUID) -> None:
        """Persist CRDT state to Workspace table."""
        from uuid import UUID as UUIDType

        # Handle string UUIDs gracefully
        if isinstance(workspace_id, str):
            workspace_id = UUIDType(workspace_id)

        doc_id = self._workspace_dirty.get(workspace_id)
        if doc_id is None:
            return

        doc = self._doc_registry.get(doc_id)
        if doc is None:
            logger.warning(
                "Document %s not found for workspace %s", doc_id, workspace_id
            )
            return

        try:
            from promptgrimoire.db.workspaces import save_workspace_crdt_state

            crdt_state = doc.get_full_state()
            success = await save_workspace_crdt_state(workspace_id, crdt_state)

            if success:
                self._workspace_dirty.pop(workspace_id, None)
                logger.info("Persisted workspace %s", workspace_id)
            else:
                logger.warning("Workspace %s not found for persistence", workspace_id)

        except Exception:
            logger.exception("Failed to persist workspace %s", workspace_id)

    async def force_persist_workspace(self, workspace_id: UUID) -> None:
        """Immediately persist a workspace's CRDT state.

        Args:
            workspace_id: The workspace UUID.
        """
        from uuid import UUID as UUIDType

        # Handle string UUIDs gracefully
        if isinstance(workspace_id, str):
            workspace_id = UUIDType(workspace_id)

        # Cancel any pending debounced save
        if workspace_id in self._workspace_pending_saves:
            self._workspace_pending_saves[workspace_id].cancel()
            del self._workspace_pending_saves[workspace_id]

        await self._persist_workspace(workspace_id)

    async def persist_all_dirty_workspaces(self) -> None:
        """Persist all dirty workspaces immediately."""
        workspace_ids = list(self._workspace_dirty.keys())
        for workspace_id in workspace_ids:
            await self.force_persist_workspace(workspace_id)

    def evict_workspace(self, workspace_id: UUID, doc_id: str) -> None:
        """Remove all state for a workspace after its last client disconnects.

        Cleans up:
        - Document from ``_doc_registry``
        - Dirty marker from ``_workspace_dirty``
        - Pending save task from ``_workspace_pending_saves`` (cancelled)
        - Last editor from ``_workspace_last_editors``

        Call this AFTER ``force_persist_workspace`` has saved any pending state.

        Args:
            workspace_id: The workspace UUID.
            doc_id: The document ID in the registry.
        """
        from uuid import UUID as UUIDType

        if isinstance(workspace_id, str):
            workspace_id = UUIDType(workspace_id)

        self.unregister_document(doc_id)
        self._workspace_dirty.pop(workspace_id, None)
        self._workspace_last_editors.pop(workspace_id, None)
        # Cancel and remove any pending save task (should already be done
        # by force_persist_workspace, but be defensive)
        task = self._workspace_pending_saves.pop(workspace_id, None)
        if task is not None and not task.done():
            task.cancel()
        logger.info(
            "Evicted workspace %s (doc %s) from persistence", workspace_id, doc_id
        )


# Global singleton instance
_persistence_manager: PersistenceManager | None = None


def get_persistence_manager() -> PersistenceManager:
    """Get the global persistence manager instance."""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = PersistenceManager()
    return _persistence_manager
