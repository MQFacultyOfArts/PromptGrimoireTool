"""CRUD and turn-cycle operations for wargame teams."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import sqlalchemy as sa
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    ACLEntry,
    Permission,
    User,
    WargameConfig,
    WargameMessage,
    WargameTeam,
)
from promptgrimoire.db.users import _find_or_create_user_with_session
from promptgrimoire.wargame import generate_codename
from promptgrimoire.wargame.agents import TurnResult, turn_agent
from promptgrimoire.wargame.roster import auto_assign_teams, parse_roster
from promptgrimoire.wargame.turn_cycle import (
    build_turn_prompt,
    expand_bootstrap,
    extract_move_text,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from promptgrimoire.wargame import RosterEntry

_logger = logging.getLogger(__name__)

_DUPLICATE_CODENAME_CONSTRAINT = "uq_wargame_team_activity_codename"
# SQLModel exposes mapped attributes as scalar Python types to `ty`, so we grab
# the underlying SQLAlchemy table columns when we need SQL expression objects.
_PERMISSION_TABLE = cast("Any", Permission).__table__
_PERMISSION_CAN_EDIT_COL = _PERMISSION_TABLE.c.can_edit
_PERMISSION_LEVEL_COL = _PERMISSION_TABLE.c.level


@dataclass(frozen=True, slots=True)
class RosterReport:
    """Summary of a roster-ingestion run."""

    entries_processed: int
    teams_created: int
    users_created: int
    memberships_created: int
    memberships_updated: int


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


async def _list_activity_teams_by_codename_with_session(
    session: AsyncSession,
    activity_id: UUID,
) -> dict[str, WargameTeam]:
    """Return persisted activity teams keyed by codename."""
    result = await session.exec(
        select(WargameTeam).where(WargameTeam.activity_id == activity_id)
    )
    return {team.codename: team for team in result.all()}


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
            _PERMISSION_CAN_EDIT_COL.is_(True),
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


def _derive_display_name(email: str) -> str:
    """Derive a human display name from an email local part."""
    return email.split("@", maxsplit=1)[0].replace(".", " ").title()


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


async def _revoke_team_permission_with_session(
    session: AsyncSession,
    team_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete one team ACL row inside a caller-owned session."""
    result = await session.exec(
        select(ACLEntry).where(
            ACLEntry.team_id == team_id,
            ACLEntry.user_id == user_id,
        )
    )
    entry = result.one_or_none()
    if entry is None:
        return False

    permission_row = await _get_permission_row_with_session(session, entry.permission)
    current_can_edit = permission_row.can_edit if permission_row is not None else False
    if current_can_edit:
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
                entry.permission,
                None,
            )

    await session.delete(entry)
    await session.flush()
    return True


async def revoke_team_permission(team_id: UUID, user_id: UUID) -> bool:
    """Delete a user's ACL entry for a team."""
    async with get_session() as session:
        return await _revoke_team_permission_with_session(session, team_id, user_id)


async def update_team_permission(
    team_id: UUID,
    user_id: UUID,
    permission: str,
) -> ACLEntry:
    """Update a team member's permission via the shared upsert path."""
    return await grant_team_permission(team_id, user_id, permission)


async def remove_team_member(team_id: UUID, user_id: UUID) -> bool:
    """Remove a team member via the shared revoke path."""
    return await revoke_team_permission(team_id, user_id)


def _classify_roster_mode(
    entries: list[RosterEntry],
    team_count: int | None,
) -> tuple[list[RosterEntry], list[str] | None]:
    """Validate mode and return (possibly-reassigned entries, bucket_ids).

    Returns ``bucket_ids=None`` for explicit-team mode. All validation
    happens before any DB session opens.
    """
    has_named = any(entry.team is not None for entry in entries)
    has_blank = any(entry.team is None for entry in entries)

    if has_named and has_blank:
        msg = "mixed team-assignment modes are unsupported"
        raise ValueError(msg)

    if not has_blank:
        return entries, None

    if team_count is None:
        msg = "team_count is required for teamless rosters"
        raise ValueError(msg)

    entries = auto_assign_teams(entries, team_count)

    # Derive distinct bucket IDs in first-seen order
    seen: dict[str, None] = {}
    for entry in entries:
        if entry.team is not None and entry.team not in seen:
            seen[entry.team] = None
    return entries, list(seen)


