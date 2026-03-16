"""Tests for Tag and TagGroup CRUD operations, lock enforcement, and permission checks.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify tag/group creation, update, deletion, lock enforcement,
permission resolution, reorder, import-from-activity, and CRDT cleanup.
"""

from __future__ import annotations

import asyncio
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
        )

        assert isinstance(tag.id, UUID)
        assert tag.workspace_id == ws_id
        assert tag.name == "Jurisdiction"
        assert tag.color == "#1f77b4"
        assert tag.group_id == group.id
        assert tag.description == "Legal jurisdiction tags"
        assert tag.locked is True
        assert tag.order_index == 0  # first tag gets index 0 from atomic counter
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
        assert tag.order_index == 0  # first tag gets index 0 from atomic counter


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
        """Create a TagGroup with name; order_index assigned atomically.

        Verifies AC2.4.
        """
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Legal Issues")

        assert isinstance(group.id, UUID)
        assert group.workspace_id == ws_id
        assert group.name == "Legal Issues"
        assert group.order_index == 0  # first group gets index 0


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

        group = await create_tag_group(ws_id, name="Original")

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

    @pytest.mark.asyncio
    async def test_update_color_to_none_clears(self) -> None:
        """update_tag_group(color=None) explicitly clears the group colour.

        Verifies AC6.7.
        """
        from promptgrimoire.db.tags import (
            create_tag_group,
            get_tag_group,
            update_tag_group,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Coloured")
        # Set a colour first
        await update_tag_group(group.id, color="#FF0000")

        # Now explicitly clear it
        updated = await update_tag_group(group.id, color=None)
        assert updated is not None

        # Reload from DB to confirm persistence
        reloaded = await get_tag_group(group.id)
        assert reloaded is not None
        assert reloaded.color is None

    @pytest.mark.asyncio
    async def test_update_without_color_preserves(self) -> None:
        """update_tag_group without color parameter preserves existing colour.

        Verifies AC6.8.
        """
        from promptgrimoire.db.tags import (
            create_tag_group,
            get_tag_group,
            update_tag_group,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="KeepColor")
        # Set a colour
        await update_tag_group(group.id, color="#FF0000")

        # Update name only — color should not be passed at all
        updated = await update_tag_group(group.id, name="Renamed")
        assert updated is not None

        # Reload from DB to confirm colour preserved
        reloaded = await get_tag_group(group.id)
        assert reloaded is not None
        assert reloaded.color == "#FF0000"


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


class TestDeleteTag:
    """Tests for delete_tag."""

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self) -> None:
        """Deleting a non-existent tag returns False.

        Verifies AC6.5.
        """
        from promptgrimoire.db.tags import delete_tag

        result = await delete_tag(uuid4())
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

        tag = await create_tag(ws_id, name="Locked", color="#000000", locked=True)

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

        tag = await create_tag(ws_id, name="Locked", color="#000000", locked=True)

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

        tag = await create_tag(ws_id, name="ToUnlock", color="#000000", locked=True)

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

        tag = await create_tag(ws_id, name="Unlocked", color="#000000", locked=False)

        updated = await update_tag(tag.id, name="Renamed")
        assert updated is not None
        assert updated.name == "Renamed"

        deleted = await delete_tag(tag.id)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_update_locked_tag_with_bypass_lock(self) -> None:
        """update_tag with bypass_lock=True succeeds on a locked tag.

        Verifies AC6.3: instructor bypass allows editing locked tags.
        """
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Locked", color="#000000", locked=True)

        updated = await update_tag(tag.id, name="New Name", bypass_lock=True)
        assert updated is not None
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_delete_locked_tag_with_bypass_lock(self) -> None:
        """delete_tag with bypass_lock=True succeeds on a locked tag.

        Verifies AC6.4: instructor bypass allows deleting locked tags.
        """
        from promptgrimoire.db.tags import create_tag, delete_tag, get_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Locked", color="#000000", locked=True)

        deleted = await delete_tag(tag.id, bypass_lock=True)
        assert deleted is True

        # Verify tag no longer exists
        refetched = await get_tag(tag.id)
        assert refetched is None


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
            await create_tag(ws.id, name="Should Fail", color="#000000")

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

        tag = await create_tag(ws.id, name="Allowed", color="#112233")
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


