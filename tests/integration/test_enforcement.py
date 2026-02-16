"""Integration tests for workspace access enforcement and revocation.

These tests verify check_workspace_access() composition and revocation broadcast.

Acceptance Criteria:
- AC6.6: Admin (via Stytch) gets owner-level access regardless of ACL/enrollment
- AC6.9: User with no auth session gets None
- AC10.1: Unauthenticated user redirected to /login (tested via return value)
- AC10.2: Unauthorised user redirected to /courses (tested via return value)
- AC10.3: Viewer sees read-only UI (tested via return value "viewer")
- AC10.4: Editor/owner sees full edit UI (tested via return value)
- AC10.5: Revocation pushes redirect (deferred to E2E -- websocket needed)
- AC10.6: Revoked user sees toast (deferred to E2E -- websocket needed)
- AC10.7: No websocket -- revocation returns 0, takes effect on next page load
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _make_auth_user(user_id: str, *, is_admin: bool = False) -> dict[str, object]:
    """Build a minimal auth_user dict for testing."""
    return {
        "user_id": user_id,
        "is_admin": is_admin,
        "roles": [],
    }


class TestCheckWorkspaceAccessAdminBypass:
    """AC6.6: Admin gets owner-level access regardless of ACL/enrollment."""

    @pytest.mark.asyncio
    async def test_admin_gets_owner_without_acl(self) -> None:
        """Admin user gets 'owner' even with no ACL entry."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        auth_user = _make_auth_user(str(uuid4()), is_admin=True)

        result = await check_workspace_access(workspace.id, auth_user)

        assert result == "owner"

    @pytest.mark.asyncio
    async def test_instructor_role_gets_owner(self) -> None:
        """User with instructor Stytch role gets 'owner' (privileged bypass)."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        auth_user: dict[str, object] = {
            "user_id": str(uuid4()),
            "is_admin": False,
            "roles": ["instructor"],
        }

        result = await check_workspace_access(workspace.id, auth_user)

        assert result == "owner"


class TestCheckWorkspaceAccessNoAuth:
    """AC6.9: User with no auth session gets None."""

    @pytest.mark.asyncio
    async def test_none_auth_user_returns_none(self) -> None:
        """None auth_user (unauthenticated) returns None."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        result = await check_workspace_access(workspace.id, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_none(self) -> None:
        """Auth user dict without user_id key returns None."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        auth_user: dict[str, object] = {"is_admin": False, "roles": []}

        result = await check_workspace_access(workspace.id, auth_user)

        assert result is None


class TestCheckWorkspaceAccessUnauthenticated:
    """AC10.1: Unauthenticated user accessing workspace URL is redirected to /login.

    Tested at integration level via return value -- page layer redirects on None.
    """

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_none(self) -> None:
        """Unauthenticated (None) -> None, page layer redirects to /login."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        result = await check_workspace_access(workspace.id, None)

        assert result is None


class TestCheckWorkspaceAccessUnauthorised:
    """AC10.2: Unauthorised user redirected to /courses with notification.

    Tested at integration level via return value -- page layer redirects on None.
    """

    @pytest.mark.asyncio
    async def test_unauthorised_user_returns_none(self) -> None:
        """User with no ACL entry and no enrollment -> None."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"enforce-unauth-{tag}@test.local",
            display_name=f"Unauth {tag}",
        )
        workspace = await create_workspace()
        auth_user = _make_auth_user(str(user.id))

        result = await check_workspace_access(workspace.id, auth_user)

        assert result is None


class TestCheckWorkspaceAccessViewer:
    """AC10.3: Authorised user with viewer permission sees read-only UI.

    Tested at integration level -- return value "viewer" means read-only.
    """

    @pytest.mark.asyncio
    async def test_viewer_returns_viewer(self) -> None:
        """User with explicit viewer ACL -> 'viewer'."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"enforce-viewer-{tag}@test.local",
            display_name=f"Viewer {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "viewer")
        auth_user = _make_auth_user(str(user.id))

        result = await check_workspace_access(workspace.id, auth_user)

        assert result == "viewer"


class TestCheckWorkspaceAccessEditorOwner:
    """AC10.4: Authorised user with editor/owner permission sees full edit UI.

    Tested at integration level -- return value "editor"/"owner" means full UI.
    """

    @pytest.mark.asyncio
    async def test_editor_returns_editor(self) -> None:
        """User with explicit editor ACL -> 'editor'."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"enforce-editor-{tag}@test.local",
            display_name=f"Editor {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "editor")
        auth_user = _make_auth_user(str(user.id))

        result = await check_workspace_access(workspace.id, auth_user)

        assert result == "editor"

    @pytest.mark.asyncio
    async def test_owner_returns_owner(self) -> None:
        """User with explicit owner ACL -> 'owner'."""
        from promptgrimoire.auth import check_workspace_access
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"enforce-owner-{tag}@test.local",
            display_name=f"Owner {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "owner")
        auth_user = _make_auth_user(str(user.id))

        result = await check_workspace_access(workspace.id, auth_user)

        assert result == "owner"


class TestRevocationBroadcast:
    """AC10.5, AC10.6, AC10.7: Revocation broadcast.

    AC10.5 and AC10.6 require connected NiceGUI websocket clients -- deferred
    to E2E. AC10.7 (no websocket) is tested here.
    """

    @pytest.mark.asyncio
    async def test_revoke_no_connected_clients_returns_zero(self) -> None:
        """revoke_and_redirect returns 0 when user has no websocket connection.

        AC10.7: revocation takes effect on next page load because
        check_workspace_access() re-checks permissions every page load.
        """
        from promptgrimoire.pages.annotation.broadcast import revoke_and_redirect

        # No clients connected for this workspace
        result = await revoke_and_redirect(uuid4(), uuid4())

        assert result == 0

    @pytest.mark.asyncio
    async def test_revoke_cleans_up_empty_workspace_dict(self) -> None:
        """After revoking with no matching clients, workspace dict stays clean."""
        from promptgrimoire.pages.annotation import _workspace_presence
        from promptgrimoire.pages.annotation.broadcast import revoke_and_redirect

        workspace_id = uuid4()
        user_id = uuid4()

        # Ensure workspace not in presence registry
        _workspace_presence.pop(str(workspace_id), None)

        result = await revoke_and_redirect(workspace_id, user_id)

        assert result == 0
        assert str(workspace_id) not in _workspace_presence
