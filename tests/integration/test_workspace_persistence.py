"""Tests for workspace-aware CRDT persistence.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping database integration tests",
    ),
    pytest.mark.xdist_group("db_integration"),
]


class TestWorkspacePersistence:
    """Tests for workspace-aware persistence."""

    @pytest.mark.asyncio
    async def test_mark_dirty_workspace_schedules_save(self) -> None:
        """mark_dirty_workspace schedules save to Workspace."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        # Setup
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create document and register
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Test",
            author="Author",
            document_id=str(uuid4()),
        )

        pm = get_persistence_manager()
        pm.register_document(doc)

        # Mark dirty with workspace_id
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")

        # Force persist (don't wait for debounce)
        await pm.force_persist_workspace(workspace.id)

        # Verify saved to Workspace
        loaded = await get_workspace(workspace.id)
        assert loaded is not None
        assert loaded.crdt_state is not None
        assert len(loaded.crdt_state) > 0

    @pytest.mark.asyncio
    async def test_workspace_persist_preserves_highlights(self) -> None:
        """Persisted workspace CRDT state preserves all highlights."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create document with highlights
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc_uuid = str(uuid4())
        hl1_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="First",
            author="Author",
            document_id=doc_uuid,
        )
        hl2_id = doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="Second",
            author="Author",
            document_id=doc_uuid,
        )

        pm = get_persistence_manager()
        pm.register_document(doc)
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")
        await pm.force_persist_workspace(workspace.id)

        # Load and verify
        loaded_workspace = await get_workspace(workspace.id)
        assert loaded_workspace is not None
        assert loaded_workspace.crdt_state is not None
        loaded_doc = AnnotationDocument("loaded")
        loaded_doc.apply_update(loaded_workspace.crdt_state)

        highlights = loaded_doc.get_all_highlights()
        assert len(highlights) == 2
        assert any(h["id"] == hl1_id for h in highlights)
        assert any(h["id"] == hl2_id for h in highlights)


class TestWorkspaceLoading:
    """Tests for loading documents from Workspace."""

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_loads_existing(self) -> None:
        """Loads existing CRDT state from Workspace."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            AnnotationDocumentRegistry,
        )
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            save_workspace_crdt_state,
        )

        # Setup: create workspace with persisted CRDT state
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create and save initial state
        initial_doc = AnnotationDocument("initial")
        doc_uuid = str(uuid4())
        hl_id = initial_doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Persisted highlight",
            author="Author",
            document_id=doc_uuid,
        )
        await save_workspace_crdt_state(workspace.id, initial_doc.get_full_state())

        # Load via registry
        registry = AnnotationDocumentRegistry()
        loaded_doc = await registry.get_or_create_for_workspace(workspace.id)

        # Verify loaded
        assert loaded_doc is not None
        highlights = loaded_doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["id"] == hl_id
        assert highlights[0]["document_id"] == doc_uuid

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_creates_empty_if_no_state(self) -> None:
        """Creates empty document if workspace has no CRDT state."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        assert doc is not None
        assert doc.get_all_highlights() == []

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_caches_document(self) -> None:
        """Second call returns cached document."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc1 = await registry.get_or_create_for_workspace(workspace.id)
        doc2 = await registry.get_or_create_for_workspace(workspace.id)

        assert doc1 is doc2  # Same instance

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_registers_with_persistence(self) -> None:
        """Loaded document is registered with PersistenceManager."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        pm = get_persistence_manager()
        # Doc should be registered
        assert pm._doc_registry.get(doc.doc_id) is doc
