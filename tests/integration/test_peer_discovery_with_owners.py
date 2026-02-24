"""Integration tests for list_peer_workspaces_with_owners.

Verifies the companion query returns owner display names alongside
workspace data, using the same filtering as list_peer_workspaces.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestPeerWorkspacesWithOwners:
    """list_peer_workspaces_with_owners returns (Workspace, display_name, user_id)."""

    @pytest.mark.asyncio
    async def test_returns_owner_display_name(self) -> None:
        """Each result tuple includes the owner's display name and user_id."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces_with_owners,
        )
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"pwo-owner-{tag}@test.local",
            display_name=f"Owner {tag}",
        )
        viewer = await create_user(
            email=f"pwo-viewer-{tag}@test.local",
            display_name=f"Viewer {tag}",
        )
        course = await create_course(
            code=f"PW{tag[:5]}",
            name=f"Peer Owners {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, owner.id, "owner")
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            ws.title = "Test Title"
            session.add(ws)

        result = await list_peer_workspaces_with_owners(activity.id, viewer.id)

        assert len(result) == 1
        ws_row, display_name, owner_id = result[0]
        assert ws_row.id == workspace.id
        assert ws_row.title == "Test Title"
        assert display_name == f"Owner {tag}"
        assert owner_id == owner.id

    @pytest.mark.asyncio
    async def test_excludes_own_workspace(self) -> None:
        """Same filtering as list_peer_workspaces — own workspace excluded."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces_with_owners,
        )
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        user_a = await create_user(
            email=f"pwo-a-{tag}@test.local",
            display_name=f"User A {tag}",
        )
        user_b = await create_user(
            email=f"pwo-b-{tag}@test.local",
            display_name=f"User B {tag}",
        )
        course = await create_course(
            code=f"PX{tag[:5]}",
            name=f"Peer Excl {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        # Both workspaces shared
        for user, ws_title in [(user_a, "A's Work"), (user_b, "B's Work")]:
            ws = await create_workspace()
            await place_workspace_in_activity(ws.id, activity.id)
            await grant_permission(ws.id, user.id, "owner")
            async with get_session() as session:
                w = await session.get(Workspace, ws.id)
                assert w is not None
                w.shared_with_class = True
                w.title = ws_title
                session.add(w)

        # User A sees only B's workspace
        result = await list_peer_workspaces_with_owners(activity.id, user_a.id)
        assert len(result) == 1
        assert result[0][1] == f"User B {tag}"
