"""ACL (Access Control List) operations for workspace permissions.

Provides grant, revoke, query, and permission resolution operations
for per-user, per-workspace permission entries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    Permission,
    Week,
    Workspace,
    _utcnow,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

# Roles that derive instructor-level access from course enrollment
_STAFF_ROLES = frozenset({"coordinator", "instructor", "tutor"})


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
            user_id=user_id,
            permission=permission,
            created_at=_utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_acl_entry_workspace_user",
            set_={"permission": stmt.excluded.permission},
        )
        await session.execute(stmt)
        await session.flush()

        # Fetch the upserted row
        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        return entry.one()


async def revoke_permission(workspace_id: UUID, user_id: UUID) -> bool:
    """Revoke a user's permission on a workspace.

    Returns True if an entry was deleted, False if no entry existed.
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


async def _derive_enrollment_permission(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> str | None:
    """Derive permission from course enrollment for staff roles.

    Resolves Workspace -> (Activity -> Week ->) Course hierarchy.
    Checks CourseEnrollment for instructor/coordinator/tutor role.
    Returns Course.default_instructor_permission if staff, None otherwise.
    """
    # Find workspace
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        return None

    # Resolve course_id from workspace placement
    course_id: UUID | None = None

    if workspace.activity_id is not None:
        # Activity-placed: Activity -> Week -> Course
        activity = await session.get(Activity, workspace.activity_id)
        if activity is not None:
            week = await session.get(Week, activity.week_id)
            if week is not None:
                course_id = week.course_id
    elif workspace.course_id is not None:
        # Course-placed: direct
        course_id = workspace.course_id

    # Loose workspaces (no activity_id, no course_id): no enrollment derivation
    if course_id is None:
        return None

    # Check enrollment with staff role
    enrollment_result = await session.exec(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.user_id == user_id,
        )
    )
    enrollment = enrollment_result.one_or_none()
    if enrollment is None:
        return None

    # Staff roles get derived access; students do not
    if enrollment.role not in _STAFF_ROLES:
        return None

    # Return course's default instructor permission
    course = await session.get(Course, course_id)
    if course is None:
        return None
    return course.default_instructor_permission


async def _resolve_permission_with_session(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> str | None:
    """Internal: resolve permission using an existing session.

    Two-step hybrid resolution:
    1. Explicit ACL lookup: query ACLEntry for (workspace_id, user_id).
    2. Enrollment-derived: resolve Workspace -> Activity -> Week -> Course
       hierarchy, check CourseEnrollment for staff role.
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
        explicit_level_result = await session.exec(
            select(Permission.level).where(Permission.name == explicit.permission)
        )
        derived_level_result = await session.exec(
            select(Permission.level).where(Permission.name == derived_permission)
        )
        e_level = explicit_level_result.one()
        d_level = derived_level_result.one()
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
