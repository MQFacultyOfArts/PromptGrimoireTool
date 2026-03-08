"""Integration tests for wargame team CRUD services."""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import ACLEntry, Activity, Course, WargameMessage, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str) -> tuple[Course, Week]:
    """Create a unique course/week pair for team CRUD tests."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"WT{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"Wargame Team {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


async def _make_wargame_activity(suffix: str) -> Activity:
    """Create a persisted wargame activity for one CRUD test."""
    from promptgrimoire.db.engine import get_session

    _, week = await _make_course_and_week(suffix)

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Wargame {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


class TestCreateAndGetTeam:
    """Service-level tests for create_team and get_team."""

    @pytest.mark.asyncio
    async def test_create_team_persists_generated_codename_and_get_team_round_trips(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC3.1: create_team persists through the public service boundary."""
        from promptgrimoire.db.wargames import create_team, get_team

        activity = await _make_wargame_activity("create-team")
        monkeypatch.setattr(
            "promptgrimoire.db.wargames.generate_codename",
            lambda _existing: "RED-FOX",
        )

        created = await create_team(activity.id)
        fetched = await get_team(created.id)

        assert created.id is not None
        assert created.activity_id == activity.id
        assert created.codename == "RED-FOX"
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.activity_id == activity.id
        assert fetched.codename == "RED-FOX"

    @pytest.mark.asyncio
    async def test_get_team_returns_none_for_missing_team(self) -> None:
        """Missing teams return None rather than raising."""
        from promptgrimoire.db.wargames import get_team

        assert await get_team(uuid4()) is None

    @pytest.mark.asyncio
    async def test_create_team_uses_explicit_empty_codename_without_generating(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit empty-string codenames are treated as caller-provided."""
        from promptgrimoire.db.wargames import create_team, get_team

        activity = await _make_wargame_activity("create-empty-codename")

        def fail_if_called(_existing: set[str]) -> str:
            msg = "generate_codename should not be called for explicit codename"
            raise AssertionError(msg)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.generate_codename",
            fail_if_called,
        )

        created = await create_team(activity.id, codename="")
        fetched = await get_team(created.id)

        assert created.codename == ""
        assert fetched is not None
        assert fetched.codename == ""


class TestCreateAndListTeams:
    """Service-level tests for batch creation and listing."""

    @pytest.mark.asyncio
    async def test_create_teams_persists_distinct_codenames_after_existing_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC3.2: batch creation avoids collisions within one activity."""
        from promptgrimoire.db.wargames import create_team, create_teams, list_teams

        activity = await _make_wargame_activity("create-teams")
        existing = await create_team(activity.id, codename="EXISTING")

        def fake_generate(existing_codenames: set[str]) -> str:
            for candidate in ("EXISTING", "RED-FOX", "BLUE-WHALE", "GREEN-OWL"):
                if candidate not in existing_codenames:
                    return candidate
            msg = "exhausted fake codename candidates"
            raise AssertionError(msg)

        monkeypatch.setattr(
            "promptgrimoire.db.wargames.generate_codename",
            fake_generate,
        )

        created = await create_teams(activity.id, 3)
        persisted = await list_teams(activity.id)

        created_codenames = [team.codename for team in created]
        persisted_codenames = [team.codename for team in persisted]

        assert len(created) == 3
        assert len({team.id for team in created}) == 3
        assert created_codenames == ["RED-FOX", "BLUE-WHALE", "GREEN-OWL"]
        assert existing.codename not in created_codenames
        assert persisted_codenames == [
            "EXISTING",
            "RED-FOX",
            "BLUE-WHALE",
            "GREEN-OWL",
        ]

    @pytest.mark.asyncio
    async def test_list_teams_filters_to_one_activity_in_created_order(self) -> None:
        """list_teams returns one activity's teams in created order."""
        from promptgrimoire.db.wargames import create_team, list_teams

        activity_one = await _make_wargame_activity("list-teams-one")
        activity_two = await _make_wargame_activity("list-teams-two")

        first = await create_team(activity_one.id, codename="ALPHA")
        await create_team(activity_two.id, codename="OTHER")
        second = await create_team(activity_one.id, codename="BRAVO")

        listed = await list_teams(activity_one.id)

        assert [team.id for team in listed] == [first.id, second.id]
        assert [team.codename for team in listed] == ["ALPHA", "BRAVO"]
        assert all(team.activity_id == activity_one.id for team in listed)

    @pytest.mark.asyncio
    async def test_create_teams_rejects_non_positive_count_without_new_rows(
        self,
    ) -> None:
        """Non-positive team counts raise and preserve persisted state."""
        from promptgrimoire.db.wargames import create_team, create_teams, list_teams

        activity = await _make_wargame_activity("create-teams-invalid")
        kept = await create_team(activity.id, codename="KEEP-ME")

        with pytest.raises(ValueError, match="team_count must be positive"):
            await create_teams(activity.id, 0)

        persisted = await list_teams(activity.id)

        assert [team.id for team in persisted] == [kept.id]
        assert [team.codename for team in persisted] == ["KEEP-ME"]


class TestRenameTeam:
    """Service-level tests for team renaming."""

    @pytest.mark.asyncio
    async def test_rename_team_updates_persisted_codename(self) -> None:
        """AC3.4: rename_team persists the new codename."""
        from promptgrimoire.db.wargames import (
            create_team,
            get_team,
            list_teams,
            rename_team,
        )

        activity = await _make_wargame_activity("rename-team")
        team = await create_team(activity.id, codename="ALPHA")

        renamed = await rename_team(team.id, "BRAVO")
        fetched = await get_team(team.id)
        listed = await list_teams(activity.id)

        assert renamed is not None
        assert renamed.codename == "BRAVO"
        assert fetched is not None
        assert fetched.codename == "BRAVO"
        assert [row.codename for row in listed] == ["BRAVO"]

    @pytest.mark.asyncio
    async def test_rename_team_raises_duplicate_codename_and_preserves_original(
        self,
    ) -> None:
        """AC3.5: duplicate rename is translated and rolled back."""
        from promptgrimoire.db.wargames import (
            DuplicateCodenameError,
            create_team,
            get_team,
            rename_team,
        )

        activity = await _make_wargame_activity("rename-duplicate")
        first = await create_team(activity.id, codename="ALPHA")
        second = await create_team(activity.id, codename="BRAVO")

        with pytest.raises(DuplicateCodenameError, match="ALPHA") as exc_info:
            await rename_team(second.id, "ALPHA")

        unchanged = await get_team(second.id)
        winner = await get_team(first.id)

        assert exc_info.value.activity_id == activity.id
        assert exc_info.value.codename == "ALPHA"
        assert unchanged is not None
        assert unchanged.codename == "BRAVO"
        assert winner is not None
        assert winner.codename == "ALPHA"

    @pytest.mark.asyncio
    async def test_rename_team_returns_none_for_missing_team(self) -> None:
        """Missing teams return None rather than raising."""
        from promptgrimoire.db.wargames import rename_team

        assert await rename_team(uuid4(), "BRAVO") is None


class TestDeleteTeam:
    """Service-level tests for team deletion."""

    @pytest.mark.asyncio
    async def test_delete_team_removes_team_acl_entries_and_messages(self) -> None:
        """AC3.3: delete_team cascades through dependent rows."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.wargames import create_team, delete_team, get_team

        activity = await _make_wargame_activity("delete-team")
        team = await create_team(activity.id, codename="ALPHA")
        user = await create_user(
            email=f"wargame-delete-{uuid4().hex[:8]}@test.local",
            display_name="Delete Team User",
        )

        async with get_session() as session:
            acl_entry = ACLEntry(
                workspace_id=None,
                team_id=team.id,
                user_id=user.id,
                permission="viewer",
            )
            message = WargameMessage(
                team_id=team.id,
                sequence_no=1,
                role="user",
                content="hello",
            )
            session.add(acl_entry)
            session.add(message)
            await session.flush()
            acl_entry_id = acl_entry.id
            message_id = message.id

        deleted = await delete_team(team.id)

        assert deleted is True
        assert await get_team(team.id) is None

        async with get_session() as session:
            assert await session.get(ACLEntry, acl_entry_id) is None
            assert await session.get(WargameMessage, message_id) is None

    @pytest.mark.asyncio
    async def test_delete_team_returns_false_for_missing_team(self) -> None:
        """Missing teams return False and preserve unrelated rows."""
        from promptgrimoire.db.wargames import create_team, delete_team, get_team

        activity = await _make_wargame_activity("delete-missing")
        kept = await create_team(activity.id, codename="KEEP-ME")

        assert await delete_team(uuid4()) is False

        persisted = await get_team(kept.id)
        assert persisted is not None
        assert persisted.codename == "KEEP-ME"
