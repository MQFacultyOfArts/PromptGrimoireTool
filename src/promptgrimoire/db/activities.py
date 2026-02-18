"""CRUD operations for Activity.

Provides async database functions for activity management.
Activities are assignments within Weeks that own template workspaces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Activity, Week, Workspace

if TYPE_CHECKING:
    from uuid import UUID


async def create_activity(
    week_id: UUID,
    title: str,
    description: str | None = None,
    copy_protection: bool | None = None,
) -> Activity:
    """Create a new activity with its template workspace atomically.

    Creates a Workspace first, then the Activity referencing it.
    Both operations are within a single session (atomic).

    Parameters
    ----------
    week_id : UUID
        The parent week's UUID.
    title : str
        Activity title.
    description : str | None
        Optional markdown description.
    copy_protection : bool | None
        Tri-state copy protection. None=inherit from course,
        True=on, False=off.

    Returns
    -------
    Activity
        The created Activity with template_workspace_id set.
    """
    async with get_session() as session:
        template = Workspace()
        session.add(template)
        await session.flush()

        activity = Activity(
            week_id=week_id,
            title=title,
            description=description,
            copy_protection=copy_protection,
            template_workspace_id=template.id,
        )
        session.add(activity)
        await session.flush()

        # Back-link: template workspace belongs to this activity
        template.activity_id = activity.id
        session.add(template)
        await session.flush()

        await session.refresh(activity)
        return activity


async def get_activity(activity_id: UUID) -> Activity | None:
    """Get an activity by ID."""
    async with get_session() as session:
        return await session.get(Activity, activity_id)


async def update_activity(
    activity_id: UUID,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (clear description)
    copy_protection: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    allow_sharing: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    allow_tag_creation: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
) -> Activity | None:
    """Update activity details.

    Use description=None to clear it.
    Use copy_protection=None / allow_sharing=None / allow_tag_creation=None
    to reset to inherit from course.
    Omit any parameter (or pass ...) to leave it unchanged.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return None

        if title is not None:
            activity.title = title
        if description is not ...:
            activity.description = description
        if copy_protection is not ...:
            activity.copy_protection = copy_protection
        if allow_sharing is not ...:
            activity.allow_sharing = allow_sharing
        if allow_tag_creation is not ...:
            activity.allow_tag_creation = allow_tag_creation

        activity.updated_at = datetime.now(UTC)
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def delete_activity(activity_id: UUID) -> bool:
    """Delete an activity and its template workspace.

    Deletion order matters due to circular FKs:
    1. Delete Activity first -- this triggers SET NULL on any
       student workspace.activity_id references.
    2. Then delete the orphaned template Workspace, which is now
       safe because no RESTRICT FK points to it.

    (Activity.template_workspace_id uses RESTRICT, so deleting
    the Workspace first would be blocked while the Activity exists.)
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return False

        template_workspace_id = activity.template_workspace_id
        await session.delete(activity)
        await session.flush()

        template = await session.get(Workspace, template_workspace_id)
        if template:
            await session.delete(template)

        return True


async def list_activities_for_week(week_id: UUID) -> list[Activity]:
    """List all activities for a week, ordered by created_at."""
    async with get_session() as session:
        result = await session.exec(
            select(Activity)
            .where(Activity.week_id == week_id)
            .order_by(Activity.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())


async def list_activities_for_course(course_id: UUID) -> list[Activity]:
    """List all activities for a course (via Week join).

    Returns activities across all weeks, ordered by week number then created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Activity)
            .join(Week, Activity.week_id == Week.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement, not bool
            .where(Week.course_id == course_id)
            .order_by(Week.week_number, Activity.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())
