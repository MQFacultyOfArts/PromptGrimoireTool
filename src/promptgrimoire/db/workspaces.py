"""CRUD operations for Workspace.

Provides async database functions for workspace management.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import exists, func, text
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import OwnershipError
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    Permission,
    Tag,
    TagGroup,
    User,
    Week,
    Workspace,
)
from promptgrimoire.db.roles import get_staff_roles

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument

logger = structlog.get_logger()


async def get_user_workspace_for_activity(
    activity_id: UUID, user_id: UUID
) -> Workspace | None:
    """Find an existing workspace owned by the user in an activity.

    Looks for a non-template workspace placed in this activity where the user
    has an owner ACL entry. Returns the first match, or None if the user has
    no owned workspace for this activity.

    Filters by permission == "owner" to exclude shared workspaces -- a viewer
    of someone else's workspace should not be treated as having their own
    workspace for this activity (which would suppress the "Start Activity"
    button and show "Resume" instead).
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement, not bool
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        return result.first()


async def has_student_workspaces(activity_id: UUID) -> int:
    """Count non-template workspaces for an activity.

    Returns the number of student (cloned) workspaces placed in this
    activity, excluding the template workspace itself.  A return value
    of 0 means the activity is safe to delete without force.

    Args:
        activity_id: The activity UUID.

    Returns:
        Count of student workspaces (0 = safe to delete).
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return 0

        result = await session.exec(
            select(func.count())
            .select_from(Workspace)
            .where(
                Workspace.activity_id == activity_id,
                Workspace.id != activity.template_workspace_id,
            )
        )
        return result.one()


async def check_clone_eligibility(activity_id: UUID, user_id: UUID) -> str | None:
    """Check if a user is eligible to clone a workspace from an activity.

    Validates:
    1. Activity exists
    2. User is enrolled in the activity's course
    3. Activity's week is visible to the user (staff bypass)

    Returns:
        None if eligible, or an error message string explaining why not.
    """
    staff_roles = await get_staff_roles()

    async with get_session() as session:
        # 1. Activity must exist
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return "Activity not found"

        # 2. Resolve course via Week
        week = await session.get(Week, activity.week_id)
        if week is None:
            return "Week not found"

        # 3. User must be enrolled in the course
        enrollment_result = await session.exec(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == week.course_id,
                CourseEnrollment.user_id == user_id,
            )
        )
        enrollment = enrollment_result.one_or_none()
        if enrollment is None:
            return "User is not enrolled in this course"

        # 4. Week must be visible to the user
        # Staff always have access regardless of publish state
        is_student = enrollment.role not in staff_roles
        if is_student and not week.is_published:
            return "Week is not published"
        if is_student and week.visible_from and week.visible_from > datetime.now(UTC):
            return "Week is not yet visible"

        return None


@dataclass(frozen=True)
class PlacementContext:
    """Full hierarchy context for a workspace's placement."""

    placement_type: Literal["activity", "course", "loose"]
    activity_title: str | None = None
    week_number: int | None = None
    week_title: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    is_template: bool = False
    copy_protection: bool = False
    """Resolved copy protection for this workspace.

    True = protection active.
    """
    allow_sharing: bool = True
    """Resolved sharing permission for this workspace.

    True = owner can share with other students.
    Loose workspaces default to True (no course policy restricts them).
    Activity/course-placed paths set this explicitly via resolve_tristate().
    """
    anonymous_sharing: bool = False
    """Resolved anonymity setting for this workspace.

    True = author names hidden from peer viewers.
    """
    allow_tag_creation: bool = True
    """Resolved tag creation permission.

    True = students can create tags.
    """
    word_minimum: int | None = None
    """Resolved minimum word count.

    None = no minimum enforced. Passes through from Activity directly.
    """
    word_limit: int | None = None
    """Resolved maximum word count.

    None = no limit enforced. Passes through from Activity directly.
    """
    word_limit_enforcement: bool = False
    """Resolved word limit enforcement mode.

    True = hard (block submit), False = soft (warn only).
    Resolved via resolve_tristate from Activity override and Course default.
    """
    course_id: UUID | None = None
    """Course UUID for activity-placed workspaces.

    None for loose/course-only placement.
    """

    @property
    def display_label(self) -> str:
        """Human-readable placement label.

        Shows full hierarchy: "Activity Title in Week N for COURSE_CODE"
        """
        if self.placement_type == "activity":
            return (
                f"{self.activity_title} "
                f"in Week {self.week_number} "
                f"for {self.course_code}"
            )
        if self.placement_type == "course":
            return f"Loose work for {self.course_code}"
        return "Unplaced"


