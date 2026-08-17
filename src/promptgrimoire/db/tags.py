"""CRUD operations for TagGroup and Tag.

Provides async database functions for tag management within workspaces.
Tags are per-workspace annotation categories; TagGroups visually group them.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from sqlalchemy import text, tstring
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import (
    DuplicateNameError,
    HasChildTagsError,
    HasHighlightsError,
    SharePermissionError,
    TagCreationDeniedError,
    TagLockedError,
)
from promptgrimoire.db.models import Tag, TagGroup

logger = structlog.get_logger()
if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import EllipsisType
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@contextmanager
def _safe_crdt_write(operation: str) -> Iterator[None]:
    """Guard CRDT dual-writes: log and suppress failures.

    DB state is authoritative. CRDT failures are programming errors
    (wrong types, missing keys) that self-heal on next page load.
    Logged at ERROR level, which triggers Discord alerting.
    """
    try:
        yield
    except Exception:
        logger.exception("crdt_dual_write_failed", operation=operation)


def _validate_hex_color(color: str, *, nullable: bool = False) -> None:
    """Validate a hex colour string matches ^#[0-9a-fA-F]{6}$.

    Raises ValueError for invalid colours so the error surfaces as a
    clean application-level rejection rather than a DB IntegrityError
    from the ck_tag_color_hex / ck_tag_group_color_hex constraints.
    """
    if nullable and color is None:
        return
    if not isinstance(color, str) or not _HEX_COLOR_RE.match(color):
        msg = f"Color must be a 7-character hex string (e.g. '#1f77b4'), got {color!r}"
        raise ValueError(msg)


async def _check_tag_creation_permission(workspace_id: UUID) -> None:
    """Resolve PlacementContext and raise if tag creation is denied.

    Args:
        workspace_id: The workspace to check.

    Raises:
        TagCreationDeniedError: If allow_tag_creation resolves to False.
    """
    from promptgrimoire.db.workspaces import get_placement_context

    ctx = await get_placement_context(workspace_id)
    if not ctx.allow_tag_creation:
        msg = "Tag creation not allowed on this workspace"
        raise TagCreationDeniedError(msg)


# ── TagGroup CRUD ────────────────────────────────────────────────────


async def create_tag_group(
    workspace_id: UUID,
    name: str,
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> TagGroup:
    """Create a TagGroup in a workspace.

    Resolves PlacementContext and raises TagCreationDeniedError if
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
        duplicate_name = await _flush_or_detect_duplicate(
            session,
            "uq_tag_group_workspace_name",
            "Duplicate tag group name",
            name=name,
            workspace_id=str(workspace_id),
        )
        if not duplicate_name:
            await session.refresh(group)

    if duplicate_name:
        msg = f"A tag group named '{name}' already exists in this workspace"
        raise DuplicateNameError(msg)

    if crdt_doc is not None:
        with _safe_crdt_write("create_tag_group"):
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


class _Unset(Enum):
    """Sentinel enum member distinguishing "not provided" from explicit ``None``.

    A plain ``object()`` singleton cannot be narrowed by ty's ``is``/``is not``
    analysis (it stays typed as ``object`` after the check), so a single-member
    enum is used instead -- ty narrows enum-literal identity checks correctly.
    """

    TOKEN = auto()


_UNSET = _Unset.TOKEN


async def _flush_or_detect_duplicate(
    session: AsyncSession,
    constraint: str,
    log_msg: str,
    **log_kwargs: str,
) -> bool:
    """Flush *session*; return True if a duplicate-name constraint fired.

    Returns False on clean flush (caller must then call session.refresh).
    Raises IntegrityError for any non-duplicate constraint violation.
    """
    try:
        await session.flush()
    except IntegrityError as exc:
        if constraint in str(exc):
            logger.warning(log_msg, **log_kwargs)
            await session.rollback()
            return True
        raise
    return False


