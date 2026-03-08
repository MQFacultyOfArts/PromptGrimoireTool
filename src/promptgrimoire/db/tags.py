"""CRUD operations for TagGroup and Tag.

Provides async database functions for tag management within workspaces.
Tags are per-workspace annotation categories; TagGroups visually group them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Tag, TagGroup

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument


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
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> TagGroup:
    """Create a TagGroup in a workspace.

    Resolves PlacementContext and raises PermissionError if
    allow_tag_creation is False.

    Order index is assigned atomically via the workspace's
    ``next_group_order`` counter column, preventing duplicate
    indices under concurrent creation.

    Parameters
    ----------
    workspace_id : UUID
        The parent workspace's UUID.
    name : str
        Display name for the group.

    Returns
    -------
    TagGroup
        The created TagGroup.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        result = await session.execute(
            text(
                "UPDATE workspace SET next_group_order = next_group_order + 1 "
                "WHERE id = :ws_id RETURNING next_group_order - 1"
            ),
            {"ws_id": str(workspace_id)},
        )
        order_index = result.scalar_one_or_none()
        if order_index is None:
            msg = (
                f"Workspace {workspace_id} not found. "
                "Cannot determine tag group order index."
            )
            raise ValueError(msg)

        group = TagGroup(
            workspace_id=workspace_id,
            name=name,
            order_index=order_index,
        )
        session.add(group)
        await session.flush()
        await session.refresh(group)

    if crdt_doc is not None:
        crdt_doc.set_tag_group(
            group_id=group.id,
            name=group.name,
            order_index=group.order_index,
            colour=group.color,
        )

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
    *,
    crdt_doc: AnnotationDocument | None = None,
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

    if crdt_doc is not None:
        crdt_doc.set_tag_group(
            group_id=group.id,
            name=group.name,
            order_index=group.order_index,
            colour=group.color,
        )

    return group


async def delete_tag_group(
    group_id: UUID,
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> bool:
    """Delete a TagGroup.

    Tags in the group get group_id=NULL via the SET NULL FK constraint.

    Returns True if found and deleted.
    """
    async with get_session() as session:
        group = await session.get(TagGroup, group_id)
        if not group:
            return False

        await session.delete(group)

    if crdt_doc is not None:
        crdt_doc.delete_tag_group(group_id)

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
    crdt_doc: AnnotationDocument | None = None,
) -> Tag:
    """Create a Tag in a workspace.

    Resolves PlacementContext and raises PermissionError if
    allow_tag_creation is False.

    Order index is assigned atomically via the workspace's
    ``next_tag_order`` counter column, preventing duplicate
    indices under concurrent creation.

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

    Returns
    -------
    Tag
        The created Tag.
    """
    await _check_tag_creation_permission(workspace_id)

    async with get_session() as session:
        result = await session.execute(
            text(
                "UPDATE workspace SET next_tag_order = next_tag_order + 1 "
                "WHERE id = :ws_id RETURNING next_tag_order - 1"
            ),
            {"ws_id": str(workspace_id)},
        )
        order_index = result.scalar_one_or_none()
        if order_index is None:
            msg = (
                f"Workspace {workspace_id} not found. Cannot determine tag order index."
            )
            raise ValueError(msg)

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

    if crdt_doc is not None:
        crdt_doc.set_tag(
            tag_id=tag.id,
            name=tag.name,
            colour=tag.color,
            order_index=tag.order_index,
            group_id=tag.group_id,
            description=tag.description,
            highlights=[],
        )

    return tag


async def get_tag(tag_id: UUID) -> Tag | None:
    """Get a Tag by ID."""
    async with get_session() as session:
        return await session.get(Tag, tag_id)


def _enforce_tag_lock(
    tag: Tag,
    *,
    bypass_lock: bool,
    name: object,
    color: object,
    description: object,
    group_id: object,
) -> None:
    """Raise ValueError if a locked tag has non-lock field changes.

    Skipped when ``bypass_lock`` is True (instructor operations).
    """
    if not tag.locked or bypass_lock:
        return
    has_non_lock_changes = any(
        v is not ... for v in [name, color, description, group_id]
    )
    if has_non_lock_changes:
        msg = "Tag is locked"
        raise ValueError(msg)


def _apply_tag_field_updates(
    tag: Tag,
    *,
    name: object,
    color: object,
    description: object,
    group_id: object,
    locked: bool | None,
) -> None:
    """Apply Ellipsis-sentinel partial updates to a Tag model."""
    if name is not ...:
        tag.name = name  # type: ignore[assignment]  -- Ellipsis sentinel already checked
    if color is not ...:
        tag.color = color  # type: ignore[assignment]  -- Ellipsis sentinel already checked
    if description is not ...:
        tag.description = description  # type: ignore[assignment]  -- Ellipsis sentinel already checked
    if group_id is not ...:
        tag.group_id = group_id  # type: ignore[assignment]  -- Ellipsis sentinel already checked
    if locked is not None:
        tag.locked = locked