@dataclass(frozen=True)
class WorkspaceExportMetadata:
    """Export-focused metadata from workspace, owner ACL, and placement."""

    course_code: str | None
    activity_title: str | None
    workspace_title: str | None
    owner_display_name: str | None


@dataclass(frozen=True)
class AnnotationContext:
    """All data needed for annotation page load, resolved in a single session.

    Replaces 5+ separate DB function calls that each opened their own session:
    - get_workspace()
    - check_workspace_access() -> resolve_permission()
    - get_placement_context()
    - get_privileged_user_ids_for_workspace()
    - list_tags_for_workspace() + list_tag_groups_for_workspace()
    """

    workspace: Workspace
    permission: str | None
    """Effective permission for the requesting user. None = no access."""
    placement: PlacementContext
    privileged_user_ids: frozenset[str]
    """String-form User.id values for staff/admins.

    Matches CRDT annotation author format.
    """
    tags: list[Tag]
    tag_groups: list[TagGroup]


async def _resolve_enrollment_permission(
    session: AsyncSession,
    workspace: Workspace,
    course_id: UUID,
    user_id: UUID,
) -> str | None:
    """Derive permission from course enrollment for a single user.

    Returns the derived permission string or None if the user has no
    enrollment-based access. Extracted from resolve_annotation_context
    to keep branch/statement counts within linter limits.
    """
    enrollment_result = await session.exec(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.user_id == user_id,
        )
    )
    enrollment = enrollment_result.one_or_none()
    if enrollment is None:
        return None

    course = await session.get(Course, course_id)
    if course is None:
        return None

    staff_roles = await get_staff_roles()
    if enrollment.role in staff_roles:
        return course.default_instructor_permission

    if not workspace.shared_with_class:
        return None

    # Activity override for allow_sharing (identity map absorbs re-fetch)
    activity_override = None
    if workspace.activity_id is not None:
        activity = await session.get(Activity, workspace.activity_id)
        if activity is not None:
            activity_override = activity.allow_sharing
    allow_sharing = resolve_tristate(activity_override, course.default_allow_sharing)
    return "peer" if allow_sharing else None


async def _resolve_effective_permission(
    session: AsyncSession,
    workspace: Workspace,
    placement: PlacementContext,
    user_id: UUID,
) -> str | None:
    """Resolve the effective permission for a user on a workspace.

    Combines explicit ACL lookup with enrollment-derived access,
    picking the highest permission level. Returns None if no access.
    Extracted from resolve_annotation_context to keep branch/statement
    counts within linter limits.
    """
    # Explicit ACL lookup
    explicit_result = await session.exec(
        select(ACLEntry).where(
            ACLEntry.workspace_id == workspace.id,
            ACLEntry.user_id == user_id,
        )
    )
    explicit = explicit_result.one_or_none()

    # Enrollment-derived access
    course_id = placement.course_id
    if course_id is None and workspace.course_id is not None:
        course_id = workspace.course_id

    derived_permission: str | None = None
    if course_id is not None:
        derived_permission = await _resolve_enrollment_permission(
            session, workspace, course_id, user_id
        )

    # Highest wins
    if explicit and derived_permission:
        level_result = await session.exec(
            select(Permission.name, Permission.level).where(
                Permission.name.in_([explicit.permission, derived_permission])  # type: ignore[unresolved-attribute]  -- Column has in_ at runtime
            )
        )
        levels = dict(level_result.all())
        e_level = levels[explicit.permission]
        d_level = levels[derived_permission]
        return explicit.permission if e_level >= d_level else derived_permission
    if explicit:
        return explicit.permission
    return derived_permission


