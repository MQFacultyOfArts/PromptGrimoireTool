"""Integration tests for week and activity edit persistence.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Covers:
- AC1.1: update_week() persists week_number and title changes
- AC1.2: update_activity() persists title and description changes
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course() -> UUID:
    """Create a course, returning course_id."""
    from promptgrimoire.db.courses import create_course

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Edit Test", semester="2026-S1")
    return course.id


async def _make_week(
    course_id: UUID,
    week_number: int = 1,
    title: str = "Week 1",
) -> UUID:
    """Create a week in a course, returning week_id."""
    from promptgrimoire.db.weeks import create_week

    week = await create_week(
        course_id=course_id,
        week_number=week_number,
        title=title,
    )
    return week.id


async def _make_activity(
    week_id: UUID,
    title: str = "Test Activity",
    description: str | None = None,
) -> UUID:
    """Create an activity in a week, returning activity_id."""
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(
        week_id=week_id,
        title=title,
        description=description,
    )
    return activity.id


class TestUpdateWeek:
    """Tests for update_week() persistence."""

    @pytest.mark.asyncio
    async def test_edit_week_number(self) -> None:
        """Changing week_number via update_week() persists to DB.

        Verifies crud-management-229.AC1.1: week_number update persists.
        """
        from promptgrimoire.db.weeks import get_week_by_id, update_week

        course_id = await _make_course()
        week_id = await _make_week(course_id, week_number=1)

        result = await update_week(week_id, week_number=5)
        assert result is not None
        assert result.week_number == 5

        # Re-fetch from DB to confirm persistence
        refetched = await get_week_by_id(week_id)
        assert refetched is not None
        assert refetched.week_number == 5

    @pytest.mark.asyncio
    async def test_edit_week_title(self) -> None:
        """Changing title via update_week() persists to DB.

        Verifies crud-management-229.AC1.1: title update persists.
        """
        from promptgrimoire.db.weeks import get_week_by_id, update_week

        course_id = await _make_course()
        week_id = await _make_week(course_id, title="Original Title")

        result = await update_week(week_id, title="New Title")
        assert result is not None
        assert result.title == "New Title"

        # Re-fetch from DB to confirm persistence
        refetched = await get_week_by_id(week_id)
        assert refetched is not None
        assert refetched.title == "New Title"

    @pytest.mark.asyncio
    async def test_edit_both_fields(self) -> None:
        """Changing both week_number and title simultaneously persists.

        Verifies crud-management-229.AC1.1: simultaneous field updates.
        """
        from promptgrimoire.db.weeks import get_week_by_id, update_week

        course_id = await _make_course()
        week_id = await _make_week(course_id, week_number=1, title="Original")

        result = await update_week(week_id, week_number=10, title="Updated Both")
        assert result is not None
        assert result.week_number == 10
        assert result.title == "Updated Both"

        # Re-fetch from DB to confirm persistence
        refetched = await get_week_by_id(week_id)
        assert refetched is not None
        assert refetched.week_number == 10
        assert refetched.title == "Updated Both"


class TestUpdateActivity:
    """Tests for update_activity() persistence."""

    @pytest.mark.asyncio
    async def test_edit_activity_title(self) -> None:
        """Changing title via update_activity() persists to DB.

        Verifies crud-management-229.AC1.2: title update persists.
        """
        from promptgrimoire.db.activities import get_activity, update_activity

        course_id = await _make_course()
        week_id = await _make_week(course_id)
        activity_id = await _make_activity(week_id, title="Original Activity")

        result = await update_activity(activity_id, title="New Title")
        assert result is not None
        assert result.title == "New Title"

        # Re-fetch from DB to confirm persistence
        refetched = await get_activity(activity_id)
        assert refetched is not None
        assert refetched.title == "New Title"

    @pytest.mark.asyncio
    async def test_edit_activity_description(self) -> None:
        """Changing description via update_activity() persists to DB.

        Verifies crud-management-229.AC1.2: description update persists.
        """
        from promptgrimoire.db.activities import get_activity, update_activity

        course_id = await _make_course()
        week_id = await _make_week(course_id)
        activity_id = await _make_activity(
            week_id,
            title="Activity With Desc",
            description="Original description",
        )

        result = await update_activity(activity_id, description="Updated description")
        assert result is not None
        assert result.description == "Updated description"

        # Re-fetch from DB to confirm persistence
        refetched = await get_activity(activity_id)
        assert refetched is not None
        assert refetched.description == "Updated description"

    @pytest.mark.asyncio
    async def test_clear_activity_description(self) -> None:
        """Setting description to None clears it in DB.

        Verifies crud-management-229.AC1.2: description=None clears the field.
        The Ellipsis sentinel in update_activity() distinguishes "not provided"
        from explicit None.
        """
        from promptgrimoire.db.activities import get_activity, update_activity

        course_id = await _make_course()
        week_id = await _make_week(course_id)
        activity_id = await _make_activity(
            week_id,
            title="Activity Clear Desc",
            description="Will be cleared",
        )

        # Verify description is set
        before = await get_activity(activity_id)
        assert before is not None
        assert before.description == "Will be cleared"

        # Clear the description
        result = await update_activity(activity_id, description=None)
        assert result is not None
        assert result.description is None

        # Re-fetch from DB to confirm persistence
        refetched = await get_activity(activity_id)
        assert refetched is not None
        assert refetched.description is None

    @pytest.mark.asyncio
    async def test_edit_title_only_preserves_description(self) -> None:
        """Updating only title leaves description unchanged.

        Verifies crud-management-229.AC1.2: partial updates do not
        clobber unrelated fields. The Ellipsis sentinel ensures
        omitted parameters are not applied.
        """
        from promptgrimoire.db.activities import get_activity, update_activity

        course_id = await _make_course()
        week_id = await _make_week(course_id)
        activity_id = await _make_activity(
            week_id,
            title="Original Title",
            description="Should survive title edit",
        )

        result = await update_activity(activity_id, title="Changed Title")
        assert result is not None
        assert result.title == "Changed Title"
        assert result.description == "Should survive title edit"

        # Re-fetch from DB to confirm persistence
        refetched = await get_activity(activity_id)
        assert refetched is not None
        assert refetched.title == "Changed Title"
        assert refetched.description == "Should survive title edit"
