"""Tests for check_clone_eligibility() pre-clone gate.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify enrollment check (AC7.2), week visibility (AC7.3),
and unenrolled user rejection (AC7.6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_test_data() -> dict:
    """Create full hierarchy for eligibility tests.

    Returns course, week, activity, student, instructor, unenrolled user.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course, enroll_user
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"E{tag[:6].upper()}", name="Eligibility Test", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Eligible Activity")

    student = await create_user(
        email=f"student-{tag}@test.local", display_name=f"Student {tag}"
    )
    await enroll_user(course_id=course.id, user_id=student.id, role="student")

    instructor = await create_user(
        email=f"instr-{tag}@test.local", display_name=f"Instructor {tag}"
    )
    await enroll_user(course_id=course.id, user_id=instructor.id, role="instructor")

    unenrolled = await create_user(
        email=f"outsider-{tag}@test.local", display_name=f"Outsider {tag}"
    )

    return {
        "course": course,
        "week": week,
        "activity": activity,
        "student": student,
        "instructor": instructor,
        "unenrolled": unenrolled,
    }


class TestCheckCloneEligibility:
    """Tests for check_clone_eligibility()."""

    @pytest.mark.asyncio
    async def test_enrolled_student_published_week_eligible(self) -> None:
        """Enrolled student with published week is eligible (returns None).

        Verifies AC7.2.
        """
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(data["activity"].id, data["student"].id)
        assert result is None

    @pytest.mark.asyncio
    async def test_unenrolled_user_rejected(self) -> None:
        """Unenrolled user gets error message.

        Verifies AC7.6.
        """
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(
            data["activity"].id, data["unenrolled"].id
        )
        assert result is not None
        assert "not enrolled" in result.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_activity_rejected(self) -> None:
        """Non-existent activity returns error."""
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()
        result = await check_clone_eligibility(uuid4(), data["student"].id)
        assert result is not None
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_unpublished_week_rejected_for_student(self) -> None:
        """Unpublished week blocks student clone.

        Verifies AC7.3.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()

        # Create an unpublished week with its own activity
        unpub_week = await create_week(
            course_id=data["course"].id, week_number=99, title="Unpublished"
        )
        unpub_activity = await create_activity(
            week_id=unpub_week.id, title="Hidden Activity"
        )

        result = await check_clone_eligibility(unpub_activity.id, data["student"].id)
        assert result is not None
        assert "not published" in result.lower()

    @pytest.mark.asyncio
    async def test_future_visible_from_rejected_for_student(self) -> None:
        """Week with future visible_from blocks student clone.

        Verifies AC7.3.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.weeks import (
            create_week,
            publish_week,
            schedule_week_visibility,
        )
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()

        # Create a published but future-visible week
        future_week = await create_week(
            course_id=data["course"].id, week_number=98, title="Future"
        )
        await publish_week(future_week.id)
        future_time = datetime.now(UTC) + timedelta(days=7)
        await schedule_week_visibility(future_week.id, future_time)

        future_activity = await create_activity(
            week_id=future_week.id, title="Future Activity"
        )

        result = await check_clone_eligibility(future_activity.id, data["student"].id)
        assert result is not None
        assert "not yet visible" in result.lower()

    @pytest.mark.asyncio
    async def test_staff_bypasses_unpublished_week(self) -> None:
        """Staff (instructor) can clone even when week is unpublished.

        Verifies AC7.3 staff bypass.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()

        # Create unpublished week
        unpub_week = await create_week(
            course_id=data["course"].id, week_number=97, title="Staff Only"
        )
        unpub_activity = await create_activity(
            week_id=unpub_week.id, title="Staff Activity"
        )

        result = await check_clone_eligibility(unpub_activity.id, data["instructor"].id)
        assert result is None

    @pytest.mark.asyncio
    async def test_staff_bypasses_future_visibility(self) -> None:
        """Staff (instructor) can clone even with future visible_from.

        Verifies AC7.3 staff bypass.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.weeks import (
            create_week,
            publish_week,
            schedule_week_visibility,
        )
        from promptgrimoire.db.workspaces import check_clone_eligibility

        data = await _make_test_data()

        future_week = await create_week(
            course_id=data["course"].id, week_number=96, title="Future Staff"
        )
        await publish_week(future_week.id)
        await schedule_week_visibility(
            future_week.id, datetime.now(UTC) + timedelta(days=30)
        )
        future_activity = await create_activity(
            week_id=future_week.id, title="Future Staff Activity"
        )

        result = await check_clone_eligibility(
            future_activity.id, data["instructor"].id
        )
        assert result is None