class TestReorderTags:
    """Tests for reorder_tags."""

    @pytest.mark.asyncio
    async def test_reorder_tags_updates_order_index(self) -> None:
        """Reorder tags sets order_index to list position.

        Verifies AC2.6.
        """
        from promptgrimoire.db.tags import (
            create_tag,
            get_tag,
            reorder_tags,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        t1 = await create_tag(ws_id, name="Tag1", color="#aaaaaa")
        t2 = await create_tag(ws_id, name="Tag2", color="#bbbbbb")
        t3 = await create_tag(ws_id, name="Tag3", color="#cccccc")

        # Reorder: Tag3, Tag1, Tag2
        await reorder_tags([t3.id, t1.id, t2.id])

        r1 = await get_tag(t1.id)
        r2 = await get_tag(t2.id)
        r3 = await get_tag(t3.id)
        assert r3 is not None and r3.order_index == 0
        assert r1 is not None and r1.order_index == 1
        assert r2 is not None and r2.order_index == 2

    @pytest.mark.asyncio
    async def test_reorder_with_unknown_tag_raises_value_error(self) -> None:
        """reorder_tags raises ValueError when a tag UUID is not found.

        Verifies AC6.9.
        """
        from promptgrimoire.db.tags import create_tag, reorder_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        t1 = await create_tag(ws_id, name="Tag1", color="#aaaaaa")

        with pytest.raises(ValueError, match=r"Tag.*not found"):
            await reorder_tags([t1.id, uuid4()])


class TestReorderTagGroups:
    """Tests for reorder_tag_groups."""

    @pytest.mark.asyncio
    async def test_reorder_groups_updates_order_index(self) -> None:
        """Reorder groups sets order_index to list position.

        Verifies AC2.7.
        """
        from promptgrimoire.db.tags import (
            create_tag_group,
            get_tag_group,
            reorder_tag_groups,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        g1 = await create_tag_group(ws_id, name="G1")
        g2 = await create_tag_group(ws_id, name="G2")
        g3 = await create_tag_group(ws_id, name="G3")

        # Reverse order
        await reorder_tag_groups([g3.id, g2.id, g1.id])

        r1 = await get_tag_group(g1.id)
        r2 = await get_tag_group(g2.id)
        r3 = await get_tag_group(g3.id)
        assert r3 is not None and r3.order_index == 0
        assert r2 is not None and r2.order_index == 1
        assert r1 is not None and r1.order_index == 2

    @pytest.mark.asyncio
    async def test_reorder_with_unknown_group_raises_value_error(self) -> None:
        """reorder_tag_groups raises ValueError when a group UUID is not found.

        Verifies AC6.10.
        """
        from promptgrimoire.db.tags import create_tag_group, reorder_tag_groups

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        g1 = await create_tag_group(ws_id, name="G1")

        with pytest.raises(ValueError, match=r"TagGroup.*not found"):
            await reorder_tag_groups([g1.id, uuid4()])


class TestDeleteTagCrdtCleanup:
    """Tests for CRDT highlight cleanup on tag deletion."""

    @pytest.mark.asyncio
    async def test_delete_tag_removes_crdt_highlights(self) -> None:
        """Deleting a tag removes its CRDT highlights.

        Verifies AC2.3.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        _, activity = await _make_course_week_activity()
        ws = await create_workspace()

        # Place workspace in activity so tag creation is permitted
        from promptgrimoire.db.workspaces import place_workspace_in_activity

        await place_workspace_in_activity(ws.id, activity.id)

        tag = await create_tag(ws.id, name="ToDelete", color="#ff0000")

        # Build CRDT state with 3 highlights for this tag
        doc = AnnotationDocument("test")
        tag_str = str(tag.id)
        hl_ids = []
        for i in range(3):
            hl_id = doc.add_highlight(
                start_char=i * 10,
                end_char=(i + 1) * 10,
                tag=tag_str,
                text=f"text{i}",
                author="test",
            )
            hl_ids.append(hl_id)

        # Save CRDT state to workspace
        await save_workspace_crdt_state(ws.id, doc.get_full_state())

        # Delete tag
        deleted = await delete_tag(tag.id)
        assert deleted is True

        # Verify CRDT state is cleaned up
        ws_after = await get_workspace(ws.id)
        assert ws_after is not None
        assert ws_after.crdt_state is not None

        doc2 = AnnotationDocument("verify")
        doc2.apply_update(ws_after.crdt_state)
        assert doc2.get_all_highlights() == []

    @pytest.mark.asyncio
    async def test_delete_tag_preserves_other_highlights(self) -> None:
        """Deleting tag A removes only its highlights; tag B remains.

        Verifies AC2.3.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            save_workspace_crdt_state,
        )

        _, activity = await _make_course_week_activity()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        tag_a = await create_tag(ws.id, name="TagA", color="#aa0000")
        tag_b = await create_tag(ws.id, name="TagB", color="#00bb00")

        # Build CRDT state with highlights for both tags
        doc = AnnotationDocument("test")
        a_str = str(tag_a.id)
        b_str = str(tag_b.id)

        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag=a_str,
            text="a1",
            author="test",
        )
        doc.add_highlight(
            start_char=20,
            end_char=30,
            tag=b_str,
            text="b1",
            author="test",
        )
        await save_workspace_crdt_state(ws.id, doc.get_full_state())

        # Delete tag A only
        await delete_tag(tag_a.id)

        # Verify tag B highlights remain
        ws_after = await get_workspace(ws.id)
        assert ws_after is not None
        assert ws_after.crdt_state is not None

        doc2 = AnnotationDocument("verify")
        doc2.apply_update(ws_after.crdt_state)

        remaining = doc2.get_all_highlights()
        assert len(remaining) == 1
        assert remaining[0]["tag"] == b_str

    @pytest.mark.asyncio
    async def test_delete_tag_no_crdt_tag_entry(self) -> None:
        """Cleanup succeeds when tag has highlights but no tags Map entry.

        Verifies AC2.3 edge case: highlights are still removed even
        when the tag has no entry in the CRDT tags Map.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            save_workspace_crdt_state,
        )

        _, activity = await _make_course_week_activity()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        tag = await create_tag(ws.id, name="NoOrder", color="#ff00ff")

        # Build CRDT with highlights but no tags Map entry
        doc = AnnotationDocument("test")
        tag_str = str(tag.id)
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag=tag_str,
            text="hi",
            author="test",
        )

        await save_workspace_crdt_state(ws.id, doc.get_full_state())

        # Delete tag -- should not error
        deleted = await delete_tag(tag.id)
        assert deleted is True

        # Verify highlights removed
        ws_after = await get_workspace(ws.id)
        assert ws_after is not None
        assert ws_after.crdt_state is not None

        doc2 = AnnotationDocument("verify")
        doc2.apply_update(ws_after.crdt_state)
        assert doc2.get_all_highlights() == []


class TestAtomicTagCounter:
    """Tests for atomic counter-based order_index assignment.

    Verifies AC5.2, AC5.3, AC5.5.
    """

    @pytest.mark.asyncio
    async def test_create_tag_assigns_sequential_order_index(self) -> None:
        """Two sequential create_tag calls produce distinct order_index values.

        Verifies AC5.2.
        """
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag_a = await create_tag(ws_id, name="TagA", color="#aa0000")
        tag_b = await create_tag(ws_id, name="TagB", color="#bb0000")

        assert tag_a.order_index != tag_b.order_index
        assert {tag_a.order_index, tag_b.order_index} == {0, 1}

    @pytest.mark.asyncio
    async def test_create_tag_group_assigns_sequential_order_index(self) -> None:
        """Two sequential create_tag_group calls produce distinct order_index values.

        Verifies AC5.3.
        """
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group_a = await create_tag_group(ws_id, name="GroupA")
        group_b = await create_tag_group(ws_id, name="GroupB")

        assert group_a.order_index != group_b.order_index
        assert {group_a.order_index, group_b.order_index} == {0, 1}

    @pytest.mark.asyncio
    async def test_counter_correct_after_reorder_then_create(self) -> None:
        """After reorder, new tag gets order_index == count.

        Verifies AC5.5.
        """
        from promptgrimoire.db.tags import create_tag, reorder_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        t1 = await create_tag(ws_id, name="T1", color="#110000")
        t2 = await create_tag(ws_id, name="T2", color="#220000")
        t3 = await create_tag(ws_id, name="T3", color="#330000")

        # Reorder to [t3, t1, t2]
        await reorder_tags([t3.id, t1.id, t2.id])

        # Create a 4th tag -- should get order_index == 3
        t4 = await create_tag(ws_id, name="T4", color="#440000")
        assert t4.order_index == 3


class TestConcurrentTagCreation:
    """Tests for concurrent tag/group creation via asyncio.gather.

    Verifies AC5.4: two concurrent create_tag() calls produce distinct
    order_index values (no duplicate indices from race conditions).
    Also re-verifies AC5.5 with a reorder-then-create sequence.
    """

    @pytest.mark.asyncio
    async def test_concurrent_create_tag_distinct_order(self) -> None:
        """Two concurrent create_tag calls produce distinct order_index values.

        Verifies AC5.4: under the atomic counter pattern, the UPDATE
        row-level lock serialises concurrent inserts and they get
        distinct indices.
        """
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag_a, tag_b = await asyncio.gather(
            create_tag(ws_id, name="ConcA", color="#aa0000"),
            create_tag(ws_id, name="ConcB", color="#bb0000"),
        )

        assert tag_a.order_index != tag_b.order_index
        assert {tag_a.order_index, tag_b.order_index} == {0, 1}

    @pytest.mark.asyncio
    async def test_concurrent_create_tag_group_distinct_order(self) -> None:
        """Two concurrent create_tag_group calls produce distinct order_index values.

        Verifies AC5.4 for tag groups.
        """
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group_a, group_b = await asyncio.gather(
            create_tag_group(ws_id, name="ConcGroupA"),
            create_tag_group(ws_id, name="ConcGroupB"),
        )

        assert group_a.order_index != group_b.order_index
        assert {group_a.order_index, group_b.order_index} == {0, 1}


# ── Phase 2: DB-CRDT Dual Write ──────────────────────────────────────


class TestCreateTagCrdt:
    """Tests for create_tag with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.1.
    """

    @pytest.mark.asyncio
    async def test_create_tag_writes_to_both_db_and_crdt(self) -> None:
        """create_tag with crdt_doc writes tag metadata to both DB and CRDT.

        Verifies AC1.1: matching fields in both stores.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-create")
        tag = await create_tag(
            ws_id,
            name="Jurisdiction",
            color="#1f77b4",
            description="Legal jurisdiction",
            crdt_doc=doc,
        )

        # Verify DB row
        from promptgrimoire.db.tags import get_tag

        db_tag = await get_tag(tag.id)
        assert db_tag is not None
        assert db_tag.name == "Jurisdiction"
        assert db_tag.color == "#1f77b4"

        # Verify CRDT entry
        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["name"] == "Jurisdiction"
        assert crdt_tag["colour"] == "#1f77b4"
        assert crdt_tag["order_index"] == tag.order_index
        assert crdt_tag["description"] == "Legal jurisdiction"
        assert crdt_tag["highlights"] == []

    @pytest.mark.asyncio
    async def test_create_tag_without_crdt_doc_no_crash(self) -> None:
        """create_tag without crdt_doc creates DB row without error.

        Edge case: existing callers pass no crdt_doc.
        """
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="NoCrdt", color="#000000")
        assert tag.name == "NoCrdt"

    @pytest.mark.asyncio
    async def test_create_tag_with_group_writes_group_id_to_crdt(self) -> None:
        """create_tag with group_id includes group_id in CRDT entry.

        Verifies AC1.1: group_id field synced.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-group")
        group = await create_tag_group(ws_id, name="Legal")
        tag = await create_tag(
            ws_id,
            name="WithGroup",
            color="#aabbcc",
            group_id=group.id,
            crdt_doc=doc,
        )

        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["group_id"] == str(group.id)


class TestCreateTagGroupCrdt:
    """Tests for create_tag_group with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.4.
    """

    @pytest.mark.asyncio
    async def test_create_tag_group_writes_to_both_db_and_crdt(self) -> None:
        """create_tag_group with crdt_doc writes to both DB and CRDT.

        Verifies AC1.4.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-create-group")
        group = await create_tag_group(ws_id, name="Evidence", crdt_doc=doc)

        # Verify DB row
        from promptgrimoire.db.tags import get_tag_group

        db_group = await get_tag_group(group.id)
        assert db_group is not None
        assert db_group.name == "Evidence"

        # Verify CRDT entry
        crdt_group = doc.get_tag_group(group.id)
        assert crdt_group is not None
        assert crdt_group["name"] == "Evidence"
        assert crdt_group["order_index"] == group.order_index

    @pytest.mark.asyncio
    async def test_create_tag_group_without_crdt_doc_no_crash(self) -> None:
        """create_tag_group without crdt_doc creates DB row without error."""
        from promptgrimoire.db.tags import create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="NoCrdt")
        assert group.name == "NoCrdt"


