"""Tests for tag schema constraints and PlacementContext resolution.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify:
- AC1.5: tri-state allow_tag_creation inheritance
- AC1.6: workspace delete cascades to TagGroup and Tag rows
- AC1.7: tag group delete sets group_id=NULL on Tags (not delete)
- AC6.1: tag_group.color CHECK constraint rejects invalid hex
- AC6.2: tag_group.color CHECK constraint allows NULL
"""

from __future__ import annotations

from typing import Any
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
) -> dict[str, Any]:
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


class TestTagCascadeOnWorkspaceDelete:
    """Tests for CASCADE delete from Workspace to TagGroup and Tag.

    Verifies AC1.6: deleting a Workspace removes its TagGroup and Tag rows.
    """

    @pytest.mark.asyncio
    async def test_workspace_delete_cascades_to_tags(self) -> None:
        """Deleting a workspace CASCADE-deletes its TagGroup and Tag rows.

        Verifies AC1.6.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, TagGroup, Workspace

        # Create a workspace with a tag group and tag
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()
            ws_id = ws.id

            group = TagGroup(
                workspace_id=ws_id,
                name="Test Group",
                order_index=0,
            )
            session.add(group)
            await session.flush()
            group_id = group.id

            tag = Tag(
                workspace_id=ws_id,
                group_id=group_id,
                name="Test Tag",
                color="#1f77b4",
                order_index=0,
            )
            session.add(tag)
            await session.flush()
            tag_id = tag.id

        # Verify they exist
        async with get_session() as session:
            assert await session.get(TagGroup, group_id) is not None
            assert await session.get(Tag, tag_id) is not None

        # Delete the workspace
        async with get_session() as session:
            ws = await session.get(Workspace, ws_id)
            assert ws is not None
            await session.delete(ws)

        # Verify TagGroup and Tag are gone (CASCADE)
        async with get_session() as session:
            assert await session.get(TagGroup, group_id) is None
            assert await session.get(Tag, tag_id) is None


class TestTagGroupSetNullOnDelete:
    """Tests for SET NULL on TagGroup delete.

    Verifies AC1.7: deleting a TagGroup sets group_id=NULL on its Tags,
    does not delete the Tags.
    """

    @pytest.mark.asyncio
    async def test_tag_group_delete_nulls_tag_group_id(self) -> None:
        """Deleting a TagGroup sets group_id=NULL on its Tags.

        Verifies AC1.7.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, TagGroup, Workspace

        # Create workspace, tag group, and tag
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()
            ws_id = ws.id

            group = TagGroup(
                workspace_id=ws_id,
                name="Will Be Deleted",
                order_index=0,
            )
            session.add(group)
            await session.flush()
            group_id = group.id

            tag = Tag(
                workspace_id=ws_id,
                group_id=group_id,
                name="Surviving Tag",
                color="#ff7f0e",
                order_index=0,
            )
            session.add(tag)
            await session.flush()
            tag_id = tag.id

        # Verify tag has group_id set
        async with get_session() as session:
            tag_before = await session.get(Tag, tag_id)
            assert tag_before is not None
            assert tag_before.group_id == group_id

        # Delete the tag group
        async with get_session() as session:
            group = await session.get(TagGroup, group_id)
            assert group is not None
            await session.delete(group)

        # Verify: tag still exists with group_id=None
        async with get_session() as session:
            tag_after = await session.get(Tag, tag_id)
            assert tag_after is not None, (
                "Tag should NOT be deleted when TagGroup is deleted"
            )
            assert tag_after.group_id is None, (
                "Tag.group_id should be NULL after TagGroup delete"
            )
            assert tag_after.workspace_id == ws_id, (
                "Tag should still belong to its workspace"
            )


class TestTagGroupColorConstraint:
    """Tests for ck_tag_group_color_hex CHECK constraint.

    Verifies AC6.1 (invalid hex rejected) and AC6.2 (NULL allowed).
    """

    @pytest.mark.asyncio
    async def test_invalid_hex_rejected(self) -> None:
        """Non-hex color string is rejected by CHECK constraint.

        Verifies AC6.1.
        """
        from sqlalchemy.exc import IntegrityError

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import TagGroup, Workspace

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            group = TagGroup(
                workspace_id=ws.id,
                name="Bad Color",
                color="red",
                order_index=0,
            )
            session.add(group)
            with pytest.raises(IntegrityError):
                await session.flush()
            # Rollback so get_session() context manager
            # can exit cleanly after the failed flush.
            await session.rollback()

    @pytest.mark.asyncio
    async def test_null_color_allowed(self) -> None:
        """NULL color is accepted by CHECK constraint.

        Verifies AC6.2.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import TagGroup, Workspace

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            group = TagGroup(
                workspace_id=ws.id,
                name="No Color",
                color=None,
                order_index=0,
            )
            session.add(group)
            await session.flush()
            await session.refresh(group)

            assert group.color is None
            assert group.id is not None

    @pytest.mark.asyncio
    async def test_valid_hex_accepted(self) -> None:
        """Valid 6-digit hex color is accepted by CHECK constraint."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import TagGroup, Workspace

        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            group = TagGroup(
                workspace_id=ws.id,
                name="Valid Color",
                color="#FF0000",
                order_index=0,
            )
            session.add(group)
            await session.flush()
            await session.refresh(group)

            assert group.color == "#FF0000"
            assert group.id is not None