async def _resolve_privileged_user_ids(
    session: AsyncSession,
    workspace: Workspace,
    placement: PlacementContext,
) -> frozenset[str]:
    """Collect string-form user IDs for staff and admin users.

    Staff are resolved from course enrollment; admins from the User table.
    Returns a frozenset suitable for AnnotationContext.privileged_user_ids.
    """
    staff_ids: set[str] = set()
    priv_course_id = placement.course_id or workspace.course_id
    if priv_course_id is not None:
        staff_roles = await get_staff_roles()
        staff_result = await session.exec(
            select(CourseEnrollment.user_id).where(
                CourseEnrollment.course_id == priv_course_id,
                CourseEnrollment.role.in_(staff_roles),  # type: ignore[unresolved-attribute]  -- Column has in_ at runtime
            )
        )
        staff_ids = {str(uid) for uid in staff_result.all()}

    admin_result = await session.exec(
        select(User.id).where(User.is_admin == True)  # noqa: E712
    )
    admin_ids = {str(uid) for uid in admin_result.all()}
    return frozenset(staff_ids | admin_ids)


async def resolve_annotation_context(
    workspace_id: UUID,
    user_id: UUID,
    *,
    is_admin: bool = False,
) -> AnnotationContext | None:
    """Resolve all data needed for annotation page load in a single session.

    Returns None if workspace does not exist.
    """
    async with get_session() as session:
        # 1. Workspace + template flag in a single query
        template_exists = exists(
            select(Activity.id).where(Activity.template_workspace_id == workspace_id)
        )
        ws_result = await session.exec(
            select(Workspace, template_exists.label("is_template")).where(
                Workspace.id == workspace_id
            )
        )
        ws_row = ws_result.first()
        if ws_row is None:
            return None

        workspace, is_template = ws_row

        # 2. Hierarchy resolution — reuse existing private helpers
        if workspace.activity_id is not None:
            placement = await _resolve_activity_placement(
                session, workspace.activity_id
            )
        elif workspace.course_id is not None:
            placement = await _resolve_course_placement(session, workspace.course_id)
        else:
            placement = PlacementContext(placement_type="loose")
        if is_template:
            placement = replace(placement, is_template=True)

        # 3. Permission resolution (inline to avoid double-fetch)
        if is_admin:
            permission: str | None = "owner"
        else:
            permission = await _resolve_effective_permission(
                session, workspace, placement, user_id
            )

        # 4. Privileged user IDs (staff + admins)
        privileged_user_ids = await _resolve_privileged_user_ids(
            session, workspace, placement
        )

        # 5. Tags and tag groups
        tags_result = await session.exec(
            select(Tag)
            .where(Tag.workspace_id == workspace_id)
            .order_by(Tag.order_index)  # type: ignore[arg-type]  -- Column expression valid at runtime
        )
        tags = list(tags_result.all())

        groups_result = await session.exec(
            select(TagGroup)
            .where(TagGroup.workspace_id == workspace_id)
            .order_by(TagGroup.order_index)  # type: ignore[arg-type]  -- Column expression valid at runtime
        )
        tag_groups = list(groups_result.all())

        # 6. Return
        return AnnotationContext(
            workspace=workspace,
            permission=permission,
            placement=placement,
            privileged_user_ids=privileged_user_ids,
            tags=tags,
            tag_groups=tag_groups,
        )


