"""Tests for ACL CRUD operations (grant, revoke, list).

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- AC4.1: ACLEntry can be created with valid workspace_id, user_id, permission
- AC4.2: Deleting a Workspace CASCADEs to its ACLEntry rows
- AC4.3: Deleting a User CASCADEs to their ACLEntry rows
- AC4.4: Duplicate (workspace_id, user_id) pair is rejected (UNIQUE constraint)
- AC4.5: Granting new permission to existing pair upserts the permission
- AC5.1: grant_permission() creates an entry
- AC5.2: revoke_permission() deletes an entry
- AC5.3: list_entries_for_workspace() returns all entries for a workspace
- AC5.4: list_entries_for_user() returns all entries for a user
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestGrantPermission:
    """Tests for grant_permission (AC4.1, AC5.1).

    Verifies that ACLEntry can be created with valid references and that
    returned entries have correct fields.
    """

    @pytest.mark.asyncio
    async def test_creates_acl_entry(self) -> None:
        """grant_permission creates an ACLEntry with correct fields."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-grant-{tag}@test.local",
            display_name=f"ACL Grant {tag}",
        )
        workspace = await create_workspace()

        entry = await grant_permission(workspace.id, user.id, "viewer")

        assert entry.workspace_id == workspace.id
        assert entry.user_id == user.id
        assert entry.permission == "viewer"
        assert entry.id is not None
        assert entry.created_at is not None

    @pytest.mark.asyncio
    async def test_upsert_updates_permission(self) -> None:
        """Granting again to same pair updates permission (AC4.5)."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-upsert-{tag}@test.local",
            display_name=f"ACL Upsert {tag}",
        )
        workspace = await create_workspace()

        first = await grant_permission(workspace.id, user.id, "viewer")
        second = await grant_permission(workspace.id, user.id, "editor")

        # Same row was updated, not a new one created
        assert second.id == first.id
        assert second.workspace_id == first.workspace_id
        assert second.user_id == first.user_id
        assert second.permission == "editor"


class TestRevokePermission:
    """Tests for revoke_permission (AC5.2).

    Verifies that revoking deletes the entry and returns appropriate booleans.
    """

    @pytest.mark.asyncio
    async def test_revoke_existing_returns_true(self) -> None:
        """Revoking an existing entry returns True."""
        from promptgrimoire.db.acl import grant_permission, revoke_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-revoke-{tag}@test.local",
            display_name=f"ACL Revoke {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "viewer")

        result = await revoke_permission(workspace.id, user.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_false(self) -> None:
        """Revoking when no entry exists returns False."""
        from promptgrimoire.db.acl import revoke_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-revoke-none-{tag}@test.local",
            display_name=f"ACL Revoke None {tag}",
        )
        workspace = await create_workspace()

        result = await revoke_permission(workspace.id, user.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_then_revoke_returns_false(self) -> None:
        """Revoking twice: first True, second False."""
        from promptgrimoire.db.acl import grant_permission, revoke_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-double-revoke-{tag}@test.local",
            display_name=f"ACL Double Revoke {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "editor")

        first = await revoke_permission(workspace.id, user.id)
        second = await revoke_permission(workspace.id, user.id)

        assert first is True
        assert second is False


class TestListEntriesForWorkspace:
    """Tests for list_entries_for_workspace (AC5.3).

    Verifies that all ACL entries for a workspace are returned.
    """

    @pytest.mark.asyncio
    async def test_returns_all_entries_for_workspace(self) -> None:
        """Multiple users granted on one workspace are all returned."""
        from promptgrimoire.db.acl import grant_permission, list_entries_for_workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user1 = await create_user(
            email=f"acl-list-ws-1-{tag}@test.local",
            display_name=f"User 1 {tag}",
        )
        user2 = await create_user(
            email=f"acl-list-ws-2-{tag}@test.local",
            display_name=f"User 2 {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user1.id, "viewer")
        await grant_permission(workspace.id, user2.id, "editor")

        entries = await list_entries_for_workspace(workspace.id)

        assert len(entries) == 2
        user_ids = {e.user_id for e in entries}
        assert user_ids == {user1.id, user2.id}

    @pytest.mark.asyncio
    async def test_returns_empty_for_workspace_without_entries(self) -> None:
        """Workspace with no ACL entries returns empty list."""
        from promptgrimoire.db.acl import list_entries_for_workspace
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        entries = await list_entries_for_workspace(workspace.id)

        assert entries == []


class TestListEntriesForUser:
    """Tests for list_entries_for_user (AC5.4).

    Verifies that all ACL entries for a user are returned.
    """

    @pytest.mark.asyncio
    async def test_returns_all_entries_for_user(self) -> None:
        """User granted on multiple workspaces: all entries returned."""
        from promptgrimoire.db.acl import grant_permission, list_entries_for_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-list-user-{tag}@test.local",
            display_name=f"ACL List User {tag}",
        )
        ws1 = await create_workspace()
        ws2 = await create_workspace()
        await grant_permission(ws1.id, user.id, "viewer")
        await grant_permission(ws2.id, user.id, "owner")

        entries = await list_entries_for_user(user.id)

        assert len(entries) == 2
        ws_ids = {e.workspace_id for e in entries}
        assert ws_ids == {ws1.id, ws2.id}

    @pytest.mark.asyncio
    async def test_returns_empty_for_user_without_entries(self) -> None:
        """User with no ACL entries returns empty list."""
        from promptgrimoire.db.acl import list_entries_for_user
        from promptgrimoire.db.users import create_user

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-list-empty-{tag}@test.local",
            display_name=f"ACL List Empty {tag}",
        )

        entries = await list_entries_for_user(user.id)

        assert entries == []


class TestCascadeDeleteWorkspace:
    """Verify CASCADE delete from Workspace to ACLEntry (AC4.2).

    Deleting a Workspace must delete all its ACL entries.
    """

    @pytest.mark.asyncio
    async def test_deleting_workspace_deletes_acl_entries(self) -> None:
        """ACL entries are cascade-deleted when workspace is deleted."""
        from promptgrimoire.db.acl import grant_permission, list_entries_for_workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, delete_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-cascade-ws-{tag}@test.local",
            display_name=f"ACL Cascade WS {tag}",
        )
        workspace = await create_workspace()
        workspace_id = workspace.id
        await grant_permission(workspace.id, user.id, "editor")

        await delete_workspace(workspace.id)

        entries = await list_entries_for_workspace(workspace_id)
        assert entries == []


class TestCascadeDeleteUser:
    """Verify CASCADE delete from User to ACLEntry (AC4.3).

    Deleting a User must delete all their ACL entries.
    """

    @pytest.mark.asyncio
    async def test_deleting_user_deletes_acl_entries(self) -> None:
        """ACL entries are cascade-deleted when user is deleted."""
        from sqlmodel import delete, select

        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import ACLEntry, User
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-cascade-user-{tag}@test.local",
            display_name=f"ACL Cascade User {tag}",
        )
        user_id = user.id
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "viewer")

        # Delete the user directly via session
        async with get_session() as session:
            # ty: SQLModel column comparison returns expression, not bool
            stmt = delete(User).where(User.id == user_id)  # type: ignore[arg-type]
            await session.execute(stmt)

        # Verify ACL entries for this user are gone
        async with get_session() as session:
            result = await session.exec(
                select(ACLEntry).where(ACLEntry.user_id == user_id)
            )
            remaining = result.all()
            assert len(remaining) == 0


class TestDuplicateConstraint:
    """Verify UNIQUE constraint on (workspace_id, user_id) (AC4.4).

    Direct INSERT (not upsert) of duplicate pair must raise IntegrityError.
    """

    @pytest.mark.asyncio
    async def test_duplicate_pair_raises_integrity_error(self) -> None:
        """Direct INSERT of duplicate (workspace_id, user_id) raises IntegrityError."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import ACLEntry
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"acl-dup-{tag}@test.local",
            display_name=f"ACL Dup {tag}",
        )
        workspace = await create_workspace()

        # Insert first entry directly
        async with get_session() as session:
            entry = ACLEntry(
                workspace_id=workspace.id,
                user_id=user.id,
                permission="viewer",
            )
            session.add(entry)
            await session.flush()

        # Insert duplicate -- should raise
        with pytest.raises(IntegrityError):
            async with get_session() as session:
                dup = ACLEntry(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    permission="editor",
                )
                session.add(dup)
                await session.flush()
