"""Tests for delete guard logic (student workspace protection).

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify has_student_workspaces() count accuracy, which is the
foundation for all delete guard logic in activities, weeks, and courses.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str = "") -> tuple[UUID, UUID]:
    """Create a course and week, returning (course_id, week_id)."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name=f"Test{suffix}", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course.id, week.id


async def _make_activity(week_id: UUID, title: str = "Test Activity") -> UUID:
    """Create an activity with template workspace, returning activity_id."""
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title=title)
    return activity.id


async def _create_student() -> UUID:
    """Create a real user in the DB and return user_id."""
    from promptgrimoire.db.users import create_user

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"student-{tag}@test.local",
        display_name=f"Student {tag}",
    )
    return user.id


async def _clone_for_student(activity_id: UUID) -> UUID:
    """Clone activity template for a new student, returning workspace_id."""
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    user_id = await _create_student()
    workspace, _doc_map = await clone_workspace_from_activity(activity_id, user_id)
    return workspace.id


class TestHasStudentWorkspaces:
    """Tests for has_student_workspaces() count accuracy."""

    @pytest.mark.asyncio
    async def test_returns_zero_for_activity_with_no_students(self) -> None:
        """Activity with only template workspace returns 0."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("no-students")
        activity_id = await _make_activity(week_id)

        count = await has_student_workspaces(activity_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_one_after_single_clone(self) -> None:
        """Activity with one student clone returns 1."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("one-student")
        activity_id = await _make_activity(week_id)
        await _clone_for_student(activity_id)

        count = await has_student_workspaces(activity_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_returns_two_after_two_clones(self) -> None:
        """Activity with two student clones returns 2."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("two-students")
        activity_id = await _make_activity(week_id)
        await _clone_for_student(activity_id)
        await _clone_for_student(activity_id)

        count = await has_student_workspaces(activity_id)
        assert count == 2
