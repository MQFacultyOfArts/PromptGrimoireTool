"""Tests for workspace sharing and title update operations.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify update_workspace_sharing and update_workspace_title functions
that persist sharing state and display titles on workspaces.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestUpdateWorkspaceSharing:
    """Tests for update_workspace_sharing."""

    @pytest.mark.asyncio
    async def test_set_shared_with_class_true(self) -> None:
        """Setting shared_with_class=True persists."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            update_workspace_sharing,
        )

        workspace = await create_workspace()
        assert workspace.shared_with_class is False

        updated = await update_workspace_sharing(workspace.id, shared_with_class=True)

        assert updated.shared_with_class is True

        # Verify persistence via fresh read
        reloaded = await get_workspace(workspace.id)
        assert reloaded is not None
        assert reloaded.shared_with_class is True

    @pytest.mark.asyncio
    async def test_set_shared_with_class_false(self) -> None:
        """Setting shared_with_class=False persists after being True."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            update_workspace_sharing,
        )

        workspace = await create_workspace()
        await update_workspace_sharing(workspace.id, shared_with_class=True)

        updated = await update_workspace_sharing(workspace.id, shared_with_class=False)

        assert updated.shared_with_class is False

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_raises_valueerror(self) -> None:
        """Updating a non-existent workspace raises ValueError."""
        from promptgrimoire.db.workspaces import update_workspace_sharing

        with pytest.raises(ValueError, match="not found"):
            await update_workspace_sharing(uuid4(), shared_with_class=True)

    @pytest.mark.asyncio
    async def test_updated_at_advances(self) -> None:
        """updated_at timestamp advances after sharing update."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            update_workspace_sharing,
        )

        workspace = await create_workspace()
        original_updated_at = workspace.updated_at

        updated = await update_workspace_sharing(workspace.id, shared_with_class=True)

        assert updated.updated_at >= original_updated_at


class TestUpdateWorkspaceTitle:
    """Tests for update_workspace_title."""

    @pytest.mark.asyncio
    async def test_set_title(self) -> None:
        """Setting a title persists."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            update_workspace_title,
        )

        workspace = await create_workspace()
        assert workspace.title is None

        updated = await update_workspace_title(workspace.id, title="My Workspace")

        assert updated.title == "My Workspace"

        # Verify persistence via fresh read
        reloaded = await get_workspace(workspace.id)
        assert reloaded is not None
        assert reloaded.title == "My Workspace"

    @pytest.mark.asyncio
    async def test_set_title_to_none(self) -> None:
        """Setting title to None clears it."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            update_workspace_title,
        )

        workspace = await create_workspace()
        await update_workspace_title(workspace.id, title="Temporary Name")

        updated = await update_workspace_title(workspace.id, title=None)

        assert updated.title is None

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_raises_valueerror(self) -> None:
        """Updating title of a non-existent workspace raises ValueError."""
        from promptgrimoire.db.workspaces import update_workspace_title

        with pytest.raises(ValueError, match="not found"):
            await update_workspace_title(uuid4(), title="Nope")

    @pytest.mark.asyncio
    async def test_updated_at_advances(self) -> None:
        """updated_at timestamp advances after title update."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            update_workspace_title,
        )

        workspace = await create_workspace()
        original_updated_at = workspace.updated_at

        updated = await update_workspace_title(workspace.id, title="New Title")

        assert updated.updated_at >= original_updated_at
