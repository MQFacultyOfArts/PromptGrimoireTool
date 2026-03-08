"""CRUD operations for wargame teams."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import ACLEntry, Permission, User, WargameTeam
from promptgrimoire.wargame import generate_codename

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_DUPLICATE_CODENAME_CONSTRAINT = "uq_wargame_team_activity_codename"


class DuplicateCodenameError(Exception):
    """Raised when a team codename already exists within one activity."""

    def __init__(self, activity_id: UUID, codename: str) -> None:
        self.activity_id = activity_id
        self.codename = codename
        super().__init__(
            f"Codename {codename!r} already exists in activity {activity_id}"
        )


class ZeroEditorError(Exception):
    """Raised when a change would leave a team without any editable member."""

    def __init__(
        self,
        team_id: UUID,
        user_id: UUID,
        current_permission: str | None,
        attempted_permission: str | None,
    ) -> None:
        self.team_id = team_id
        self.user_id = user_id
        self.current_permission = current_permission
        self.attempted_permission = attempted_permission
        super().__init__(
            "Requested team permission change would leave the team without any "
            "member whose permission grants can_edit = TRUE"
        )


def _is_duplicate_codename_error(error: IntegrityError) -> bool:
    """Return True when the integrity error is the team codename constraint."""
    constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
    return bool(
        constraint_name == _DUPLICATE_CODENAME_CONSTRAINT
        or _DUPLICATE_CODENAME_CONSTRAINT in str(error)
    )


async def _list_existing_codenames(
    session: AsyncSession,
    activity_id: UUID,
) -> set[str]:
    """Load the current codename set for one wargame activity."""
    result = await session.exec(
        select(WargameTeam.codename).where(WargameTeam.activity_id == activity_id)
    )
    return set(result.all())


async def _resolve_team_permission_with_session(
    session: AsyncSession,
    team_id: UUID,
    user_id: UUID,
) -> str | None:
    """Return the exact stored team ACL permission for one user."""
    result = await session.exec(
        select(ACLEntry.permission).where(
            ACLEntry.team_id == team_id,
            ACLEntry.user_id == user_id,
        )
    )
    return result.one_or_none()


async def _get_permission_row_with_session(
    session: AsyncSession,
    permission_name: str,
) -> Permission | None:
    """Return one permission reference row by name."""
    result = await session.exec(
        select(Permission).where(Permission.name == permission_name)
    )
    return result.one_or_none()


async def _get_team_member_permission_state_with_session(
    session: AsyncSession,
    team_id: UUID,
    user_id: UUID,
) -> tuple[str, bool] | None:
    """Return the current stored permission and can_edit state for one member."""
    result = await session.exec(
        select(ACLEntry.permission, Permission.can_edit)
        .join(Permission, Permission.name == ACLEntry.permission)  # type: ignore[arg-type]  -- SQLAlchemy join expression
        .where(
            ACLEntry.team_id == team_id,
            ACLEntry.user_id == user_id,
        )
    )
    row = result.one_or_none()
    return (row[0], row[1]) if row is not None else None


async def _lock_team_acl_rows_with_session(
    session: AsyncSession,
    team_id: UUID,
) -> None:
    """Lock all ACL rows for one team inside the current transaction."""
    await session.exec(
        select(ACLEntry.id).where(ACLEntry.team_id == team_id).with_for_update()
    )


async def _count_other_editable_team_members_with_session(
    session: AsyncSession,
    team_id: UUID,
    excluded_user_id: UUID,
) -> int:
    """Count editable team members excluding one user."""
    result = await session.exec(
        select(sa.func.count())
        .select_from(ACLEntry)
        .join(Permission, Permission.name == ACLEntry.permission)
        .where(
            ACLEntry.team_id == team_id,
            ACLEntry.user_id != excluded_user_id,
            sa.literal_column("permission.can_edit") == sa.true(),
        )
    )
    return result.one()


async def _create_team(
    session: AsyncSession,
    activity_id: UUID,
    *,
    codename: str | None = None,
    existing_codenames: set[str] | None = None,
) -> WargameTeam:
    """Create one team inside a caller-owned async session."""
    collision_set = (
        existing_codenames
        if existing_codenames is not None
        else await _list_existing_codenames(session, activity_id)
    )
    codename_value = (
        codename if codename is not None else generate_codename(collision_set)
    )

    team = WargameTeam(activity_id=activity_id, codename=codename_value)
    session.add(team)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_duplicate_codename_error(exc):
            raise DuplicateCodenameError(activity_id, codename_value) from exc
        raise

    await session.refresh(team)
    if existing_codenames is not None:
        existing_codenames.add(codename_value)
    return team


async def create_team(
    activity_id: UUID,
    *,
    codename: str | None = None,
) -> WargameTeam:
    """Create one wargame team for an activity.

    Parameters
    ----------
    activity_id : UUID
        Parent wargame activity identifier.
    codename : str | None
        Optional explicit codename. When omitted, a unique codename is generated.

    Returns
    -------
    WargameTeam
        The created team row.
    """
    async with get_session() as session:
        return await _create_team(session, activity_id, codename=codename)


async def _grant_team_permission_with_session(
    session: AsyncSession,
    team_id: UUID,
    user_id: UUID,
    permission: str,
) -> ACLEntry:
    """Create or update a team ACL row inside a caller-owned session."""
    requested_permission = await _get_permission_row_with_session(session, permission)
    if requested_permission is None:
        msg = f"unknown permission: {permission}"
        raise ValueError(msg)

    current_state = await _get_team_member_permission_state_with_session(
        session,
        team_id,
        user_id,
    )
    if (
        current_state is not None
        and current_state[1]
        and not requested_permission.can_edit
    ):
        await _lock_team_acl_rows_with_session(session, team_id)
        remaining_editable = await _count_other_editable_team_members_with_session(
            session,
            team_id,
            user_id,
        )
        if remaining_editable == 0:
            raise ZeroEditorError(
                team_id,
                user_id,
                current_state[0],
                permission,
            )

    stmt = pg_insert(ACLEntry).values(
        workspace_id=None,
        team_id=team_id,
        user_id=user_id,
        permission=permission,
        created_at=datetime.now(UTC),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["team_id", "user_id"],
        index_where=sa.text("team_id IS NOT NULL"),
        set_={"permission": stmt.excluded.permission},
    )
    await session.execute(stmt)
    await session.flush()

    result = await session.exec(
        select(ACLEntry).where(
            ACLEntry.team_id == team_id,
            ACLEntry.user_id == user_id,
        )
    )
    return result.one()


async def grant_team_permission(
    team_id: UUID,
    user_id: UUID,
    permission: str,
) -> ACLEntry:
    """Create or update a user's ACL entry for a team."""
    async with get_session() as session:
        return await _grant_team_permission_with_session(
            session,
            team_id,
            user_id,
            permission,
        )