async def _resolve_bucket_teams(
    session: AsyncSession,
    activity_id: UUID,
    bucket_ids: list[str],
    teams_by_codename: dict[str, WargameTeam],
    existing_codenames: set[str],
) -> tuple[dict[str, WargameTeam], int]:
    """Map auto-assign bucket IDs to real teams, creating if needed.

    Returns ``(bucket_to_team, teams_created)``.
    """
    existing_teams = list(teams_by_codename.values())
    existing_count = len(existing_teams)
    bucket_to_team: dict[str, WargameTeam] = {}
    teams_created = 0

    if existing_count == 0:
        for bucket_id in bucket_ids:
            team = await _create_team(
                session,
                activity_id,
                existing_codenames=existing_codenames,
            )
            teams_by_codename[team.codename] = team
            teams_created += 1
            bucket_to_team[bucket_id] = team
    elif existing_count == len(bucket_ids):
        sorted_teams = sorted(existing_teams, key=lambda t: t.created_at)
        for bucket_id, team in zip(bucket_ids, sorted_teams, strict=True):
            bucket_to_team[bucket_id] = team
    else:
        msg = (
            f"auto-assign team_count={len(bucket_ids)} does not match "
            f"existing team count {existing_count}"
        )
        raise ValueError(msg)

    return bucket_to_team, teams_created


async def ingest_roster(
    activity_id: UUID,
    csv_content: str,
    *,
    team_count: int | None = None,
) -> RosterReport:
    """Ingest a roster CSV atomically for one wargame activity.

    Parameters
    ----------
    activity_id : UUID
        Parent wargame activity identifier.
    csv_content : str
        Raw roster CSV content.
    team_count : int | None
        Number of teams for auto-assign mode (teamless rosters). Ignored
        when all roster entries have explicit team names.

    Returns
    -------
    RosterReport
        Summary counters for the completed ingest.

    Raises
    ------
    ValueError
        If the roster mixes named and blank teams, if a teamless roster
        is provided without ``team_count``, or if ``team_count`` does not
        match the existing team count for the activity.

    All writes happen inside a single database session. Any failure
    rolls back the entire import — no partial state is persisted.
    """
    entries = parse_roster(csv_content)
    entries, bucket_ids = _classify_roster_mode(entries, team_count)

    async with get_session() as session:
        return await _ingest_entries(
            session,
            activity_id,
            entries,
            bucket_ids,
        )


@dataclass(frozen=True, slots=True)
class _PendingGrant:
    """One resolved grant awaiting application, sortable by can_edit."""

    team_id: UUID
    user_id: UUID
    permission: str
    can_edit: bool
    is_new: bool
    is_changed: bool


async def _ingest_entries(
    session: AsyncSession,
    activity_id: UUID,
    entries: list[RosterEntry],
    bucket_ids: list[str] | None,
) -> RosterReport:
    """Apply parsed roster entries inside a caller-owned session."""
    teams_by_codename = await _list_activity_teams_by_codename_with_session(
        session,
        activity_id,
    )
    existing_codenames = set(teams_by_codename)
    teams_created = 0
    users_created = 0

    bucket_to_team: dict[str, WargameTeam] = {}
    if bucket_ids is not None:
        bucket_to_team, teams_created = await _resolve_bucket_teams(
            session,
            activity_id,
            bucket_ids,
            teams_by_codename,
            existing_codenames,
        )

    # Pre-fetch distinct permission rows to avoid one SELECT per entry
    distinct_roles = {e.role for e in entries}
    perm_cache: dict[str, Permission] = {}
    for role in distinct_roles:
        perm_row = await _get_permission_row_with_session(session, role)
        if perm_row is None:
            msg = f"unknown permission: {role}"
            raise ValueError(msg)
        perm_cache[role] = perm_row

    # Phase 1: resolve teams and users, build pending grants
    pending: list[_PendingGrant] = []
    for entry in entries:
        team_name = _require_entry_team(entry)
        if bucket_ids is not None:
            team = bucket_to_team[team_name]
        else:
            team = teams_by_codename.get(team_name)
            if team is None:
                team = await _create_team(
                    session,
                    activity_id,
                    codename=team_name,
                    existing_codenames=existing_codenames,
                )
                teams_by_codename[team_name] = team
                teams_created += 1

        user, created_user = await _find_or_create_user_with_session(
            session,
            entry.email,
            _derive_display_name(entry.email),
        )
        users_created += int(created_user)

        current_permission = await _resolve_team_permission_with_session(
            session,
            team.id,
            user.id,
        )
        desired_perm_row = perm_cache[entry.role]

        pending.append(
            _PendingGrant(
                team_id=team.id,
                user_id=user.id,
                permission=entry.role,
                can_edit=desired_perm_row.can_edit,
                is_new=current_permission is None,
                is_changed=current_permission is not None
                and current_permission != entry.role,
            )
        )

    # Phase 2: apply grants with can_edit=TRUE first for safe editor handoffs
    pending.sort(key=lambda g: (not g.can_edit, g.permission))
    memberships_created = 0
    memberships_updated = 0
    for grant in pending:
        if grant.is_new:
            memberships_created += 1
        elif grant.is_changed:
            memberships_updated += 1

        await _grant_team_permission_with_session(
            session,
            grant.team_id,
            grant.user_id,
            grant.permission,
        )

    return RosterReport(
        entries_processed=len(entries),
        teams_created=teams_created,
        users_created=users_created,
        memberships_created=memberships_created,
        memberships_updated=memberships_updated,
    )


