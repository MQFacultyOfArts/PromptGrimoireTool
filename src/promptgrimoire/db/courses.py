"""CRUD operations for Course and CourseEnrollment.

Provides async database functions for course management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Course, CourseEnrollment, CourseRole


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


async def enroll_member(
    course_id: UUID,
    member_id: str,
    role: CourseRole = CourseRole.student,
) -> CourseEnrollment:
    """Enroll a member in a course.

    Args:
        course_id: The course UUID.
        member_id: Stytch member_id.
        role: Course-level role (default: student).

    Returns:
        The created CourseEnrollment.
    """
    async with get_session() as session:
        enrollment = CourseEnrollment(
            course_id=course_id,
            member_id=member_id,
            role=role,
        )
        session.add(enrollment)
        await session.flush()
        await session.refresh(enrollment)
        return enrollment


async def get_enrollment(
    course_id: UUID,
    member_id: str,
) -> CourseEnrollment | None:
    """Get enrollment for a member in a course.

    Args:
        course_id: The course UUID.
        member_id: Stytch member_id.

    Returns:
        The CourseEnrollment or None if not enrolled.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.member_id == member_id)
        )
        return result.first()


async def list_member_enrollments(member_id: str) -> list[CourseEnrollment]:
    """List all course enrollments for a member.

    Args:
        member_id: Stytch member_id.

    Returns:
        List of CourseEnrollment objects.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.member_id == member_id)
            .order_by(CourseEnrollment.created_at)
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
            .order_by(CourseEnrollment.role, CourseEnrollment.member_id)
        )
        return list(result.all())


async def unenroll_member(
    course_id: UUID,
    member_id: str,
) -> bool:
    """Remove a member from a course.

    Args:
        course_id: The course UUID.
        member_id: Stytch member_id.

    Returns:
        True if removed, False if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.member_id == member_id)
        )
        enrollment = result.first()
        if not enrollment:
            return False
        await session.delete(enrollment)
        return True


async def update_member_role(
    course_id: UUID,
    member_id: str,
    role: CourseRole,
) -> CourseEnrollment | None:
    """Update a member's role in a course.

    Args:
        course_id: The course UUID.
        member_id: Stytch member_id.
        role: New course-level role.

    Returns:
        Updated CourseEnrollment or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.member_id == member_id)
        )
        enrollment = result.first()
        if not enrollment:
            return None
        enrollment.role = role
        session.add(enrollment)
        await session.flush()
        await session.refresh(enrollment)
        return enrollment
