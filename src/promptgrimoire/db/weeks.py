"""CRUD operations for Week with visibility logic.

Provides async database functions for week management.
Handles student visibility based on is_published and visible_from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import or_, select

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import CourseEnrollment, Week


async def create_week(
    course_id: UUID,
    week_number: int,
    title: str,
) -> Week:
    """Create a new week in a course.

    Args:
        course_id: The course UUID.
        week_number: Week number (1-52).
        title: Week title.

    Returns:
        The created Week with generated ID.
    """
    async with get_session() as session:
        week = Week(
            course_id=course_id,
            week_number=week_number,
            title=title,
        )
        session.add(week)
        await session.flush()
        await session.refresh(week)
        return week


async def get_week_by_id(week_id: UUID) -> Week | None:
    """Get a week by ID.

    Args:
        week_id: The week UUID.

    Returns:
        The Week or None if not found.
    """
    async with get_session() as session:
        return await session.get(Week, week_id)


async def list_weeks(course_id: UUID) -> list[Week]:
    """List all weeks for a course, ordered by week number.

    Args:
        course_id: The course UUID.

    Returns:
        List of Week objects ordered by week_number.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Week).where(Week.course_id == course_id).order_by("week_number")
        )
        return list(result.all())


async def publish_week(week_id: UUID) -> bool:
    """Publish a week (make visible to students).

    Args:
        week_id: The week UUID.

    Returns:
        True if published, False if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False
        week.is_published = True
        session.add(week)
        return True


async def unpublish_week(week_id: UUID) -> bool:
    """Unpublish a week (hide from students).

    Args:
        week_id: The week UUID.

    Returns:
        True if unpublished, False if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False
        week.is_published = False
        session.add(week)
        return True


async def schedule_week_visibility(
    week_id: UUID,
    visible_from: datetime,
) -> bool:
    """Schedule when a week becomes visible to students.

    The week must also be published for this to take effect.

    Args:
        week_id: The week UUID.
        visible_from: When the week becomes visible (UTC).

    Returns:
        True if scheduled, False if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False
        week.visible_from = visible_from
        session.add(week)
        return True


async def clear_week_schedule(week_id: UUID) -> bool:
    """Clear the visibility schedule (visible immediately when published).

    Args:
        week_id: The week UUID.

    Returns:
        True if cleared, False if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False
        week.visible_from = None
        session.add(week)
        return True


async def update_week(
    week_id: UUID,
    title: str | None = None,
    week_number: int | None = None,
) -> Week | None:
    """Update week details.

    Args:
        week_id: The week UUID.
        title: New title (optional).
        week_number: New week number (optional).

    Returns:
        Updated Week or None if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return None

        if title is not None:
            week.title = title
        if week_number is not None:
            week.week_number = week_number

        session.add(week)
        await session.flush()
        await session.refresh(week)
        return week


async def delete_week(week_id: UUID) -> bool:
    """Delete a week.

    Args:
        week_id: The week UUID.

    Returns:
        True if deleted, False if not found.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False
        await session.delete(week)
        return True


async def get_visible_weeks(
    course_id: UUID,
    user_id: UUID,
) -> list[Week]:
    """Get weeks visible to a user based on their enrollment role.

    Visibility rules:
    - coordinator/instructor/tutor: See all weeks
    - student: See only published weeks where visible_from has passed
    - Not enrolled: See no weeks

    Args:
        course_id: The course UUID.
        user_id: The user's UUID.

    Returns:
        List of visible Week objects ordered by week_number.
    """
    async with get_session() as session:
        # Check enrollment within the same transaction
        enrollment_result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        enrollment = enrollment_result.first()
        if not enrollment:
            return []

        # Instructors and above see all weeks
        if enrollment.role in ("coordinator", "instructor", "tutor"):
            result = await session.exec(
                select(Week).where(Week.course_id == course_id).order_by("week_number")
            )
            return list(result.all())

        # Students see published weeks where visible_from has passed
        now = datetime.now(UTC)
        result = await session.exec(
            select(Week)
            .where(Week.course_id == course_id)
            .where(Week.is_published == True)  # noqa: E712
            .where(
                or_(
                    Week.visible_from == None,  # noqa: E711
                    Week.visible_from <= now,  # type: ignore[operator]  # or_ handles None
                )
            )
            .order_by("week_number")
        )
        return list(result.all())


async def can_access_week(
    week_id: UUID,
    user_id: UUID,
) -> bool:
    """Check if a user can access a specific week.

    Args:
        week_id: The week UUID.
        user_id: The user's UUID.

    Returns:
        True if the user can access the week.
    """
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False

        # Check enrollment within the same transaction
        enrollment_result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == week.course_id)
            .where(CourseEnrollment.user_id == user_id)
        )
        enrollment = enrollment_result.first()
        if not enrollment:
            return False

        # Instructors always have access
        if enrollment.role in ("coordinator", "instructor", "tutor"):
            return True

        # Students need published + visible
        if not week.is_published:
            return False

        return not (week.visible_from and week.visible_from > datetime.now(UTC))
