"""CRUD operations for Course and CourseEnrollment.

Provides async database functions for course management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import DeletionBlockedError
from promptgrimoire.db.models import (
    Activity,
    Course,
    CourseEnrollment,
    User,
    Week,
    Workspace,
)
from promptgrimoire.db.weeks import purge_activity
from promptgrimoire.db.workspaces import has_student_workspaces

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


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
    default_anonymous_sharing: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    default_allow_tag_creation: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    default_word_limit_enforcement: bool = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
) -> Course | None:
    """Update a course's mutable fields.

    Uses Ellipsis sentinel to distinguish 'not provided' from explicit values.
    Pass default_copy_protection=True/False to change, or omit to leave unchanged.
    Pass default_allow_sharing=True/False to change, or omit to leave unchanged.
    Pass default_anonymous_sharing=True/False to change, or omit to leave unchanged.
    Pass default_allow_tag_creation=True/False to change, or omit to leave unchanged.
    Pass default_word_limit_enforcement=True/False to change, or omit to
    leave unchanged.

    Args:
        course_id: The course UUID.
        name: New course name, or None to leave unchanged.
        default_copy_protection: New default copy protection value,
            or omit (Ellipsis) to leave unchanged.
        default_allow_sharing: New default sharing value,
            or omit (Ellipsis) to leave unchanged.
        default_anonymous_sharing: New default anonymous sharing value,
            or omit (Ellipsis) to leave unchanged.
        default_allow_tag_creation: New default tag creation permission,
            or omit (Ellipsis) to leave unchanged.
        default_word_limit_enforcement: New default word limit enforcement,
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
        if default_anonymous_sharing is not ...:
            course.default_anonymous_sharing = default_anonymous_sharing
        if default_allow_tag_creation is not ...:
            course.default_allow_tag_creation = default_allow_tag_creation
        if default_word_limit_enforcement is not ...:
            course.default_word_limit_enforcement = default_word_limit_enforcement
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


async def _fetch_course_children(
    session: AsyncSession,
    course_id: UUID,
) -> tuple[list[Week], list[Activity]]:
    """Fetch weeks and activities for a course within a session.

    Returns:
        Tuple of (weeks, activities) attached to the given session.
    """
    week_rows = await session.exec(select(Week).where(Week.course_id == course_id))
    weeks = list(week_rows.all())

    week_ids = [w.id for w in weeks]
    if not week_ids:
        return weeks, []

    activity_rows = await session.exec(
        select(Activity).where(
            Activity.week_id.in_(week_ids)  # type: ignore[union-attr]  -- Column has .in_()
        )
    )
    return weeks, list(activity_rows.all())


async def delete_course(
    course_id: UUID,
    *,
    force: bool = False,
) -> bool:
    """Delete a course and all its weeks, activities, and workspaces.

    When ``force=False`` (default), raises
    :class:`~promptgrimoire.db.exceptions.DeletionBlockedError` if any
    activity in this course has student workspaces.  The error carries
    the aggregate count across all activities in all weeks.

    When ``force=True``, student workspaces are deleted first, then each
    activity is removed with proper FK ordering (activity first to SET
    NULL workspace.activity_id, then template workspace), then loose
    workspaces (course-placed, activity_id IS NULL) are removed, then
    weeks, then the course itself.

    The UI layer handles role checking (admin or coordinator).  This
    function does NOT check roles -- that is a UI-layer concern.

    Args:
        course_id: The course UUID.
        force: If True, force-delete even with student workspaces.

    Returns:
        True if deleted, False if not found.
    """
    async with get_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            return False

        weeks, activities = await _fetch_course_children(session, course_id)

        # Guard: aggregate student workspace count
        # TODO(perf): N+1 sessions — has_student_workspaces opens
        # its own session per call. Replace with single GROUP BY
        # query if activity counts grow.
        total_students = 0
        for act in activities:
            total_students += await has_student_workspaces(act.id)

        if total_students > 0 and not force:
            raise DeletionBlockedError(
                student_workspace_count=total_students,
            )

        # Purge each activity with proper FK ordering
        for act in activities:
            await purge_activity(session, act)

        # Delete loose workspaces (course-placed, no activity)
        loose_rows = await session.exec(
            select(Workspace).where(
                Workspace.course_id == course_id,
                Workspace.activity_id.is_(None),  # type: ignore[union-attr]  -- Column has .is_()
            )
        )
        for ws in loose_rows.all():
            await session.delete(ws)
        await session.flush()

        # Delete weeks
        for wk in weeks:
            await session.delete(wk)
        await session.flush()

        # Delete the course itself
        await session.delete(course)

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
        return await _enroll_user_with_session(session, course_id, user_id, role)


async def _enroll_user_with_session(
    session: AsyncSession,
    course_id: UUID,
    user_id: UUID,
    role: str = "student",
) -> CourseEnrollment:
    """Enrol a user within a caller-owned session.

    Raises:
        DuplicateEnrollmentError: If already enrolled.
    """
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


async def list_enrollment_rows(course_id: UUID) -> list[dict[str, Any]]:
    """Return enrollment + user data as table-ready dicts.

    Single joined query — no N+1. Each dict contains keys:
    email, display_name, student_id, role, created_at (ISO string), user_id (string).

    Args:
        course_id: The course UUID.

    Returns:
        List of dicts ready for ui.table rows parameter.
    """
    async with get_session() as session:
        result = await session.exec(
            select(CourseEnrollment, User)
            .join(User, User.id == CourseEnrollment.user_id)  # type: ignore[arg-type]
            .where(CourseEnrollment.course_id == course_id)
            .order_by(CourseEnrollment.role, User.display_name)  # type: ignore[arg-type]
        )
        return [
            {
                "email": user.email,
                "display_name": user.display_name,
                "student_id": user.student_id or "",
                "role": enrollment.role,
                "created_at": enrollment.created_at.isoformat(),
                "user_id": str(enrollment.user_id),
            }
            for enrollment, user in result.all()
        ]


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


_ZERO_WORKSPACE_SQL = """\
SELECT u.display_name, u.email
FROM course_enrollment ce
JOIN "user" u ON u.id = ce.user_id
JOIN course_role cr ON cr.name = ce.role
WHERE ce.course_id = :course_id
  AND cr.is_staff = false
  AND NOT EXISTS (
    SELECT 1
    FROM acl_entry acl
    JOIN workspace w ON w.id = acl.workspace_id
    LEFT JOIN activity a ON a.id = w.activity_id
    LEFT JOIN week wk ON wk.id = a.week_id
    WHERE acl.user_id = ce.user_id
      AND acl.permission = 'owner'
      AND (wk.course_id = ce.course_id OR w.course_id = ce.course_id)
  )
ORDER BY u.display_name
"""


async def list_students_without_workspaces(
    course_id: UUID,
) -> list[tuple[str, str]]:
    """List students enrolled in a course who own no workspaces.

    Returns (display_name, email) tuples for students with zero
    activity-placed or loose workspaces in the given course.
    Staff roles are excluded.

    See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/198
    for a proper analytics page.
    """
    async with get_session() as session:
        result = await session.execute(
            text(_ZERO_WORKSPACE_SQL),
            {"course_id": course_id},
        )
        return [(row[0], row[1]) for row in result.all()]