class TestUpdateTagCrdt:
    """Tests for update_tag with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.2.
    """

    @pytest.mark.asyncio
    async def test_update_tag_writes_to_crdt(self) -> None:
        """update_tag with crdt_doc updates CRDT entry with new name.

        Verifies AC1.2.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-update")
        tag = await create_tag(ws_id, name="Original", color="#000000", crdt_doc=doc)

        updated = await update_tag(tag.id, name="Renamed", crdt_doc=doc)
        assert updated is not None
        assert updated.name == "Renamed"

        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_update_tag_preserves_highlights_in_crdt(self) -> None:
        """update_tag preserves existing highlights list in CRDT.

        Verifies AC1.2: metadata update does not clobber highlights.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-preserve")
        tag = await create_tag(ws_id, name="HasHL", color="#111111", crdt_doc=doc)

        # Manually add highlights to CRDT tag
        doc.set_tag(
            tag_id=tag.id,
            name="HasHL",
            colour="#111111",
            order_index=tag.order_index,
            highlights=["hl-1", "hl-2"],
        )

        updated = await update_tag(tag.id, color="#222222", crdt_doc=doc)
        assert updated is not None

        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["colour"] == "#222222"
        assert crdt_tag["highlights"] == ["hl-1", "hl-2"]

    @pytest.mark.asyncio
    async def test_update_tag_without_crdt_doc_no_crash(self) -> None:
        """update_tag without crdt_doc updates DB without error."""
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="NoCrdt", color="#000000")
        updated = await update_tag(tag.id, name="Renamed")
        assert updated is not None
        assert updated.name == "Renamed"

    @pytest.mark.asyncio
    async def test_update_tag_creates_crdt_entry_if_missing(self) -> None:
        """update_tag with crdt_doc creates CRDT entry if tag was created without it.

        Edge case: tag created without crdt_doc, then updated with one.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Create without crdt_doc
        tag = await create_tag(ws_id, name="NoDoc", color="#aaa000")

        # Update with crdt_doc
        doc = AnnotationDocument("test-late-crdt")
        updated = await update_tag(tag.id, name="NowHasDoc", crdt_doc=doc)
        assert updated is not None

        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["name"] == "NowHasDoc"


class TestUpdateTagGroupCrdt:
    """Tests for update_tag_group with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.4.
    """

    @pytest.mark.asyncio
    async def test_update_tag_group_writes_to_crdt(self) -> None:
        """update_tag_group with crdt_doc updates CRDT entry.

        Verifies AC1.4.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag_group, update_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-update-group")
        group = await create_tag_group(ws_id, name="Original", crdt_doc=doc)

        updated = await update_tag_group(group.id, name="Renamed", crdt_doc=doc)
        assert updated is not None

        crdt_group = doc.get_tag_group(group.id)
        assert crdt_group is not None
        assert crdt_group["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_update_tag_group_without_crdt_doc_no_crash(self) -> None:
        """update_tag_group without crdt_doc updates DB without error."""
        from promptgrimoire.db.tags import create_tag_group, update_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="NoCrdt")
        updated = await update_tag_group(group.id, name="Renamed")
        assert updated is not None
        assert updated.name == "Renamed"


