"""CRUD operations for TagGroup and Tag.

Provides async database functions for tag management within workspaces.
Tags are per-workspace annotation categories; TagGroups visually group them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Tag, TagGroup

if TYPE_CHECKING:
    from uuid import UUID


async def _check_tag_creation_permission(workspace_id: UUID) -> None:
    """Resolve PlacementContext and raise if tag creation is denied.

    Args:
        workspace_id: The workspace to check.

    Raises:
        PermissionError: If allow_tag_creation resolves to False.
    """
    from promptgrimoire.db.workspaces import get_placement_context

    ctx = await get_placement_context(workspace_id)
    if not ctx.allow_tag_creation:
        msg = "Tag creation not allowed on this workspace"
        raise PermissionError(msg)


# ── TagGroup CRUD ────────────────────────────────────────────────────


async def create_tag_group(
    workspace_id: UUID,
    name: str,
    order_index: int = 0,
) -> TagGroup:
    """Create a TagGroup in a workspace.

    Resolves PlacementContext and raises PermissionError if
    allow_tag_creation is False.

    Parameters
    ----------
    workspace_id : UUID
        The parent workspace's UUID.
    name : str
        Display name for the group.
    order_index : int
        Display order within the workspace.

    Returns
    -------
    TagGroup
        The created TagGroup.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        group = TagGroup(
            workspace_id=workspace_id,
            name=name,
            order_index=order_index,
        )
        session.add(group)
        await session.flush()
        await session.refresh(group)
        return group


async def get_tag_group(group_id: UUID) -> TagGroup | None:
    """Get a TagGroup by ID."""
    async with get_session() as session:
        return await session.get(TagGroup, group_id)


async def update_tag_group(
    group_id: UUID,
    name: str | None = None,
    order_index: int | None = None,
) -> TagGroup | None:
    """Update TagGroup details.

    Omit any parameter (or pass None) to leave it unchanged.
    """
    async with get_session() as session:
        group = await session.get(TagGroup, group_id)
        if not group:
            return None

        if name is not None:
            group.name = name
        if order_index is not None:
            group.order_index = order_index

        session.add(group)
        await session.flush()
        await session.refresh(group)
        return group


async def delete_tag_group(group_id: UUID) -> bool:
    """Delete a TagGroup.

    Tags in the group get group_id=NULL via the SET NULL FK constraint.

    Returns True if found and deleted.
    """
    async with get_session() as session:
        group = await session.get(TagGroup, group_id)
        if not group:
            return False

        await session.delete(group)
        return True


async def list_tag_groups_for_workspace(workspace_id: UUID) -> list[TagGroup]:
    """List all TagGroups for a workspace, ordered by order_index."""
    async with get_session() as session:
        result = await session.exec(
            select(TagGroup)
            .where(TagGroup.workspace_id == workspace_id)
            .order_by(TagGroup.order_index)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())


# ── Tag CRUD ─────────────────────────────────────────────────────────


async def create_tag(
    workspace_id: UUID,
    name: str,
    color: str,
    *,
    group_id: UUID | None = None,
    description: str | None = None,
    locked: bool = False,
    order_index: int = 0,
) -> Tag:
    """Create a Tag in a workspace.

    Resolves PlacementContext and raises PermissionError if
    allow_tag_creation is False.

    Parameters
    ----------
    workspace_id : UUID
        The parent workspace's UUID.
    name : str
        Tag display name.
    color : str
        Hex colour string (e.g. "#1f77b4").
    group_id : UUID | None
        Optional TagGroup to place the tag in.
    description : str | None
        Optional longer description.
    locked : bool
        Whether students can modify this tag.
    order_index : int
        Display order within group or workspace.

    Returns
    -------
    Tag
        The created Tag.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        tag = Tag(
            workspace_id=workspace_id,
            name=name,
            color=color,
            group_id=group_id,
            description=description,
            locked=locked,
            order_index=order_index,
        )
        session.add(tag)
        await session.flush()
        await session.refresh(tag)
        return tag


async def get_tag(tag_id: UUID) -> Tag | None:
    """Get a Tag by ID."""
    async with get_session() as session:
        return await session.get(Tag, tag_id)


async def update_tag(
    tag_id: UUID,
    *,
    name: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None
    color: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    group_id: UUID | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    locked: bool | None = None,
) -> Tag | None:
    """Update Tag details.

    Uses the Ellipsis sentinel pattern: omit a parameter to leave it
    unchanged. If the tag is locked, only the ``locked`` field itself
    may be changed (to allow instructor lock toggle); all other field
    changes raise ``ValueError("Tag is locked")``.
    """
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return None

        # Lock enforcement
        if tag.locked:
            has_non_lock_changes = any(
                v is not ... for v in [name, color, description, group_id]
            )
            if has_non_lock_changes:
                msg = "Tag is locked"
                raise ValueError(msg)

        if name is not ...:
            tag.name = name  # type: ignore[assignment]  -- sentinel
        if color is not ...:
            tag.color = color  # type: ignore[assignment]  -- sentinel
        if description is not ...:
            tag.description = description
        if group_id is not ...:
            tag.group_id = group_id
        if locked is not None:
            tag.locked = locked

        session.add(tag)
        await session.flush()
        await session.refresh(tag)
        return tag


async def delete_tag(tag_id: UUID) -> bool:
    """Delete a Tag.

    Checks tag.locked and raises ValueError if locked. Before deleting
    the Tag row, calls _cleanup_crdt_highlights_for_tag() to remove
    CRDT highlights referencing this tag.

    Returns True if found and deleted.
    """
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return False

        if tag.locked:
            msg = "Tag is locked"
            raise ValueError(msg)

        workspace_id = tag.workspace_id
        tag_id_for_cleanup = tag.id

    # CRDT cleanup before row deletion (separate session)
    await _cleanup_crdt_highlights_for_tag(workspace_id, tag_id_for_cleanup)

    # Delete the tag row
    async with get_session() as session:
        tag_row = await session.get(Tag, tag_id_for_cleanup)
        if tag_row:
            await session.delete(tag_row)
            return True
    return False


async def list_tags_for_workspace(workspace_id: UUID) -> list[Tag]:
    """List all Tags for a workspace, ordered by order_index."""
    async with get_session() as session:
        result = await session.exec(
            select(Tag)
            .where(Tag.workspace_id == workspace_id)
            .order_by(Tag.order_index)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())


# ── CRDT cleanup (stub, fully implemented in Task 3) ────────────────


async def _cleanup_crdt_highlights_for_tag(
    workspace_id: UUID,
    tag_id: UUID,
) -> int:
    """Remove CRDT highlights referencing a tag.

    Loads workspace CRDT state, removes highlights matching the tag,
    removes the tag_order entry, and saves the updated state.

    Returns the count of removed highlights.
    """
    _ = workspace_id, tag_id  # Used in full implementation (Task 3)
    return 0