def _require_entry_team(entry: RosterEntry) -> str:
    """Return ``entry.team`` after Task 1 explicit-team validation."""
    if entry.team is None:
        msg = "entry.team must be present after explicit-team validation"
        raise RuntimeError(msg)
    return entry.team


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
                sa.desc(_PERMISSION_CAN_EDIT_COL),
                sa.desc(_PERMISSION_LEVEL_COL),
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


async def start_game(activity_id: UUID) -> None:
    """Bootstrap all teams for a wargame activity with initial AI responses.

    For each team: expands the scenario bootstrap template with the team's
    codename, calls the turn agent for an initial response, and stores both
    messages. Sets all teams to round 1, state "locked".

    Parameters
    ----------
    activity_id : UUID
        The wargame activity to start.

    Raises
    ------
    ValueError
        If the game has already been started (messages exist for any team).
    """
    async with get_session() as session:
        config = await session.get(WargameConfig, activity_id)
        if config is None:
            msg = f"no wargame config for activity {activity_id}"
            raise ValueError(msg)

        result = await session.exec(
            select(WargameTeam).where(WargameTeam.activity_id == activity_id)
        )
        teams = list(result.all())

        if not teams:
            msg = f"no teams for activity {activity_id}"
            raise ValueError(msg)

        # Precondition: no messages exist for any of these teams
        team_ids = [team.id for team in teams]
        msg_count_result = await session.exec(
            select(sa.func.count())
            .select_from(WargameMessage)
            .where(
                WargameMessage.team_id.in_(team_ids)  # type: ignore[union-attr]  -- SQLAlchemy column expression
            )
        )
        if msg_count_result.one() > 0:
            msg = "game already started"
            raise ValueError(msg)

        for team in teams:
            bootstrap_text = expand_bootstrap(config.scenario_bootstrap, team.codename)
            prompt = build_turn_prompt(bootstrap_text, "")

            # Store the human-readable bootstrap as the user message
            user_msg = WargameMessage(
                team_id=team.id,
                sequence_no=1,
                role="user",
                content=bootstrap_text,
            )
            session.add(user_msg)

            # Call the turn agent
            ai_result = await turn_agent.run(prompt, instructions=config.system_prompt)
            # ty cannot track PydanticAI Agent generics; cast narrows to the
            # concrete output type. TurnResult is a real runtime import (not
            # TYPE_CHECKING-only) so the non-string form is used here.
            turn_output = cast("TurnResult", ai_result.output)

            # Store assistant response with PydanticAI history
            assistant_msg = WargameMessage(
                team_id=team.id,
                sequence_no=2,
                role="assistant",
                content=turn_output.response_text,
                metadata_json=to_jsonable_python(ai_result.all_messages()),
            )
            session.add(assistant_msg)

            team.game_state_text = turn_output.game_state
            team.current_round = 1
            team.round_state = "locked"
            session.add(team)


