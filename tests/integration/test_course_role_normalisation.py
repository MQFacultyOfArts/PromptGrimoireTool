"""Tests for CourseRole normalisation (StrEnum → string FK).

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Verifies that CourseEnrollment.role is now a string FK to course_role
reference table, and that enrollment CRUD works with string role values.

Acceptance Criteria:
- AC3.1: CourseEnrollment.role is a FK to course_role table
- AC3.2: Week visibility works identically after normalisation
- AC3.3: Enrollment CRUD accepts role as string
- AC3.4: Invalid role string rejected by FK constraint
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestRoleFKConstraint:
    """Verify CourseEnrollment.role is a FK to course_role.

    AC3.1: Role column references course_role.name.
    AC3.4: Invalid role rejected by FK constraint.
    """

    @pytest.mark.asyncio
    async def test_enrollment_with_valid_role(self) -> None:
        """Enrollment with a valid role string succeeds (AC3.1)."""
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User

        async with get_session() as session:
            user = User(
                email=f"fk-valid-{uuid4().hex[:8]}@example.com",
                display_name="FK Test",
            )
            course = Course(
                code="FK01",
                name="FK Test",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        enrollment = await enroll_user(
            course_id=course.id,
            user_id=user.id,
            role="instructor",
        )

        assert enrollment.role == "instructor"

    @pytest.mark.asyncio
    async def test_enrollment_with_invalid_role_raises(self) -> None:
        """Enrollment with nonexistent role raises IntegrityError (AC3.4)."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, CourseEnrollment, User

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                user = User(
                    email=f"fk-invalid-{uuid4().hex[:8]}@example.com",
                    display_name="Bad Role",
                )
                course = Course(
                    code="FK02",
                    name="FK Bad",
                    semester="2026-S1",
                )
                session.add(user)
                session.add(course)
                await session.flush()

                enrollment = CourseEnrollment(
                    course_id=course.id,
                    user_id=user.id,
                    role="nonexistent",
                )
                session.add(enrollment)
                await session.flush()


class TestEnrollmentCRUDWithStringRoles:
    """Verify enrollment CRUD accepts string role values.

    AC3.3: enroll_user() and update_user_role() work with strings.
    """

    @pytest.mark.asyncio
    async def test_enroll_with_string_role(self) -> None:
        """enroll_user() accepts role as plain string (AC3.3)."""
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User

        async with get_session() as session:
            user = User(
                email=f"str-role-{uuid4().hex[:8]}@example.com",
                display_name="String Role",
            )
            course = Course(
                code="STR01",
                name="String Test",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        enrollment = await enroll_user(
            course_id=course.id,
            user_id=user.id,
            role="tutor",
        )

        assert enrollment.role == "tutor"

    @pytest.mark.asyncio
    async def test_update_role_with_string(self) -> None:
        """update_user_role() accepts string role (AC3.3)."""
        from promptgrimoire.db.courses import enroll_user, update_user_role
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User

        async with get_session() as session:
            user = User(
                email=f"update-role-{uuid4().hex[:8]}@example.com",
                display_name="Update Role",
            )
            course = Course(
                code="UPD01",
                name="Update Test",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        await enroll_user(
            course_id=course.id,
            user_id=user.id,
            role="student",
        )

        updated = await update_user_role(
            course_id=course.id,
            user_id=user.id,
            role="coordinator",
        )

        assert updated is not None
        assert updated.role == "coordinator"

    @pytest.mark.asyncio
    async def test_default_role_is_student(self) -> None:
        """enroll_user() defaults to 'student' role (AC3.3)."""
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User

        async with get_session() as session:
            user = User(
                email=f"default-{uuid4().hex[:8]}@example.com",
                display_name="Default Role",
            )
            course = Course(
                code="DEF01",
                name="Default Test",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        enrollment = await enroll_user(
            course_id=course.id,
            user_id=user.id,
        )

        assert enrollment.role == "student"


class TestGetStaffRoles:
    """Verify get_staff_roles() returns expected staff roles from reference table."""

    @pytest.mark.asyncio
    async def test_returns_expected_staff_roles(self) -> None:
        """get_staff_roles() returns coordinator, instructor, tutor."""
        from promptgrimoire.db.roles import _reset_staff_roles_cache, get_staff_roles

        _reset_staff_roles_cache()
        roles = await get_staff_roles()
        assert roles == frozenset({"coordinator", "instructor", "tutor"})

    @pytest.mark.asyncio
    async def test_get_all_roles_ordered_by_level(self) -> None:
        """get_all_roles() returns all roles ordered by level ascending."""
        from promptgrimoire.db.roles import _reset_all_roles_cache, get_all_roles

        _reset_all_roles_cache()
        roles = await get_all_roles()
        assert roles == ("student", "tutor", "instructor", "coordinator")

    @pytest.mark.asyncio
    async def test_excludes_student(self) -> None:
        """get_staff_roles() does not include student."""
        from promptgrimoire.db.roles import _reset_staff_roles_cache, get_staff_roles

        _reset_staff_roles_cache()
        roles = await get_staff_roles()
        assert "student" not in roles

    @pytest.mark.asyncio
    async def test_cache_returns_same_result(self) -> None:
        """Second call returns cached result without DB query."""
        from promptgrimoire.db.roles import _reset_staff_roles_cache, get_staff_roles

        _reset_staff_roles_cache()
        first = await get_staff_roles()
        second = await get_staff_roles()
        assert first is second  # Same object = cached


class TestWeekVisibilityAfterNormalisation:
    """Verify week visibility works identically after normalisation.

    AC3.2: Instructors see all weeks, students see only published.
    """

    @pytest.mark.asyncio
    async def test_instructor_sees_all_weeks(self) -> None:
        """Instructor enrolled with string role sees all weeks (AC3.2)."""
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User
        from promptgrimoire.db.weeks import create_week, get_visible_weeks, publish_week

        async with get_session() as session:
            user = User(
                email=f"vis-instr-{uuid4().hex[:8]}@example.com",
                display_name="Instructor",
            )
            course = Course(
                code="VIS01",
                name="Visibility",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        await enroll_user(course_id=course.id, user_id=user.id, role="instructor")
        w1 = await create_week(course_id=course.id, week_number=1, title="Published")
        await publish_week(w1.id)
        await create_week(course_id=course.id, week_number=2, title="Unpublished")

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 2

    @pytest.mark.asyncio
    async def test_student_sees_only_published_weeks(self) -> None:
        """Student enrolled with string role sees only published (AC3.2)."""
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, User
        from promptgrimoire.db.weeks import create_week, get_visible_weeks, publish_week

        async with get_session() as session:
            user = User(
                email=f"vis-student-{uuid4().hex[:8]}@example.com",
                display_name="Student",
            )
            course = Course(
                code="VIS02",
                name="Visibility 2",
                semester="2026-S1",
            )
            session.add(user)
            session.add(course)
            await session.flush()

        await enroll_user(course_id=course.id, user_id=user.id, role="student")
        w1 = await create_week(course_id=course.id, week_number=1, title="Published")
        await publish_week(w1.id)
        await create_week(course_id=course.id, week_number=2, title="Unpublished")

        weeks = await get_visible_weeks(course_id=course.id, user_id=user.id)

        assert len(weeks) == 1
        assert weeks[0].title == "Published"
