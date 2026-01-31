"""CRUD operations for Workspace.

Provides async database functions for workspace management.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Workspace

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
