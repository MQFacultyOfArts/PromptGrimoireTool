"""Integration tests for list_peer_workspaces discovery query.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Verifies workspace-sharing-97.AC2.1 (discovery aspect):
- Returns shared workspaces for an activity
- Excludes workspaces where shared_with_class=False
- Excludes the requesting user's own workspace(s)
- Excludes template workspaces
- Returns empty list when no workspaces are shared
- Workspaces from other activities not included
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestPeerDiscoveryReturnsShared:
    """Returns shared workspaces for an activity."""

    @pytest.mark.asyncio
    async def test_returns_shared_workspaces(self) -> None:
        """Workspace with shared_with_class=True appears in results."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces,
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
            email=f"disc-shared-owner-{tag}@test.local",
            display_name=f"Disc Owner {tag}",
        )
        viewer = await create_user(
            email=f"disc-shared-viewer-{tag}@test.local",
            display_name=f"Disc Viewer {tag}",
        )
        course = await create_course(
            code=f"DS{tag[:5]}",
            name=f"Disc Shared {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Shared Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, owner.id, "owner")
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await list_peer_workspaces(activity.id, viewer.id)

        assert len(result) == 1
        assert result[0].id == workspace.id


class TestPeerDiscoveryExcludesUnshared:
    """Excludes workspaces where shared_with_class=False."""

    @pytest.mark.asyncio
    async def test_excludes_unshared(self) -> None:
        """Workspace with shared_with_class=False not in results."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces,
        )
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"disc-unshared-owner-{tag}@test.local",
            display_name=f"Unshared Owner {tag}",
        )
        viewer = await create_user(
            email=f"disc-unshared-viewer-{tag}@test.local",
            display_name=f"Unshared Viewer {tag}",
        )
        course = await create_course(
            code=f"DU{tag[:5]}",
            name=f"Disc Unshared {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        # shared_with_class defaults to False
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, owner.id, "owner")

        result = await list_peer_workspaces(activity.id, viewer.id)

        assert result == []


class TestPeerDiscoveryExcludesOwn:
    """Excludes the requesting user's own workspace(s)."""

    @pytest.mark.asyncio
    async def test_excludes_own_workspace(self) -> None:
        """User's own workspace (owner ACL) not in their results."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces,
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
            email=f"disc-own-a-{tag}@test.local",
            display_name=f"Own A {tag}",
        )
        user_b = await create_user(
            email=f"disc-own-b-{tag}@test.local",
            display_name=f"Own B {tag}",
        )
        course = await create_course(
            code=f"DO{tag[:5]}",
            name=f"Disc Own {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        # User A's workspace -- shared
        ws_a = await create_workspace()
        await place_workspace_in_activity(ws_a.id, activity.id)
        await grant_permission(ws_a.id, user_a.id, "owner")
        async with get_session() as session:
            ws = await session.get(Workspace, ws_a.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        # User B's workspace -- shared
        ws_b = await create_workspace()
        await place_workspace_in_activity(ws_b.id, activity.id)
        await grant_permission(ws_b.id, user_b.id, "owner")
        async with get_session() as session:
            ws = await session.get(Workspace, ws_b.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        # User A should see B's workspace but not their own
        result_a = await list_peer_workspaces(activity.id, user_a.id)
        assert len(result_a) == 1
        assert result_a[0].id == ws_b.id

        # User B should see A's workspace but not their own
        result_b = await list_peer_workspaces(activity.id, user_b.id)
        assert len(result_b) == 1
        assert result_b[0].id == ws_a.id


class TestPeerDiscoveryExcludesTemplate:
    """Excludes template workspaces."""

    @pytest.mark.asyncio
    async def test_excludes_template_workspace(self) -> None:
        """Activity's template workspace not in results."""
        from promptgrimoire.db.acl import list_peer_workspaces
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week

        tag = uuid4().hex[:8]
        viewer = await create_user(
            email=f"disc-tmpl-viewer-{tag}@test.local",
            display_name=f"Tmpl Viewer {tag}",
        )
        course = await create_course(
            code=f"DT{tag[:5]}",
            name=f"Disc Template {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        # Template workspace is auto-created by create_activity
        # Set shared_with_class=True on it to test exclusion
        async with get_session() as session:
            ws = await session.get(Workspace, activity.template_workspace_id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await list_peer_workspaces(activity.id, viewer.id)

        assert result == []


class TestPeerDiscoveryEmptyList:
    """Returns empty list when no workspaces are shared."""

    @pytest.mark.asyncio
    async def test_empty_when_none_shared(self) -> None:
        """No shared workspaces -> empty list."""
        from promptgrimoire.db.acl import list_peer_workspaces
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week

        tag = uuid4().hex[:8]
        viewer = await create_user(
            email=f"disc-empty-{tag}@test.local",
            display_name=f"Empty {tag}",
        )
        course = await create_course(
            code=f"DE{tag[:5]}",
            name=f"Disc Empty {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Activity")

        result = await list_peer_workspaces(activity.id, viewer.id)

        assert result == []


class TestPeerDiscoveryCrossActivity:
    """Workspaces from other activities not included."""

    @pytest.mark.asyncio
    async def test_other_activity_excluded(self) -> None:
        """Shared workspace in activity B not visible from activity A."""
        from promptgrimoire.db.acl import (
            grant_permission,
            list_peer_workspaces,
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
            email=f"disc-cross-owner-{tag}@test.local",
            display_name=f"Cross Owner {tag}",
        )
        viewer = await create_user(
            email=f"disc-cross-viewer-{tag}@test.local",
            display_name=f"Cross Viewer {tag}",
        )
        course = await create_course(
            code=f"DX{tag[:5]}",
            name=f"Disc Cross {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity_a = await create_activity(week.id, title="Activity A")
        activity_b = await create_activity(week.id, title="Activity B")

        # Shared workspace in activity B
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity_b.id)
        await grant_permission(workspace.id, owner.id, "owner")
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        # Query for activity A -- should not see workspace from B
        result = await list_peer_workspaces(activity_a.id, viewer.id)

        assert result == []
