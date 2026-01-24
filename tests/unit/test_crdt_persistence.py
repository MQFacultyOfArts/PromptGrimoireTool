"""Unit tests for CRDT persistence manager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.crdt.persistence import DEBOUNCE_SECONDS, PersistenceManager


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

    @pytest.mark.asyncio
    async def test_mark_dirty_adds_to_dirty_set(self) -> None:
        """mark_dirty should add doc_id to dirty set."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)

        pm.mark_dirty("test-doc")

        assert "test-doc" in pm._dirty_docs

        # Clean up
        pm._cancel_pending_save("test-doc")

    @pytest.mark.asyncio
    async def test_mark_dirty_schedules_save(self) -> None:
        """mark_dirty should schedule a debounced save."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)

        pm.mark_dirty("test-doc")

        assert "test-doc" in pm._pending_saves
        assert not pm._pending_saves["test-doc"].done()

        # Clean up
        pm._cancel_pending_save("test-doc")

    @pytest.mark.asyncio
    async def test_mark_dirty_tracks_last_editor(self) -> None:
        """mark_dirty should track last editor name."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)

        pm.mark_dirty("test-doc", last_editor="TestUser")

        assert pm._last_editors.get("test-doc") == "TestUser"

        # Clean up
        pm._cancel_pending_save("test-doc")

    @pytest.mark.asyncio
    async def test_cancel_pending_save(self) -> None:
        """_cancel_pending_save should cancel task."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)

        pm.mark_dirty("test-doc")
        task = pm._pending_saves["test-doc"]

        pm._cancel_pending_save("test-doc")

        # Give the event loop a chance to process the cancellation
        await asyncio.sleep(0)

        assert task.cancelled() or task.done()
        assert "test-doc" not in pm._pending_saves

    @pytest.mark.asyncio
    async def test_force_persist_saves_immediately(self) -> None:
        """force_persist should save without waiting for debounce."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        mock_doc.get_full_state.return_value = b"state"
        mock_doc.get_all_highlights.return_value = []
        pm.register_document(mock_doc)
        pm._dirty_docs.add("test-doc")

        with patch(
            "promptgrimoire.db.annotation_state.save_state", new_callable=AsyncMock
        ) as mock_save:
            await pm.force_persist("test-doc")

            mock_save.assert_called_once_with(
                case_id="test-doc",
                crdt_state=b"state",
                highlight_count=0,
                last_editor=None,
            )

        assert "test-doc" not in pm._dirty_docs

    @pytest.mark.asyncio
    async def test_force_persist_does_nothing_if_not_dirty(self) -> None:
        """force_persist should not save if document is not dirty."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        pm.register_document(mock_doc)
        # Note: not adding to _dirty_docs

        with patch(
            "promptgrimoire.db.annotation_state.save_state", new_callable=AsyncMock
        ) as mock_save:
            await pm.force_persist("test-doc")

            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_all_dirty(self) -> None:
        """persist_all_dirty should save all dirty documents."""
        pm = PersistenceManager()

        # Create two mock documents
        for doc_id in ["doc-1", "doc-2"]:
            mock_doc = MagicMock()
            mock_doc.doc_id = doc_id
            mock_doc.get_full_state.return_value = b"state"
            mock_doc.get_all_highlights.return_value = []
            pm.register_document(mock_doc)
            pm._dirty_docs.add(doc_id)

        with patch(
            "promptgrimoire.db.annotation_state.save_state", new_callable=AsyncMock
        ) as mock_save:
            await pm.persist_all_dirty()

            assert mock_save.call_count == 2

        assert len(pm._dirty_docs) == 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_debounced_save_fires_after_delay(self) -> None:
        """Debounced save should fire after DEBOUNCE_SECONDS (real timing)."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        mock_doc.get_full_state.return_value = b"state"
        mock_doc.get_all_highlights.return_value = [{"id": "1"}]
        pm.register_document(mock_doc)

        with patch(
            "promptgrimoire.db.annotation_state.save_state", new_callable=AsyncMock
        ) as mock_save:
            pm.mark_dirty("test-doc", last_editor="User1")

            # Should not have saved yet
            mock_save.assert_not_called()

            # Wait for debounce (with some buffer)
            await asyncio.sleep(DEBOUNCE_SECONDS + 0.5)

            # Should have saved now
            mock_save.assert_called_once_with(
                case_id="test-doc",
                crdt_state=b"state",
                highlight_count=1,
                last_editor="User1",
            )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_debounce_resets_on_new_edit(self) -> None:
        """New edit should reset debounce timer (real timing)."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        mock_doc.get_full_state.return_value = b"state"
        mock_doc.get_all_highlights.return_value = []
        pm.register_document(mock_doc)

        with patch(
            "promptgrimoire.db.annotation_state.save_state", new_callable=AsyncMock
        ) as mock_save:
            # First edit
            pm.mark_dirty("test-doc")

            # Wait less than debounce time
            await asyncio.sleep(DEBOUNCE_SECONDS / 2)

            # Second edit - should reset timer
            pm.mark_dirty("test-doc")

            # Wait less than debounce time again
            await asyncio.sleep(DEBOUNCE_SECONDS / 2)

            # Should not have saved yet (timer was reset)
            mock_save.assert_not_called()

            # Wait for the rest of the debounce
            await asyncio.sleep(DEBOUNCE_SECONDS / 2 + 0.5)

            # Now it should have saved
            mock_save.assert_called_once()


class TestPersistenceManagerFast:
    """Fast debounce tests - verify scheduling without waiting."""

    @pytest.mark.asyncio
    async def test_mark_dirty_schedules_debounced_save(self) -> None:
        """mark_dirty schedules a save task that will call save_state."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        mock_doc.get_full_state.return_value = b"state"
        mock_doc.get_all_highlights.return_value = [{"id": "1"}]
        pm.register_document(mock_doc)

        pm.mark_dirty("test-doc", last_editor="User1")

        # Verify task was scheduled
        assert "test-doc" in pm._pending_saves
        assert not pm._pending_saves["test-doc"].done()
        assert "test-doc" in pm._dirty_docs
        assert pm._last_editors.get("test-doc") == "User1"

        # Clean up
        pm._cancel_pending_save("test-doc")

    @pytest.mark.asyncio
    async def test_second_edit_cancels_first_task(self) -> None:
        """Second edit cancels first pending save and schedules new one."""
        pm = PersistenceManager()
        mock_doc = MagicMock()
        mock_doc.doc_id = "test-doc"
        mock_doc.get_full_state.return_value = b"state"
        mock_doc.get_all_highlights.return_value = []
        pm.register_document(mock_doc)

        # First edit
        pm.mark_dirty("test-doc")
        first_task = pm._pending_saves.get("test-doc")

        # Second edit - should cancel first
        pm.mark_dirty("test-doc")
        second_task = pm._pending_saves.get("test-doc")

        # Tasks should be different
        assert first_task is not second_task

        # Give event loop a chance to process cancellation
        await asyncio.sleep(0.01)

        # First task should be cancelled
        assert first_task.cancelled() or first_task.done()

        # Clean up
        pm._cancel_pending_save("test-doc")