async def _lock_round_with_session(
    session: AsyncSession,
    activity_id: UUID,
    *,
    strict: bool = True,
) -> None:
    """Lock all drafting teams inside a caller-owned session.

    Parameters
    ----------
    session:
        Active async database session.
    activity_id:
        The wargame activity whose round to lock.
    strict:
        When ``True`` (default, used by the public ``lock_round``), raise
        ``ValueError`` if any team is not in ``"drafting"`` state.  When
        ``False`` (used by ``on_deadline_fired``), log a warning for
        already-locked teams and proceed.
    """
    result = await session.exec(
        select(WargameTeam).where(WargameTeam.activity_id == activity_id)
    )
    teams = list(result.all())

    not_drafting = [t for t in teams if t.round_state != "drafting"]
    if not_drafting:
        if strict:
            msg = "not all teams in drafting state"
            raise ValueError(msg)
        _logger.warning(
            "on_deadline_fired: %d team(s) already in non-drafting state for "
            "activity %s — proceeding",
            len(not_drafting),
            activity_id,
        )

    for team in teams:
        if team.round_state == "drafting":
            team.round_state = "locked"
            team.current_deadline = None
            session.add(team)


async def lock_round(activity_id: UUID) -> None:
    """Lock all teams in a wargame activity, transitioning from drafting to locked.

    Clears deadlines on all teams.

    Parameters
    ----------
    activity_id : UUID
        The wargame activity whose round to lock.

    Raises
    ------
    ValueError
        If any team is not in "drafting" state.
    """
    async with get_session() as session:
        await _lock_round_with_session(session, activity_id, strict=True)


async def _preprocess_one_team(
    session: AsyncSession,
    config: WargameConfig,
    team: WargameTeam,
) -> None:
    """Run AI preprocessing for a single team inside a caller-owned session.

    Extracts move text from the CRDT buffer, restores PydanticAI history
    from the previous assistant message, calls the turn agent, and stores
    both user and assistant messages.

    Parameters
    ----------
    session:
        Active async database session (one per team call).
    config:
        The wargame configuration for the activity.
    team:
        The team to preprocess (must be freshly loaded in this session).

    Raises
    ------
    ValueError
        If an assistant message already exists for the current round
        (one-response invariant).
    """
    expected_assistant_seq = team.current_round * 2
    expected_user_seq = team.current_round * 2 - 1

    # One-response invariant: skip if assistant message already exists.
    # This prevents double-processing of already-succeeded teams on retry
    # after partial failure (errored teams won't have an assistant message,
    # so they'll be processed; successful teams will have one and are skipped).
    existing_result = await session.exec(
        select(WargameMessage).where(
            WargameMessage.team_id == team.id,
            WargameMessage.sequence_no == expected_assistant_seq,
        )
    )
    if existing_result.one_or_none() is not None:
        _logger.info(
            "Skipping team %s: assistant message already exists for round %d",
            team.id,
            team.current_round,
        )
        return

    # Snapshot: extract move text from CRDT buffer
    move_text = extract_move_text(team.move_buffer_crdt)

    # Restore PydanticAI history from most recent assistant message
    history_result = await session.exec(
        select(WargameMessage)
        .where(
            WargameMessage.team_id == team.id,
            WargameMessage.role == "assistant",
        )
        .order_by(
            WargameMessage.sequence_no.desc()  # type: ignore[union-attr]  -- SQLAlchemy column expression
        )
        .limit(1)
    )
    prev_assistant = history_result.one_or_none()
    message_history = (
        ModelMessagesTypeAdapter.validate_python(prev_assistant.metadata_json)
        if prev_assistant is not None and prev_assistant.metadata_json is not None
        else None
    )

    # Build prompt and store user message
    prompt = build_turn_prompt(move_text, team.game_state_text or "")

    user_msg = WargameMessage(
        team_id=team.id,
        sequence_no=expected_user_seq,
        role="user",
        content=move_text,
    )
    session.add(user_msg)

    # AI call
    ai_result = await turn_agent.run(
        prompt,
        message_history=message_history,
        instructions=config.system_prompt,
    )
    turn_output = cast("TurnResult", ai_result.output)

    # Store assistant message with PydanticAI history
    assistant_msg = WargameMessage(
        team_id=team.id,
        sequence_no=expected_assistant_seq,
        role="assistant",
        content=turn_output.response_text,
        metadata_json=to_jsonable_python(ai_result.all_messages()),
    )
    session.add(assistant_msg)

    # Update game state
    team.game_state_text = turn_output.game_state
    session.add(team)