async def get_workspace_export_metadata(
    workspace_id: UUID,
) -> WorkspaceExportMetadata | None:
    """Return export metadata for a workspace, or None if the workspace is missing.

    Resolves owner identity via an ACL join and placement via the existing
    private placement helpers, all within a single async session. This helper
    is viewer-agnostic: it never reads NiceGUI or session state.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None:
            return None

        # Resolve owner display name via ACL -> User join
        owner_result = await session.exec(
            select(User.display_name)
            .join(ACLEntry, ACLEntry.user_id == User.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement, not bool
            .where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.permission == "owner",
            )
        )
        owner_display_name: str | None = owner_result.first()

        # Resolve placement using private helpers (same session)
        if workspace.activity_id is not None:
            placement = await _resolve_activity_placement(
                session, workspace.activity_id
            )
        elif workspace.course_id is not None:
            placement = await _resolve_course_placement(session, workspace.course_id)
        else:
            placement = PlacementContext(placement_type="loose")

        return WorkspaceExportMetadata(
            course_code=placement.course_code,
            activity_title=placement.activity_title,
            workspace_title=workspace.title,
            owner_display_name=owner_display_name,
        )


async def get_placement_context(workspace_id: UUID) -> PlacementContext:
    """Resolve the full hierarchy context for a workspace's placement.

    Fetches the workspace and walks the Activity -> Week -> Course chain
    (if placed in an Activity) or just the Course (if placed in a Course)
    within a single session for consistency.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        PlacementContext with all resolved fields. Returns a loose context
        if the workspace is not found or has no placement.
    """
    loose = PlacementContext(placement_type="loose")
    async with get_session() as session:
        # Fetch workspace and template flag in a single query using an
        # EXISTS subquery, avoiding a separate round-trip for the check.
        template_exists = exists(
            select(Activity.id).where(Activity.template_workspace_id == workspace_id)
        )
        result = await session.exec(
            select(Workspace, template_exists.label("is_template")).where(
                Workspace.id == workspace_id
            )
        )
        row = result.first()
        if row is None:
            return loose

        workspace, is_template = row

        if workspace.activity_id is not None:
            ctx = await _resolve_activity_placement(session, workspace.activity_id)
            if is_template:
                return replace(ctx, is_template=True)
            return ctx

        if workspace.course_id is not None:
            return await _resolve_course_placement(session, workspace.course_id)

        return loose


def resolve_tristate(override: bool | None, default: bool) -> bool:
    """Resolve a tri-state activity setting against its course default.

    Activity-level overrides (True/False) win; None inherits the course default.
    """
    if override is not None:
        return override
    return default


async def _resolve_activity_placement(
    session: AsyncSession,
    activity_id: UUID,
) -> PlacementContext:
    """Walk Activity -> Week -> Course chain in a single JOIN query.

    Falls back to loose placement if any link in the chain is missing.
    """
    result = await session.exec(
        select(Activity, Week, Course)
        .join(Week, Activity.week_id == Week.id)  # type: ignore[arg-type]  -- Column == returns ColumnElement
        .join(Course, Week.course_id == Course.id)  # type: ignore[arg-type]  -- Column == returns ColumnElement
        .where(Activity.id == activity_id)
    )
    row = result.first()
    if row is None:
        return PlacementContext(placement_type="loose")

    activity, week, course = row

    return PlacementContext(
        placement_type="activity",
        activity_title=activity.title,
        week_number=week.week_number,
        week_title=week.title,
        course_code=course.code,
        course_name=course.name,
        copy_protection=resolve_tristate(
            activity.copy_protection, course.default_copy_protection
        ),
        allow_sharing=resolve_tristate(
            activity.allow_sharing, course.default_allow_sharing
        ),
        anonymous_sharing=resolve_tristate(
            activity.anonymous_sharing, course.default_anonymous_sharing
        ),
        allow_tag_creation=resolve_tristate(
            activity.allow_tag_creation, course.default_allow_tag_creation
        ),
        word_minimum=activity.word_minimum,
        word_limit=activity.word_limit,
        word_limit_enforcement=resolve_tristate(
            activity.word_limit_enforcement, course.default_word_limit_enforcement
        ),
        course_id=course.id,
    )


async def _resolve_course_placement(
    session: AsyncSession,
    course_id: UUID,
) -> PlacementContext:
    """Resolve Course placement. Falls back to loose on orphan.

    Propagates all course-level defaults (copy_protection, allow_sharing,
    anonymous_sharing) since there is no Activity to override them.
    """
    course = await session.get(Course, course_id)
    if course is None:
        return PlacementContext(placement_type="loose")
    return PlacementContext(
        placement_type="course",
        course_code=course.code,
        course_name=course.name,
        copy_protection=course.default_copy_protection,
        allow_sharing=course.default_allow_sharing,
        anonymous_sharing=course.default_anonymous_sharing,
        word_limit_enforcement=course.default_word_limit_enforcement,
    )


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


async def delete_workspace(workspace_id: UUID, *, user_id: UUID) -> None:
    """Delete a workspace and all its documents (CASCADE).

    Checks that ``user_id`` is a literal owner of the workspace via
    :class:`ACLEntry` before proceeding.  This is a defence-in-depth
    check -- the UI layer should also verify ownership.

    Uses a direct ACLEntry query for ``permission == "owner"``, NOT
    ``resolve_permission()`` which would let admins pass via the full
    ACL chain.  Admin bypass belongs in the UI layer only.

    Args:
        workspace_id: The workspace UUID.
        user_id: The user attempting the deletion. Must be workspace owner.

    Raises:
        PermissionError: If ``user_id`` is not the workspace owner.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            return

        # Check literal ownership via ACLEntry (NOT resolve_permission)
        owner_entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        if owner_entry.first() is None:
            msg = "Only workspace owner can delete"
            raise OwnershipError(msg)

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
            workspace.search_dirty = True
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
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
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
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        return list(result.all())


