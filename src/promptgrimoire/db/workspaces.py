"""CRUD operations for Workspace.

Provides async database functions for workspace management.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Activity, Course, Workspace

if TYPE_CHECKING:
    from uuid import UUID


async def create_workspace() -> Workspace:
    """Create a new workspace.

    Returns:
        The created Workspace with generated ID.
    """
    async with get_session() as session:
        workspace = Workspace()
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def get_workspace(workspace_id: UUID) -> Workspace | None:
    """Get a workspace by ID.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The Workspace or None if not found.
    """
    async with get_session() as session:
        return await session.get(Workspace, workspace_id)


async def delete_workspace(workspace_id: UUID) -> None:
    """Delete a workspace and all its documents (CASCADE).

    Args:
        workspace_id: The workspace UUID.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            await session.delete(workspace)


async def save_workspace_crdt_state(workspace_id: UUID, crdt_state: bytes) -> bool:
    """Save CRDT state to a workspace.

    Args:
        workspace_id: The workspace UUID.
        crdt_state: Serialized pycrdt state bytes.

    Returns:
        True if workspace was found and updated, False otherwise.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.crdt_state = crdt_state
            workspace.updated_at = datetime.now(UTC)
            session.add(workspace)
            return True
        return False


async def place_workspace_in_activity(
    workspace_id: UUID,
    activity_id: UUID,
) -> Workspace:
    """Place a workspace in an Activity.

    Sets activity_id and clears course_id (mutual exclusivity).

    Args:
        workspace_id: The workspace UUID.
        activity_id: The activity UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace or activity not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        activity = await session.get(Activity, activity_id)
        if not activity:
            msg = f"Activity {activity_id} not found"
            raise ValueError(msg)

        workspace.activity_id = activity_id
        workspace.course_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def place_workspace_in_course(
    workspace_id: UUID,
    course_id: UUID,
) -> Workspace:
    """Place a workspace in a Course (loose association).

    Sets course_id and clears activity_id (mutual exclusivity).

    Args:
        workspace_id: The workspace UUID.
        course_id: The course UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace or course not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        course = await session.get(Course, course_id)
        if not course:
            msg = f"Course {course_id} not found"
            raise ValueError(msg)

        workspace.course_id = course_id
        workspace.activity_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def make_workspace_loose(workspace_id: UUID) -> Workspace:
    """Remove a workspace from any Activity or Course placement.

    Clears both activity_id and course_id.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace not found.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)

        workspace.activity_id = None
        workspace.course_id = None
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def list_workspaces_for_activity(
    activity_id: UUID,
) -> list[Workspace]:
    """List all workspaces placed in an Activity.

    Args:
        activity_id: The activity UUID.

    Returns:
        List of Workspaces ordered by created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .where(Workspace.activity_id == activity_id)
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())


async def list_loose_workspaces_for_course(
    course_id: UUID,
) -> list[Workspace]:
    """List workspaces associated with a Course but not in an Activity.

    The activity_id == None filter is defense-in-depth. The mutual
    exclusivity constraint guarantees that course_id being set implies
    activity_id is None, but the explicit filter protects against
    constraint violations and makes the query intent clear.

    Args:
        course_id: The course UUID.

    Returns:
        List of loose Workspaces ordered by created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .where(Workspace.course_id == course_id)
            .where(Workspace.activity_id == None)  # noqa: E711
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())
