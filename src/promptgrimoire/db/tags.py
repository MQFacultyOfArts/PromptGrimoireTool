"""CRUD operations for TagGroup and Tag.

Provides async database functions for tag management within workspaces.
Tags are per-workspace annotation categories; TagGroups visually group them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Tag, TagGroup

logger = logging.getLogger(__name__)

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
    order_index: int | None = None,
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
    order_index : int | None
        Display order within the workspace.
        ``None`` (default) appends after existing groups.

    Returns
    -------
    TagGroup
        The created TagGroup.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        if order_index is None:
            from sqlalchemy import func

            result = await session.exec(
                select(func.max(TagGroup.order_index)).where(
                    TagGroup.workspace_id == workspace_id
                )
            )
            max_idx = result.one_or_none()
            order_index = (max_idx or 0) + 1

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


_UNSET = object()


async def update_tag_group(
    group_id: UUID,
    name: str | None = None,
    order_index: int | None = None,
    # ``color`` uses the ``_UNSET`` object sentinel (not ``...``) because the
    # parameter lives in the public function signature where ``Ellipsis`` as a
    # default looks unusual to callers.  The ``_UNSET`` name makes the intent
    # ("omitted") explicit.  ``update_tag`` uses ``...`` (Ellipsis) for the
    # same purpose in an internal helper -- both patterns are valid, but we keep
    # them separate here for readability.
    color: str | None | object = _UNSET,
) -> TagGroup | None:
    """Update TagGroup details.

    Omit any parameter (or pass None) to leave it unchanged.
    ``color`` uses a sentinel default so that passing ``None`` explicitly
    clears the colour.
    """
    async with get_session() as session:
        group = await session.get(TagGroup, group_id)
        if not group:
            return None

        if name is not None:
            group.name = name
        if order_index is not None:
            group.order_index = order_index
        if color is not _UNSET:
            group.color = color  # type: ignore[assignment]  -- sentinel pattern

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
    order_index: int | None = None,
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
    order_index : int | None
        Display order within group or workspace.
        ``None`` (default) appends after existing tags.

    Returns
    -------
    Tag
        The created Tag.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        if order_index is None:
            from sqlalchemy import func

            result = await session.exec(
                select(func.max(Tag.order_index)).where(
                    Tag.workspace_id == workspace_id
                )
            )
            max_idx = result.one_or_none()
            order_index = (max_idx or 0) + 1

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
    bypass_lock: bool = False,
) -> Tag | None:
    """Update Tag details.

    Uses the Ellipsis sentinel pattern: omit a parameter to leave it
    unchanged. If the tag is locked, only the ``locked`` field itself
    may be changed (to allow instructor lock toggle); all other field
    changes raise ``ValueError("Tag is locked")``.

    Pass ``bypass_lock=True`` to allow instructors to edit locked tags.
    """
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return None

        # Lock enforcement (skipped for instructors via bypass_lock)
        if tag.locked and not bypass_lock:
            has_non_lock_changes = any(
                v is not ... for v in [name, color, description, group_id]
            )
            if has_non_lock_changes:
                msg = "Tag is locked"
                raise ValueError(msg)

        if name is not ...:
            tag.name = name  # type: ignore[assignment]  -- Ellipsis sentinel already checked above
        if color is not ...:
            tag.color = color  # type: ignore[assignment]  -- Ellipsis sentinel already checked above
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


async def delete_tag(tag_id: UUID, *, bypass_lock: bool = False) -> bool:
    """Delete a Tag.

    Checks tag.locked and raises ValueError if locked (unless
    ``bypass_lock=True`` for instructor operations). Before deleting
    the Tag row, calls _cleanup_crdt_highlights_for_tag() to remove
    CRDT highlights referencing this tag.

    Returns True if found and deleted.

    Note: Uses three separate sessions (read, CRDT cleanup, delete) rather
    than one long transaction. If the process crashes between CRDT cleanup
    and row deletion, the tag row survives but its highlights are already
    removed. This is recoverable by re-calling delete_tag(). The split is
    intentional to avoid holding a transaction across the CRDT serialisation.
    """
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return False

        if tag.locked and not bypass_lock:
            msg = "Tag is locked"
            raise ValueError(msg)

        workspace_id = tag.workspace_id
        tag_id_for_cleanup = tag.id

    # CRDT cleanup before row deletion (separate session)
    await _cleanup_crdt_highlights_for_tag(workspace_id, tag_id_for_cleanup)

    # Delete the tag row (separate session — see docstring)
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


# ── Reorder ──────────────────────────────────────────────────────────


async def reorder_tags(tag_ids: list[UUID]) -> None:
    """Set tag order_index values to match the given list order.

    Takes an ordered list of tag UUIDs and sets each tag's
    order_index to its position in the list (0, 1, 2, ...).

    Args:
        tag_ids: Ordered list of tag UUIDs.

    Raises:
        ValueError: If any tag ID is not found.
    """
    async with get_session() as session:
        for idx, tid in enumerate(tag_ids):
            tag = await session.get(Tag, tid)
            if not tag:
                msg = f"Tag {tid} not found"
                raise ValueError(msg)
            tag.order_index = idx
            session.add(tag)
        await session.flush()


async def reorder_tag_groups(group_ids: list[UUID]) -> None:
    """Set tag group order_index values to match the given list order.

    Takes an ordered list of TagGroup UUIDs and sets each group's
    order_index to its position in the list (0, 1, 2, ...).

    Args:
        group_ids: Ordered list of TagGroup UUIDs.

    Raises:
        ValueError: If any group ID is not found.
    """
    async with get_session() as session:
        for idx, gid in enumerate(group_ids):
            group = await session.get(TagGroup, gid)
            if not group:
                msg = f"TagGroup {gid} not found"
                raise ValueError(msg)
            group.order_index = idx
            session.add(group)
        await session.flush()


# ── Import from activity ─────────────────────────────────────────────


async def import_tags_from_activity(
    source_activity_id: UUID,
    target_workspace_id: UUID,
) -> list[Tag]:
    """Copy TagGroups and Tags from a source activity's template into a workspace.

    Creates independent copies with new UUIDs, preserving name, color,
    description, locked, order_index, and group assignment (remapped to
    new group UUIDs).

    This follows the same ID-remapping pattern as
    ``clone_workspace_from_activity()`` in ``db/workspaces.py``.

    Args:
        source_activity_id: Activity whose template workspace to copy from.
        target_workspace_id: Workspace to copy tags into.

    Returns:
        List of newly created Tags in the target workspace.

    Raises:
        ValueError: If source activity is not found.
    """
    from promptgrimoire.db.models import Activity

    async with get_session() as session:
        activity = await session.get(Activity, source_activity_id)
        if not activity:
            msg = f"Activity {source_activity_id} not found"
            raise ValueError(msg)

        source_workspace_id = activity.template_workspace_id

        # Load source groups
        source_groups = list(
            (
                await session.exec(
                    select(TagGroup)
                    .where(TagGroup.workspace_id == source_workspace_id)
                    .order_by(TagGroup.order_index)  # type: ignore[arg-type]  -- SQLModel order_by() stubs
                )
            ).all()
        )

        # Load source tags
        source_tags = list(
            (
                await session.exec(
                    select(Tag)
                    .where(Tag.workspace_id == source_workspace_id)
                    .order_by(Tag.order_index)  # type: ignore[arg-type]  -- SQLModel order_by() stubs
                )
            ).all()
        )

        # Create new groups with ID remapping
        group_id_map: dict[UUID, UUID] = {}
        for src_group in source_groups:
            new_group = TagGroup(
                workspace_id=target_workspace_id,
                name=src_group.name,
                color=src_group.color,
                order_index=src_group.order_index,
            )
            session.add(new_group)
            await session.flush()
            group_id_map[src_group.id] = new_group.id

        # Create new tags with remapped group_id
        new_tags: list[Tag] = []
        for src_tag in source_tags:
            new_group_id = (
                group_id_map.get(src_tag.group_id) if src_tag.group_id else None
            )
            new_tag = Tag(
                workspace_id=target_workspace_id,
                name=src_tag.name,
                color=src_tag.color,
                description=src_tag.description,
                locked=src_tag.locked,
                order_index=src_tag.order_index,
                group_id=new_group_id,
            )
            session.add(new_tag)
            await session.flush()
            await session.refresh(new_tag)
            new_tags.append(new_tag)

        return new_tags


# ── CRDT cleanup ─────────────────────────────────────────────────────


async def _cleanup_crdt_highlights_for_tag(
    workspace_id: UUID,
    tag_id: UUID,
) -> int:
    """Remove CRDT highlights referencing a tag and its tag_order entry.

    Loads the workspace's CRDT state, iterates all highlights to find
    those matching the tag UUID, removes them and the tag_order entry,
    then saves the updated state back to the workspace.

    Uses the same lazy-import pattern as ``_replay_crdt_state()`` in
    ``db/workspaces.py`` to avoid circular imports.

    Args:
        workspace_id: The workspace whose CRDT state to update.
        tag_id: The tag UUID whose highlights should be removed.

    Returns:
        The count of removed highlights.
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.models import Workspace

    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace or not workspace.crdt_state:
            return 0

        doc = AnnotationDocument("cleanup-tmp")
        doc.apply_update(workspace.crdt_state)

        # Collect highlight IDs matching this tag
        tag_str = str(tag_id)
        to_remove = [
            hl["id"] for hl in doc.get_all_highlights() if hl.get("tag") == tag_str
        ]

        # Remove matching highlights (best-effort: skip corrupted entries)
        for hl_id in to_remove:
            try:
                doc.remove_highlight(hl_id)
            except Exception:  # CRDT corruption should not block cleanup
                logger.warning(
                    "Failed to remove highlight %s during tag cleanup", hl_id
                )

        # Remove the tag_order entry (silently skip if missing)
        if tag_str in doc.tag_order:
            del doc.tag_order[tag_str]

        # Save updated state
        workspace.crdt_state = doc.get_full_state()
        session.add(workspace)
        await session.flush()

        return len(to_remove)
