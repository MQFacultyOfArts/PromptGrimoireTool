"""Integration tests for wargame roster ingestion services."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession
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


class TestAdditiveReimport:
    """Integration tests for additive re-import semantics and editor handoff."""

    @pytest.mark.asyncio
    async def test_reimport_updates_role_and_retains_omitted_member(self) -> None:
        """AC7.1: re-import updates changed roles, omitted members keep ACL."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        carol = _unique_email("carol")
        activity = await _make_wargame_activity("reimport-additive")

        # Initial import: alice=editor, bob=viewer, carol=viewer on ALPHA
        csv_1 = (
            f"email,team,role\n"
            f"{alice},ALPHA,editor\n"
            f"{bob},ALPHA,viewer\n"
            f"{carol},ALPHA,viewer\n"
        )
        await ingest_roster(activity.id, csv_1)

        # Re-import: change bob to editor, omit carol entirely
        csv_2 = f"email,team,role\n{alice},ALPHA,editor\n{bob},ALPHA,editor\n"
        report = await ingest_roster(activity.id, csv_2)

        memberships = await _list_team_memberships(activity.id)

        assert report.memberships_updated == 1  # bob: viewer→editor
        assert report.memberships_created == 0
        assert report.teams_created == 0

        membership_map = {email: perm for _, email, perm in memberships}
        assert membership_map[alice] == "editor"
        assert membership_map[bob] == "editor"
        # Carol was omitted but must still be present
        assert membership_map[carol] == "viewer"

    @pytest.mark.asyncio
    async def test_reimport_preserves_existing_user_display_name(self) -> None:
        """Existing users keep their custom display_name after re-import."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        activity = await _make_wargame_activity("reimport-display-name")

        csv_1 = f"email,team,role\n{alice},ALPHA,editor\n"
        await ingest_roster(activity.id, csv_1)

        # Manually update display_name to a custom value
        async with get_session() as session:
            from sqlmodel import select as sel

            result = await session.exec(sel(User).where(User.email == alice))
            user = result.one()
            user.display_name = "Dr Alice Custom"
            session.add(user)
            await session.flush()

        # Re-import same user
        csv_2 = f"email,team,role\n{alice},ALPHA,editor\n"
        await ingest_roster(activity.id, csv_2)

        users = await _list_users_by_email([alice])
        assert users[0].display_name == "Dr Alice Custom"

    @pytest.mark.asyncio
    async def test_editor_handoff_swap_succeeds_with_can_edit_ordering(self) -> None:
        """Editor handoff: Alice editor→viewer, Bob viewer→editor succeeds."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        activity = await _make_wargame_activity("editor-handoff")

        # Initial: Alice=editor, Bob=viewer
        csv_1 = f"email,team,role\n{alice},ALPHA,editor\n{bob},ALPHA,viewer\n"
        await ingest_roster(activity.id, csv_1)

        # Swap: Alice→viewer, Bob→editor
        # Without can_edit ordering, Alice's downgrade would fail zero-editor check
        csv_2 = f"email,team,role\n{alice},ALPHA,viewer\n{bob},ALPHA,editor\n"
        report = await ingest_roster(activity.id, csv_2)

        memberships = await _list_team_memberships(activity.id)
        membership_map = {email: perm for _, email, perm in memberships}

        assert report.memberships_updated == 2
        assert membership_map[alice] == "viewer"
        assert membership_map[bob] == "editor"

    @pytest.mark.asyncio
    async def test_reimport_demoting_sole_editor_raises_zero_editor_error(
        self,
    ) -> None:
        """Demoting sole editor with no replacement raises ZeroEditorError."""
        from promptgrimoire.db.wargames import ZeroEditorError, ingest_roster

        alice = _unique_email("alice")
        activity = await _make_wargame_activity("sole-editor-demote")

        csv_1 = f"email,team,role\n{alice},ALPHA,editor\n"
        await ingest_roster(activity.id, csv_1)

        # Demote sole editor with no one becoming editor
        csv_2 = f"email,team,role\n{alice},ALPHA,viewer\n"
        with pytest.raises(ZeroEditorError):
            await ingest_roster(activity.id, csv_2)

        # DB state unchanged: alice still editor
        memberships = await _list_team_memberships(activity.id)
        assert len(memberships) == 1
        assert memberships[0] == ("ALPHA", alice, "editor")

    @pytest.mark.asyncio
    async def test_auto_assign_reimport_preserves_existing_acl_rows(self) -> None:
        """Auto-assign re-import reuses teams AND retains first-import ACL rows."""
        from promptgrimoire.db.wargames import ingest_roster

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        carol = _unique_email("carol")
        dave = _unique_email("dave")
        activity = await _make_wargame_activity("auto-assign-reimport")

        csv_1 = f"email,role\n{alice},editor\n{bob},editor\n"
        await ingest_roster(activity.id, csv_1, team_count=2)
        teams_first = await _list_activity_teams(activity.id)
        memberships_first = await _list_team_memberships(activity.id)

        csv_2 = f"email,role\n{carol},editor\n{dave},editor\n"
        report = await ingest_roster(activity.id, csv_2, team_count=2)
        teams_second = await _list_activity_teams(activity.id)
        memberships_after = await _list_team_memberships(activity.id)

        assert report.teams_created == 0
        assert [t.id for t in teams_second] == [t.id for t in teams_first]
        # First-import ACL rows must survive the second import (additive)
        first_import_emails = {email for _, email, _ in memberships_first}
        surviving_emails = {email for _, email, _ in memberships_after}
        assert first_import_emails <= surviving_emails


class TestAtomicRollback:
    """Integration tests for atomicity guarantees."""

    @pytest.mark.asyncio
    async def test_failure_after_partial_writes_rolls_back_all_rows(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failure mid-ingest rolls back users, teams, and ACL rows."""
        import promptgrimoire.db.wargames as wargames_mod

        alice = _unique_email("alice")
        bob = _unique_email("bob")
        activity = await _make_wargame_activity("rollback")
        csv_content = f"email,team,role\n{alice},ALPHA,editor\n{bob},BRAVO,editor\n"

        # Let the first grant succeed (stages a user, team, ACL row),
        # then blow up on the second grant.
        original_grant = wargames_mod._grant_team_permission_with_session
        call_count = 0

        async def _exploding_grant(
            session: AsyncSession,
            team_id: UUID,
            user_id: UUID,
            permission: str,
        ) -> ACLEntry:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                msg = "injected failure for atomicity test"
                raise RuntimeError(msg)
            return await original_grant(session, team_id, user_id, permission)

        monkeypatch.setattr(
            wargames_mod,
            "_grant_team_permission_with_session",
            _exploding_grant,
        )

        with pytest.raises(RuntimeError, match="injected failure"):
            await wargames_mod.ingest_roster(activity.id, csv_content)

        # Nothing should have survived the rollback
        teams = await _list_activity_teams(activity.id)
        users = await _list_users_by_email([alice, bob])
        memberships = await _list_team_memberships(activity.id)

        assert teams == []
        assert users == []
        assert memberships == []


class TestPublicAPIExport:
    """Smoke tests for the public API surface."""

    def test_roster_report_and_ingest_importable_from_db_package(self) -> None:
        """RosterReport and ingest_roster are importable from promptgrimoire.db."""
        from promptgrimoire.db import RosterReport, ingest_roster

        assert callable(ingest_roster)
        assert hasattr(RosterReport, "entries_processed")
        assert hasattr(RosterReport, "teams_created")
        assert hasattr(RosterReport, "users_created")
        assert hasattr(RosterReport, "memberships_created")
        assert hasattr(RosterReport, "memberships_updated")
