"""Tests for Tag and TagGroup CRUD operations, lock enforcement, and permission checks.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify tag/group creation, update, deletion, lock enforcement,
permission resolution, reorder, import-from-activity, and CRDT cleanup.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Activity, Course

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_week_activity(
    *,
    default_allow_tag_creation: bool = True,
    allow_tag_creation: bool | None = None,
) -> tuple[Course, Activity]:
    """Create a Course, Week, and Activity for tag tests.

    Returns the Course and Activity. The Activity's template workspace
    is automatically created by create_activity() and back-linked.

    Args:
        default_allow_tag_creation: Course-level default.
        allow_tag_creation: Activity-level override (None=inherit).
    """
    from promptgrimoire.db.activities import create_activity, update_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="TagTest", semester="2026-S1")

    # Set default_allow_tag_creation directly since create_course doesn't accept it
    if not default_allow_tag_creation:
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_allow_tag_creation = default_allow_tag_creation
            session.add(c)
            await session.flush()
            await session.refresh(c)
            course = c

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(
        week_id=week.id,
        title="Tag Activity",
    )

    # Set allow_tag_creation via update if specified
    if allow_tag_creation is not None:
        updated = await update_activity(
            activity.id, allow_tag_creation=allow_tag_creation
        )
        assert updated is not None
        activity = updated

    return course, activity


class TestCreateTag:
    """Tests for create_tag."""

    @pytest.mark.asyncio
    async def test_create_tag_with_all_fields(self) -> None:
        """Create a tag with name, color, group_id, description.

        Verifies AC2.1: all fields set, UUID generated, created_at set.
        """
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Test Group")
        tag = await create_tag(
            ws_id,
            name="Jurisdiction",
            color="#1f77b4",
            group_id=group.id,
            description="Legal jurisdiction tags",
            locked=True,
            order_index=5,
        )

        assert isinstance(tag.id, UUID)
        assert tag.workspace_id == ws_id
        assert tag.name == "Jurisdiction"
        assert tag.color == "#1f77b4"
        assert tag.group_id == group.id
        assert tag.description == "Legal jurisdiction tags"
        assert tag.locked is True
        assert tag.order_index == 5
        assert tag.created_at is not None

    @pytest.mark.asyncio
    async def test_create_tag_with_only_required_fields(self) -> None:
        """Create a tag with only name and color.

        Verifies AC2.1: group_id is None, description is None,
        locked is False, order_index is 0.
        """
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Simple", color="#ff0000")

        assert isinstance(tag.id, UUID)
        assert tag.workspace_id == ws_id
        assert tag.name == "Simple"
        assert tag.color == "#ff0000"
        assert tag.group_id is None
        assert tag.description is None
        assert tag.locked is False
        assert tag.order_index == 0


class TestUpdateTag:
    """Tests for update_tag."""

    @pytest.mark.asyncio
    async def test_update_tag_fields(self) -> None:
        """Update tag name, color, description, group_id.

        Verifies AC2.2.
        """
        from promptgrimoire.db.tags import create_tag, create_tag_group, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Group A")
        tag = await create_tag(ws_id, name="Original", color="#000000")

        updated = await update_tag(
            tag.id,
            name="Renamed",
            color="#ffffff",
            description="Updated desc",
            group_id=group.id,
        )

        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.color == "#ffffff"
        assert updated.description == "Updated desc"
        assert updated.group_id == group.id

    @pytest.mark.asyncio
    async def test_update_with_ellipsis_leaves_unchanged(self) -> None:
        """Update with Ellipsis (not provided) leaves field unchanged.

        Verifies AC2.2.
        """
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(
            ws_id,
            name="Keep",
            color="#123456",
            description="Original desc",
        )

        # Update only locked, leave everything else as Ellipsis
        updated = await update_tag(tag.id, locked=True)

        assert updated is not None
        assert updated.name == "Keep"
        assert updated.color == "#123456"
        assert updated.description == "Original desc"
        assert updated.locked is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self) -> None:
        """Updating a non-existent tag returns None."""
        from promptgrimoire.db.tags import update_tag

        result = await update_tag(uuid4(), name="Nope")
        assert result is None


class TestCreateTagGroup:
    """Tests for create_tag_group."""

    @pytest.mark.asyncio
    async def test_create_tag_group_with_fields(self) -> None:
        """Create a TagGroup with name and order_index.

        Verifies AC2.4.
        """
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Legal Issues", order_index=3)

        assert isinstance(group.id, UUID)
        assert group.workspace_id == ws_id
        assert group.name == "Legal Issues"
        assert group.order_index == 3


class TestUpdateTagGroup:
    """Tests for update_tag_group."""

    @pytest.mark.asyncio
    async def test_update_tag_group_name_and_order(self) -> None:
        """Update TagGroup name and order_index.

        Verifies AC2.4.
        """
        from promptgrimoire.db.tags import create_tag_group, update_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Original", order_index=0)

        updated = await update_tag_group(group.id, name="Renamed", order_index=5)

        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.order_index == 5

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self) -> None:
        """Updating a non-existent tag group returns None."""
        from promptgrimoire.db.tags import update_tag_group

        result = await update_tag_group(uuid4(), name="Nope")
        assert result is None


class TestDeleteTagGroup:
    """Tests for delete_tag_group."""

    @pytest.mark.asyncio
    async def test_delete_group_ungroups_tags(self) -> None:
        """Delete a TagGroup; its tags remain with group_id=None.

        Verifies AC2.5.
        """
        from promptgrimoire.db.tags import (
            create_tag,
            create_tag_group,
            delete_tag_group,
            get_tag,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="To Delete")
        tag = await create_tag(
            ws_id, name="Grouped", color="#aabbcc", group_id=group.id
        )

        deleted = await delete_tag_group(group.id)
        assert deleted is True

        # Tag still exists with group_id=None
        refetched = await get_tag(tag.id)
        assert refetched is not None
        assert refetched.group_id is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self) -> None:
        """Deleting a non-existent tag group returns False."""
        from promptgrimoire.db.tags import delete_tag_group

        result = await delete_tag_group(uuid4())
        assert result is False


class TestLockEnforcement:
    """Tests for tag lock enforcement."""

    @pytest.mark.asyncio
    async def test_update_locked_tag_rejects_field_changes(self) -> None:
        """Update on a locked tag raises ValueError for non-lock fields.

        Verifies AC2.8.
        """
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Locked", color="#000", locked=True)

        with pytest.raises(ValueError, match="Tag is locked"):
            await update_tag(tag.id, name="New Name")

    @pytest.mark.asyncio
    async def test_delete_locked_tag_raises(self) -> None:
        """Deleting a locked tag raises ValueError.

        Verifies AC2.8.
        """
        from promptgrimoire.db.tags import create_tag, delete_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Locked", color="#000", locked=True)

        with pytest.raises(ValueError, match="Tag is locked"):
            await delete_tag(tag.id)

    @pytest.mark.asyncio
    async def test_lock_toggle_always_permitted(self) -> None:
        """Toggling locked field on a locked tag succeeds.

        Verifies AC2.8: lock toggle is always permitted.
        """
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="ToUnlock", color="#000", locked=True)

        updated = await update_tag(tag.id, locked=False)
        assert updated is not None
        assert updated.locked is False

    @pytest.mark.asyncio
    async def test_unlocked_tag_allows_update_and_delete(self) -> None:
        """Unlocked tags permit update and delete.

        Verifies AC2.8: unlocked tags are freely modifiable.
        """
        from promptgrimoire.db.tags import create_tag, delete_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Unlocked", color="#000", locked=False)

        updated = await update_tag(tag.id, name="Renamed")
        assert updated is not None
        assert updated.name == "Renamed"

        deleted = await delete_tag(tag.id)
        assert deleted is True


class TestPermissionEnforcement:
    """Tests for allow_tag_creation permission enforcement."""

    @pytest.mark.asyncio
    async def test_create_tag_denied_when_tag_creation_false(self) -> None:
        """create_tag raises PermissionError when allow_tag_creation resolves False.

        Verifies AC2.9.
        """
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _, activity = await _make_course_week_activity(
            default_allow_tag_creation=False,
            allow_tag_creation=None,  # inherits False from course
        )

        # Create a student workspace placed in the activity
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        with pytest.raises(PermissionError, match="Tag creation not allowed"):
            await create_tag(ws.id, name="Should Fail", color="#000")

    @pytest.mark.asyncio
    async def test_create_tag_allowed_when_tag_creation_true(self) -> None:
        """create_tag succeeds when allow_tag_creation resolves True.

        Verifies AC2.9.
        """
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _, activity = await _make_course_week_activity(
            default_allow_tag_creation=True,
            allow_tag_creation=None,  # inherits True from course
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        tag = await create_tag(ws.id, name="Allowed", color="#123")
        assert tag.name == "Allowed"

    @pytest.mark.asyncio
    async def test_create_tag_group_denied_when_tag_creation_false(self) -> None:
        """create_tag_group raises PermissionError when denied.

        Verifies AC2.9.
        """
        from promptgrimoire.db.tags import create_tag_group
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _, activity = await _make_course_week_activity(
            default_allow_tag_creation=False,
            allow_tag_creation=None,  # inherits False from course
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        with pytest.raises(PermissionError, match="Tag creation not allowed"):
            await create_tag_group(ws.id, name="Should Fail")