async def update_tag_group(
    group_id: UUID,
    name: str | None = None,
    order_index: int | None = None,
    # ``color`` uses the ``_UNSET`` enum sentinel (not ``...``) because the
    # parameter lives in the public function signature where ``Ellipsis`` as a
    # default looks unusual to callers.  The ``_UNSET`` name makes the intent
    # ("omitted") explicit.  ``update_tag`` uses ``...`` (Ellipsis) for the
    # same purpose in an internal helper -- both patterns are valid, but we keep
    # them separate here for readability.
    color: str | _Unset | None = _UNSET,
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> TagGroup | None:
    """Update TagGroup details.

    Omit any parameter (or pass None) to leave it unchanged.
    ``color`` uses a sentinel default so that passing ``None`` explicitly
    clears the colour.

    Raises:
        DuplicateNameError: If *name* conflicts with an existing group name.
    """
    if color is not _UNSET and color is not None:
        _validate_hex_color(color)

    async with get_session() as session:
        group = await session.get(TagGroup, group_id)
        if not group:
            return None

        if name is not None:
            group.name = name
        if order_index is not None:
            group.order_index = order_index
        if color is not _UNSET:
            group.color = color

        session.add(group)
        duplicate = await _flush_or_detect_duplicate(
            session,
            "uq_tag_group_workspace_name",
            "Duplicate tag group name on update",
            group_id=str(group_id),
        )
        if not duplicate:
            await session.refresh(group)

    if duplicate:
        msg = f"A tag group named '{name}' already exists in this workspace"
        raise DuplicateNameError(msg)

    if crdt_doc is not None:
        with _safe_crdt_write("update_tag_group"):
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

        tag_count_result = await session.exec(
            select(func.count()).select_from(Tag).where(Tag.group_id == group_id)
        )
        tag_count = tag_count_result.one()
        if tag_count > 0:
            raise HasChildTagsError(group_id, tag_count)

        await session.delete(group)

    if crdt_doc is not None:
        with _safe_crdt_write("delete_tag_group"):
            crdt_doc.delete_tag_group(group_id)

    return True


async def list_tag_groups_for_workspace(workspace_id: UUID) -> list[TagGroup]:
    """List all TagGroups for a workspace, ordered by order_index."""
    async with get_session() as session:
        result = await session.execute(
            tstring(
                t"""
                SELECT id, workspace_id, name, color, order_index, created_at
                FROM tag_group
                WHERE workspace_id = {workspace_id}
                ORDER BY order_index
                """
            )
        )
        return [TagGroup(**row._mapping) for row in result.all()]


# ── Tag CRUD ─────────────────────────────────────────────────────────


async def create_tag(  # noqa: PLR0913 -- param-object migration: tracker ledger 8
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

    Resolves PlacementContext and raises TagCreationDeniedError if
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
    _validate_hex_color(color)
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
        duplicate_name = await _flush_or_detect_duplicate(
            session,
            "uq_tag_workspace_name",
            "Duplicate tag name",
            name=name,
            workspace_id=str(workspace_id),
        )
        if not duplicate_name:
            await session.refresh(tag)

    if duplicate_name:
        msg = f"A tag named '{name}' already exists in this workspace"
        raise DuplicateNameError(msg)

    if crdt_doc is not None:
        with _safe_crdt_write("create_tag"):
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


@dataclass(frozen=True, slots=True)
class _TagFieldUpdate:
    """Sentinel-typed partial-update fields shared by lock-checking and apply.

    Bundles ``update_tag``'s four Ellipsis-sentinel fields so the two
    single-call-site helpers below take one param instead of four.
    """

    name: str | EllipsisType
    color: str | EllipsisType
    description: str | EllipsisType | None
    group_id: UUID | EllipsisType | None


def _enforce_tag_lock(tag: Tag, fields: _TagFieldUpdate, *, bypass_lock: bool) -> None:
    """Raise TagLockedError if a locked tag has non-lock field changes.

    Skipped when ``bypass_lock`` is True (instructor operations).
    """
    if not tag.locked or bypass_lock:
        return
    has_non_lock_changes = any(
        v is not ...
        for v in (fields.name, fields.color, fields.description, fields.group_id)
    )
    if has_non_lock_changes:
        msg = "Tag is locked"
        raise TagLockedError(msg)


def _apply_tag_field_updates(
    tag: Tag, fields: _TagFieldUpdate, *, locked: bool | None
) -> None:
    """Apply Ellipsis-sentinel partial updates to a Tag model."""
    if fields.name is not ...:
        tag.name = fields.name
    if fields.color is not ...:
        tag.color = fields.color
    if fields.description is not ...:
        tag.description = fields.description
    if fields.group_id is not ...:
        tag.group_id = fields.group_id
    if locked is not None:
        tag.locked = locked


def _sync_tag_to_crdt(tag: Tag, crdt_doc: AnnotationDocument) -> None:
    """Write the current tag state to CRDT, preserving existing highlights."""
    with _safe_crdt_write("sync_tag_to_crdt"):
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


async def update_tag(  # noqa: PLR0913 -- param-object migration: tracker ledger 8
    tag_id: UUID,
    *,
    name: str | EllipsisType = ...,
    color: str | EllipsisType = ...,
    description: str | EllipsisType | None = ...,
    group_id: UUID | EllipsisType | None = ...,
    locked: bool | None = None,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
) -> Tag | None:
    """Update Tag details.

    Uses the Ellipsis sentinel pattern: omit a parameter to leave it
    unchanged. If the tag is locked, only the ``locked`` field itself
    may be changed (to allow instructor lock toggle); all other field
    changes raise ``TagLockedError``.

    ``name`` and ``color`` cannot be cleared to ``None`` -- both are
    NOT NULL columns on ``Tag`` -- so their sentinel type omits ``None``
    (unlike ``description``/``group_id``, which are nullable).

    Pass ``bypass_lock=True`` to allow instructors to edit locked tags.
    """
    if color is not ...:
        _validate_hex_color(color)

    fields = _TagFieldUpdate(
        name=name, color=color, description=description, group_id=group_id
    )

    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return None

        _enforce_tag_lock(tag, fields, bypass_lock=bypass_lock)
        _apply_tag_field_updates(tag, fields, locked=locked)

        session.add(tag)
        duplicate_name = await _flush_or_detect_duplicate(
            session,
            "uq_tag_workspace_name",
            "Duplicate tag name on update",
            tag_id=str(tag_id),
        )
        if not duplicate_name:
            await session.refresh(tag)

    if duplicate_name:
        msg = f"A tag named '{name}' already exists in this workspace"
        raise DuplicateNameError(msg)

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

    Guard behaviour: The highlight count is read from the persisted CRDT
    state inside the first session. If ``crdt_state`` is None (workspace
    has no persisted annotations), the guard is skipped and deletion
    proceeds directly to CRDT cleanup and row deletion.
    """
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return False

        if tag.locked and not bypass_lock:
            msg = "Tag is locked"
            raise TagLockedError(msg)

        workspace_id = tag.workspace_id
        tag_id_for_cleanup = tag.id

        # Guard: count highlights from DB-persisted CRDT state (same session)
        from promptgrimoire.db.models import Workspace

        workspace = await session.get(Workspace, workspace_id)
        if workspace and workspace.crdt_state:
            from promptgrimoire.crdt.annotation_doc import (
                AnnotationDocument as AnnotationDocumentCls,
            )

            guard_doc = AnnotationDocumentCls("guard-tmp")
            guard_doc.apply_update(workspace.crdt_state)
            tag_str = str(tag_id_for_cleanup)
            highlight_count = sum(
                1 for hl in guard_doc.get_all_highlights() if hl.get("tag") == tag_str
            )
            if highlight_count > 0:
                raise HasHighlightsError(tag_id_for_cleanup, highlight_count)

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
        result = await session.execute(
            tstring(
                t"""
                SELECT id, workspace_id, group_id, name, description, color,
                       locked, order_index, created_at
                FROM tag
                WHERE workspace_id = {workspace_id}
                ORDER BY order_index
                """
            )
        )
        return [Tag(**row._mapping) for row in result.all()]


# ── Reorder ──────────────────────────────────────────────────────────


def _sync_tag_order_index_to_crdt(
    tag_ids: list[UUID], crdt_doc: AnnotationDocument
) -> None:
    """Update order_index for each tag in the CRDT doc."""
    with _safe_crdt_write("sync_tag_order_to_crdt"):
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


def _sync_group_order_index_to_crdt(
    group_ids: list[UUID], crdt_doc: AnnotationDocument
) -> None:
    """Update order_index for each tag group in the CRDT doc."""
    with _safe_crdt_write("sync_group_order_to_crdt"):
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
        _sync_tag_order_index_to_crdt(tag_ids, crdt_doc)


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
        _sync_group_order_index_to_crdt(group_ids, crdt_doc)


# ── Import from workspace ─────────────────────────────────────────────


@dataclass
class ImportResult:
    """Result of import_tags_from_workspace.

    Attributes:
        created_tags: Newly created Tag objects.
        skipped_tags: Count of source tags skipped (name already existed).
        created_groups: Newly created TagGroup objects.
        skipped_groups: Count of source groups skipped (name already existed).
    """

    created_tags: list[Tag] = field(default_factory=list)
    skipped_tags: int = 0
    created_groups: list[TagGroup] = field(default_factory=list)
    skipped_groups: int = 0


@dataclass(slots=True)
class _ImportContext:
    """Mutable state threaded through one import_tags_from_workspace() run.

    Bundles the session, target workspace, and the two in-place-mutated
    accumulators so ``_import_groups``/``_import_tags`` take three params
    instead of six.
    """

    session: AsyncSession
    target_workspace_id: UUID
    group_id_map: dict[UUID, UUID]
    result_obj: ImportResult


async def _import_groups(
    ctx: _ImportContext,
    source_groups: list[TagGroup],
    base_order: int,
) -> None:
    """Insert source groups into target via ON CONFLICT DO NOTHING.

    Populates *ctx.result_obj* and *ctx.group_id_map* in place.
    """
    # ty cannot type ``TagGroup.__table__`` (SQLModel metaclass access, #3421);
    # go through .metadata.tables[...] to get a plain Core Table/Column instead.
    tag_group_table = TagGroup.metadata.tables[TagGroup.__tablename__]
    for idx, src_group in enumerate(source_groups):
        new_id = uuid4()
        stmt = (
            pg_insert(TagGroup)
            .values(
                id=new_id,
                workspace_id=ctx.target_workspace_id,
                name=src_group.name,
                color=src_group.color or "#808080",
                order_index=base_order + idx,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_tag_group_workspace_name")
            .returning(tag_group_table.c.id)
        )
        insert_result = await ctx.session.execute(stmt)
        created_id = insert_result.scalar_one_or_none()

        if created_id is not None:
            created_group = await ctx.session.get(TagGroup, created_id)
            assert created_group is not None  # noqa: S101  -- RETURNING guarantees non-None after insert
            ctx.result_obj.created_groups.append(created_group)
            ctx.group_id_map[src_group.id] = created_id
        else:
            ctx.result_obj.skipped_groups += 1
            target_workspace_id = ctx.target_workspace_id
            src_group_name = src_group.name
            existing_id = await ctx.session.execute(
                tstring(
                    t"""
                    SELECT id FROM tag_group
                    WHERE workspace_id = {target_workspace_id}
                      AND name = {src_group_name}
                    """
                )
            )
            ctx.group_id_map[src_group.id] = existing_id.scalar_one()


async def _import_tags(
    ctx: _ImportContext,
    source_tags: list[Tag],
    base_order: int,
) -> None:
    """Insert source tags into target via ON CONFLICT DO NOTHING.

    Populates *ctx.result_obj* in place.
    """
    # ty cannot type ``Tag.__table__`` (SQLModel metaclass access, #3421);
    # go through .metadata.tables[...] to get a plain Core Table/Column instead.
    tag_table = Tag.metadata.tables[Tag.__tablename__]
    for src_tag in source_tags:
        new_group_id = (
            ctx.group_id_map.get(src_tag.group_id) if src_tag.group_id else None
        )
        new_id = uuid4()
        stmt = (
            pg_insert(Tag)
            .values(
                id=new_id,
                workspace_id=ctx.target_workspace_id,
                name=src_tag.name,
                color=src_tag.color,
                group_id=new_group_id,
                description=src_tag.description,
                locked=False,
                order_index=base_order + len(ctx.result_obj.created_tags),
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_tag_workspace_name")
            .returning(tag_table.c.id)
        )
        insert_result = await ctx.session.execute(stmt)
        created_id = insert_result.scalar_one_or_none()

        if created_id is not None:
            created_tag = await ctx.session.get(Tag, created_id)
            assert created_tag is not None  # noqa: S101  -- RETURNING guarantees non-None after insert
            ctx.result_obj.created_tags.append(created_tag)
        else:
            ctx.result_obj.skipped_tags += 1


def _import_crdt_dual_write(
    crdt_doc: AnnotationDocument,
    result_obj: ImportResult,
) -> None:
    """Write newly created groups and tags to the live CRDT document.

    Callers **must** wrap this in ``_safe_crdt_write`` to ensure partial
    CRDT mutations are caught and logged rather than propagated.
    """
    for group in result_obj.created_groups:
        crdt_doc.set_tag_group(
            group_id=group.id,
            name=group.name,
            order_index=group.order_index,
            colour=group.color,
        )
    for tag in result_obj.created_tags:
        crdt_doc.set_tag(
            tag_id=tag.id,
            name=tag.name,
            colour=tag.color,
            order_index=tag.order_index,
            group_id=tag.group_id,
            description=tag.description,
            highlights=[],
        )


async def import_tags_from_workspace(
    source_workspace_id: UUID,
    target_workspace_id: UUID,
    user_id: UUID,
    crdt_doc: AnnotationDocument | None = None,
) -> ImportResult:
    """Import tags and groups from a source workspace.

    Runs all mutations in a single transaction with ``ON CONFLICT DO
    NOTHING``, making the import atomic and idempotent.  Additive merge:
    existing tags in target are preserved.  Tags with duplicate names are
    skipped.  Imported tags default to unlocked regardless of source
    locked status.

    Args:
        source_workspace_id: Workspace to import from.
        target_workspace_id: Workspace to import into.
        user_id: User performing the import (must have read access to source).
        crdt_doc: Optional live CRDT doc for dual-write.

    Returns:
        ImportResult with created/skipped counts.

    Raises:
        SharePermissionError: If user lacks read access to source workspace.
        TagCreationDeniedError: If tag creation is not allowed on target.
    """
    await _check_import_access(source_workspace_id, user_id)
    await _check_tag_creation_permission(target_workspace_id)

    source_groups = await list_tag_groups_for_workspace(source_workspace_id)
    source_tags = await list_tags_for_workspace(source_workspace_id)

    if not source_tags and not source_groups:
        return ImportResult()

    result_obj = ImportResult()
    group_id_map: dict[UUID, UUID] = {}

    async with get_session() as session:
        # Read current counters for order_index assignment
        counters = await session.execute(
            text(
                "SELECT next_group_order, next_tag_order "
                "FROM workspace WHERE id = :ws_id"
            ),
            {"ws_id": str(target_workspace_id)},
        )
        row = counters.one_or_none()
        if row is None:
            msg = f"Workspace {target_workspace_id} not found"
            raise ValueError(msg)
        # Attribute access by label, not row[0]/row[1] -- SQLModel's
        # AsyncSession.execute() stub declares Result[Any], which ty resolves
        # as a length-1 Row TypeVarTuple; positional indexing past 0 is
        # therefore flagged as out-of-bounds even though the query selects
        # two columns. See docs/architecture/raw-sql-convention.md.
        next_group_order = row.next_group_order
        next_tag_order = row.next_tag_order

        ctx = _ImportContext(
            session=session,
            target_workspace_id=target_workspace_id,
            group_id_map=group_id_map,
            result_obj=result_obj,
        )
        await _import_groups(ctx, source_groups, next_group_order)
        await _import_tags(ctx, source_tags, next_tag_order)

        # Counter bumps
        if result_obj.created_groups:
            await session.execute(
                text(
                    "UPDATE workspace SET next_group_order = next_group_order + :count "
                    "WHERE id = :ws_id"
                ),
                {
                    "count": len(result_obj.created_groups),
                    "ws_id": str(target_workspace_id),
                },
            )
        if result_obj.created_tags:
            await session.execute(
                text(
                    "UPDATE workspace SET next_tag_order = next_tag_order + :count "
                    "WHERE id = :ws_id"
                ),
                {
                    "count": len(result_obj.created_tags),
                    "ws_id": str(target_workspace_id),
                },
            )

    if crdt_doc is not None:
        with _safe_crdt_write("import_tags"):
            _import_crdt_dual_write(crdt_doc, result_obj)

    return result_obj


async def _check_import_access(source_workspace_id: UUID, user_id: UUID) -> None:
    """Verify user has read access to the source workspace.

    Raises:
        SharePermissionError: If user has no permission on the source workspace.
    """
    from promptgrimoire.db.acl import resolve_permission

    permission = await resolve_permission(source_workspace_id, user_id)
    if permission is None:
        msg = "No read access to source workspace"
        raise SharePermissionError(msg)


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

        # Remove the tag from the tags Map (matches _cleanup_crdt_highlights_on_doc)
        doc.delete_tag(tag_id)

        # Save updated state
        workspace.crdt_state = doc.get_full_state()
        session.add(workspace)
        await session.flush()

        return len(to_remove)
