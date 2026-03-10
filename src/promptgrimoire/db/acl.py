"""ACL (Access Control List) operations for workspace and team permissions.

Provides grant, revoke, query, and permission resolution operations
for per-user permission entries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    Permission,
    User,
    Week,
    Workspace,
)
from promptgrimoire.db.roles import get_staff_roles
from promptgrimoire.db.workspaces import resolve_tristate

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


async def grant_permission(
    workspace_id: UUID, user_id: UUID, permission: str
) -> ACLEntry:
    """Grant a permission to a user on a workspace.

    If the user already has a permission on this workspace, it is updated
    (upsert). Returns the created or updated ACLEntry.
    """
    async with get_session() as session:
        stmt = pg_insert(ACLEntry).values(
            workspace_id=workspace_id,
            team_id=None,
            user_id=user_id,
            permission=permission,
            created_at=datetime.now(UTC),
        )
        # Team-target ACL rows satisfy num_nonnulls(workspace_id, team_id) = 1
        # with workspace_id NULL, so workspace upserts must target the
        # workspace-only partial unique index explicitly.
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "user_id"],
            index_where=sa.text("workspace_id IS NOT NULL"),
            set_={"permission": stmt.excluded.permission},
        )
        await session.execute(stmt)
        await session.flush()

        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        return entry.one()


async def revoke_permission(
    workspace_id: UUID,
    user_id: UUID,
    *,
    on_revoke: Callable[[UUID, UUID], Awaitable[int]] | None = None,
) -> bool:
    """Revoke a user's permission on a workspace.

    Returns True if an entry was deleted, False if no entry existed.
    If on_revoke is provided and an entry was deleted, calls
    on_revoke(workspace_id, user_id) to notify connected clients.
    """
    async with get_session() as session:
        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        row = entry.one_or_none()
        if row is None:
            return False
        await session.delete(row)
        await session.flush()

    if on_revoke is not None:
        await on_revoke(workspace_id, user_id)

    return True


async def list_entries_for_workspace(workspace_id: UUID) -> list[ACLEntry]:
    """List all ACL entries for a workspace."""
    async with get_session() as session:
        result = await session.exec(
            select(ACLEntry).where(ACLEntry.workspace_id == workspace_id)
        )
        return list(result.all())


async def list_entries_for_user(user_id: UUID) -> list[ACLEntry]:
    """List all ACL entries for a user."""
    async with get_session() as session:
        result = await session.exec(select(ACLEntry).where(ACLEntry.user_id == user_id))
        return list(result.all())


async def list_accessible_workspaces(
    user_id: UUID,
) -> list[tuple[Workspace, str]]:
    """List all workspaces a user can access, with their permission level.

    Returns workspaces where the user has an explicit ACL entry. This covers:
    - Owned workspaces (permission="owner")
    - Shared workspaces (permission="editor" or "viewer")
    - Workspaces whose activity was deleted (activity_id SET NULL) —
      still returned because the ACLEntry persists.

    Returns
    -------
    list[tuple[Workspace, str]]
        (Workspace, permission_name) tuples, ordered by workspace.created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace, ACLEntry.permission)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement
            .where(
                ACLEntry.user_id == user_id,
                ACLEntry.workspace_id != None,  # noqa: E711
            )
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        return list(result.all())


