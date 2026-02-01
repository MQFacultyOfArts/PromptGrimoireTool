"""Unit tests for CRDT persistence manager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from promptgrimoire.crdt.persistence import PersistenceManager


class TestPersistenceManager:
    """Tests for PersistenceManager."""

    def test_register_document(self) -> None:
        """register_document should add document to registry."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"

        pm.register_document(mock_doc)

        assert "test-doc" in pm._doc_registry
        assert pm._doc_registry["test-doc"] is mock_doc

    def test_unregister_document(self) -> None:
        """unregister_document should remove document from registry."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)

        pm.unregister_document("test-doc")

        assert "test-doc" not in pm._doc_registry


class TestWorkspacePersistence:
    """Tests for workspace-aware persistence."""

    @pytest.mark.asyncio
    async def test_mark_dirty_workspace_schedules_save(self) -> None:
        """mark_dirty_workspace should schedule a debounced save."""
        pm = PersistenceManager()
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        pm.register_document(mock_doc)

        pm.mark_dirty_workspace(workspace_id, doc_id, last_editor="User1")

        assert workspace_id in pm._workspace_dirty
        assert workspace_id in pm._workspace_pending_saves
        assert not pm._workspace_pending_saves[workspace_id].done()

        # Clean up
        pm._workspace_pending_saves[workspace_id].cancel()

    @pytest.mark.asyncio
    async def test_mark_dirty_workspace_tracks_last_editor(self) -> None:
        """mark_dirty_workspace should track last editor name."""
        pm = PersistenceManager()
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        pm.register_document(mock_doc)

        pm.mark_dirty_workspace(workspace_id, doc_id, last_editor="TestUser")

        assert pm._workspace_last_editors.get(workspace_id) == "TestUser"

        # Clean up
        pm._workspace_pending_saves[workspace_id].cancel()

    @pytest.mark.asyncio
    async def test_force_persist_workspace_saves_immediately(self) -> None:
        """force_persist_workspace should save without waiting for debounce."""
        pm = PersistenceManager()
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        mock_doc.get_full_state.return_value = b"state"
        pm.register_document(mock_doc)
        pm._workspace_dirty[workspace_id] = doc_id

        with patch(
            "promptgrimoire.db.workspaces.save_workspace_crdt_state",
            new_callable=AsyncMock,
        ) as mock_save:
            mock_save.return_value = True
            await pm.force_persist_workspace(workspace_id)

            mock_save.assert_called_once_with(workspace_id, b"state")

        assert workspace_id not in pm._workspace_dirty

    @pytest.mark.asyncio
    async def test_force_persist_workspace_does_nothing_if_not_dirty(self) -> None:
        """force_persist_workspace should not save if workspace is not dirty."""
        pm = PersistenceManager()
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        pm.register_document(mock_doc)
        # Note: not adding to _workspace_dirty

        with patch(
            "promptgrimoire.db.workspaces.save_workspace_crdt_state",
            new_callable=AsyncMock,
        ) as mock_save:
            await pm.force_persist_workspace(workspace_id)

            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_all_dirty_workspaces(self) -> None:
        """persist_all_dirty_workspaces should save all dirty workspaces."""
        pm = PersistenceManager()

        # Create two mock workspaces
        workspace_ids = [uuid4(), uuid4()]
        for workspace_id in workspace_ids:
            doc_id = f"ws-{workspace_id}"
            mock_doc = MagicMock()
            mock_doc.doc_id = doc_id
            mock_doc.get_full_state.return_value = b"state"
            pm.register_document(mock_doc)
            pm._workspace_dirty[workspace_id] = doc_id

        with patch(
            "promptgrimoire.db.workspaces.save_workspace_crdt_state",
            new_callable=AsyncMock,
        ) as mock_save:
            mock_save.return_value = True
            await pm.persist_all_dirty_workspaces()

            assert mock_save.call_count == 2

        assert len(pm._workspace_dirty) == 0

    @pytest.mark.asyncio
    async def test_debounced_workspace_save_fires_after_delay(self) -> None:
        """Debounced workspace save should fire after debounce_seconds."""
        pm = PersistenceManager()
        pm.debounce_seconds = 0.1  # Fast for testing
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        mock_doc.get_full_state.return_value = b"state"
        pm.register_document(mock_doc)

        with patch(
            "promptgrimoire.db.workspaces.save_workspace_crdt_state",
            new_callable=AsyncMock,
        ) as mock_save:
            mock_save.return_value = True
            pm.mark_dirty_workspace(workspace_id, doc_id, last_editor="User1")

            # Should not have saved yet
            mock_save.assert_not_called()

            # Wait for debounce (with some buffer)
            await asyncio.sleep(pm.debounce_seconds + 0.05)

            # Should have saved now
            mock_save.assert_called_once_with(workspace_id, b"state")

    @pytest.mark.asyncio
    async def test_debounce_resets_on_new_workspace_edit(self) -> None:
        """New workspace edit should reset debounce timer."""
        pm = PersistenceManager()
        pm.debounce_seconds = 0.1  # Fast for testing
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        mock_doc.get_full_state.return_value = b"state"
        pm.register_document(mock_doc)

        with patch(
            "promptgrimoire.db.workspaces.save_workspace_crdt_state",
            new_callable=AsyncMock,
        ) as mock_save:
            mock_save.return_value = True

            # First edit
            pm.mark_dirty_workspace(workspace_id, doc_id)

            # Wait less than debounce time
            await asyncio.sleep(pm.debounce_seconds / 2)

            # Second edit - should reset timer
            pm.mark_dirty_workspace(workspace_id, doc_id)

            # Wait less than debounce time again
            await asyncio.sleep(pm.debounce_seconds / 2)

            # Should not have saved yet (timer was reset)
            mock_save.assert_not_called()

            # Wait for the rest of the debounce
            await asyncio.sleep(pm.debounce_seconds / 2 + 0.05)

            # Now it should have saved
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_workspace_edit_cancels_first_task(self) -> None:
        """Second workspace edit cancels first pending save and schedules new one."""
        pm = PersistenceManager()
        workspace_id = uuid4()
        doc_id = f"ws-{workspace_id}"

        mock_doc = MagicMock()
        mock_doc.doc_id = doc_id
        mock_doc.get_full_state.return_value = b"state"
        pm.register_document(mock_doc)

        # First edit
        pm.mark_dirty_workspace(workspace_id, doc_id)
        first_task = pm._workspace_pending_saves.get(workspace_id)

        # Second edit - should cancel first
        pm.mark_dirty_workspace(workspace_id, doc_id)
        second_task = pm._workspace_pending_saves.get(workspace_id)

        # Tasks should be different
        assert first_task is not second_task

        # Give event loop a chance to process cancellation
        await asyncio.sleep(0.01)

        # First task should be cancelled
        assert first_task.cancelled() or first_task.done()

        # Clean up
        second_task.cancel()