async def create_teams(activity_id: UUID, team_count: int) -> list[WargameTeam]:
    """Create multiple wargame teams for one activity in one transaction.

    Parameters
    ----------
    activity_id : UUID
        Parent wargame activity identifier.
    team_count : int
        Number of teams to create.

    Returns
    -------
    list[WargameTeam]
        Created team rows in creation order.

    Raises
    ------
    ValueError
        If ``team_count`` is not positive.
    """
    if team_count <= 0:
        msg = "team_count must be positive"
        raise ValueError(msg)

    async with get_session() as session:
        collision_set = await _list_existing_codenames(session, activity_id)
        return [
            await _create_team(
                session,
                activity_id,
                existing_codenames=collision_set,
            )
            for _ in range(team_count)
        ]


async def get_team(team_id: UUID) -> WargameTeam | None:
    """Return a wargame team by primary key, or None when missing."""
    async with get_session() as session:
        return await session.get(WargameTeam, team_id)


async def resolve_team_permission(team_id: UUID, user_id: UUID) -> str | None:
    """Return the exact stored team permission for one user, or None."""
    async with get_session() as session:
        return await _resolve_team_permission_with_session(session, team_id, user_id)


async def list_teams(activity_id: UUID) -> list[WargameTeam]:
    """Return teams for one activity ordered by creation time."""
    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam)
            .where(WargameTeam.activity_id == activity_id)
            .order_by(WargameTeam.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs don't accept Column expressions
        )
        return list(result.all())


async def list_team_members(team_id: UUID) -> list[tuple[User, str]]:
    """Return team members with permission names in deterministic order."""
    async with get_session() as session:
        result = await session.exec(
            select(User, ACLEntry.permission)
            .join(ACLEntry, ACLEntry.user_id == User.id)  # type: ignore[arg-type]  -- SQLAlchemy join expression
            .join(Permission, Permission.name == ACLEntry.permission)  # type: ignore[arg-type]  -- SQLAlchemy join expression
            .where(ACLEntry.team_id == team_id)
            .order_by(
                sa.desc(sa.literal_column("permission.can_edit")),
                sa.desc(sa.literal_column("permission.level")),
                User.display_name,
                User.email,
            )
        )
        return list(result.all())


async def rename_team(team_id: UUID, codename: str) -> WargameTeam | None:
    """Rename a team, translating duplicate-codename failures.

    Parameters
    ----------
    team_id : UUID
        Team identifier to rename.
    codename : str
        Replacement codename.

    Returns
    -------
    WargameTeam | None
        Updated team row, or None when the team does not exist.

    Raises
    ------
    DuplicateCodenameError
        If another team in the same activity already has ``codename``.
    """
    async with get_session() as session:
        team = await session.get(WargameTeam, team_id)
        if team is None:
            return None

        activity_id = team.activity_id
        team.codename = codename
        session.add(team)
        try:
            await session.flush()
        except IntegrityError as exc:
            if _is_duplicate_codename_error(exc):
                raise DuplicateCodenameError(activity_id, codename) from exc
            raise

        await session.refresh(team)
        return team


async def delete_team(team_id: UUID) -> bool:
    """Delete a team by primary key.

    Parameters
    ----------
    team_id : UUID
        Team identifier to delete.

    Returns
    -------
    bool
        True when a row was deleted, otherwise False.
    """
    async with get_session() as session:
        team = await session.get(WargameTeam, team_id)
        if team is None:
            return False

        await session.delete(team)
        await session.flush()
        return True
