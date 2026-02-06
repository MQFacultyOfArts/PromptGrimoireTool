"""Tests for workspace-aware CRDT persistence.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Workspace isolation: Each test creates its own workspace via UUID.
No user creation needed - workspaces are standalone silos.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


class TestWorkspacePersistence:
    """Tests for workspace-aware persistence."""

    @pytest.mark.asyncio
    async def test_mark_dirty_workspace_schedules_save(self) -> None:
        """mark_dirty_workspace schedules save to Workspace."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        # Setup
        workspace = await create_workspace()

        # Create document and register
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc.add_highlight(
            start_char=0,
            end_char=5,
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
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        workspace = await create_workspace()

        # Create document with highlights
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc_uuid = str(uuid4())
        hl1_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="issue",
            text="First",
            author="Author",
            document_id=doc_uuid,
        )
        hl2_id = doc.add_highlight(
            start_char=10,
            end_char=15,
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
        from promptgrimoire.db.workspaces import (
            create_workspace,
            save_workspace_crdt_state,
        )

        # Setup: create workspace with persisted CRDT state
        workspace = await create_workspace()

        # Create and save initial state
        initial_doc = AnnotationDocument("initial")
        doc_uuid = str(uuid4())
        hl_id = initial_doc.add_highlight(
            start_char=0,
            end_char=5,
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
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        assert doc is not None
        assert doc.get_all_highlights() == []

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_caches_document(self) -> None:
        """Second call returns cached document."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        registry = AnnotationDocumentRegistry()
        doc1 = await registry.get_or_create_for_workspace(workspace.id)
        doc2 = await registry.get_or_create_for_workspace(workspace.id)

        assert doc1 is doc2  # Same instance

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_registers_with_persistence(self) -> None:
        """Loaded document is registered with PersistenceManager."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        pm = get_persistence_manager()
        # Doc should be registered
        assert pm._doc_registry.get(doc.doc_id) is doc


class TestWorkspaceCRDTRoundTrip:
    """Full round-trip tests for workspace CRDT persistence."""

    @pytest.mark.asyncio
    async def test_full_workflow_create_annotate_persist_load(self) -> None:
        """Complete workflow: create workspace, annotate, persist, reload."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.workspaces import create_workspace

        # 1. Create workspace
        workspace = await create_workspace()
        workspace_doc_id = str(uuid4())  # Simulated WorkspaceDocument ID

        # 2. Get document for workspace
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        # 3. Add annotations
        hl1 = doc.add_highlight(
            start_char=0,
            end_char=10,
            tag="issue",
            text="The main legal issue here",
            author="Test Author",
            para_ref="[1]",
            document_id=workspace_doc_id,
        )
        hl2 = doc.add_highlight(
            start_char=20,
            end_char=30,
            tag="citation",
            text="Smith v Jones [2024]",
            author="Test Author",
            para_ref="[2]",
            document_id=workspace_doc_id,
        )
        doc.add_comment(hl1, author="Reviewer", text="Good catch!")

        # 4. Persist via workspace-aware method
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Test Author")
        await pm.force_persist_workspace(workspace.id)

        # 5. Clear registry to force reload
        registry.clear_all()

        # 6. Reload from database
        reloaded_doc = await registry.get_or_create_for_workspace(workspace.id)

        # 7. Verify all data survived
        highlights = reloaded_doc.get_all_highlights()
        assert len(highlights) == 2

        # Check highlight details
        hl1_loaded = reloaded_doc.get_highlight(hl1)
        assert hl1_loaded is not None
        assert hl1_loaded["tag"] == "issue"
        assert hl1_loaded["document_id"] == workspace_doc_id
        assert len(hl1_loaded.get("comments", [])) == 1
        assert hl1_loaded["comments"][0]["text"] == "Good catch!"

        hl2_loaded = reloaded_doc.get_highlight(hl2)
        assert hl2_loaded is not None
        assert hl2_loaded["tag"] == "citation"
        assert hl2_loaded["document_id"] == workspace_doc_id

    @pytest.mark.asyncio
    async def test_filter_highlights_by_document_after_reload(self) -> None:
        """Can filter reloaded highlights by document_id."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        doc_a_id = str(uuid4())
        doc_b_id = str(uuid4())

        # Create highlights for two different documents
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="issue",
            text="Doc A hl 1",
            author="Author",
            document_id=doc_a_id,
        )
        doc.add_highlight(
            start_char=10,
            end_char=15,
            tag="citation",
            text="Doc B hl 1",
            author="Author",
            document_id=doc_b_id,
        )
        doc.add_highlight(
            start_char=20,
            end_char=25,
            tag="issue",
            text="Doc A hl 2",
            author="Author",
            document_id=doc_a_id,
        )

        # Persist and reload
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")
        await pm.force_persist_workspace(workspace.id)
        registry.clear_all()
        reloaded = await registry.get_or_create_for_workspace(workspace.id)

        # Filter by document
        doc_a_highlights = reloaded.get_highlights_for_document(doc_a_id)
        doc_b_highlights = reloaded.get_highlights_for_document(doc_b_id)

        assert len(doc_a_highlights) == 2
        assert len(doc_b_highlights) == 1
        assert all(h["document_id"] == doc_a_id for h in doc_a_highlights)
        assert all(h["document_id"] == doc_b_id for h in doc_b_highlights)
