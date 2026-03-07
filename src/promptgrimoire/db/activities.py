"""CRUD operations for Activity.

Provides async database functions for activity management.
Activities are assignments within Weeks that own template workspaces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import DeletionBlockedError
from promptgrimoire.db.models import Activity, Week, Workspace
from promptgrimoire.db.weeks import purge_activity
from promptgrimoire.db.workspaces import has_student_workspaces

if TYPE_CHECKING:
    from uuid import UUID


async def create_activity(
    week_id: UUID,
    title: str,
    description: str | None = None,
    copy_protection: bool | None = None,
    allow_tag_creation: bool | None = None,
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
    allow_tag_creation : bool | None
        Tri-state tag creation permission. None=inherit from course,
        True=allowed, False=not allowed.

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
            type="annotation",
            title=title,
            description=description,
            copy_protection=copy_protection,
            allow_tag_creation=allow_tag_creation,
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


def validate_word_count_limits(
    *, word_minimum: int | None, word_limit: int | None
) -> None:
    """Validate that word_minimum < word_limit when both are set.

    Parameters
    ----------
    word_minimum : int | None
        Minimum word count (None = no minimum).
    word_limit : int | None
        Maximum word count (None = no limit).

    Raises
    ------
    ValueError
        If both are set and word_minimum >= word_limit.
    """
    if (
        word_minimum is not None
        and word_limit is not None
        and word_minimum >= word_limit
    ):
        msg = "word_minimum must be less than word_limit"
        raise ValueError(msg)


async def get_activity(activity_id: UUID) -> Activity | None:
    """Get an activity by ID."""
    async with get_session() as session:
        return await session.get(Activity, activity_id)


def _apply_sentinel_fields(model: Activity, **fields: object) -> None:
    """Set model attributes for non-sentinel values.

    Each kwarg whose value is not ``...`` (Ellipsis) is assigned
    to the corresponding attribute on *model*.
    """
    for attr, value in fields.items():
        if value is not ...:
            setattr(model, attr, value)


async def update_activity(
    activity_id: UUID,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (clear description)
    copy_protection: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    allow_sharing: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    anonymous_sharing: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    allow_tag_creation: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
    word_minimum: int | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (clear minimum)
    word_limit: int | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (clear limit)
    word_limit_enforcement: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (reset to inherit)
) -> Activity | None:
    """Update activity details.

    Use description=None to clear it.
    Use copy_protection=None / allow_sharing=None / anonymous_sharing=None /
    allow_tag_creation=None / word_limit_enforcement=None to reset to inherit
    from course.
    Use word_minimum=None / word_limit=None to clear the limit.
    Omit any parameter (or pass ...) to leave it unchanged.

    Raises
    ------
    ValueError
        If the resolved word_minimum >= word_limit (when both are set).
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return None

        if title is not None:
            activity.title = title

        # Apply sentinel-guarded partial updates: Ellipsis means "not provided".
        _apply_sentinel_fields(
            activity,
            description=description,
            copy_protection=copy_protection,
            allow_sharing=allow_sharing,
            anonymous_sharing=anonymous_sharing,
            allow_tag_creation=allow_tag_creation,
            word_minimum=word_minimum,
            word_limit=word_limit,
            word_limit_enforcement=word_limit_enforcement,
        )

        # Cross-field validation on the resolved state
        validate_word_count_limits(
            word_minimum=activity.word_minimum,
            word_limit=activity.word_limit,
        )

        activity.updated_at = datetime.now(UTC)
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def delete_activity(
    activity_id: UUID,
    *,
    force: bool = False,
) -> bool:
    """Delete an activity and its template workspace.

    When ``force=False`` (default), raises
    :class:`~promptgrimoire.db.exceptions.DeletionBlockedError` if
    student workspaces exist under this activity.  When ``force=True``,
    student workspaces are deleted first, then the activity.

    Delegates FK-ordered deletion to :func:`purge_activity`.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return False

        # Guard: check for student workspaces
        count = await has_student_workspaces(activity_id)
        if count > 0 and not force:
            raise DeletionBlockedError(
                student_workspace_count=count,
            )

        # Delegate FK-ordered deletion to shared helper
        await purge_activity(session, activity)

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
