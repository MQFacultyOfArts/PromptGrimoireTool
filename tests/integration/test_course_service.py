"""Tests for course CRUD operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL
environment variable to point to a test database.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from promptgrimoire.db.models import CourseRole

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


class TestCreateCourse:
    """Tests for create_course."""

    @pytest.mark.asyncio
    async def test_creates_course_with_required_fields(self) -> None:
        """Course is created with code, name, semester."""
        from promptgrimoire.db.courses import create_course

        course = await create_course(
            code="LAWS1100",
            name="Contracts",
            semester="2025-S1",
        )

        assert course.id is not None
        assert course.code == "LAWS1100"
        assert course.name == "Contracts"
        assert course.semester == "2025-S1"
        assert course.is_archived is False

    @pytest.mark.asyncio
    async def test_creates_course_with_unique_id(self) -> None:
        """Each course gets a unique UUID."""
        from promptgrimoire.db.courses import create_course

        course1 = await create_course(
            code="LAWS1100",
            name="Contracts",
            semester="2025-S1",
        )
        course2 = await create_course(
            code="LAWS1100",
            name="Contracts",
            semester="2025-S2",
        )

        assert course1.id != course2.id


class TestGetCourse:
    """Tests for get_course_by_id."""

    @pytest.mark.asyncio
    async def test_returns_course_by_id(self) -> None:
        """Returns course when found."""
        from promptgrimoire.db.courses import create_course, get_course_by_id

        course = await create_course(
            code="LAWS2200",
            name="Torts",
            semester="2025-S1",
        )

        found = await get_course_by_id(course.id)

        assert found is not None
        assert found.id == course.id
        assert found.code == "LAWS2200"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self) -> None:
        """Returns None when course not found."""
        from promptgrimoire.db.courses import get_course_by_id

        found = await get_course_by_id(uuid4())

        assert found is None


class TestListCourses:
    """Tests for list_courses."""

    @pytest.mark.asyncio
    async def test_returns_all_non_archived_courses(self) -> None:
        """Returns active courses ordered by code."""
        from promptgrimoire.db.courses import create_course, list_courses

        # Create with unique semester to avoid collision
        semester = f"test-{uuid4().hex[:8]}"
        await create_course(code="LAWS3300", name="Equity", semester=semester)
        await create_course(code="LAWS1100", name="Contracts", semester=semester)

        courses = await list_courses(semester=semester)

        codes = [c.code for c in courses]
        assert "LAWS1100" in codes
        assert "LAWS3300" in codes

    @pytest.mark.asyncio
    async def test_excludes_archived_courses(self) -> None:
        """Archived courses are not returned by default."""
        from promptgrimoire.db.courses import (
            archive_course,
            create_course,
            list_courses,
        )

        semester = f"test-{uuid4().hex[:8]}"
        course = await create_course(
            code="LAWS9999", name="Archived", semester=semester
        )
        await archive_course(course.id)

        courses = await list_courses(semester=semester)

        assert all(c.code != "LAWS9999" for c in courses)


class TestArchiveCourse:
    """Tests for archive_course."""

    @pytest.mark.asyncio
    async def test_marks_course_as_archived(self) -> None:
        """Course is_archived becomes True."""
        from promptgrimoire.db.courses import (
            archive_course,
            create_course,
            get_course_by_id,
        )

        course = await create_course(
            code="LAWS5500",
            name="To Archive",
            semester="2025-S1",
        )

        result = await archive_course(course.id)

        assert result is True
        updated = await get_course_by_id(course.id)
        assert updated is not None
        assert updated.is_archived is True

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_course(self) -> None:
        """Returns False when course not found."""
        from promptgrimoire.db.courses import archive_course

        result = await archive_course(uuid4())

        assert result is False


class TestEnrollment:
    """Tests for course enrollment."""

    @pytest.mark.asyncio
    async def test_enroll_user_in_course(self) -> None:
        """User is enrolled with specified role."""
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user

        course = await create_course(
            code="LAWS6600",
            name="Evidence",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        enrollment = await enroll_user(
            course_id=course.id,
            user_id=user.id,
            role=CourseRole.student,
        )

        assert enrollment.course_id == course.id
        assert enrollment.user_id == user.id
        assert enrollment.role == CourseRole.student

    @pytest.mark.asyncio
    async def test_get_enrollment(self) -> None:
        """Can retrieve enrollment by user and course."""
        from promptgrimoire.db.courses import (
            create_course,
            enroll_user,
            get_enrollment,
        )
        from promptgrimoire.db.users import create_user

        course = await create_course(
            code="LAWS7700",
            name="Criminal",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        await enroll_user(course_id=course.id, user_id=user.id)

        enrollment = await get_enrollment(course_id=course.id, user_id=user.id)

        assert enrollment is not None
        assert enrollment.user_id == user.id

    @pytest.mark.asyncio
    async def test_list_enrollments_for_user(self) -> None:
        """Returns all courses a user is enrolled in."""
        from promptgrimoire.db.courses import (
            create_course,
            enroll_user,
            list_user_enrollments,
        )
        from promptgrimoire.db.users import create_user

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        semester = f"test-{uuid4().hex[:8]}"

        course1 = await create_course(code="LAWS1111", name="One", semester=semester)
        course2 = await create_course(code="LAWS2222", name="Two", semester=semester)

        await enroll_user(course_id=course1.id, user_id=user.id)
        await enroll_user(course_id=course2.id, user_id=user.id, role=CourseRole.tutor)

        enrollments = await list_user_enrollments(user.id)

        assert len(enrollments) >= 2
        course_ids = [e.course_id for e in enrollments]
        assert course1.id in course_ids
        assert course2.id in course_ids

    @pytest.mark.asyncio
    async def test_unenroll_user(self) -> None:
        """User can be removed from course."""
        from promptgrimoire.db.courses import (
            create_course,
            enroll_user,
            get_enrollment,
            unenroll_user,
        )
        from promptgrimoire.db.users import create_user

        course = await create_course(
            code="LAWS8800",
            name="Property",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        await enroll_user(course_id=course.id, user_id=user.id)

        result = await unenroll_user(course_id=course.id, user_id=user.id)

        assert result is True
        enrollment = await get_enrollment(course_id=course.id, user_id=user.id)
        assert enrollment is None

    @pytest.mark.asyncio
    async def test_duplicate_enrollment_raises_error(self) -> None:
        """Enrolling same user twice raises DuplicateEnrollmentError."""
        from promptgrimoire.db.courses import (
            DuplicateEnrollmentError,
            create_course,
            enroll_user,
        )
        from promptgrimoire.db.users import create_user

        course = await create_course(
            code="LAWS8801",
            name="Duplicate Test",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        # First enrollment succeeds
        await enroll_user(course_id=course.id, user_id=user.id)

        # Second enrollment fails
        with pytest.raises(DuplicateEnrollmentError) as exc_info:
            await enroll_user(course_id=course.id, user_id=user.id)

        assert exc_info.value.course_id == course.id
        assert exc_info.value.user_id == user.id

    @pytest.mark.asyncio
    async def test_concurrent_enrollment_acid_compliance(self) -> None:
        """Concurrent enrollments are ACID-compliant: exactly one succeeds."""
        import asyncio

        from promptgrimoire.db.courses import (
            DuplicateEnrollmentError,
            create_course,
            enroll_user,
            get_enrollment,
        )
        from promptgrimoire.db.users import create_user

        course = await create_course(
            code="LAWS8802",
            name="Concurrent Test",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        async def try_enroll() -> str:
            """Attempt enrollment, return 'success' or 'duplicate'."""
            try:
                await enroll_user(course_id=course.id, user_id=user.id)
                return "success"
            except DuplicateEnrollmentError:
                return "duplicate"

        # Run two enrollments concurrently
        results = await asyncio.gather(try_enroll(), try_enroll())

        # Exactly one should succeed, one should fail
        assert sorted(results) == ["duplicate", "success"], (
            f"Expected exactly one success and one duplicate, got {results}"
        )

        # Verify enrollment exists
        enrollment = await get_enrollment(course_id=course.id, user_id=user.id)
        assert enrollment is not None
        assert enrollment.user_id == user.id


class TestWeeks:
    """Tests for week CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_week(self) -> None:
        """Week is created with course reference."""
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.weeks import create_week

        course = await create_course(
            code="LAWS1000",
            name="Intro",
            semester="2025-S1",
        )

        week = await create_week(
            course_id=course.id,
            week_number=1,
            title="Introduction to Legal Studies",
        )

        assert week.id is not None
        assert week.course_id == course.id
        assert week.week_number == 1
        assert week.title == "Introduction to Legal Studies"
        assert week.is_published is False
        assert week.visible_from is None

    @pytest.mark.asyncio
    async def test_list_weeks_for_course(self) -> None:
        """Returns all weeks for a course ordered by week number."""
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.weeks import create_week, list_weeks

        course = await create_course(
            code="LAWS1001",
            name="Intro 2",
            semester="2025-S1",
        )

        await create_week(course_id=course.id, week_number=2, title="Week 2")
        await create_week(course_id=course.id, week_number=1, title="Week 1")
        await create_week(course_id=course.id, week_number=3, title="Week 3")

        weeks = await list_weeks(course_id=course.id)

        assert len(weeks) == 3
        assert weeks[0].week_number == 1
        assert weeks[1].week_number == 2
        assert weeks[2].week_number == 3

    @pytest.mark.asyncio
    async def test_publish_week(self) -> None:
        """Week can be published."""
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.weeks import create_week, get_week_by_id, publish_week

        course = await create_course(
            code="LAWS1002",
            name="Intro 3",
            semester="2025-S1",
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")

        await publish_week(week.id)

        updated = await get_week_by_id(week.id)
        assert updated is not None
        assert updated.is_published is True

    @pytest.mark.asyncio
    async def test_schedule_week_visibility(self) -> None:
        """Week can be scheduled for future visibility."""
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.weeks import (
            create_week,
            get_week_by_id,
            schedule_week_visibility,
        )

        course = await create_course(
            code="LAWS1003",
            name="Intro 4",
            semester="2025-S1",
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        future_date = datetime.now(UTC) + timedelta(days=7)

        await schedule_week_visibility(week.id, visible_from=future_date)

        updated = await get_week_by_id(week.id)
        assert updated is not None
        assert updated.visible_from is not None
        assert updated.visible_from >= future_date - timedelta(seconds=1)


class TestWeekVisibility:
    """Tests for week visibility logic."""

    @pytest.mark.asyncio
    async def test_get_visible_weeks_for_instructor(self) -> None:
        """Instructors see all weeks regardless of publish status."""
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, get_visible_weeks, publish_week

        course = await create_course(
            code="LAWS2001",
            name="Visibility Test 1",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"instructor-{uuid4().hex[:8]}@example.com",
            display_name="Instructor",
        )
        await enroll_user(
            course_id=course.id, user_id=user.id, role=CourseRole.instructor
        )

        # Create published and unpublished weeks
        week1 = await create_week(course_id=course.id, week_number=1, title="Published")
        await publish_week(week1.id)
        await create_week(course_id=course.id, week_number=2, title="Unpublished")

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 2

    @pytest.mark.asyncio
    async def test_get_visible_weeks_for_student_only_published(self) -> None:
        """Students only see published weeks."""
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, get_visible_weeks, publish_week

        course = await create_course(
            code="LAWS2002",
            name="Visibility Test 2",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"student-{uuid4().hex[:8]}@example.com",
            display_name="Student",
        )
        await enroll_user(course_id=course.id, user_id=user.id, role=CourseRole.student)

        # Create published and unpublished weeks
        week1 = await create_week(course_id=course.id, week_number=1, title="Published")
        await publish_week(week1.id)
        await create_week(course_id=course.id, week_number=2, title="Unpublished")

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 1
        assert weeks[0].title == "Published"

    @pytest.mark.asyncio
    async def test_get_visible_weeks_respects_visible_from(self) -> None:
        """Students don't see weeks with future visible_from."""
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import (
            create_week,
            get_visible_weeks,
            publish_week,
            schedule_week_visibility,
        )

        course = await create_course(
            code="LAWS2003",
            name="Visibility Test 3",
            semester="2025-S1",
        )
        user = await create_user(
            email=f"student-{uuid4().hex[:8]}@example.com",
            display_name="Student",
        )
        await enroll_user(course_id=course.id, user_id=user.id, role=CourseRole.student)

        # Week 1: published, no schedule (visible now)
        week1 = await create_week(course_id=course.id, week_number=1, title="Now")
        await publish_week(week1.id)

        # Week 2: published, but scheduled for future
        week2 = await create_week(course_id=course.id, week_number=2, title="Future")
        await publish_week(week2.id)
        await schedule_week_visibility(
            week2.id, visible_from=datetime.now(UTC) + timedelta(days=7)
        )

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 1
        assert weeks[0].title == "Now"

    @pytest.mark.asyncio
    async def test_unenrolled_user_sees_no_weeks(self) -> None:
        """Users not enrolled in course see no weeks."""
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, get_visible_weeks, publish_week

        course = await create_course(
            code="LAWS2004",
            name="Visibility Test 4",
            semester="2025-S1",
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        await publish_week(week.id)

        user = await create_user(
            email=f"unenrolled-{uuid4().hex[:8]}@example.com",
            display_name="Unenrolled",
        )

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 0


class TestUpdateCourse:
    """Tests for update_course."""

    @pytest.mark.asyncio
    async def test_update_default_copy_protection_false_to_true(self) -> None:
        """Update default_copy_protection from False to True and verify round-trip."""
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        course = await create_course(
            code="LAWS9001", name="CP Test 1", semester="2025-S1"
        )
        assert course.default_copy_protection is False

        updated = await update_course(course.id, default_copy_protection=True)
        assert updated is not None
        assert updated.default_copy_protection is True

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_copy_protection is True

    @pytest.mark.asyncio
    async def test_update_default_copy_protection_true_to_false(self) -> None:
        """Update default_copy_protection from True to False and verify round-trip."""
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        course = await create_course(
            code="LAWS9002", name="CP Test 2", semester="2025-S1"
        )
        # Set to True first
        await update_course(course.id, default_copy_protection=True)

        updated = await update_course(course.id, default_copy_protection=False)
        assert updated is not None
        assert updated.default_copy_protection is False

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_copy_protection is False

    @pytest.mark.asyncio
    async def test_update_name_only_preserves_default_copy_protection(self) -> None:
        """Updating only name does not change default_copy_protection."""
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        course = await create_course(
            code="LAWS9003", name="CP Test 3", semester="2025-S1"
        )
        await update_course(course.id, default_copy_protection=True)

        updated = await update_course(course.id, name="Renamed Course")
        assert updated is not None
        assert updated.name == "Renamed Course"
        assert updated.default_copy_protection is True

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_copy_protection is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_course_returns_none(self) -> None:
        """Updating a non-existent course returns None."""
        from promptgrimoire.db.courses import update_course

        result = await update_course(uuid4(), name="Nope")
        assert result is None
