"""CRUD operations for wargame teams."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import WargameTeam
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


async def list_teams(activity_id: UUID) -> list[WargameTeam]:
    """Return teams for one activity ordered by creation time."""
    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam)
            .where(WargameTeam.activity_id == activity_id)
            .order_by(WargameTeam.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs don't accept Column expressions
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