def _remap_uuid_str(raw: str, id_map: dict[UUID, UUID] | None) -> str:
    """Remap a string through a UUID mapping, passing non-UUIDs through.

    If *id_map* is ``None`` or *raw* is not a valid UUID, the original
    string is returned unchanged.  This handles legacy BriefTag strings
    (e.g. ``"jurisdiction"``) that are not UUIDs.
    """
    if id_map is None:
        return raw
    try:
        original = UUID(raw)
    except ValueError:
        logger.warning("uuid_remap_parse_failed", operation="remap_tag_id", raw=raw)
        return raw
    return str(id_map.get(original, original))


def _remap_cloned_tag_highlights(
    doc: AnnotationDocument,
    highlight_id_map: dict[str, str],
) -> None:
    """Remap highlight IDs in cloned workspace's tags Map entries."""
    for tag_id, tag_data in doc.list_tags().items():
        old_highlights = tag_data.get("highlights", [])
        remapped = [highlight_id_map.get(h, h) for h in old_highlights]
        doc.set_tag(
            tag_id=tag_id,
            name=tag_data["name"],
            colour=tag_data["colour"],
            order_index=tag_data["order_index"],
            group_id=tag_data.get("group_id"),
            description=tag_data.get("description"),
            highlights=remapped,
        )


