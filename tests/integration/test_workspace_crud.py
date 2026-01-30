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
