"""Tests for workspace CRUD operations.

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


class TestCreateWorkspace:
    """Tests for create_workspace."""

    @pytest.mark.asyncio
    async def test_creates_workspace_with_user_reference(self) -> None:
        """Workspace is created with created_by user."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        workspace = await create_workspace(created_by=user.id)

        assert workspace.id is not None
        assert workspace.created_by == user.id
        assert workspace.crdt_state is None
        assert workspace.created_at is not None

    @pytest.mark.asyncio
    async def test_creates_workspace_with_unique_id(self) -> None:
        """Each workspace gets a unique UUID."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        ws1 = await create_workspace(created_by=user.id)
        ws2 = await create_workspace(created_by=user.id)

        assert ws1.id != ws2.id


class TestGetWorkspace:
    """Tests for get_workspace."""

    @pytest.mark.asyncio
    async def test_returns_workspace_by_id(self) -> None:
        """Returns workspace when found."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        found = await get_workspace(workspace.id)

        assert found is not None
        assert found.id == workspace.id

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self) -> None:
        """Returns None when workspace not found."""
        from promptgrimoire.db.workspaces import get_workspace

        found = await get_workspace(uuid4())

        assert found is None


class TestDeleteWorkspace:
    """Tests for delete_workspace."""

    @pytest.mark.asyncio
    async def test_deletes_workspace(self) -> None:
        """Workspace is deleted."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            delete_workspace,
            get_workspace,
        )

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        await delete_workspace(workspace.id)

        found = await get_workspace(workspace.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_workspace_is_noop(self) -> None:
        """Deleting nonexistent workspace doesn't raise."""
        from promptgrimoire.db.workspaces import delete_workspace

        # Should not raise
        await delete_workspace(uuid4())


class TestAddDocument:
    """Tests for add_document."""

    @pytest.mark.asyncio
    async def test_adds_document_to_workspace(self) -> None:
        """Document is created in workspace."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p><span>Hello</span></p>",
            raw_content="Hello",
            title="My Document",
        )

        assert doc.id is not None
        assert doc.workspace_id == workspace.id
        assert doc.type == "source"
        assert doc.content == "<p><span>Hello</span></p>"
        assert doc.raw_content == "Hello"
        assert doc.title == "My Document"
        assert doc.order_index == 0

    @pytest.mark.asyncio
    async def test_auto_increments_order_index(self) -> None:
        """Documents get sequential order_index."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc1 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="Doc 1",
            raw_content="Doc 1",
        )
        doc2 = await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Doc 2",
            raw_content="Doc 2",
        )

        assert doc1.order_index == 0
        assert doc2.order_index == 1


class TestListDocuments:
    """Tests for list_documents."""

    @pytest.mark.asyncio
    async def test_returns_documents_ordered_by_order_index(self) -> None:
        """Documents returned in order_index order."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="First",
            raw_content="First",
        )
        await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Second",
            raw_content="Second",
        )

        docs = await list_documents(workspace.id)

        assert len(docs) == 2
        assert docs[0].content == "First"
        assert docs[1].content == "Second"

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_workspace(self) -> None:
        """Returns empty list when workspace has no documents."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        docs = await list_documents(workspace.id)

        assert docs == []


class TestReorderDocuments:
    """Tests for reorder_documents."""

    @pytest.mark.asyncio
    async def test_reorders_documents(self) -> None:
        """Documents are reordered to match provided order."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_documents,
            reorder_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc1 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="First",
            raw_content="First",
        )
        doc2 = await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Second",
            raw_content="Second",
        )

        # Reverse order
        await reorder_documents(workspace.id, [doc2.id, doc1.id])

        docs = await list_documents(workspace.id)
        assert docs[0].id == doc2.id
        assert docs[1].id == doc1.id


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    @pytest.mark.asyncio
    async def test_deleting_workspace_deletes_documents(self) -> None:
        """Documents are deleted when workspace is deleted."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace, delete_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        workspace_id = workspace.id

        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="Will be deleted",
            raw_content="Will be deleted",
        )

        await delete_workspace(workspace.id)

        # Workspace is gone, so documents must be too (CASCADE)
        docs = await list_documents(workspace_id)
        assert docs == []