class TestDeleteTagCrdt:
    """Tests for delete_tag with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.3.
    """

    @pytest.mark.asyncio
    async def test_delete_tag_removes_from_crdt(self) -> None:
        """delete_tag with crdt_doc removes tag from CRDT tags Map.

        Verifies AC1.3.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-delete")
        tag = await create_tag(ws_id, name="ToDelete", color="#ff0000", crdt_doc=doc)

        # Verify tag exists in CRDT before delete
        assert doc.get_tag(tag.id) is not None

        deleted = await delete_tag(tag.id, crdt_doc=doc)
        assert deleted is True

        # Verify tag removed from CRDT
        assert doc.get_tag(tag.id) is None

    @pytest.mark.asyncio
    async def test_delete_tag_removes_highlights_from_crdt(self) -> None:
        """delete_tag with crdt_doc removes highlights and tag entry.

        Verifies AC1.3: highlights and tags Map entry cleaned up.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-delete-hl")
        tag = await create_tag(ws_id, name="WithHL", color="#ff0000", crdt_doc=doc)

        # Add highlights to CRDT
        tag_str = str(tag.id)
        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag=tag_str,
            text="test",
            author="test",
        )
        deleted = await delete_tag(tag.id, crdt_doc=doc)
        assert deleted is True

        # Verify highlights and tag entry removed
        assert doc.get_all_highlights() == []
        assert doc.get_tag(tag.id) is None

    @pytest.mark.asyncio
    async def test_delete_tag_without_crdt_doc_uses_db_cleanup(self) -> None:
        """delete_tag without crdt_doc still does DB-based CRDT cleanup.

        Regression test for existing TestDeleteTagCrdtCleanup behaviour.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            save_workspace_crdt_state,
        )

        _, activity = await _make_course_week_activity()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        tag = await create_tag(ws.id, name="DbCleanup", color="#ff0000")

        # Build CRDT state with highlights
        doc = AnnotationDocument("test")
        tag_str = str(tag.id)
        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag=tag_str,
            text="test",
            author="test",
        )
        await save_workspace_crdt_state(ws.id, doc.get_full_state())

        # Delete without crdt_doc — should use DB-based cleanup
        deleted = await delete_tag(tag.id)
        assert deleted is True

        # Verify DB-saved CRDT state is cleaned up
        ws_after = await get_workspace(ws.id)
        assert ws_after is not None
        assert ws_after.crdt_state is not None

        doc2 = AnnotationDocument("verify")
        doc2.apply_update(ws_after.crdt_state)
        assert doc2.get_all_highlights() == []

    @pytest.mark.asyncio
    async def test_delete_tag_no_crdt_entry_no_crash(self) -> None:
        """delete_tag with crdt_doc when tag has no CRDT entry does not crash.

        Edge case: tag created without crdt_doc, deleted with one.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Create without crdt_doc
        tag = await create_tag(ws_id, name="NoEntry", color="#000000")

        # Delete with crdt_doc
        doc = AnnotationDocument("test-no-entry")
        deleted = await delete_tag(tag.id, crdt_doc=doc)
        assert deleted is True


