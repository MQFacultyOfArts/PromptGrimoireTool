"""Tests for tag schema: PlacementContext allow_tag_creation resolution.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify tri-state allow_tag_creation inheritance (AC1.5).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_tag_creation_data(
    *,
    course_tag_creation: bool = True,
    activity_tag_creation: bool | None = None,
) -> dict:
    """Create hierarchy for tag creation tri-state tests.

    Returns course, activity, and the cloned workspace_id.
    """
    from promptgrimoire.db.activities import create_activity, update_activity
    from promptgrimoire.db.courses import create_course, enroll_user
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"T{tag[:6].upper()}", name="Tag Test", semester="2026-S1"
    )

    # Update course default_allow_tag_creation
    async with get_session() as session:
        c = await session.get(Course, course.id)
        assert c is not None
        c.default_allow_tag_creation = course_tag_creation
        session.add(c)
        await session.flush()
        await session.refresh(c)
        course = c

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Tag Activity")
    await update_activity(activity.id, allow_tag_creation=activity_tag_creation)

    owner = await create_user(
        email=f"tagowner-{tag}@test.local", display_name=f"TagOwner {tag}"
    )
    await enroll_user(course_id=course.id, user_id=owner.id, role="student")

    clone, _ = await clone_workspace_from_activity(activity.id, owner.id)

    return {
        "course": course,
        "activity": activity,
        "owner": owner,
        "workspace_id": clone.id,
    }


class TestPlacementContextTagCreation:
    """Tests for allow_tag_creation tri-state resolution in PlacementContext."""

    @pytest.mark.asyncio
    async def test_inherits_from_course_true(self) -> None:
        """Activity with allow_tag_creation=None inherits course default=True.

        Verifies AC1.5 (inherit).
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_tag_creation_data(
            course_tag_creation=True, activity_tag_creation=None
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_tag_creation is True
        assert ctx.course_id == data["course"].id

    @pytest.mark.asyncio
    async def test_activity_overrides_course_true_with_false(self) -> None:
        """Activity allow_tag_creation=False overrides course default=True.

        Verifies AC1.5 (override False).
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_tag_creation_data(
            course_tag_creation=True, activity_tag_creation=False
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_tag_creation is False
        assert ctx.course_id == data["course"].id

    @pytest.mark.asyncio
    async def test_activity_overrides_course_false_with_true(self) -> None:
        """Activity allow_tag_creation=True overrides course default=False.

        Verifies AC1.5 (override True).
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_tag_creation_data(
            course_tag_creation=False, activity_tag_creation=True
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.allow_tag_creation is True
        assert ctx.course_id == data["course"].id