def _replay_crdt_state(
    template: Workspace,
    clone: Workspace,
    doc_id_map: dict[UUID, UUID],
    tag_id_map: dict[UUID, UUID] | None = None,
    group_id_map: dict[UUID, UUID] | None = None,
) -> None:
    """Replay CRDT state from template into clone with ID remapping.

    Loads the template's CRDT state into a temporary AnnotationDocument,
    creates a fresh AnnotationDocument for the clone, and replays all
    highlights (with remapped document_id and tag values), comments,
    general notes, response draft markdown, and tags Map entries (with
    remapped tag IDs, group IDs, and highlight IDs). Client metadata is
    deliberately NOT replayed (AC4.9).

    If template has no crdt_state, the clone gets None (AC4.10).

    Args:
        template: The template Workspace (source of CRDT state).
        clone: The cloned Workspace (destination for replayed state).
        doc_id_map: Mapping of {template_doc_id: cloned_doc_id}.
        tag_id_map: Optional mapping of {template_tag_id: cloned_tag_id}.
            When provided, highlight tag fields containing valid UUIDs are
            remapped to the cloned tag UUIDs, and tags Map keys and
            group_id fields are similarly remapped. Non-UUID tag strings
            (legacy BriefTag values) pass through unchanged.
        group_id_map: Optional mapping of {template_group_id: cloned_group_id}.
            When provided, tag group_id fields in the tags Map are remapped
            to the cloned group UUIDs.
    """
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument as AnnotDoc

    if template.crdt_state is None:
        return

    # Load template CRDT state
    template_doc = AnnotDoc("template-tmp")
    template_doc.apply_update(template.crdt_state)

    # Fresh document for clone (empty client_meta satisfies AC4.9)
    clone_doc = AnnotDoc("clone-tmp")

    # Replay highlights with remapped document_id and tag
    highlight_id_map: dict[str, str] = {}
    for hl in template_doc.get_all_highlights():
        old_hl_id = hl["id"]

        # Remap document_id: template doc UUID -> cloned doc UUID
        raw_doc_id = hl.get("document_id")
        if raw_doc_id is not None:
            template_uuid = UUID(raw_doc_id)
            remapped_uuid = doc_id_map.get(template_uuid, template_uuid)
            remapped_doc_id: str | None = str(remapped_uuid)
        else:
            remapped_doc_id = None

        new_hl_id = clone_doc.add_highlight(
            start_char=hl["start_char"],
            end_char=hl["end_char"],
            tag=_remap_uuid_str(hl["tag"], tag_id_map),
            text=hl["text"],
            author=hl["author"],
            para_ref=hl.get("para_ref", ""),
            document_id=remapped_doc_id,
            user_id=hl.get("user_id"),
        )
        highlight_id_map[old_hl_id] = new_hl_id

        # Replay comments for this highlight
        for comment in hl.get("comments", []):
            clone_doc.add_comment(
                highlight_id=new_hl_id,
                author=comment["author"],
                text=comment["text"],
                user_id=comment.get("user_id"),
            )

    # Clone general notes
    notes = template_doc.get_general_notes()
    if notes:
        clone_doc.set_general_notes(notes)

    # Clone response draft markdown
    response_md = template_doc.get_response_draft_markdown()
    if response_md:
        md_field = clone_doc.response_draft_markdown
        with clone_doc.doc.transaction():
            md_field += response_md

    # Copy tags Map entries with remapped tag IDs and group IDs
    for old_tag_id, tag_data in template_doc.list_tags().items():
        remapped_tag_id = _remap_uuid_str(old_tag_id, tag_id_map)
        raw_group = tag_data.get("group_id")
        remapped_group = _remap_uuid_str(raw_group, group_id_map) if raw_group else None
        clone_doc.set_tag(
            tag_id=remapped_tag_id,
            name=tag_data["name"],
            colour=tag_data["colour"],
            order_index=tag_data["order_index"],
            group_id=remapped_group,
            description=tag_data.get("description"),
            highlights=tag_data.get("highlights", []),
        )

    # Remap highlight IDs within cloned tags Map entries
    _remap_cloned_tag_highlights(clone_doc, highlight_id_map)

    # Serialise and assign to cloned workspace
    clone.crdt_state = clone_doc.get_full_state()


async def find_duplicate_workspaces() -> list[dict[str, Any]]:
    """Find (activity_id, user_id) pairs with duplicate owner workspaces.

    Returns a list of dicts with keys: activity_id, user_id, user_email,
    user_display_name, workspace_ids (list ordered by created_at),
    duplicate_count.

    Automated deletion is unsafe — either duplicate may contain student edits.
    Results require manual review.
    """
    async with get_session() as session:
        result = await session.execute(
            text("""
                SELECT w.activity_id, ae.user_id, u.email, u.display_name,
                       array_agg(w.id ORDER BY w.created_at) AS workspace_ids,
                       count(*) AS duplicate_count
                FROM workspace w
                JOIN acl_entry ae ON ae.workspace_id = w.id AND ae.permission = 'owner'
                JOIN "user" u ON u.id = ae.user_id
                WHERE w.activity_id IS NOT NULL
                GROUP BY w.activity_id, ae.user_id, u.email, u.display_name
                HAVING count(*) > 1
                ORDER BY duplicate_count DESC
            """)
        )
        return [
            {
                "activity_id": row.activity_id,
                "user_id": row.user_id,
                "user_email": row.email,
                "user_display_name": row.display_name,
                "workspace_ids": list(row.workspace_ids),
                "duplicate_count": row.duplicate_count,
            }
            for row in result.fetchall()
        ]


