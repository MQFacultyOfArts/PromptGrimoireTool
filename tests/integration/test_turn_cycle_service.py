"""Integration tests for wargame turn cycle service layer.

Verifies:
- turn-cycle-296.AC1.1: Bootstrap expanded with team codename (seq=1 user message)
- turn-cycle-296.AC1.2: AI response stored (seq=2) with PydanticAI history
- turn-cycle-296.AC1.3: game_state_text populated from TurnResult
- turn-cycle-296.AC1.4: start_game rejects if game already started
- turn-cycle-296.AC3.1: All teams transition from drafting to locked
- turn-cycle-296.AC3.2: current_deadline cleared on lock
- turn-cycle-296.AC3.3: lock_round rejects if any team not in drafting state
- turn-cycle-296.AC5.2: PydanticAI history restored from metadata_json
- turn-cycle-296.AC5.3: Updated PydanticAI history stored on new assistant message
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import (
    Activity,
    WargameConfig,
    WargameMessage,
)
from promptgrimoire.wargame.agents import turn_agent

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _set_teams_to_drafting(activity_id: UUID) -> None:
    """Directly set all teams for an activity to drafting state with a deadline.

    Used as test setup for lock_round tests, bypassing start_game to avoid
    coupling tests to start_game's correctness.
    """
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import WargameTeam

    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam).where(WargameTeam.activity_id == activity_id)
        )
        teams = list(result.all())
        for team in teams:
            team.round_state = "drafting"
            team.current_deadline = datetime.now(UTC) + timedelta(hours=1)
            session.add(team)


async def _make_wargame_activity_with_config(
    suffix: str,
) -> tuple[Activity, WargameConfig]:
    """Create a persisted wargame activity with config and 2 teams."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.wargames import create_teams
    from promptgrimoire.db.weeks import create_week

    code = f"TC{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"Turn Cycle {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Wargame {suffix}",
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)

        config = WargameConfig(
            activity_id=activity.id,
            system_prompt="You are the GM of a test wargame scenario.",
            scenario_bootstrap="Welcome, team {codename}. Your mission begins now.",
            timer_delta=timedelta(hours=24),
        )
        session.add(config)
        await session.flush()
        await session.refresh(config)

    await create_teams(activity.id, 2)
    return activity, config


class TestStartGame:
    """Integration tests for start_game()."""

    @pytest.mark.asyncio
    async def test_ac1_1_bootstrap_expanded_with_codename(self) -> None:
        """AC1.1: Each team has a user message (seq=1) with codename in content."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, start_game

        activity, _config = await _make_wargame_activity_with_config("start-codename")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 1,
                    )
                )
                msg = result.one()
                assert msg.role == "user"
                assert team.codename in msg.content

    @pytest.mark.asyncio
    async def test_ac1_2_assistant_message_with_pydantic_history(self) -> None:
        """AC1.2: Assistant message (seq=2) has valid PydanticAI history."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, start_game

        activity, _config = await _make_wargame_activity_with_config("start-history")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 2,
                    )
                )
                msg = result.one()
                assert msg.role == "assistant"
                assert msg.metadata_json is not None
                # Validate PydanticAI history deserialises
                restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
                assert len(restored) > 0

    @pytest.mark.asyncio
    async def test_ac1_3_game_state_text_populated(self) -> None:
        """AC1.3: Each team's game_state_text is populated after start_game."""
        from promptgrimoire.db.wargames import list_teams, start_game

        activity, _config = await _make_wargame_activity_with_config("start-gamestate")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.game_state_text is not None

    @pytest.mark.asyncio
    async def test_ac1_4_rejects_already_started(self) -> None:
        """AC1.4: Calling start_game a second time raises ValueError."""
        from promptgrimoire.db.wargames import start_game

        activity, _config = await _make_wargame_activity_with_config("start-reject")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)
            with pytest.raises(ValueError, match="game already started"):
                await start_game(activity.id)

    @pytest.mark.asyncio
    async def test_ac5_2_ac5_3_metadata_history_round_trip(self) -> None:
        """AC5.2/5.3: metadata_json can be restored and used as message_history."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, start_game

        activity, _config = await _make_wargame_activity_with_config("start-roundtrip")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

            async with get_session() as session:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == teams[0].id,
                        WargameMessage.sequence_no == 2,
                    )
                )
                msg = result.one()

            # Restore history and make a follow-up call
            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            result2 = await turn_agent.run("follow-up orders", message_history=restored)
            assert result2.output is not None

    @pytest.mark.asyncio
    async def test_teams_locked_after_start(self) -> None:
        """After start_game, all teams are round=1, state=locked."""
        from promptgrimoire.db.wargames import list_teams, start_game

        activity, _config = await _make_wargame_activity_with_config("start-locked")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_round == 1
            assert team.round_state == "locked"


class TestLockRound:
    """Integration tests for lock_round()."""

    @pytest.mark.asyncio
    async def test_ac3_1_all_teams_locked(self) -> None:
        """AC3.1: After lock_round, all teams have round_state=locked."""
        from promptgrimoire.db.wargames import list_teams, lock_round

        activity, _config = await _make_wargame_activity_with_config("lock-all")
        await _set_teams_to_drafting(activity.id)

        await lock_round(activity.id)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "locked"

    @pytest.mark.asyncio
    async def test_ac3_2_deadline_cleared(self) -> None:
        """AC3.2: After lock_round, current_deadline is None for all teams."""
        from promptgrimoire.db.wargames import list_teams, lock_round

        activity, _config = await _make_wargame_activity_with_config("lock-deadline")
        await _set_teams_to_drafting(activity.id)

        await lock_round(activity.id)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_deadline is None

    @pytest.mark.asyncio
    async def test_ac3_3_rejects_non_drafting(self) -> None:
        """AC3.3: lock_round raises ValueError if any team not in drafting state."""
        from promptgrimoire.db.wargames import lock_round

        activity, _config = await _make_wargame_activity_with_config("lock-reject")
        # Teams start in default "drafting" state but with no other setup.
        # Lock them first so they are in "locked" state, then verify lock_round rejects.
        await _set_teams_to_drafting(activity.id)
        await lock_round(activity.id)

        # Now teams are locked, so lock_round should fail
        with pytest.raises(ValueError, match="not all teams in drafting state"):
            await lock_round(activity.id)
