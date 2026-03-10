"""Integration tests for wargame roster ingestion services."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import ACLEntry, Activity, Course, User, WargameTeam, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _unique_email(name: str) -> str:
    """Generate a globally unique test email to avoid xdist collisions."""
    return f"{name}-{uuid4().hex[:8]}@test.local"


async def _make_course_and_week(suffix: str) -> tuple[Course, Week]:
    """Create a unique course/week pair for roster-ingestion tests."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"RI{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"Roster Ingest {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


async def _make_wargame_activity(suffix: str) -> Activity:
    """Create a persisted wargame activity for one ingestion test."""
    from promptgrimoire.db.engine import get_session

    _, week = await _make_course_and_week(suffix)

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Roster Ingest {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def _list_activity_teams(activity_id: object) -> list[WargameTeam]:
    """Return persisted teams for one activity ordered by creation time."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam)
            .where(WargameTeam.activity_id == activity_id)
            .order_by(WargameTeam.created_at)  # type: ignore[arg-type]  -- SQLModel order_by stubs do not accept column expressions
        )
        return list(result.all())


async def _list_users_by_email(emails: list[str]) -> list[User]:
    """Return persisted users for the given emails ordered by email."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(User)
            .where(User.email.in_(emails))  # type: ignore[arg-type]  -- SQLAlchemy in_ works with a Python list here
            .order_by(User.email)
        )
        return list(result.all())


async def _list_team_memberships(activity_id: object) -> list[tuple[str, str, str]]:
    """Return persisted team ACL tuples for one activity."""
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam.codename, User.email, ACLEntry.permission)
            .join(ACLEntry, ACLEntry.team_id == WargameTeam.id)  # type: ignore[arg-type]  -- SQLAlchemy join expression
            .join(User, User.id == ACLEntry.user_id)  # type: ignore[arg-type]  -- SQLAlchemy join expression
            .where(WargameTeam.activity_id == activity_id)
            .order_by(WargameTeam.codename, User.email)
        )
        return list(result.all())


