"""Tests for workspace placement and listing operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Tests verify placing workspaces in Activities/Courses, making them loose,
listing by Activity/Course, and error handling for non-existent entities.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from promptgrimoire.db.models import Activity, Course, Week

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


async def _setup_hierarchy() -> tuple[Course, Week, Activity]:
    """Create a full Course -> Week -> Activity hierarchy."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"P{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Placement Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Test Activity")
    return course, week, activity


class TestPlaceWorkspace:
    """Tests for workspace placement functions."""

    @pytest.mark.asyncio
    async def test_place_in_activity_sets_activity_id_clears_course_id(
        self,
    ) -> None:
        """Place in Activity: sets activity_id, clears course_id.

        Verifies AC3.1.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # First place in course
        await place_workspace_in_course(ws.id, course.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.course_id == course.id
        original_updated_at = before.updated_at

        # Now place in activity -- should clear course_id
        result = await place_workspace_in_activity(ws.id, activity.id)

        assert result.activity_id == activity.id
        assert result.course_id is None
        assert result.updated_at > original_updated_at

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.activity_id == activity.id
        assert after.course_id is None

    @pytest.mark.asyncio
    async def test_place_in_course_sets_course_id_clears_activity_id(
        self,
    ) -> None:
        """Place in Course: sets course_id, clears activity_id.

        Verifies AC3.2.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # First place in activity
        await place_workspace_in_activity(ws.id, activity.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.activity_id == activity.id

        # Now place in course -- should clear activity_id
        result = await place_workspace_in_course(ws.id, course.id)

        assert result.course_id == course.id
        assert result.activity_id is None

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.course_id == course.id
        assert after.activity_id is None

    @pytest.mark.asyncio
    async def test_make_loose_clears_both(self) -> None:
        """Make workspace loose: clears both activity_id and course_id.

        Verifies AC3.3.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            make_workspace_loose,
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # Place in activity
        await place_workspace_in_activity(ws.id, activity.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.activity_id == activity.id

        # Make loose
        result = await make_workspace_loose(ws.id)

        assert result.activity_id is None
        assert result.course_id is None

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.activity_id is None
        assert after.course_id is None

    @pytest.mark.asyncio
    async def test_place_in_nonexistent_activity_raises(self) -> None:
        """Placing in non-existent Activity raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        ws = await create_workspace()

        with pytest.raises(ValueError, match=r"Activity.*not found"):
            await place_workspace_in_activity(ws.id, uuid4())

    @pytest.mark.asyncio
    async def test_place_in_nonexistent_course_raises(self) -> None:
        """Placing in non-existent Course raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_course,
        )

        ws = await create_workspace()

        with pytest.raises(ValueError, match=r"Course.*not found"):
            await place_workspace_in_course(ws.id, uuid4())

    @pytest.mark.asyncio
    async def test_place_nonexistent_workspace_raises(self) -> None:
        """Placing a non-existent workspace raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()

        with pytest.raises(ValueError, match=r"Workspace.*not found"):
            await place_workspace_in_activity(uuid4(), activity.id)


class TestListWorkspaces:
    """Tests for workspace listing functions."""

    @pytest.mark.asyncio
    async def test_list_for_activity(self) -> None:
        """List workspaces for Activity returns only placed workspaces.

        Verifies AC3.5.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            list_workspaces_for_activity,
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()

        ws1 = await create_workspace()
        ws2 = await create_workspace()
        await create_workspace()  # unplaced

        await place_workspace_in_activity(ws1.id, activity.id)
        await place_workspace_in_activity(ws2.id, activity.id)

        result = await list_workspaces_for_activity(activity.id)

        result_ids = {w.id for w in result}
        assert ws1.id in result_ids
        assert ws2.id in result_ids
        # +1 for the template workspace auto-placed by create_activity
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_loose_for_course(self) -> None:
        """Loose workspaces for Course excludes activity-placed ones.

        Verifies AC3.6.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            list_loose_workspaces_for_course,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()

        ws1 = await create_workspace()
        await place_workspace_in_course(ws1.id, course.id)

        ws2 = await create_workspace()
        await place_workspace_in_activity(ws2.id, activity.id)

        ws3 = await create_workspace()
        await place_workspace_in_course(ws3.id, course.id)

        result = await list_loose_workspaces_for_course(course.id)

        result_ids = {w.id for w in result}
        assert ws1.id in result_ids
        assert ws3.id in result_ids
        assert ws2.id not in result_ids
        assert len(result) == 2


class TestPlacementContext:
    """Tests for get_placement_context hierarchy resolution."""

    @pytest.mark.asyncio
    async def test_loose_workspace(self) -> None:
        """Loose workspace returns placement_type='loose' and 'Unplaced' label.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            PlacementContext,
            create_workspace,
            get_placement_context,
        )

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)

        assert isinstance(ctx, PlacementContext)
        assert ctx.placement_type == "loose"
        assert ctx.activity_title is None
        assert ctx.week_number is None
        assert ctx.week_title is None
        assert ctx.course_code is None
        assert ctx.course_name is None
        assert ctx.display_label == "Unplaced"

    @pytest.mark.asyncio
    async def test_activity_placement_shows_full_hierarchy(self) -> None:
        """Activity placement populates all hierarchy fields.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        course, _week, activity = await _setup_hierarchy()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "activity"
        assert ctx.activity_title == "Test Activity"
        assert ctx.week_number == _week.week_number
        assert ctx.week_title == _week.title
        assert ctx.course_code == course.code
        assert ctx.course_name == course.name
        assert ctx.display_label == (f"Test Activity in Week 1 for {course.code}")

    @pytest.mark.asyncio
    async def test_course_placement(self) -> None:
        """Course placement populates course fields only.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_course,
        )

        course, _, _ = await _setup_hierarchy()
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)

        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "course"
        assert ctx.activity_title is None
        assert ctx.week_number is None
        assert ctx.week_title is None
        assert ctx.course_code == course.code
        assert ctx.course_name == course.name
        assert ctx.display_label == f"Loose work for {course.code}"

    @pytest.mark.asyncio
    async def test_nonexistent_workspace(self) -> None:
        """Non-existent workspace returns loose context.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import get_placement_context

        ctx = await get_placement_context(uuid4())

        assert ctx.placement_type == "loose"
        assert ctx.display_label == "Unplaced"