def _sync_tag_to_crdt(tag: Tag, crdt_doc: AnnotationDocument) -> None:
    """Write the current tag state to CRDT, preserving existing highlights."""
    existing = crdt_doc.get_tag(tag.id)
    highlights = existing.get("highlights", []) if existing else []
    crdt_doc.set_tag(
        tag_id=tag.id,
        name=tag.name,
        colour=tag.color,
        order_index=tag.order_index,
        group_id=tag.group_id,
        description=tag.description,
        highlights=highlights,
    )


async def update_tag(
    tag_id: UUID,
    *,
    name: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None
    color: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    group_id: UUID | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    locked: bool | None = None,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
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

        _enforce_tag_lock(
            tag,
            bypass_lock=bypass_lock,
            name=name,
            color=color,
            description=description,
            group_id=group_id,
        )
        _apply_tag_field_updates(
            tag,
            name=name,
            color=color,
            description=description,
            group_id=group_id,
            locked=locked,
        )

        session.add(tag)
        await session.flush()
        await session.refresh(tag)

    if crdt_doc is not None:
        _sync_tag_to_crdt(tag, crdt_doc)

    return tag


async def delete_tag(
    tag_id: UUID,
    *,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
) -> bool:
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
    await _cleanup_crdt_highlights_for_tag(
        workspace_id, tag_id_for_cleanup, crdt_doc=crdt_doc
    )

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


def _sync_tag_order_to_crdt(tag_ids: list[UUID], crdt_doc: AnnotationDocument) -> None:
    """Update order_index for each tag in the CRDT doc."""
    for idx, tag_id in enumerate(tag_ids):
        existing = crdt_doc.get_tag(tag_id)
        if existing:
            crdt_doc.set_tag(
                tag_id=tag_id,
                name=existing["name"],
                colour=existing["colour"],
                order_index=idx,
                group_id=existing.get("group_id"),
                description=existing.get("description"),
                highlights=existing.get("highlights", []),
            )


def _sync_group_order_to_crdt(
    group_ids: list[UUID], crdt_doc: AnnotationDocument
) -> None:
    """Update order_index for each tag group in the CRDT doc."""
    for idx, gid in enumerate(group_ids):
        existing = crdt_doc.get_tag_group(gid)
        if existing:
            crdt_doc.set_tag_group(
                group_id=gid,
                name=existing["name"],
                order_index=idx,
                colour=existing.get("colour"),
            )


async def reorder_tags(
    tag_ids: list[UUID],
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> None:
    """Set tag order_index values to match the given list order.

    Takes an ordered list of tag UUIDs and sets each tag's
    order_index to its position in the list (0, 1, 2, ...).
    Also syncs the workspace's ``next_tag_order`` counter.

    Args:
        tag_ids: Ordered list of tag UUIDs.
        crdt_doc: Optional live AnnotationDocument for CRDT dual-write.

    Raises:
        ValueError: If any tag ID is not found.
    """
    if not tag_ids:
        return

    async with get_session() as session:
        workspace_id: UUID | None = None
        for idx, tid in enumerate(tag_ids):
            tag = await session.get(Tag, tid)
            if not tag:
                msg = f"Tag {tid} not found"
                raise ValueError(msg)
            tag.order_index = idx
            session.add(tag)
            if workspace_id is None:
                workspace_id = tag.workspace_id
        await session.flush()

        # Sync counter so next create_tag() uses the correct index
        await session.execute(
            text("UPDATE workspace SET next_tag_order = :count WHERE id = :ws_id"),
            {"count": len(tag_ids), "ws_id": str(workspace_id)},
        )

    if crdt_doc is not None:
        _sync_tag_order_to_crdt(tag_ids, crdt_doc)


async def reorder_tag_groups(
    group_ids: list[UUID],
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> None:
    """Set tag group order_index values to match the given list order.

    Takes an ordered list of TagGroup UUIDs and sets each group's
    order_index to its position in the list (0, 1, 2, ...).
    Also syncs the workspace's ``next_group_order`` counter.

    Args:
        group_ids: Ordered list of TagGroup UUIDs.
        crdt_doc: Optional live AnnotationDocument for CRDT dual-write.

    Raises:
        ValueError: If any group ID is not found.
    """
    if not group_ids:
        return

    async with get_session() as session:
        workspace_id: UUID | None = None
        for idx, gid in enumerate(group_ids):
            group = await session.get(TagGroup, gid)
            if not group:
                msg = f"TagGroup {gid} not found"
                raise ValueError(msg)
            group.order_index = idx
            session.add(group)
            if workspace_id is None:
                workspace_id = group.workspace_id
        await session.flush()

        # Sync counter so next create_tag_group() uses the correct index
        await session.execute(
            text("UPDATE workspace SET next_group_order = :count WHERE id = :ws_id"),
            {"count": len(group_ids), "ws_id": str(workspace_id)},
        )

    if crdt_doc is not None:
        _sync_group_order_to_crdt(group_ids, crdt_doc)


# ── Import from workspace ─────────────────────────────────────────────


async def import_tags_from_workspace(
    source_workspace_id: UUID,
    target_workspace_id: UUID,
    user_id: UUID,
    crdt_doc: AnnotationDocument | None = None,
) -> list[Tag]:
    """Import tags and groups from a source workspace.

    Additive merge: existing tags in target are preserved. Tags with
    duplicate names (case-insensitive) are skipped. Imported tags default
    to unlocked regardless of source locked status.

    Args:
        source_workspace_id: Workspace to import from.
        target_workspace_id: Workspace to import into.
        user_id: User performing the import (must have read access to source).
        crdt_doc: Optional live CRDT doc for dual-write.

    Returns:
        List of newly created Tag objects.

    Raises:
        PermissionError: If user lacks read access to source workspace.
    """
    await _check_import_access(source_workspace_id, user_id)

    source_groups = await list_tag_groups_for_workspace(source_workspace_id)
    source_tags = await list_tags_for_workspace(source_workspace_id)

    if not source_tags and not source_groups:
        return []

    existing_tags = await list_tags_for_workspace(target_workspace_id)
    existing_names = {t.name.lower() for t in existing_tags}

    # Create groups with ID remapping
    group_id_map: dict[UUID, UUID] = {}
    for src_group in source_groups:
        new_group = await create_tag_group(
            target_workspace_id, src_group.name, crdt_doc=crdt_doc
        )
        group_id_map[src_group.id] = new_group.id

    # Create tags, skipping duplicates
    new_tags: list[Tag] = []
    for src_tag in source_tags:
        if src_tag.name.lower() in existing_names:
            continue
        new_group_id = group_id_map.get(src_tag.group_id) if src_tag.group_id else None
        new_tag = await create_tag(
            target_workspace_id,
            src_tag.name,
            src_tag.color,
            group_id=new_group_id,
            description=src_tag.description,
            locked=False,
            crdt_doc=crdt_doc,
        )
        new_tags.append(new_tag)

    return new_tags


async def _check_import_access(source_workspace_id: UUID, user_id: UUID) -> None:
    """Verify user has read access to the source workspace.

    Raises:
        PermissionError: If user has no permission on the source workspace.
    """
    from promptgrimoire.db.acl import resolve_permission

    permission = await resolve_permission(source_workspace_id, user_id)
    if permission is None:
        msg = "No read access to source workspace"
        raise PermissionError(msg)


# ── CRDT cleanup ─────────────────────────────────────────────────────


async def _cleanup_crdt_highlights_for_tag(
    workspace_id: UUID,
    tag_id: UUID,
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> int:
    """Remove CRDT highlights referencing a tag.

    When ``crdt_doc`` is provided, operates on the live document directly
    (no DB load/save round-trip). When ``None``, falls back to loading
    from the workspace's persisted CRDT state in the database.

    Args:
        workspace_id: The workspace whose CRDT state to update.
        tag_id: The tag UUID whose highlights should be removed.
        crdt_doc: Optional live AnnotationDocument to operate on directly.

    Returns:
        The count of removed highlights.
    """
    if crdt_doc is not None:
        return _cleanup_crdt_highlights_on_doc(crdt_doc, tag_id)

    return await _cleanup_crdt_highlights_from_db(workspace_id, tag_id)


def _cleanup_crdt_highlights_on_doc(
    doc: AnnotationDocument,
    tag_id: UUID,
) -> int:
    """Remove highlights for a tag from a live AnnotationDocument.

    Also removes the tag itself from the ``tags`` Map.  Does NOT save
    back to DB -- the persistence layer handles that via the observer.
    """
    tag_str = str(tag_id)
    to_remove = [
        hl["id"] for hl in doc.get_all_highlights() if hl.get("tag") == tag_str
    ]

    for hl_id in to_remove:
        try:
            doc.remove_highlight(hl_id)
        except ValueError, KeyError:  # CRDT corruption should not block cleanup
            logger.warning("Failed to remove highlight %s during tag cleanup", hl_id)

    # Remove from the tags Map
    doc.delete_tag(tag_id)

    return len(to_remove)


async def _cleanup_crdt_highlights_from_db(
    workspace_id: UUID,
    tag_id: UUID,
) -> int:
    """Remove highlights for a tag from persisted CRDT state in the DB.

    Loads the workspace's CRDT state, modifies it, and saves back.
    """
    from promptgrimoire.crdt.annotation_doc import (
        AnnotationDocument as AnnotationDocumentCls,
    )
    from promptgrimoire.db.models import Workspace

    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace or not workspace.crdt_state:
            return 0

        doc = AnnotationDocumentCls("cleanup-tmp")
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
            except ValueError, KeyError:  # CRDT corruption should not block cleanup
                logger.warning(
                    "Failed to remove highlight %s during tag cleanup", hl_id
                )

        # Save updated state
        workspace.crdt_state = doc.get_full_state()
        session.add(workspace)
        await session.flush()

        return len(to_remove)