class TestDeleteTagGroupCrdt:
    """Tests for delete_tag_group with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.4.
    """

    @pytest.mark.asyncio
    async def test_delete_tag_group_removes_from_crdt(self) -> None:
        """delete_tag_group with crdt_doc removes group from CRDT.

        Verifies AC1.4.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag_group, delete_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-delete-group")
        group = await create_tag_group(ws_id, name="ToDelete", crdt_doc=doc)

        # Verify exists in CRDT
        assert doc.get_tag_group(group.id) is not None

        deleted = await delete_tag_group(group.id, crdt_doc=doc)
        assert deleted is True

        # Verify removed from CRDT
        assert doc.get_tag_group(group.id) is None

    @pytest.mark.asyncio
    async def test_delete_tag_group_without_crdt_doc_no_crash(self) -> None:
        """delete_tag_group without crdt_doc deletes DB row without error."""
        from promptgrimoire.db.tags import create_tag_group, delete_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="NoCrdt")
        deleted = await delete_tag_group(group.id)
        assert deleted is True


class TestReorderTagsCrdt:
    """Tests for reorder_tags with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.1 (order_index sync).
    """

    @pytest.mark.asyncio
    async def test_reorder_tags_updates_crdt_order_index(self) -> None:
        """reorder_tags with crdt_doc updates order_index in CRDT entries.

        Verifies AC1.1: order_index synced to CRDT.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, reorder_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-reorder-tags")
        t1 = await create_tag(ws_id, name="Tag1", color="#aa0000", crdt_doc=doc)
        t2 = await create_tag(ws_id, name="Tag2", color="#bb0000", crdt_doc=doc)
        t3 = await create_tag(ws_id, name="Tag3", color="#cc0000", crdt_doc=doc)

        # Reorder: Tag3, Tag1, Tag2
        await reorder_tags([t3.id, t1.id, t2.id], crdt_doc=doc)

        crdt_t1 = doc.get_tag(t1.id)
        crdt_t2 = doc.get_tag(t2.id)
        crdt_t3 = doc.get_tag(t3.id)

        assert crdt_t3 is not None and crdt_t3["order_index"] == 0
        assert crdt_t1 is not None and crdt_t1["order_index"] == 1
        assert crdt_t2 is not None and crdt_t2["order_index"] == 2

        # Verify names preserved
        assert crdt_t1["name"] == "Tag1"
        assert crdt_t2["name"] == "Tag2"
        assert crdt_t3["name"] == "Tag3"

    @pytest.mark.asyncio
    async def test_reorder_tags_without_crdt_doc_no_crash(self) -> None:
        """reorder_tags without crdt_doc updates DB only, no crash.

        Edge case: existing callers pass no crdt_doc.
        """
        from promptgrimoire.db.tags import create_tag, get_tag, reorder_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        t1 = await create_tag(ws_id, name="Tag1", color="#aa0000")
        t2 = await create_tag(ws_id, name="Tag2", color="#bb0000")

        # Should not crash
        await reorder_tags([t2.id, t1.id])

        r1 = await get_tag(t1.id)
        r2 = await get_tag(t2.id)
        assert r2 is not None and r2.order_index == 0
        assert r1 is not None and r1.order_index == 1

    @pytest.mark.asyncio
    async def test_reorder_tags_preserves_crdt_highlights(self) -> None:
        """reorder_tags preserves existing highlights in CRDT entries.

        Verifies AC1.1: only order_index changes, highlights preserved.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, reorder_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-reorder-highlights")
        t1 = await create_tag(ws_id, name="Tag1", color="#aa0000", crdt_doc=doc)
        t2 = await create_tag(ws_id, name="Tag2", color="#bb0000", crdt_doc=doc)

        # Manually add a highlight to t1's CRDT entry
        crdt_t1 = doc.get_tag(t1.id)
        assert crdt_t1 is not None
        doc.set_tag(
            tag_id=t1.id,
            name=crdt_t1["name"],
            colour=crdt_t1["colour"],
            order_index=crdt_t1["order_index"],
            group_id=crdt_t1.get("group_id"),
            description=crdt_t1.get("description"),
            highlights=["highlight-1"],
        )

        # Reorder
        await reorder_tags([t2.id, t1.id], crdt_doc=doc)

        crdt_t1_after = doc.get_tag(t1.id)
        assert crdt_t1_after is not None
        assert crdt_t1_after["highlights"] == ["highlight-1"]


class TestReorderTagGroupsCrdt:
    """Tests for reorder_tag_groups with crdt_doc parameter.

    Verifies tag-lifecycle-235-291.AC1.4 (group order sync).
    """

    @pytest.mark.asyncio
    async def test_reorder_tag_groups_updates_crdt_order_index(self) -> None:
        """reorder_tag_groups with crdt_doc updates order_index in CRDT.

        Verifies AC1.4: group order_index synced.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag_group, reorder_tag_groups

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-reorder-groups")
        g1 = await create_tag_group(ws_id, name="G1", crdt_doc=doc)
        g2 = await create_tag_group(ws_id, name="G2", crdt_doc=doc)
        g3 = await create_tag_group(ws_id, name="G3", crdt_doc=doc)

        # Reverse order
        await reorder_tag_groups([g3.id, g2.id, g1.id], crdt_doc=doc)

        crdt_g1 = doc.get_tag_group(g1.id)
        crdt_g2 = doc.get_tag_group(g2.id)
        crdt_g3 = doc.get_tag_group(g3.id)

        assert crdt_g3 is not None and crdt_g3["order_index"] == 0
        assert crdt_g2 is not None and crdt_g2["order_index"] == 1
        assert crdt_g1 is not None and crdt_g1["order_index"] == 2

        # Verify names preserved
        assert crdt_g1["name"] == "G1"
        assert crdt_g2["name"] == "G2"
        assert crdt_g3["name"] == "G3"

    @pytest.mark.asyncio
    async def test_reorder_tag_groups_without_crdt_doc_no_crash(self) -> None:
        """reorder_tag_groups without crdt_doc updates DB only, no crash."""
        from promptgrimoire.db.tags import (
            create_tag_group,
            get_tag_group,
            reorder_tag_groups,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        g1 = await create_tag_group(ws_id, name="G1")
        g2 = await create_tag_group(ws_id, name="G2")

        await reorder_tag_groups([g2.id, g1.id])

        r1 = await get_tag_group(g1.id)
        r2 = await get_tag_group(g2.id)
        assert r2 is not None and r2.order_index == 0
        assert r1 is not None and r1.order_index == 1


class TestCrdtTagConsistency:
    """Tests for _ensure_crdt_tag_consistency on workspace load.

    Verifies AC1.5 (hydration) and AC1.6 (reconciliation).
    """

    @pytest.mark.asyncio
    async def test_consistency_hydrates_empty_crdt_from_db(self) -> None:
        """AC1.5: CRDT maps empty + DB has tags -> CRDT hydrated from DB."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Consistency Group")
        tag = await create_tag(
            ws_id,
            name="Consistency Tag",
            color="#112233",
            group_id=group.id,
            description="Test",
        )

        # Create a fresh CRDT doc with NO tag data
        doc = AnnotationDocument("test-consistency")
        assert doc.list_tags() == {}
        assert doc.list_tag_groups() == {}

        await _ensure_crdt_tag_consistency(doc, ws_id)

        # CRDT should now have the tag and group from DB
        crdt_tags = doc.list_tags()
        crdt_groups = doc.list_tag_groups()
        assert str(tag.id) in crdt_tags
        assert str(group.id) in crdt_groups
        assert crdt_tags[str(tag.id)]["name"] == "Consistency Tag"
        assert crdt_groups[str(group.id)]["name"] == "Consistency Group"

    @pytest.mark.asyncio
    async def test_consistency_reconciles_missing_tag(self) -> None:
        """AC1.6: CRDT has some tags but missing one from DB -> missing added."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag1 = await create_tag(ws_id, name="Present", color="#111111")
        tag2 = await create_tag(ws_id, name="Missing", color="#222222")

        # Pre-populate CRDT with only tag1
        doc = AnnotationDocument("test-reconcile")
        doc.set_tag(str(tag1.id), "Present", "#111111", 0)

        await _ensure_crdt_tag_consistency(doc, ws_id)

        # tag2 should now be in CRDT
        crdt_tags = doc.list_tags()
        assert str(tag2.id) in crdt_tags
        assert crdt_tags[str(tag2.id)]["name"] == "Missing"

    @pytest.mark.asyncio
    async def test_consistency_empty_db_empty_crdt_no_error(self) -> None:
        """Edge: Empty DB + empty CRDT -> no changes, no errors."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-empty")

        await _ensure_crdt_tag_consistency(doc, ws_id)

        assert doc.list_tags() == {}
        assert doc.list_tag_groups() == {}

    @pytest.mark.asyncio
    async def test_consistency_removes_crdt_tag_not_in_db(self) -> None:
        """Edge: CRDT has tag not in DB -> tag removed from CRDT."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # CRDT has a tag that doesn't exist in DB
        doc = AnnotationDocument("test-orphan")
        doc.set_tag("orphan-tag-id", "Orphan", "#ff0000", 0)

        await _ensure_crdt_tag_consistency(doc, ws_id)

        # Orphan tag should be removed
        assert doc.get_tag("orphan-tag-id") is None


class TestCrdtPrimaryRendering:
    """Tests for CRDT-primary tag rendering (Task 3).

    Verifies that workspace_tags_from_crdt() produces the same output
    as workspace_tags() after consistency check, validating the rendering
    switch from DB to CRDT.
    """

    @pytest.mark.asyncio
    async def test_crdt_primary_matches_db_query(self) -> None:
        """After consistency check, CRDT-primary matches DB query output."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.pages.annotation.tags import (
            workspace_tags,
            workspace_tags_from_crdt,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        from promptgrimoire.db.tags import (
            create_tag,
            create_tag_group,
            update_tag_group,
        )

        group = await create_tag_group(ws_id, name="Legal")
        await update_tag_group(group.id, color="#aa0000")
        await create_tag(
            ws_id,
            name="Jurisdiction",
            color="#3366cc",
            group_id=group.id,
            description="Courts",
        )
        await create_tag(ws_id, name="Ungrouped", color="#ff9900")

        # Build CRDT via consistency check (simulates workspace load)
        doc = AnnotationDocument("test-crdt-primary")
        await _ensure_crdt_tag_consistency(doc, ws_id)

        # Compare outputs
        db_result = await workspace_tags(ws_id)
        crdt_result = workspace_tags_from_crdt(doc)

        assert len(crdt_result) == len(db_result)
        for crdt_tag, db_tag in zip(crdt_result, db_result, strict=True):
            assert crdt_tag.name == db_tag.name
            assert crdt_tag.colour == db_tag.colour
            assert crdt_tag.raw_key == db_tag.raw_key
            assert crdt_tag.group_name == db_tag.group_name
            assert crdt_tag.group_colour == db_tag.group_colour
            assert crdt_tag.description == db_tag.description

    @pytest.mark.asyncio
    async def test_crdt_primary_ordering_matches_db(self) -> None:
        """CRDT-primary preserves group-then-tag ordering from DB."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.pages.annotation.tags import (
            workspace_tags,
            workspace_tags_from_crdt,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        from promptgrimoire.db.tags import create_tag, create_tag_group

        g1 = await create_tag_group(ws_id, name="Group A")
        g2 = await create_tag_group(ws_id, name="Group B")
        await create_tag(ws_id, name="A-Tag1", color="#111111", group_id=g1.id)
        await create_tag(ws_id, name="A-Tag2", color="#222222", group_id=g1.id)
        await create_tag(ws_id, name="B-Tag1", color="#333333", group_id=g2.id)
        await create_tag(ws_id, name="Ungrouped", color="#444444")

        doc = AnnotationDocument("test-crdt-ordering")
        await _ensure_crdt_tag_consistency(doc, ws_id)

        db_names = [t.name for t in await workspace_tags(ws_id)]
        crdt_names = [t.name for t in workspace_tags_from_crdt(doc)]

        assert crdt_names == db_names


class TestDualWriteColourUpdate:
    """AC4.1: Colour changes via update_tag persist in both DB and CRDT.

    Verifies tag-lifecycle-235-291.AC4.1.
    """

    @pytest.mark.asyncio
    async def test_colour_update_persists_in_db_and_crdt(self) -> None:
        """update_tag colour change writes to both DB and CRDT.

        Verifies AC4.1: create tag with crdt_doc, update colour with
        crdt_doc, verify both stores reflect the new colour.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, get_tag, update_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-colour-update")
        tag = await create_tag(ws_id, name="ColourTest", color="#1f77b4", crdt_doc=doc)

        # Update colour
        await update_tag(tag.id, color="#ff0000", crdt_doc=doc)

        # Verify DB
        db_tag = await get_tag(tag.id)
        assert db_tag is not None
        assert db_tag.color == "#ff0000"

        # Verify CRDT
        crdt_tag = doc.get_tag(tag.id)
        assert crdt_tag is not None
        assert crdt_tag["colour"] == "#ff0000"


class TestDualWriteDeleteTag:
    """AC2.5: Deleting a tag removes it from both DB and CRDT.

    Verifies tag-lifecycle-235-291.AC2.5.
    """

    @pytest.mark.asyncio
    async def test_delete_removes_from_db_and_crdt(self) -> None:
        """delete_tag with crdt_doc removes tag from both stores.

        Verifies AC2.5: after deletion, tag absent from DB and CRDT.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag, get_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        doc = AnnotationDocument("test-delete-dual")
        tag = await create_tag(ws_id, name="ToDelete", color="#ff0000", crdt_doc=doc)

        # Verify tag exists in both stores before delete
        assert doc.get_tag(tag.id) is not None
        assert await get_tag(tag.id) is not None

        # Delete
        await delete_tag(tag.id, crdt_doc=doc)

        # Verify removed from DB
        assert await get_tag(tag.id) is None

        # Verify removed from CRDT
        assert doc.get_tag(tag.id) is None


class TestDuplicateTagNameRejection:
    """AC2.7: Creating a tag with a duplicate name is rejected.

    Verifies tag-lifecycle-235-291.AC2.7.
    """

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_duplicate_name_error(
        self,
    ) -> None:
        """create_tag twice with same name raises DuplicateNameError.

        Verifies AC2.7: duplicate name within same workspace is
        rejected. Since #360, the DB layer catches IntegrityError
        and raises DuplicateNameError instead.
        """
        from promptgrimoire.db.tags import DuplicateNameError, create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        await create_tag(ws_id, name="Unique", color="#111111")

        with pytest.raises(DuplicateNameError, match="already exists"):
            await create_tag(ws_id, name="Unique", color="#222222")


class TestQuickCreateDefaultGroup:
    """AC2.6: Quick-created tags get explicit group when selected, ungrouped otherwise.

    Verifies tag-lifecycle-235-291.AC2.6.
    """

    @pytest.mark.asyncio
    async def test_create_tag_with_group_has_group_id(self) -> None:
        """create_tag with explicit group_id sets group_id on result."""
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Default Group")
        tag = await create_tag(
            ws_id, name="Grouped", color="#111111", group_id=group.id
        )

        assert tag.group_id is not None
        assert tag.group_id == group.id

    @pytest.mark.asyncio
    async def test_create_tag_without_group_is_ungrouped(self) -> None:
        """Quick-create with no group selected creates ungrouped tag.

        The quick-create dialog defaults to no group (ungrouped).
        Tags without a group appear at the end of the tag list.
        """
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(
            ws_id,
            name="Ungrouped",
            color="#222222",
            group_id=None,
        )

        assert tag.group_id is None


class TestImportTagsFromWorkspace:
    """Tests for import_tags_from_workspace.

    Verifies AC3.1-AC3.5, AC3.7, and permission enforcement.
    """

    @pytest.mark.asyncio
    async def test_import_workspace_creates_tags(self) -> None:
        """Import from accessible workspace creates tags.

        Verifies AC3.1: user can import tags from a workspace with read access.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import (
            create_tag,
            create_tag_group,
            import_tags_from_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.users import create_user

        # Source workspace with tags (standalone, not template)
        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        src_group = await create_tag_group(src_ws, name="Legal")
        await create_tag(
            src_ws,
            name="Jurisdiction",
            color="#1f77b4",
            group_id=src_group.id,
            description="Court jurisdiction",
        )
        await create_tag(src_ws, name="Facts", color="#ff7f0e")

        # Target: separate workspace
        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id

        # User with explicit read access to source
        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"importer-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        result = await import_tags_from_workspace(src_ws, tgt_ws, user.id)

        assert len(result) == 2
        tgt_tags = await list_tags_for_workspace(tgt_ws)
        imported_names = {t.name for t in tgt_tags}
        assert "Jurisdiction" in imported_names
        assert "Facts" in imported_names

    @pytest.mark.asyncio
    async def test_import_preserves_existing_tags(self) -> None:
        """Existing tags in target are preserved after import.

        Verifies AC3.2: additive merge.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import (
            create_tag,
            import_tags_from_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.users import create_user

        # Source with one tag
        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        await create_tag(src_ws, name="NewTag", color="#aabbcc")

        # Target with existing tag (different activity so no overlap)
        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id
        await create_tag(tgt_ws, name="Existing", color="#112233")

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        await import_tags_from_workspace(src_ws, tgt_ws, user.id)

        tgt_tags = await list_tags_for_workspace(tgt_ws)
        names = {t.name for t in tgt_tags}
        assert "Existing" in names
        assert "NewTag" in names

    @pytest.mark.asyncio
    async def test_import_skips_duplicate_names(self) -> None:
        """Tags with duplicate names (case-insensitive) are skipped.

        Verifies AC3.3.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import (
            create_tag,
            import_tags_from_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.users import create_user

        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        await create_tag(src_ws, name="Overlap", color="#111111")
        await create_tag(src_ws, name="Unique", color="#222222")

        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id
        await create_tag(tgt_ws, name="overlap", color="#333333")  # case mismatch

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        result = await import_tags_from_workspace(src_ws, tgt_ws, user.id)

        # Only "Unique" should be imported; "Overlap" skipped
        assert len(result) == 1
        assert result[0].name == "Unique"

        tgt_tags = await list_tags_for_workspace(tgt_ws)
        overlap_tags = [t for t in tgt_tags if t.name.lower() == "overlap"]
        assert len(overlap_tags) == 1  # original preserved, dupe not added

    @pytest.mark.asyncio
    async def test_import_preserves_group_ordering(self) -> None:
        """Imported groups and tags are appended after existing.

        Verifies AC3.4.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import (
            create_tag,
            create_tag_group,
            import_tags_from_workspace,
            list_tag_groups_for_workspace,
            list_tags_for_workspace,
        )
        from promptgrimoire.db.users import create_user

        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        src_group = await create_tag_group(src_ws, name="ImportedGroup")
        await create_tag(
            src_ws, name="ImportedTag", color="#aaaaaa", group_id=src_group.id
        )

        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id
        existing_group = await create_tag_group(tgt_ws, name="ExistingGroup")
        await create_tag(
            tgt_ws, name="ExistingTag", color="#bbbbbb", group_id=existing_group.id
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        await import_tags_from_workspace(src_ws, tgt_ws, user.id)

        groups = await list_tag_groups_for_workspace(tgt_ws)
        tags = await list_tags_for_workspace(tgt_ws)

        # Existing group should have lower order_index than imported
        existing_g = next(g for g in groups if g.name == "ExistingGroup")
        imported_g = next(g for g in groups if g.name == "ImportedGroup")
        assert existing_g.order_index < imported_g.order_index

        # Existing tag should have lower order_index than imported
        existing_t = next(t for t in tags if t.name == "ExistingTag")
        imported_t = next(t for t in tags if t.name == "ImportedTag")
        assert existing_t.order_index < imported_t.order_index

    @pytest.mark.asyncio
    async def test_import_unlocks_locked_tags(self) -> None:
        """Imported tags default to unlocked regardless of source status.

        Verifies AC3.5.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import (
            create_tag,
            import_tags_from_workspace,
        )
        from promptgrimoire.db.users import create_user

        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        await create_tag(src_ws, name="LockedSrc", color="#ff0000", locked=True)

        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        result = await import_tags_from_workspace(src_ws, tgt_ws, user.id)

        assert len(result) == 1
        assert result[0].locked is False

    @pytest.mark.asyncio
    async def test_import_empty_workspace_no_error(self) -> None:
        """Importing from workspace with no tags produces no error.

        Verifies AC3.7.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.tags import import_tags_from_workspace
        from promptgrimoire.db.users import create_user

        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id
        # No tags created in source

        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(src_ws, user.id, "viewer")

        result = await import_tags_from_workspace(src_ws, tgt_ws, user.id)
        assert result == []

    @pytest.mark.asyncio
    async def test_import_no_access_raises_permission_error(self) -> None:
        """Import from workspace user cannot access raises PermissionError."""
        from promptgrimoire.db.tags import import_tags_from_workspace
        from promptgrimoire.db.users import create_user

        _, src_activity = await _make_course_week_activity()
        src_ws = src_activity.template_workspace_id

        _, tgt_activity = await _make_course_week_activity()
        tgt_ws = tgt_activity.template_workspace_id

        # User with no enrollment or ACL at all
        outsider = await create_user(
            email=f"outsider-{uuid4().hex[:8]}@test.local",
            display_name="Outsider",
        )

        with pytest.raises(PermissionError):
            await import_tags_from_workspace(src_ws, tgt_ws, outsider.id)


class TestListImportableWorkspaces:
    """Tests for list_importable_workspaces."""

    @pytest.mark.asyncio
    async def test_user_with_acl_sees_workspace(self) -> None:
        """User with ACL on a workspace that has tags sees it in list."""
        from promptgrimoire.db.acl import grant_permission, list_importable_workspaces
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        await create_tag(ws_id, name="SomeTag", color="#123456")

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(ws_id, user.id, "viewer")

        results = await list_importable_workspaces(
            user.id,
            is_privileged=False,
            enrolled_course_ids=[],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id in ws_ids
        # Verify tag names are returned
        match = next(r for r in results if r[0].id == ws_id)
        assert match[2] == ["SomeTag"]

    @pytest.mark.asyncio
    async def test_workspace_without_tags_excluded(self) -> None:
        """Workspace with no tags is excluded from list."""
        from promptgrimoire.db.acl import grant_permission, list_importable_workspaces
        from promptgrimoire.db.users import create_user

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        # No tags created

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(ws_id, user.id, "viewer")

        results = await list_importable_workspaces(
            user.id,
            is_privileged=False,
            enrolled_course_ids=[],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id not in ws_ids

    @pytest.mark.asyncio
    async def test_target_workspace_excluded(self) -> None:
        """The exclude_workspace_id is not in the results."""
        from promptgrimoire.db.acl import grant_permission, list_importable_workspaces
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        await create_tag(ws_id, name="Tag1", color="#aabbcc")

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"imp-{tag}@test.local", display_name=f"Imp {tag}"
        )
        await grant_permission(ws_id, user.id, "viewer")

        results = await list_importable_workspaces(
            user.id,
            exclude_workspace_id=ws_id,
            is_privileged=False,
            enrolled_course_ids=[],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id not in ws_ids

    @pytest.mark.asyncio
    async def test_user_without_access_excluded(self) -> None:
        """User without ACL or enrollment does not see the workspace."""
        from promptgrimoire.db.acl import list_importable_workspaces
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        await create_tag(ws_id, name="HiddenTag", color="#654321")

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"noaccess-{tag}@test.local", display_name=f"NoAccess {tag}"
        )

        results = await list_importable_workspaces(
            user.id,
            is_privileged=False,
            enrolled_course_ids=[],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id not in ws_ids


class TestListImportableWorkspacesEnrollment:
    """Tests for enrollment-derived visibility in list_importable_workspaces."""

    @pytest.mark.asyncio
    async def test_staff_sees_template_workspace_via_enrollment(self) -> None:
        """Instructor enrolled in course sees template workspaces with tags."""
        from promptgrimoire.db.acl import list_importable_workspaces
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user

        course, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        await create_tag(ws_id, name="StaffTag", color="#1f77b4")

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"staff-{tag}@test.local", display_name=f"Staff {tag}"
        )
        await enroll_user(course.id, instructor.id, role="coordinator")

        results = await list_importable_workspaces(
            instructor.id,
            is_privileged=True,
            enrolled_course_ids=[course.id],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id in ws_ids

    @pytest.mark.asyncio
    async def test_student_sees_peer_shared_workspace(self) -> None:
        """Student sees peer-shared workspace with tags via enrollment."""
        from promptgrimoire.db.acl import list_importable_workspaces
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        course, activity = await _make_course_week_activity()

        # Create owner student and clone a workspace
        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"owner-{tag}@test.local", display_name=f"Owner {tag}"
        )
        await enroll_user(course.id, owner.id, role="student")
        clone, _doc_map = await clone_workspace_from_activity(
            activity.id,
            owner.id,
        )

        # Add tags and enable sharing prerequisites
        await create_tag(clone.id, name="PeerTag", color="#ff7f0e")
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace

        async with get_session() as session:
            # Enable sharing at course level
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_allow_sharing = True
            session.add(c)
            # Share workspace with class
            ws = await session.get(Workspace, clone.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)
            await session.flush()

        # Create viewer student enrolled in same course
        tag2 = uuid4().hex[:8]
        viewer = await create_user(
            email=f"viewer-{tag2}@test.local", display_name=f"Viewer {tag2}"
        )
        await enroll_user(course.id, viewer.id, role="student")

        results = await list_importable_workspaces(
            viewer.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert clone.id in ws_ids

    @pytest.mark.asyncio
    async def test_student_cannot_see_non_shared_workspace(self) -> None:
        """Student does NOT see another student's private workspace."""
        from promptgrimoire.db.acl import list_importable_workspaces
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        course, activity = await _make_course_week_activity()

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"priv-{tag}@test.local", display_name=f"Priv {tag}"
        )
        await enroll_user(course.id, owner.id, role="student")
        clone, _ = await clone_workspace_from_activity(activity.id, owner.id)
        await create_tag(clone.id, name="PrivateTag", color="#d62728")
        # shared_with_class defaults to False

        tag2 = uuid4().hex[:8]
        other = await create_user(
            email=f"other-{tag2}@test.local", display_name=f"Other {tag2}"
        )
        await enroll_user(course.id, other.id, role="student")

        results = await list_importable_workspaces(
            other.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert clone.id not in ws_ids

    @pytest.mark.asyncio
    async def test_unenrolled_user_cannot_see_course_workspaces(self) -> None:
        """User not enrolled in course does not see its workspaces."""
        from promptgrimoire.db.acl import list_importable_workspaces
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.users import create_user

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id
        await create_tag(ws_id, name="InvisibleTag", color="#9467bd")

        tag = uuid4().hex[:8]
        outsider = await create_user(
            email=f"out-{tag}@test.local", display_name=f"Out {tag}"
        )

        results = await list_importable_workspaces(
            outsider.id,
            is_privileged=False,
            enrolled_course_ids=[],  # Not enrolled
        )
        ws_ids = [ws.id for ws, *_ in results]
        assert ws_id not in ws_ids
