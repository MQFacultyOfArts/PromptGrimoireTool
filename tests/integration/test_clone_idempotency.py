"""Hypothesis tests for #364: clone idempotency and duplicate prevention.

These tests verify that the TOCTOU race condition described in #364 is
real. Each test targets a specific hypothesis about the system's behaviour.

Once the fix is implemented, these tests should be replaced with tests
asserting idempotent behaviour.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _setup_activity():
    """Create a minimal Course -> Week -> Activity with one template document."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspace_documents import add_document

    code = f"C{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Idempotency Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Test Activity")
    await add_document(
        workspace_id=activity.template_workspace_id,
        type="source",
        content="<p>Template content</p>",
        source_type="html",
        title="Template Doc",
    )
    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"idem-{tag}@test.local",
        display_name=f"Idempotency Tester {tag}",
    )
    return activity, user


class TestH1SequentialDoubleClone:
    """H1: clone_workspace_from_activity has no existence check.

    Calling it twice sequentially for the same (activity_id, user_id)
    creates two separate workspaces.
    """

    @pytest.mark.asyncio
    async def test_sequential_double_clone_creates_duplicates(self) -> None:
        """Call clone twice for same user+activity. Expect two workspaces (the bug)."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        clone1, _ = await clone_workspace_from_activity(activity.id, user.id)
        clone2, _ = await clone_workspace_from_activity(activity.id, user.id)

        # Bug demonstrated: two distinct workspaces created
        assert clone1.id != clone2.id


class TestH2NoDatabaseConstraint:
    """H2: No database constraint prevents duplicate workspaces per (activity, user).

    After two clones, both workspaces persist with separate owner ACL entries.
    """

    @pytest.mark.asyncio
    async def test_both_clones_persist_with_owner_acl(self) -> None:
        """Both duplicate workspaces exist in DB with owner ACL entries."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import ACLEntry, Workspace
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        clone1, _ = await clone_workspace_from_activity(activity.id, user.id)
        clone2, _ = await clone_workspace_from_activity(activity.id, user.id)

        async with get_session() as session:
            ws1 = await session.get(Workspace, clone1.id)
            ws2 = await session.get(Workspace, clone2.id)
            assert ws1 is not None
            assert ws2 is not None
            assert ws1.activity_id == ws2.activity_id == activity.id

            # Both have distinct owner ACL entries — DB doesn't prevent this
            result = await session.exec(
                select(ACLEntry).where(
                    ACLEntry.user_id == user.id,
                    ACLEntry.permission == "owner",
                    ACLEntry.workspace_id.in_([clone1.id, clone2.id]),  # type: ignore[union-attr]
                )
            )
            acl_entries = list(result.all())
            assert len(acl_entries) == 2


class TestH3ConcurrentCloneRace:
    """H3: Concurrent clones both succeed.

    asyncio.gather simulates the double-click scenario.
    """

    @pytest.mark.asyncio
    async def test_concurrent_clones_both_succeed(self) -> None:
        """Two concurrent clone calls create two workspaces."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        results = await asyncio.gather(
            clone_workspace_from_activity(activity.id, user.id),
            clone_workspace_from_activity(activity.id, user.id),
        )

        clone1, _ = results[0]
        clone2, _ = results[1]

        # Bug demonstrated: both clones succeed with distinct IDs
        assert clone1.id != clone2.id
