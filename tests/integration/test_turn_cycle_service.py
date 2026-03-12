"""Integration tests for wargame turn cycle service layer.

Verifies:
- turn-cycle-296.AC1.1: Bootstrap expanded with team codename (seq=1 user message)
- turn-cycle-296.AC1.2: AI response stored (seq=2) with PydanticAI history
- turn-cycle-296.AC1.3: game_state_text populated from TurnResult
- turn-cycle-296.AC1.4: start_game rejects if game already started
- turn-cycle-296.AC3.1: All teams transition from drafting to locked
- turn-cycle-296.AC3.2: current_deadline cleared on lock
- turn-cycle-296.AC3.3: lock_round rejects if any team not in drafting state
- turn-cycle-296.AC4.1: Markdown extracted from populated CRDT move buffer
- turn-cycle-296.AC4.2: None CRDT state → "No move submitted"
- turn-cycle-296.AC4.3: Whitespace-only CRDT content → "No move submitted"
- turn-cycle-296.AC5.1: turn_agent returns structured TurnResult
- turn-cycle-296.AC5.2: PydanticAI history restored from metadata_json
- turn-cycle-296.AC5.3: Updated PydanticAI history stored on new assistant message
- turn-cycle-296.AC8.1: One-response invariant (duplicate preprocessing rejected)
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
    WargameTeam,
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


async def _start_game_and_publish_to_round2(activity_id: UUID) -> None:
    """Bootstrap a game and transition teams to round 2 / drafting.

    Used by preprocessing tests: starts the game (round 1 locked),
    then manually transitions teams to round 2 / drafting to simulate
    what ``publish_all()`` will do.
    """
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import WargameTeam
    from promptgrimoire.db.wargames import start_game

    with turn_agent.override(model=TestModel()):
        await start_game(activity_id)

    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam).where(WargameTeam.activity_id == activity_id)
        )
        teams = list(result.all())
        for team in teams:
            team.current_round = 2
            team.round_state = "locked"
            session.add(team)


class TestRunPreprocessing:
    """Integration tests for run_preprocessing()."""

    @pytest.mark.asyncio
    async def test_ac4_1_markdown_extracted_from_crdt(self) -> None:
        """AC4.1: User message contains markdown text from CRDT move buffer."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing
        from tests.integration.conftest import make_crdt_bytes

        activity, _config = await _make_wargame_activity_with_config("preproc-crdt")
        await _start_game_and_publish_to_round2(activity.id)

        # Set CRDT move buffer on all teams
        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                db_team = await session.get(WargameTeam, team.id)
                assert db_team is not None
                db_team.move_buffer_crdt = make_crdt_bytes("Deploy forces to sector 7")
                session.add(db_team)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 3,  # round 2 user seq
                    )
                )
                msg = result.one()
                assert msg.role == "user"
                assert "Deploy forces to sector 7" in msg.content

    @pytest.mark.asyncio
    async def test_ac4_2_none_crdt_gives_sentinel(self) -> None:
        """AC4.2: None move buffer produces 'No move submitted'."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing

        activity, _config = await _make_wargame_activity_with_config("preproc-none")
        await _start_game_and_publish_to_round2(activity.id)

        # move_buffer_crdt is None by default — no action needed

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 3,
                    )
                )
                msg = result.one()
                assert msg.content == "No move submitted"

    @pytest.mark.asyncio
    async def test_ac4_3_whitespace_crdt_gives_sentinel(self) -> None:
        """AC4.3: Whitespace-only CRDT content produces 'No move submitted'."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing
        from tests.integration.conftest import make_crdt_bytes

        activity, _config = await _make_wargame_activity_with_config("preproc-ws")
        await _start_game_and_publish_to_round2(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                db_team = await session.get(WargameTeam, team.id)
                assert db_team is not None
                db_team.move_buffer_crdt = make_crdt_bytes("   \n  \t  ")
                session.add(db_team)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 3,
                    )
                )
                msg = result.one()
                assert msg.content == "No move submitted"

    @pytest.mark.asyncio
    async def test_ac5_1_assistant_message_with_content(self) -> None:
        """AC5.1: Assistant message (seq=4) has non-empty content."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing

        activity, _config = await _make_wargame_activity_with_config("preproc-asst")
        await _start_game_and_publish_to_round2(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 4,  # round 2 assistant seq
                    )
                )
                msg = result.one()
                assert msg.role == "assistant"
                assert msg.content  # non-empty

    @pytest.mark.asyncio
    async def test_ac5_2_metadata_includes_bootstrap_history(self) -> None:
        """AC5.2: Metadata contains history from both bootstrap and new round."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing

        activity, _config = await _make_wargame_activity_with_config("preproc-hist")
        await _start_game_and_publish_to_round2(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            result = await session.exec(
                select(WargameMessage).where(
                    WargameMessage.team_id == teams[0].id,
                    WargameMessage.sequence_no == 4,
                )
            )
            msg = result.one()
            assert msg.metadata_json is not None
            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            # Should contain messages from both bootstrap round AND new round
            assert len(restored) > 2

    @pytest.mark.asyncio
    async def test_ac5_3_metadata_usable_as_message_history(self) -> None:
        """AC5.3: New metadata_json can be used as message_history for follow-up."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, run_preprocessing

        activity, _config = await _make_wargame_activity_with_config("preproc-reuse")
        await _start_game_and_publish_to_round2(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

            teams = await list_teams(activity.id)
            async with get_session() as session:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == teams[0].id,
                        WargameMessage.sequence_no == 4,
                    )
                )
                msg = result.one()

            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            # Should be usable as message_history without error
            result2 = await turn_agent.run("follow-up orders", message_history=restored)
            assert result2.output is not None

    @pytest.mark.asyncio
    async def test_ac8_1_one_response_invariant(self) -> None:
        """AC8.1: Calling run_preprocessing twice raises ValueError."""
        from promptgrimoire.db.wargames import run_preprocessing

        activity, _config = await _make_wargame_activity_with_config("preproc-dup")
        await _start_game_and_publish_to_round2(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)
            with pytest.raises(
                ValueError, match="assistant message already exists for current round"
            ):
                await run_preprocessing(activity.id)


class TestOnDeadlineFired:
    """Integration tests for on_deadline_fired()."""

    @pytest.mark.asyncio
    async def test_ac3_1_deadline_locks_all_teams(self) -> None:
        """AC3.1 (deadline path): All teams locked after on_deadline_fired."""
        from promptgrimoire.db.wargames import list_teams, on_deadline_fired

        activity, _config = await _make_wargame_activity_with_config("deadline-lock")
        # Start game, then transition to round 2 drafting
        with turn_agent.override(model=TestModel()):
            await _start_game_and_publish_to_round2(activity.id)

        # Set teams to drafting for on_deadline_fired
        await _set_teams_to_drafting(activity.id)

        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "locked"

    @pytest.mark.asyncio
    async def test_full_pipeline_lock_and_preprocess(self) -> None:
        """Full pipeline: on_deadline_fired locks AND creates messages."""
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.wargames import list_teams, on_deadline_fired

        activity, _config = await _make_wargame_activity_with_config("deadline-full")
        with turn_agent.override(model=TestModel()):
            await _start_game_and_publish_to_round2(activity.id)

        # Set to drafting
        await _set_teams_to_drafting(activity.id)

        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                # Check user message (seq=3)
                user_result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 3,
                    )
                )
                user_msg = user_result.one()
                assert user_msg.role == "user"

                # Check assistant message (seq=4)
                asst_result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 4,
                    )
                )
                asst_msg = asst_result.one()
                assert asst_msg.role == "assistant"

    @pytest.mark.asyncio
    async def test_atomicity_rollback_on_preprocessing_failure(self) -> None:
        """Atomicity: if preprocessing fails, lock is also rolled back."""
        from unittest.mock import AsyncMock, patch

        from promptgrimoire.db.wargames import list_teams, on_deadline_fired

        activity, _config = await _make_wargame_activity_with_config("deadline-atom")
        with turn_agent.override(model=TestModel()):
            await _start_game_and_publish_to_round2(activity.id)

        # Set to drafting
        await _set_teams_to_drafting(activity.id)

        # Mock turn_agent.run to raise during preprocessing
        with (
            turn_agent.override(model=TestModel()),
            patch.object(
                turn_agent,
                "run",
                new_callable=AsyncMock,
                side_effect=RuntimeError("AI service unavailable"),
            ),
            pytest.raises(RuntimeError, match="AI service unavailable"),
        ):
            await on_deadline_fired(activity.id)

        # Teams should still be in drafting state (lock was rolled back)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "drafting"