async def list_course_workspaces(
    course_id: UUID,
) -> list[Workspace]:
    """List all non-template workspaces in a course (instructor view).

    Finds workspaces via two paths:
    1. Activity-placed: Workspace.activity_id -> Activity.week_id -> Week.course_id
    2. Loose: Workspace.course_id = course_id (directly placed in course)

    Excludes template workspaces (those referenced by Activity.template_workspace_id).

    Returns
    -------
    list[Workspace]
        Non-template workspaces. Activity-placed workspaces first, then
        loose workspaces, each group ordered by created_at.
    """
    async with get_session() as session:
        # Collect template workspace IDs to exclude
        template_result = await session.exec(
            select(Activity.template_workspace_id)
            .join(Week, Activity.week_id == Week.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement
            .where(Week.course_id == course_id)
        )
        template_ids = set(template_result.all())

        # Activity-placed workspaces: via Activity -> Week -> Course
        activity_result = await session.exec(
            select(Workspace)
            .join(Activity, Workspace.activity_id == Activity.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement
            .join(Week, Activity.week_id == Week.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement
            .where(Week.course_id == course_id)
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs
        )
        activity_workspaces = list(activity_result.all())

        # Loose workspaces: directly placed in course
        loose_result = await session.exec(
            select(Workspace)
            .where(Workspace.course_id == course_id)
            .where(Workspace.activity_id == None)  # noqa: E711
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs
        )
        loose_workspaces = list(loose_result.all())

        # Combine and exclude templates
        all_workspaces = activity_workspaces + loose_workspaces
        return [ws for ws in all_workspaces if ws.id not in template_ids]


async def list_activity_workspaces(
    activity_id: UUID,
) -> list[tuple[Workspace, str, UUID]]:
    """List all non-template workspaces for an activity with owner info.

    Returns workspaces placed in this activity that have an ACL entry
    with "owner" permission. This is the per-activity instructor view
    showing who has cloned the activity.

    Returns
    -------
    list[tuple[Workspace, str, UUID]]
        (Workspace, permission, user_id) tuples, ordered by workspace.created_at.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return []
        template_id = activity.template_workspace_id

        result = await session.exec(
            select(Workspace, ACLEntry.permission, ACLEntry.user_id)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy == returns ColumnElement
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.permission == "owner",
                ACLEntry.workspace_id != None,  # noqa: E711
            )
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs
        )
        rows = list(result.all())
        return [(ws, perm, uid) for ws, perm, uid in rows if ws.id != template_id]


async def _resolve_workspace_course(
    session: AsyncSession, workspace: Workspace
) -> tuple[Course | None, Activity | None]:
    """Walk Workspace → (Activity → Week →) Course hierarchy.

    Returns (course, activity) where activity is None for course-placed
    or loose workspaces.
    """
    if workspace.activity_id is not None:
        activity = await session.get(Activity, workspace.activity_id)
        if activity is not None:
            week = await session.get(Week, activity.week_id)
            if week is not None:
                course = await session.get(Course, week.course_id)
                return course, activity
        return None, activity
    if workspace.course_id is not None:
        course = await session.get(Course, workspace.course_id)
        return course, None
    return None, None


async def _derive_enrollment_permission(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> str | None:
    """Derive permission from course enrollment.

    Resolves Workspace -> (Activity -> Week ->) Course hierarchy.
    Staff roles get Course.default_instructor_permission.
    Students get "peer" if the activity allows sharing and the workspace
    has opted in via shared_with_class.
    """
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        return None

    course, activity = await _resolve_workspace_course(session, workspace)
    if course is None:
        return None

    enrollment_result = await session.exec(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.user_id == user_id,
        )
    )
    enrollment = enrollment_result.one_or_none()
    if enrollment is None:
        return None

    # Staff roles get derived instructor access
    staff_roles = await get_staff_roles()
    if enrollment.role in staff_roles:
        return course.default_instructor_permission

    # Student peer path: enrolled + allow_sharing resolved + shared_with_class
    if workspace.shared_with_class:
        activity_override = activity.allow_sharing if activity is not None else None
        allow_sharing = resolve_tristate(
            activity_override, course.default_allow_sharing
        )

        if allow_sharing:
            return "peer"

    return None


async def _resolve_permission_with_session(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> str | None:
    """Internal: resolve permission using an existing session.

    Hybrid resolution:
    1. Explicit ACL lookup: query ACLEntry for (workspace_id, user_id).
    2. Enrollment-derived: resolve Workspace -> Activity -> Week -> Course
       hierarchy, check CourseEnrollment for staff/student role.
    3. If both apply, the higher Permission.level wins.
    4. Default deny: return None.
    """
    # Step 1: Explicit ACL lookup
    explicit_result = await session.exec(
        select(ACLEntry).where(
            ACLEntry.workspace_id == workspace_id,
            ACLEntry.user_id == user_id,
        )
    )
    explicit = explicit_result.one_or_none()

    # Step 2: Enrollment-derived access
    derived_permission = await _derive_enrollment_permission(
        session, workspace_id, user_id
    )

    # Step 3: Highest wins
    if explicit and derived_permission:
        level_result = await session.exec(
            select(Permission.name, Permission.level).where(
                Permission.name.in_([explicit.permission, derived_permission])  # type: ignore[union-attr]  -- Column has in_
            )
        )
        levels = dict(level_result.all())
        e_level = levels[explicit.permission]
        d_level = levels[derived_permission]
        return explicit.permission if e_level >= d_level else derived_permission

    if explicit:
        return explicit.permission
    if derived_permission:
        return derived_permission

    # Step 4: Default deny
    return None


async def resolve_permission(workspace_id: UUID, user_id: UUID) -> str | None:
    """Resolve the effective permission for a user on a workspace.

    Two-step hybrid resolution:
    1. Explicit ACL lookup: query ACLEntry for (workspace_id, user_id).
    2. Enrollment-derived: resolve Workspace -> Activity -> Week -> Course
       hierarchy, check CourseEnrollment for staff role.
    3. If both apply, the higher Permission.level wins.
    4. Default deny: return None.

    Admin bypass is NOT checked here -- that belongs at the page level
    via is_privileged_user().

    Returns:
        Permission name string (e.g., "owner", "editor", "viewer") or None
        if denied.
    """
    async with get_session() as session:
        return await _resolve_permission_with_session(session, workspace_id, user_id)


async def grant_share(
    workspace_id: UUID,
    grantor_id: UUID,
    recipient_id: UUID,
    permission: str,
    *,
    sharing_allowed: bool,
    grantor_is_staff: bool = False,
) -> ACLEntry:
    """Share a workspace with another user.

    Validates sharing rules before creating the ACLEntry:
    1. Permission must be "editor" or "viewer" (never "owner").
    2. Grantor must be the workspace owner OR grantor_is_staff.
    3. If not staff, sharing must be allowed (sharing_allowed=True).

    The ownership check and grant happen in a single session to mitigate
    TOCTOU races. The grantor's ACLEntry is locked with SELECT ... FOR UPDATE
    to prevent concurrent revocation between the check and the grant.

    Parameters
    ----------
    workspace_id : UUID
        The Workspace UUID.
    grantor_id : UUID
        The user UUID granting the share.
    recipient_id : UUID
        The user UUID receiving the share.
    permission : str
        Permission level to grant ("editor" or "viewer").
    sharing_allowed : bool
        Whether sharing is enabled for this workspace's context.
    grantor_is_staff : bool
        Whether the grantor is an instructor/coordinator/tutor.

    Returns
    -------
    ACLEntry
        The created or updated ACLEntry.

    Raises
    ------
    PermissionError
        If sharing rules are violated.
    """
    if permission == "owner":
        raise PermissionError("cannot grant owner permission via sharing")

    async with get_session() as session:
        await _validate_share_grantor(
            session, workspace_id, grantor_id, sharing_allowed, grantor_is_staff
        )
        return await _upsert_share_entry(
            session, workspace_id, recipient_id, permission
        )


async def _validate_share_grantor(
    session: AsyncSession,
    workspace_id: UUID,
    grantor_id: UUID,
    sharing_allowed: bool,
    grantor_is_staff: bool,
) -> None:
    """Check that the grantor may share this workspace.

    Staff bypass ownership checks. Non-staff must own the workspace
    (locked with FOR UPDATE) and sharing must be enabled.
    """
    if grantor_is_staff:
        return

    entry = await session.exec(
        select(ACLEntry)
        .where(
            ACLEntry.workspace_id == workspace_id,
            ACLEntry.user_id == grantor_id,
        )
        .with_for_update()
    )
    grantor_entry = entry.one_or_none()
    if grantor_entry is None or grantor_entry.permission != "owner":
        raise PermissionError("only workspace owners can share")

    if not sharing_allowed:
        raise PermissionError("sharing is not allowed for this workspace")


async def _upsert_share_entry(
    session: AsyncSession,
    workspace_id: UUID,
    recipient_id: UUID,
    permission: str,
) -> ACLEntry:
    """Create or update an ACL entry for a share recipient."""
    existing = await session.exec(
        select(ACLEntry).where(
            ACLEntry.workspace_id == workspace_id,
            ACLEntry.user_id == recipient_id,
        )
    )
    acl_entry = existing.one_or_none()
    if acl_entry is not None:
        if acl_entry.permission == "owner":
            raise PermissionError("cannot modify owner permission via sharing")
        acl_entry.permission = permission
    else:
        acl_entry = ACLEntry(
            workspace_id=workspace_id,
            team_id=None,
            user_id=recipient_id,
            permission=permission,
        )
        session.add(acl_entry)
    await session.flush()
    await session.refresh(acl_entry)
    return acl_entry


async def list_importable_workspaces(
    user_id: UUID,
    exclude_workspace_id: UUID | None = None,
    *,
    is_privileged: bool = False,
    enrolled_course_ids: Sequence[UUID] | None = None,
) -> list[tuple[Workspace, str | None, list[str]]]:
    """List workspaces with tags that the user can read from.

    Visibility mirrors the navigator query: workspaces accessible via
    explicit ACL entries, enrollment-derived staff access, and
    peer-shared workspaces (shared_with_class + allow_sharing).

    Returns (workspace, course_name, tag_names) tuples.  Excludes the
    specified workspace (typically the target) and workspaces with no
    tags.  Deduplicates workspaces whose tag sets are identical.

    Args:
        user_id: The requesting user's UUID.
        exclude_workspace_id: Workspace to exclude (e.g. the import target).
        is_privileged: Whether the user has instructor/admin privileges
            (bypasses shared_with_class check for peer workspaces).
        enrolled_course_ids: Course UUIDs the user is enrolled in.
            Required for enrollment-derived visibility.

    Returns:
        List of (Workspace, course_name, tag_names) tuples.
    """
    course_ids = list(enrolled_course_ids) if enrolled_course_ids else []

    # Single raw SQL query combining three visibility paths:
    #   1. ACL-granted workspaces (explicit share or ownership)
    #   2. Template workspaces in enrolled courses (staff only)
    #   3. Peer-shared workspaces in enrolled courses
    #
    # Mirrors the navigator CTE visibility logic but returns only
    # workspaces that have at least one tag, with tag names aggregated.
    sql = sa.text("""
        WITH visible AS (
            -- Path 1: ACL-granted workspaces
            SELECT DISTINCT w.id AS workspace_id,
                   acl.permission AS permission
            FROM workspace w
            JOIN acl_entry acl ON acl.workspace_id = w.id
                AND acl.user_id = :user_id

            UNION ALL

            -- Path 2: Template workspaces in enrolled courses (staff)
            SELECT DISTINCT a.template_workspace_id AS workspace_id,
                   'viewer'::text AS permission
            FROM activity a
            JOIN week wk ON wk.id = a.week_id
            WHERE a.template_workspace_id IS NOT NULL
                AND wk.course_id = ANY(:enrolled_course_ids)
                AND :is_privileged = true

            UNION ALL

            -- Path 3a: Peer-shared activity-placed workspaces
            SELECT DISTINCT w.id AS workspace_id,
                   'peer'::text AS permission
            FROM workspace w
            JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
                AND owner_acl.permission = 'owner'
            LEFT JOIN activity tmpl_check
                ON tmpl_check.template_workspace_id = w.id
            JOIN activity a ON a.id = w.activity_id
            JOIN week wk ON wk.id = a.week_id
            JOIN course c ON c.id = wk.course_id
            WHERE tmpl_check.id IS NULL
                AND c.id = ANY(:enrolled_course_ids)
                AND owner_acl.user_id != :user_id
                AND (
                    :is_privileged = true
                    OR (
                        w.shared_with_class = true
                        AND COALESCE(a.allow_sharing, c.default_allow_sharing)
                            = true
                    )
                )

            UNION ALL

            -- Path 3b: Peer-shared loose workspaces (no activity)
            SELECT DISTINCT w.id AS workspace_id,
                   'peer'::text AS permission
            FROM workspace w
            JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
                AND owner_acl.permission = 'owner'
            JOIN course c ON c.id = w.course_id
            WHERE w.activity_id IS NULL
                AND c.id = ANY(:enrolled_course_ids)
                AND owner_acl.user_id != :user_id
                AND (
                    :is_privileged = true
                    OR (
                        w.shared_with_class = true
                        AND c.default_allow_sharing = true
                    )
                )
        ),
        -- Deduplicate by workspace_id, keeping highest permission
        deduped AS (
            SELECT workspace_id,
                   MIN(CASE permission
                       WHEN 'owner' THEN 0
                       WHEN 'editor' THEN 1
                       WHEN 'viewer' THEN 2
                       ELSE 3
                   END) AS perm_rank
            FROM visible
            WHERE (CAST(:exclude_id AS uuid) IS NULL
                   OR workspace_id != :exclude_id)
            GROUP BY workspace_id
        )
        -- Final: join with tags and course info
        SELECT w.id,
               COALESCE(c1.name, c2.name) AS course_name,
               array_agg(t.name ORDER BY t.order_index) AS tag_names,
               w.activity_id IS NOT NULL AS is_template,
               d.perm_rank
        FROM deduped d
        JOIN workspace w ON w.id = d.workspace_id
        JOIN tag t ON t.workspace_id = w.id
        LEFT JOIN activity a ON a.id = w.activity_id
        LEFT JOIN week wk ON wk.id = a.week_id
        LEFT JOIN course c1 ON c1.id = wk.course_id
        LEFT JOIN course c2 ON c2.id = w.course_id
        GROUP BY w.id, c1.name, c2.name, w.activity_id, d.perm_rank
        ORDER BY
            (w.activity_id IS NOT NULL) DESC,  -- templates first
            d.perm_rank,                        -- owner > editor > viewer > peer
            array_length(array_agg(t.name), 1) DESC,  -- more tags first
            COALESCE(c1.name, c2.name, ''),
            COALESCE(w.title, '')
    """)

    async with get_session() as session:
        raw = await session.execute(
            sql,
            {
                "user_id": user_id,
                "enrolled_course_ids": course_ids,
                "is_privileged": is_privileged,
                "exclude_id": exclude_workspace_id,
            },
        )
        rows = raw.fetchall()

    if not rows:
        return []

    # Hydrate Workspace objects and build result tuples
    ws_ids = [row[0] for row in rows]
    async with get_session() as session:
        ws_result = await session.exec(
            select(Workspace).where(Workspace.id.in_(ws_ids))  # type: ignore[union-attr]
        )
        ws_by_id: dict[UUID, Workspace] = {ws.id: ws for ws in ws_result.all()}

    result: list[tuple[Workspace, str | None, list[str]]] = []
    seen_tag_sets: set[tuple[str, ...]] = set()
    for ws_id, course_name, tag_names, _is_template, _perm_rank in rows:
        ws = ws_by_id.get(ws_id)
        if ws is None:
            continue
        key = tuple(sorted(n.lower() for n in tag_names))
        if key not in seen_tag_sets:
            seen_tag_sets.add(key)
            result.append((ws, course_name, tag_names))
    return result


async def get_privileged_user_ids_for_workspace(
    workspace_id: UUID,
) -> frozenset[str]:
    """Return user IDs of privileged users in this workspace's course context.

    Finds the course containing this workspace (via activity/week or
    direct course_id), then returns the string-form ``User.id`` for:
    - Users enrolled with a staff role (``CourseRoleRef.is_staff=True``)
    - Org-level admins (``User.is_admin=True``)

    These IDs match the ``user_id`` stored in CRDT annotations,
    allowing callers to determine whether an annotation author
    is privileged without per-author DB queries.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None:
            return frozenset()

        # Resolve course_id from workspace placement
        course_id = workspace.course_id
        if course_id is None and workspace.activity_id is not None:
            activity = await session.get(Activity, workspace.activity_id)
            if activity is not None:
                week = await session.get(Week, activity.week_id)
                if week is not None:
                    course_id = week.course_id

        staff_ids: set[str] = set()

        if course_id is not None:
            staff_roles = await get_staff_roles()
            result = await session.exec(
                select(CourseEnrollment.user_id).where(
                    CourseEnrollment.course_id == course_id,
                    CourseEnrollment.role.in_(staff_roles),  # type: ignore[union-attr]  -- Column has in_
                )
            )
            staff_ids = {str(uid) for uid in result.all()}

        # Also include org-level admins
        admin_result = await session.exec(
            select(User.id).where(User.is_admin == True)  # noqa: E712
        )
        admin_ids = {str(uid) for uid in admin_result.all()}

        return frozenset(staff_ids | admin_ids)


async def list_peer_workspaces(
    activity_id: UUID, exclude_user_id: UUID
) -> list[Workspace]:
    """List workspaces in an activity that have opted into peer sharing.

    Returns workspaces where shared_with_class=True for the given
    activity, excluding:
    - Template workspaces (Activity.template_workspace_id)
    - The requesting user's own workspaces (owner ACL entries)

    This is a direct query for the peer discovery UI (Phase 6).
    It does NOT check enrollment or allow_sharing -- the caller
    is responsible for gating visibility.

    Parameters
    ----------
    activity_id : UUID
        The Activity UUID to find shared workspaces for.
    exclude_user_id : UUID
        The requesting user's UUID (their own workspaces excluded).

    Returns
    -------
    list[Workspace]
        Shared workspaces, ordered by created_at.
    """
    async with get_session() as session:
        # Find template workspace ID for this activity
        activity = await session.get(Activity, activity_id)
        template_id = activity.template_workspace_id if activity else None

        # Team-target ACL rows satisfy num_nonnulls(workspace_id, team_id) = 1
        # with workspace_id NULL, so this NOT IN subquery must exclude NULLs
        # explicitly to avoid NULL poisoning workspace-only peer discovery.
        owned_subq = (
            select(ACLEntry.workspace_id)
            .where(
                ACLEntry.user_id == exclude_user_id,
                ACLEntry.permission == "owner",
                ACLEntry.workspace_id != None,  # noqa: E711
            )
            .scalar_subquery()
        )

        # Main query
        stmt = (
            select(Workspace)
            .where(
                Workspace.activity_id == activity_id,
                Workspace.shared_with_class == True,  # noqa: E712
            )
            .where(Workspace.id.not_in(owned_subq))  # type: ignore[union-attr]  -- Column has not_in
            .order_by(Workspace.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs
        )

        # Exclude template workspace
        if template_id is not None:
            stmt = stmt.where(Workspace.id != template_id)

        result = await session.exec(stmt)
        return list(result.all())


async def list_peer_workspaces_with_owners(
    activity_id: UUID, exclude_user_id: UUID
) -> list[tuple[Workspace, str, UUID]]:
    """List shared peer workspaces with owner display names.

    Same filtering as ``list_peer_workspaces`` but joins with
    ACLEntry + User to return owner info in a single query.

    Returns
    -------
    list[tuple[Workspace, str, UUID]]
        (workspace, owner_display_name, owner_user_id) tuples,
        ordered by created_at.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        template_id = activity.template_workspace_id if activity else None

        # Team-target ACL rows satisfy num_nonnulls(workspace_id, team_id) = 1
        # with workspace_id NULL, so this NOT IN subquery must exclude NULLs
        # explicitly to keep workspace-owner filtering NULL-safe.
        owned_subq = (
            select(ACLEntry.workspace_id)
            .where(
                ACLEntry.user_id == exclude_user_id,
                ACLEntry.permission == "owner",
                ACLEntry.workspace_id != None,  # noqa: E711
            )
            .scalar_subquery()
        )

        stmt = (
            select(Workspace, User.display_name, ACLEntry.user_id)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  -- SQLAlchemy join stubs
            .join(User, User.id == ACLEntry.user_id)  # type: ignore[arg-type]  -- SQLAlchemy join stubs
            .where(
                Workspace.activity_id == activity_id,
                Workspace.shared_with_class == True,  # noqa: E712
                ACLEntry.permission == "owner",
            )
            .where(Workspace.id.not_in(owned_subq))  # type: ignore[union-attr]
            .order_by(Workspace.created_at)  # type: ignore[arg-type]
        )

        if template_id is not None:
            stmt = stmt.where(Workspace.id != template_id)

        rows = await session.exec(stmt)
        return [(row[0], row[1], row[2]) for row in rows.all()]