class TestNamedTeamRosterIngestion:
    """Integration tests for named-team roster ingestion."""

    @pytest.mark.asyncio
    async def test_explicit_team_ingest_creates_users_teams_acl_and_report(
        self,
    ) -> None:
        """AC6.1: explicit-team ingest persists users, teams, and ACL rows."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice.smith")
        bob = _unique_email("bob.jones")
        activity = await _make_wargame_activity("explicit-team")
        csv_content = f"email,team,role\n{alice},ALPHA,editor\n{bob},BRAVO,viewer\n"

        report = await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        users = await _list_users_by_email([alice, bob])
        memberships = await _list_team_memberships(activity.id)

        assert report.entries_processed == 2
        assert report.teams_created == 2
        assert report.users_created == 2
        assert report.memberships_created == 2
        assert report.memberships_updated == 0
        assert [team.codename for team in teams] == ["ALPHA", "BRAVO"]
        assert len(users) == 2
        assert {u.email for u in users} == {alice, bob}
        assert len(memberships) == 2
        assert {(codename, perm) for codename, _, perm in memberships} == {
            ("ALPHA", "editor"),
            ("BRAVO", "viewer"),
        }

    @pytest.mark.asyncio
    async def test_named_team_ingest_reuses_existing_team_codename(self) -> None:
        """Existing team codenames are reused rather than duplicated."""
        from promptgrimoire.db.wargames import create_team, ingest_roster

        alice = _unique_email("alice.smith")
        carol = _unique_email("carol.ng")
        activity = await _make_wargame_activity("named-team-reuse")
        existing = await create_team(activity.id, codename="ALPHA")
        csv_content = f"email,team,role\n{alice},ALPHA,editor\n{carol},BRAVO,viewer\n"

        report = await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        alpha_teams = [team for team in teams if team.codename == "ALPHA"]

        assert report.entries_processed == 2
        assert report.teams_created == 1
        assert len(alpha_teams) == 1
        assert alpha_teams[0].id == existing.id
        assert [team.codename for team in teams] == ["ALPHA", "BRAVO"]


class TestAutoAssignRosterIngestion:
    """Integration tests for auto-assign roster ingestion mode."""

    @pytest.mark.asyncio
    async def test_auto_assign_distributes_members_round_robin_across_generated_teams(
        self,
    ) -> None:
        """AC6.2: teamless CSV + team_count distributes across generated teams."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        carol = _unique_email("carol")
        dave = _unique_email("dave")
        activity = await _make_wargame_activity("auto-assign")
        csv_content = (
            f"email,role\n{alice},editor\n{bob},editor\n{carol},editor\n{dave},editor\n"
        )

        report = await ingest_roster(activity.id, csv_content, team_count=2)

        teams = await _list_activity_teams(activity.id)
        memberships = await _list_team_memberships(activity.id)

        assert report.entries_processed == 4
        assert report.teams_created == 2
        assert report.users_created == 4
        assert report.memberships_created == 4

        # Exactly 2 teams with real generated codenames (not synthetic AUTO-*)
        assert len(teams) == 2
        for team in teams:
            assert not team.codename.startswith("AUTO-"), (
                f"codename {team.codename!r} is synthetic"
            )

        # Round-robin: team1 gets alice+carol, team2 gets bob+dave
        team1_codename = teams[0].codename
        team2_codename = teams[1].codename
        team1_emails = sorted(
            email for codename, email, _ in memberships if codename == team1_codename
        )
        team2_emails = sorted(
            email for codename, email, _ in memberships if codename == team2_codename
        )
        assert team1_emails == sorted([alice, carol])
        assert team2_emails == sorted([bob, dave])

    @pytest.mark.asyncio
    async def test_auto_assign_without_team_count_raises_and_leaves_no_rows(
        self,
    ) -> None:
        """AC6.3: teamless CSV without team_count raises ValueError, no DB writes."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        activity = await _make_wargame_activity("auto-assign-no-count")
        csv_content = f"email,role\n{alice},editor\n{bob},editor\n"

        with pytest.raises(ValueError, match="team_count"):
            await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        users = await _list_users_by_email([alice, bob])
        memberships = await _list_team_memberships(activity.id)

        assert teams == []
        assert users == []
        assert memberships == []

    @pytest.mark.asyncio
    async def test_mixed_mode_raises_and_leaves_no_rows(self) -> None:
        """Mixed named+blank teams raises ValueError with zero DB writes."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        activity = await _make_wargame_activity("mixed-mode")
        csv_content = f"email,team,role\n{alice},ALPHA,editor\n{bob},,editor\n"

        with pytest.raises(ValueError, match="mixed"):
            await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        users = await _list_users_by_email([alice, bob])
        memberships = await _list_team_memberships(activity.id)

        assert teams == []
        assert users == []
        assert memberships == []

    @pytest.mark.asyncio
    async def test_auto_assign_reuses_existing_teams_by_created_at_order(
        self,
    ) -> None:
        """Repeating auto-assign with same team_count reuses existing teams."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        carol = _unique_email("carol")
        dave = _unique_email("dave")
        activity = await _make_wargame_activity("auto-assign-reuse")
        csv_content_1 = f"email,role\n{alice},editor\n{bob},editor\n"
        await ingest_roster(activity.id, csv_content_1, team_count=2)
        teams_after_first = await _list_activity_teams(activity.id)
        assert len(teams_after_first) == 2

        csv_content_2 = f"email,role\n{carol},editor\n{dave},editor\n"
        report = await ingest_roster(activity.id, csv_content_2, team_count=2)

        teams_after_second = await _list_activity_teams(activity.id)
        assert len(teams_after_second) == 2
        assert report.teams_created == 0
        assert [t.id for t in teams_after_second] == [t.id for t in teams_after_first]

    @pytest.mark.asyncio
    async def test_auto_assign_team_count_mismatch_raises_and_leaves_rows_unchanged(
        self,
    ) -> None:
        """Auto-assign with wrong team_count raises ValueError, existing rows intact."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        carol = _unique_email("carol")
        dave = _unique_email("dave")
        eve = _unique_email("eve")
        activity = await _make_wargame_activity("auto-assign-mismatch")
        csv_content_1 = f"email,role\n{alice},editor\n{bob},editor\n"
        await ingest_roster(activity.id, csv_content_1, team_count=2)
        teams_before = await _list_activity_teams(activity.id)
        memberships_before = await _list_team_memberships(activity.id)

        csv_content_2 = f"email,role\n{carol},editor\n{dave},editor\n{eve},editor\n"
        with pytest.raises(ValueError, match="team_count"):
            await ingest_roster(activity.id, csv_content_2, team_count=3)

        teams_after = await _list_activity_teams(activity.id)
        memberships_after = await _list_team_memberships(activity.id)
        assert [t.id for t in teams_after] == [t.id for t in teams_before]
        assert memberships_after == memberships_before