async def clone_workspace_from_activity(
    activity_id: UUID,
    user_id: UUID,
) -> tuple[Workspace, dict[UUID, UUID]]:
    """Clone an Activity's template workspace into a new student workspace.

    Creates a new Workspace within a single transaction, copies all template
    documents (preserving content, type, source_type, title, order_index),
    builds a document ID mapping, clones TagGroups and Tags (with group_id
    remapping), and replays CRDT state (highlights, comments, general notes)
    with remapped document IDs and tag IDs. Client metadata is NOT cloned --
    the fresh workspace starts with empty client state.

    Tags are cloned via direct ``session.add()``, bypassing CRUD permission
    checks -- cloning is a system operation that always copies the
    instructor's tag set regardless of the ``allow_tag_creation`` flag.

    Also creates an ACLEntry granting owner permission to the cloning user.

    Args:
        activity_id: The Activity UUID whose template workspace to clone.
        user_id: The user UUID who will own the cloned workspace.

    Returns:
        Tuple of (Workspace, doc_id_map). On fresh clone, doc_id_map is
        ``{template_doc_id: cloned_doc_id}`` with one entry per template
        document. On idempotent hit (workspace already exists for this
        activity + user), returns the existing workspace with an empty
        ``{}`` map.

    Raises:
        ValueError: If Activity or its template workspace is not found.
    """
    async with get_session() as session:
        # Advisory lock: prevent concurrent duplicate clones for same (activity, user)
        ns_key = (
            int(
                hashlib.md5(
                    b"clone_workspace_from_activity", usedforsecurity=False
                ).hexdigest()[:8],
                16,
            )
            & 0x7FFFFFFF
        )
        inst_key = (
            int(
                hashlib.md5(
                    f"{activity_id}-{user_id}".encode(), usedforsecurity=False
                ).hexdigest()[:8],
                16,
            )
            & 0x7FFFFFFF
        )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :inst)").bindparams(
                ns=ns_key, inst=inst_key
            )
        )

        # Idempotency check: return existing workspace if already cloned
        existing = await session.exec(
            select(Workspace)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement, not bool
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        found = existing.first()
        if found is not None:
            return found, {}

        activity = await session.get(Activity, activity_id)
        if not activity:
            msg = f"Activity {activity_id} not found"
            raise ValueError(msg)

        template = await session.get(Workspace, activity.template_workspace_id)
        if not template:
            msg = f"Template workspace {activity.template_workspace_id} not found"
            raise ValueError(msg)

        # Create new workspace with activity_id and enable_save_as_draft copied
        clone = Workspace(
            activity_id=activity_id,
            enable_save_as_draft=template.enable_save_as_draft,
            title=activity.title,
        )
        session.add(clone)
        await session.flush()

        # Grant owner permission to cloning user
        acl_entry = ACLEntry(
            workspace_id=clone.id,
            team_id=None,
            user_id=user_id,
            permission="owner",
        )
        session.add(acl_entry)
        await session.flush()

        # --- Bulk-clone documents via INSERT...SELECT ---
        doc_result = await session.execute(
            text("""
                INSERT INTO workspace_document
                    (id, workspace_id, type, content, source_type,
                     order_index, title, auto_number_paragraphs,
                     paragraph_map, source_document_id, created_at)
                SELECT
                    gen_random_uuid(), :clone_id, type, content,
                    source_type, order_index, title,
                    auto_number_paragraphs, paragraph_map, id, now()
                FROM workspace_document
                WHERE workspace_id = :template_id
                RETURNING id, source_document_id
            """),
            {"clone_id": clone.id, "template_id": template.id},
        )
        doc_id_map: dict[UUID, UUID] = {
            row.source_document_id: row.id for row in doc_result.fetchall()
        }

        # --- Bulk-clone tag groups via INSERT...SELECT ---
        group_result = await session.execute(
            text("""
                INSERT INTO tag_group
                    (id, workspace_id, name, color, order_index,
                     created_at)
                SELECT
                    gen_random_uuid(), :clone_id, name, color,
                    order_index, now()
                FROM tag_group
                WHERE workspace_id = :template_id
                RETURNING id, name
            """),
            {"clone_id": clone.id, "template_id": template.id},
        )
        new_groups_by_name = {row.name: row.id for row in group_result.fetchall()}

        template_group_result = await session.execute(
            text("SELECT id, name FROM tag_group WHERE workspace_id = :template_id"),
            {"template_id": template.id},
        )
        group_id_map: dict[UUID, UUID] = {
            row.id: new_groups_by_name[row.name]
            for row in template_group_result.fetchall()
            if row.name in new_groups_by_name
        }

        # --- Bulk-clone tags via INSERT...SELECT with group remapping ---
        tag_result = await session.execute(
            text("""
                INSERT INTO tag
                    (id, workspace_id, group_id, name, description,
                     color, locked, order_index, created_at)
                SELECT
                    gen_random_uuid(), :clone_id, ng.id, t.name,
                    t.description, t.color, t.locked, t.order_index,
                    now()
                FROM tag t
                LEFT JOIN tag_group og ON t.group_id = og.id
                LEFT JOIN tag_group ng
                    ON ng.workspace_id = :clone_id AND ng.name = og.name
                WHERE t.workspace_id = :template_id
                RETURNING id, name
            """),
            {"clone_id": clone.id, "template_id": template.id},
        )
        new_tags_by_name = {row.name: row.id for row in tag_result.fetchall()}

        template_tag_result = await session.execute(
            text("SELECT id, name FROM tag WHERE workspace_id = :template_id"),
            {"template_id": template.id},
        )
        tag_id_map: dict[UUID, UUID] = {
            row.id: new_tags_by_name[row.name]
            for row in template_tag_result.fetchall()
            if row.name in new_tags_by_name
        }

        # --- Sync workspace counter columns after cloning tags/groups ---
        clone.next_tag_order = len(tag_id_map)
        clone.next_group_order = len(group_id_map)
        session.add(clone)

        # --- CRDT state cloning via API replay ---
        _replay_crdt_state(template, clone, doc_id_map, tag_id_map, group_id_map)

        await session.flush()
        await session.refresh(clone)
        return clone, doc_id_map


async def _update_workspace_fields(
    workspace_id: UUID,
    **fields: Any,
) -> Workspace:
    """Fetch a workspace, apply field updates, and persist.

    Shared implementation for single-field update functions. Handles
    the fetch-or-raise, timestamp bump, flush, and refresh boilerplate.

    Args:
        workspace_id: The workspace UUID.
        **fields: Field name/value pairs to set on the workspace.

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
        for attr, value in fields.items():
            setattr(workspace, attr, value)
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def update_workspace_sharing(
    workspace_id: UUID,
    shared_with_class: bool,
) -> Workspace:
    """Update a workspace's class sharing status.

    Args:
        workspace_id: The workspace UUID.
        shared_with_class: Whether to share with class.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace not found.
    """
    return await _update_workspace_fields(
        workspace_id, shared_with_class=shared_with_class
    )


async def update_workspace_title(
    workspace_id: UUID,
    title: str | None,
) -> Workspace:
    """Update a workspace's display title.

    Args:
        workspace_id: The workspace UUID.
        title: New title, or None to clear.

    Returns:
        The updated Workspace.

    Raises:
        ValueError: If workspace not found.
    """
    return await _update_workspace_fields(workspace_id, title=title, search_dirty=True)
