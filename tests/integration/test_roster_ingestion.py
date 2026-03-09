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

        activity = await _make_wargame_activity("explicit-team")
        csv_content = (
            "email,team,role\n"
            "alice.smith@test.local,ALPHA,editor\n"
            "bob.jones@test.local,BRAVO,viewer\n"
        )

        report = await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        users = await _list_users_by_email(
            ["alice.smith@test.local", "bob.jones@test.local"]
        )
        memberships = await _list_team_memberships(activity.id)

        assert report.entries_processed == 2
        assert report.teams_created == 2
        assert report.users_created == 2
        assert report.memberships_created == 2
        assert report.memberships_updated == 0
        assert [team.codename for team in teams] == ["ALPHA", "BRAVO"]
        assert [(user.email, user.display_name) for user in users] == [
            ("alice.smith@test.local", "Alice Smith"),
            ("bob.jones@test.local", "Bob Jones"),
        ]
        assert memberships == [
            ("ALPHA", "alice.smith@test.local", "editor"),
            ("BRAVO", "bob.jones@test.local", "viewer"),
        ]

    @pytest.mark.asyncio
    async def test_named_team_ingest_reuses_existing_team_codename(self) -> None:
        """Existing team codenames are reused rather than duplicated."""
        from promptgrimoire.db.wargames import create_team, ingest_roster

        activity = await _make_wargame_activity("named-team-reuse")
        existing = await create_team(activity.id, codename="ALPHA")
        csv_content = (
            "email,team,role\n"
            "alice.smith@test.local,ALPHA,editor\n"
            "carol.ng@test.local,BRAVO,viewer\n"
        )

        report = await ingest_roster(activity.id, csv_content)

        teams = await _list_activity_teams(activity.id)
        memberships = await _list_team_memberships(activity.id)
        alpha_teams = [team for team in teams if team.codename == "ALPHA"]

        assert report.entries_processed == 2
        assert report.teams_created == 1
        assert len(alpha_teams) == 1
        assert alpha_teams[0].id == existing.id
        assert [team.codename for team in teams] == ["ALPHA", "BRAVO"]
        assert memberships == [
            ("ALPHA", "alice.smith@test.local", "editor"),
            ("BRAVO", "carol.ng@test.local", "viewer"),
        ]