async def _validate_preprocessing_preconditions(
    activity_id: UUID,
) -> list[UUID]:
    """Load teams and validate they are in a processable state.

    Returns team IDs for per-team processing.

    Raises
    ------
    ValueError
        If no config exists, or if any team is not in ``"locked"`` or
        ``"error"`` state.
    """
    async with get_session() as session:
        config = await session.get(WargameConfig, activity_id)
        if config is None:
            msg = f"no wargame config for activity {activity_id}"
            raise ValueError(msg)

        result = await session.exec(
            select(WargameTeam).where(WargameTeam.activity_id == activity_id)
        )
        teams = list(result.all())

        # Accept "locked" and "error" states (error allows retry)
        not_processable = [t for t in teams if t.round_state not in ("locked", "error")]
        if not_processable:
            msg = "not all teams in locked or error state"
            raise ValueError(msg)

        return [team.id for team in teams]


async def _mark_team_errored(team_id: UUID) -> None:
    """Mark a team as errored in a fresh session after preprocessing failure."""
    try:
        async with get_session() as err_session:
            err_team = await err_session.get(WargameTeam, team_id)
            if err_team is not None:
                err_team.round_state = "error"
                err_session.add(err_team)
    except Exception:
        _logger.exception("Failed to mark team %s as errored", team_id)


async def _run_preprocessing_loop(activity_id: UUID) -> None:
    """Run AI preprocessing for all eligible teams with per-team isolation.

    Each team is processed in its own database session. If a team's
    preprocessing fails, it is marked with ``round_state="error"`` and
    processing continues for remaining teams.

    The one-response invariant (checking for an existing assistant message)
    allows safe retry: errored teams are re-processed, while teams that
    already succeeded are skipped.

    Parameters
    ----------
    activity_id:
        The wargame activity to preprocess.

    Raises
    ------
    ValueError
        If no config exists, or if no teams are in a processable state
        (``"locked"`` or ``"error"``).
    """
    team_ids = await _validate_preprocessing_preconditions(activity_id)

    # Per-team loop: each team gets its own session.
    # Config and team are re-fetched inside each session to avoid
    # detached-instance issues across session boundaries.
    for team_id in team_ids:
        try:
            async with get_session() as session:
                team_config = await session.get(WargameConfig, activity_id)
                if team_config is None:  # pragma: no cover — validated above
                    msg = f"no wargame config for activity {activity_id}"
                    raise ValueError(msg)
                team = await session.get(WargameTeam, team_id)
                if team is None:  # pragma: no cover — loaded above
                    msg = f"team {team_id} vanished during preprocessing"
                    raise ValueError(msg)

                await _preprocess_one_team(session, team_config, team)
        except Exception:
            _logger.exception(
                "Preprocessing failed for team %s in activity %s",
                team_id,
                activity_id,
            )
            await _mark_team_errored(team_id)


async def run_preprocessing(activity_id: UUID) -> None:
    """Run AI preprocessing for all locked teams in a wargame activity.

    Each team is processed in its own database session. If one team's
    AI call fails, that team is marked with ``round_state="error"`` and
    processing continues for remaining teams.

    The one-response invariant prevents double-processing of
    already-succeeded teams on retry.

    Parameters
    ----------
    activity_id : UUID
        The wargame activity to preprocess.

    Raises
    ------
    ValueError
        If any team is not in ``"locked"`` or ``"error"`` state, or if
        no wargame config exists.
    """
    await _run_preprocessing_loop(activity_id)


async def on_deadline_fired(activity_id: UUID) -> None:
    """Handle an expired wargame deadline.

    Locks all drafting teams for the activity in one session, then runs
    the preprocessing pipeline with per-team isolation. The lock phase
    commits independently so that teams are locked even if preprocessing
    partially fails.

    Parameters
    ----------
    activity_id : UUID
        The wargame activity whose deadline has expired.
    """
    # Lock phase: one atomic session
    async with get_session() as session:
        await _lock_round_with_session(session, activity_id, strict=False)

    # Preprocessing phase: per-team sessions
    await _run_preprocessing_loop(activity_id)
