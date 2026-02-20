"""CRUD operations for Course and CourseEnrollment.

Provides async database functions for course management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Course, CourseEnrollment

if TYPE_CHECKING:
    from uuid import UUID


async def create_course(
    code: str,
    name: str,
    semester: str,
) -> Course:
    """Create a new course.

    Args:
        code: Course code (e.g., "LAWS1100").
        name: Course name (e.g., "Contracts").
        semester: Semester identifier (e.g., "2025-S1").

    Returns:
        The created Course with generated ID.
    """
    async with get_session() as session:
        course = Course(
            code=code,
            name=name,
            semester=semester,
        )
        session.add(course)
        await session.flush()
        await session.refresh(course)
        return course


async def get_course_by_id(course_id: UUID) -> Course | None:
    """Get a course by ID.

    Args:
        course_id: The course UUID.

    Returns:
        The Course or None if not found.
    """
    async with get_session() as session:
        return await session.get(Course, course_id)


async def list_courses(
    semester: str | None = None,
    include_archived: bool = False,
) -> list[Course]:
    """List courses, optionally filtered by semester.

    Args:
        semester: Filter by semester (optional).
        include_archived: Include archived courses (default False).

    Returns:
        List of Course objects ordered by code.
    """
    async with get_session() as session:
        query = select(Course)

        if not include_archived:
            query = query.where(Course.is_archived == False)  # noqa: E712

        if semester:
            query = query.where(Course.semester == semester)

        query = query.order_by(Course.code)

        result = await session.exec(query)
        return list(result.all())


async def update_course(
    course_id: UUID,
    name: str | None = None,
    default_copy_protection: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    default_allow_sharing: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    default_allow_tag_creation: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
) -> Course | None:
    """Update a course's mutable fields.

    Uses Ellipsis sentinel to distinguish 'not provided' from explicit values.
    Pass default_copy_protection=True/False to change, or omit to leave unchanged.
    Pass default_allow_sharing=True/False to change, or omit to leave unchanged.
    Pass default_allow_tag_creation=True/False to change, or omit to leave unchanged.

    Args:
        course_id: The course UUID.
        name: New course name, or None to leave unchanged.
        default_copy_protection: New default copy protection value,
            or omit (Ellipsis) to leave unchanged.
        default_allow_sharing: New default sharing value,
            or omit (Ellipsis) to leave unchanged.
        default_allow_tag_creation: New default tag creation permission,
            or omit (Ellipsis) to leave unchanged.

    Returns:
        The updated Course, or None if not found.
    """
    async with get_session() as session:
        course = await session.get(Course, course_id)
        if course is None:
            return None
        if name is not None:
            course.name = name
        if default_copy_protection is not ...:
            course.default_copy_protection = default_copy_protection
        if default_allow_sharing is not ...:
            course.default_allow_sharing = default_allow_sharing
        if default_allow_tag_creation is not ...:
            course.default_allow_tag_creation = default_allow_tag_creation
        session.add(course)
        await session.flush()
        await session.refresh(course)
        return course


async def archive_course(course_id: UUID) -> bool:
    """Archive a course (soft delete).

    Args:
        course_id: The course UUID.

    Returns:
        True if archived, False if not found.
    """
    async with get_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            return False
        course.is_archived = True
        session.add(course)
        return True


class DuplicateEnrollmentError(Exception):
    """Raised when attempting to enroll a user who is already enrolled."""

    def __init__(self, course_id: UUID, user_id: UUID) -> None:
        self.course_id = course_id
        self.user_id = user_id
        super().__init__(f"User {user_id} is already enrolled in course {course_id}")


async def enroll_user(
    course_id: UUID,
    user_id: UUID,
    role: str = "student",
) -> CourseEnrollment:
    """Enroll a user in a course.

    Args:
        course_id: The course UUID.
        user_id: The user's UUID.
        role: Course-level role (default: student).

    Returns:
        The created CourseEnrollment.

    Raises:
        DuplicateEnrollmentError: If user is already enrolled in this course.
    """
    async with get_session() as session:
        # Check for existing enrollment within same transaction
        existing = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        if existing.first():
            raise DuplicateEnrollmentError(course_id, user_id)

        enrollment = CourseEnrollment(
            course_id=course_id,
            user_id=user_id,
            role=role,
        )
        session.add(enrollment)
        try:
            await session.flush()
        except IntegrityError as e:
            # Handle race condition: another transaction won the insert
            if "uq_course_enrollment_course_user" in str(e):
                raise DuplicateEnrollmentError(course_id, user_id) from e
            raise
        await session.refresh(enrollment)
        return enrollment


async def get_enrollment(
    course_id: UUID,
    user_id: UUID,
) -> CourseEnrollment | None:
    """Get enrollment for a user in a course.

    Args:
        course_id: The course UUID.
        user_id: The user's UUID.

    Returns:
        The CourseEnrollment or None if not enrolled.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        return result.first()


async def list_user_enrollments(user_id: UUID) -> list[CourseEnrollment]:
    """List all course enrollments for a user.

    Args:
        user_id: The user's UUID.

    Returns:
        List of CourseEnrollment objects.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.user_id == user_id)
            .order_by("created_at")
        )
        return list(result.all())


async def list_course_enrollments(course_id: UUID) -> list[CourseEnrollment]:
    """List all enrollments for a course.

    Args:
        course_id: The course UUID.

    Returns:
        List of CourseEnrollment objects.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .order_by("role", "user_id")
        )
        return list(result.all())


async def unenroll_user(
    course_id: UUID,
    user_id: UUID,
) -> bool:
    """Remove a user from a course.

    Args:
        course_id: The course UUID.
        user_id: The user's UUID.

    Returns:
        True if removed, False if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        enrollment = result.first()
        if not enrollment:
            return False
        await session.delete(enrollment)
        return True


async def update_user_role(
    course_id: UUID,
    user_id: UUID,
    role: str,
) -> CourseEnrollment | None:
    """Update a user's role in a course.

    Args:
        course_id: The course UUID.
        user_id: The user's UUID.
        role: New course-level role.

    Returns:
        Updated CourseEnrollment or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        enrollment = result.first()
        if not enrollment:
            return None
        enrollment.role = role
        session.add(enrollment)
        await session.flush()
        await session.refresh(enrollment)
        return enrollment
