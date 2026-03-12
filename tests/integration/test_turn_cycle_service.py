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
- turn-cycle-296.AC6.1-5: Publish pipeline (summaries, round, state, buffer)
- turn-cycle-296.AC6.5: Deadline set after publish
- turn-cycle-296.AC7.1-2: Completion gating (missing responses, wrong state)
- turn-cycle-296.AC8.2: One-response invariant (duplicate detection on publish)
- turn-cycle-296.AC2.4: Wall-clock deadline rollover
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import (
    Activity,
    WargameConfig,
    WargameMessage,
    WargameTeam,
)
from promptgrimoire.db.wargames import (
    _preprocess_one_team,
    list_teams,
    lock_round,
    on_deadline_fired,
    publish_all,
    run_preprocessing,
    start_game,
)
from promptgrimoire.wargame.agents import summary_agent, turn_agent
from tests.integration.conftest import make_crdt_bytes

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _get_message(
    session: Any,
    team_id: UUID,
    sequence_no: int,
) -> WargameMessage | None:
    """Query a single WargameMessage by team and sequence number."""
    result = await session.exec(
        select(WargameMessage).where(
            WargameMessage.team_id == team_id,
            WargameMessage.sequence_no == sequence_no,
        )
    )
    return result.one_or_none()


async def _set_teams_to_drafting(activity_id: UUID) -> None:
    """Directly set all teams for an activity to drafting state with a deadline.

    Used as test setup for lock_round tests, bypassing start_game to avoid
    coupling tests to start_game's correctness.
    """
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
        activity, _config = await _make_wargame_activity_with_config("start-codename")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        async with get_session() as session:
            for team in teams:
                msg = await _get_message(session, team.id, 1)
                assert msg is not None
                assert msg.role == "user"
                assert team.codename in msg.content

    @pytest.mark.asyncio
    async def test_ac1_2_assistant_message_with_pydantic_history(self) -> None:
        """AC1.2: Assistant message (seq=2) has valid PydanticAI history."""
        activity, _config = await _make_wargame_activity_with_config("start-history")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        async with get_session() as session:
            for team in teams:
                msg = await _get_message(session, team.id, 2)
                assert msg is not None
                assert msg.role == "assistant"
                assert msg.metadata_json is not None
                # Validate PydanticAI history deserialises
                restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
                assert len(restored) > 0

    @pytest.mark.asyncio
    async def test_ac1_3_game_state_text_populated(self) -> None:
        """AC1.3: Each team's game_state_text is populated after start_game."""
        activity, _config = await _make_wargame_activity_with_config("start-gamestate")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.game_state_text is not None

    @pytest.mark.asyncio
    async def test_ac1_4_rejects_already_started(self) -> None:
        """AC1.4: Calling start_game a second time raises ValueError."""
        activity, _config = await _make_wargame_activity_with_config("start-reject")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)
            with pytest.raises(ValueError, match="game already started"):
                await start_game(activity.id)

    @pytest.mark.asyncio
    async def test_ac5_2_ac5_3_metadata_history_round_trip(self) -> None:
        """AC5.2/5.3: metadata_json can be restored and used as message_history."""
        activity, _config = await _make_wargame_activity_with_config("start-roundtrip")
        teams = await list_teams(activity.id)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

            async with get_session() as session:
                msg = await _get_message(session, teams[0].id, 2)
                assert msg is not None

            # Restore history and make a follow-up call
            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            result2 = await turn_agent.run("follow-up orders", message_history=restored)
            assert result2.output is not None

    @pytest.mark.asyncio
    async def test_teams_locked_after_start(self) -> None:
        """After start_game, all teams are round=1, state=locked."""
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
        activity, _config = await _make_wargame_activity_with_config("lock-all")
        await _set_teams_to_drafting(activity.id)

        await lock_round(activity.id)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "locked"

    @pytest.mark.asyncio
    async def test_ac3_2_deadline_cleared(self) -> None:
        """AC3.2: After lock_round, current_deadline is None for all teams."""
        activity, _config = await _make_wargame_activity_with_config("lock-deadline")
        await _set_teams_to_drafting(activity.id)

        await lock_round(activity.id)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_deadline is None

    @pytest.mark.asyncio
    async def test_ac3_3_rejects_non_drafting(self) -> None:
        """AC3.3: lock_round raises ValueError if any team not in drafting state."""
        activity, _config = await _make_wargame_activity_with_config("lock-reject")
        # Teams start in default "drafting" state but with no other setup.
        # Lock them first so they are in "locked" state, then verify lock_round rejects.
        await _set_teams_to_drafting(activity.id)
        await lock_round(activity.id)

        # Now teams are locked, so lock_round should fail
        with pytest.raises(ValueError, match="not all teams in drafting state"):
            await lock_round(activity.id)


async def _start_game_and_advance_to_round2_locked(activity_id: UUID) -> None:
    """Bootstrap a game and leave teams in round 2 / locked state.

    Used by preprocessing tests: starts the game (round 1 locked),
    then manually advances teams to round 2 with ``round_state='locked'``
    to simulate the state after ``publish_all()`` increments the round.
    """
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
        activity, _config = await _make_wargame_activity_with_config("preproc-crdt")
        await _start_game_and_advance_to_round2_locked(activity.id)

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
                msg = await _get_message(session, team.id, 3)
                assert msg is not None
                assert msg.role == "user"
                assert "Deploy forces to sector 7" in msg.content

    @pytest.mark.asyncio
    async def test_ac4_2_none_crdt_gives_sentinel(self) -> None:
        """AC4.2: None move buffer produces 'No move submitted'."""
        activity, _config = await _make_wargame_activity_with_config("preproc-none")
        await _start_game_and_advance_to_round2_locked(activity.id)

        # move_buffer_crdt is None by default — no action needed

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                msg = await _get_message(session, team.id, 3)
                assert msg is not None
                assert msg.content == "No move submitted"

    @pytest.mark.asyncio
    async def test_ac4_3_whitespace_crdt_gives_sentinel(self) -> None:
        """AC4.3: Whitespace-only CRDT content produces 'No move submitted'."""
        activity, _config = await _make_wargame_activity_with_config("preproc-ws")
        await _start_game_and_advance_to_round2_locked(activity.id)

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
                msg = await _get_message(session, team.id, 3)
                assert msg is not None
                assert msg.content == "No move submitted"

    @pytest.mark.asyncio
    async def test_ac5_1_assistant_message_with_content(self) -> None:
        """AC5.1: Assistant message (seq=4) has non-empty content."""
        activity, _config = await _make_wargame_activity_with_config("preproc-asst")
        await _start_game_and_advance_to_round2_locked(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                msg = await _get_message(session, team.id, 4)
                assert msg is not None
                assert msg.role == "assistant"
                assert msg.content  # non-empty

    @pytest.mark.asyncio
    async def test_ac5_2_metadata_includes_bootstrap_history(self) -> None:
        """AC5.2: Metadata contains history from both bootstrap and new round."""
        activity, _config = await _make_wargame_activity_with_config("preproc-hist")
        await _start_game_and_advance_to_round2_locked(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            msg = await _get_message(session, teams[0].id, 4)
            assert msg is not None
            assert msg.metadata_json is not None
            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            # Should contain messages from both bootstrap round AND new round
            assert len(restored) > 2

    @pytest.mark.asyncio
    async def test_ac5_3_metadata_usable_as_message_history(self) -> None:
        """AC5.3: New metadata_json can be used as message_history for follow-up."""
        activity, _config = await _make_wargame_activity_with_config("preproc-reuse")
        await _start_game_and_advance_to_round2_locked(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)

            teams = await list_teams(activity.id)
            async with get_session() as session:
                msg = await _get_message(session, teams[0].id, 4)
                assert msg is not None

            restored = ModelMessagesTypeAdapter.validate_python(msg.metadata_json)
            # Should be usable as message_history without error
            result2 = await turn_agent.run("follow-up orders", message_history=restored)
            assert result2.output is not None

    @pytest.mark.asyncio
    async def test_ac8_1_one_response_invariant(self) -> None:
        """AC8.1: Calling run_preprocessing twice skips already-processed teams.

        The one-response invariant detects that assistant messages already
        exist for the current round and silently skips those teams rather
        than raising or re-processing them.
        """
        activity, _config = await _make_wargame_activity_with_config("preproc-dup")
        await _start_game_and_advance_to_round2_locked(activity.id)

        with turn_agent.override(model=TestModel()):
            await run_preprocessing(activity.id)
            # Second call should silently skip (no error, no duplicate messages)
            await run_preprocessing(activity.id)

        # Verify no duplicate messages: each team should have exactly one
        # assistant message for round 2 (sequence_no=4)
        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage).where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.sequence_no == 4,
                    )
                )
                messages = list(result.all())
                assert len(messages) == 1, (
                    f"Expected exactly 1 assistant message for round 2, "
                    f"got {len(messages)} for team {team.codename}"
                )


class TestOnDeadlineFired:
    """Integration tests for on_deadline_fired()."""

    @pytest.mark.asyncio
    async def test_ac3_1_deadline_locks_all_teams(self) -> None:
        """AC3.1 (deadline path): All teams locked after on_deadline_fired."""
        activity, _config = await _make_wargame_activity_with_config("deadline-lock")
        # Start game, then transition to round 2 drafting
        with turn_agent.override(model=TestModel()):
            await _start_game_and_advance_to_round2_locked(activity.id)

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
        activity, _config = await _make_wargame_activity_with_config("deadline-full")
        with turn_agent.override(model=TestModel()):
            await _start_game_and_advance_to_round2_locked(activity.id)

        await _set_teams_to_drafting(activity.id)

        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                user_msg = await _get_message(session, team.id, 3)
                assert user_msg is not None
                assert user_msg.role == "user"

                asst_msg = await _get_message(session, team.id, 4)
                assert asst_msg is not None
                assert asst_msg.role == "assistant"

    @pytest.mark.asyncio
    async def test_lock_committed_even_when_preprocessing_fails(self) -> None:
        """Lock phase commits independently; preprocessing errors mark teams."""
        activity, _config = await _make_wargame_activity_with_config("deadline-atom")
        with turn_agent.override(model=TestModel()):
            await _start_game_and_advance_to_round2_locked(activity.id)

        await _set_teams_to_drafting(activity.id)

        # Patch _preprocess_one_team to raise for ALL teams.
        with patch(
            "promptgrimoire.db.wargames._preprocess_one_team",
            new_callable=AsyncMock,
            side_effect=RuntimeError("AI service unavailable"),
        ):
            await on_deadline_fired(activity.id)

        # Lock phase committed: teams should NOT be in drafting state.
        # Since all teams' preprocessing failed, they should be in "error" state.
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "error"

    @pytest.mark.asyncio
    async def test_partial_failure_marks_errored_team_continues_others(self) -> None:
        """Per-team isolation: one team's AI failure doesn't block others."""
        activity, _config = await _make_wargame_activity_with_config("deadline-partial")
        with turn_agent.override(model=TestModel()):
            await _start_game_and_advance_to_round2_locked(activity.id)

        await _set_teams_to_drafting(activity.id)

        teams = await list_teams(activity.id)
        failing_team_id = teams[0].id

        call_count = 0

        async def _selective_fail(
            session: Any,
            config: Any,
            team: Any,
        ) -> None:
            nonlocal call_count
            call_count += 1
            if team.id == failing_team_id:
                raise RuntimeError("AI service unavailable")
            await _preprocess_one_team(session, config, team)

        with (
            turn_agent.override(model=TestModel()),
            patch(
                "promptgrimoire.db.wargames._preprocess_one_team",
                new_callable=AsyncMock,
                side_effect=_selective_fail,
            ),
        ):
            await on_deadline_fired(activity.id)

        # Every team (including the failing one) should have been attempted
        assert call_count == len(teams)

        # Reload teams
        teams = await list_teams(activity.id)
        for team in teams:
            if team.id == failing_team_id:
                assert team.round_state == "error"
            else:
                # Successful team should still be "locked" (preprocessing
                # doesn't change round_state — that's publish_all's job)
                assert team.round_state == "locked"

        # Verify message state per team
        async with get_session() as session:
            for team in teams:
                if team.id == failing_team_id:
                    # Errored team: per-team session rollback must roll back
                    # both user and assistant messages
                    assert await _get_message(session, team.id, 3) is None
                    assert await _get_message(session, team.id, 4) is None
                else:
                    # Successful team should have round 2 messages
                    assert await _get_message(session, team.id, 3) is not None
                    assert await _get_message(session, team.id, 4) is not None


async def _bootstrap_round1(activity_id: UUID) -> None:
    """Bootstrap a game and run preprocessing so teams have draft responses.

    After this: teams are in round 1, state "locked", with seq=1 (user) and
    seq=2 (assistant) messages. This is the correct starting state for
    publish_all tests.
    """
    with turn_agent.override(model=TestModel()):
        await start_game(activity_id)


class TestPublishAll:
    """Integration tests for publish_all()."""

    @pytest.mark.asyncio
    async def test_ac7_2_rejects_drafting_state(self) -> None:
        """AC7.2: publish_all raises ValueError if teams in drafting state."""
        activity, _config = await _make_wargame_activity_with_config("pub-drafting")
        await _bootstrap_round1(activity.id)

        # Transition teams to drafting
        await _set_teams_to_drafting(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
            pytest.raises(ValueError, match="not all teams in locked"),
        ):
            await publish_all(activity.id)

    @pytest.mark.asyncio
    async def test_ac7_1_rejects_missing_assistant_messages(self) -> None:
        """AC7.1: publish_all raises ValueError if no draft response exists."""
        activity, _config = await _make_wargame_activity_with_config("pub-noasst")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        # Delete assistant messages scoped to this activity to simulate missing drafts
        async with get_session() as session:
            team_ids_subq = select(WargameTeam.id).where(
                WargameTeam.activity_id == activity.id
            )
            result = await session.exec(
                select(WargameMessage).where(
                    WargameMessage.team_id.in_(team_ids_subq),  # type: ignore[union-attr]  -- Column has .in_()
                    WargameMessage.role == "assistant",
                )
            )
            for msg in result.all():
                await session.delete(msg)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
            pytest.raises(ValueError, match="not all teams have draft responses"),
        ):
            await publish_all(activity.id)

    @pytest.mark.asyncio
    async def test_ac6_1_summary_text_populated(self) -> None:
        """AC6.1: After publish_all, each team has student_summary_text."""
        activity, _config = await _make_wargame_activity_with_config("pub-summary")
        await _bootstrap_round1(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.student_summary_text is not None
            assert team.student_summary_text != ""

    @pytest.mark.asyncio
    async def test_ac6_2_round_advanced(self) -> None:
        """AC6.2: After publish_all, current_round advances by 1."""
        activity, _config = await _make_wargame_activity_with_config("pub-round")
        await _bootstrap_round1(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_round == 2

    @pytest.mark.asyncio
    async def test_ac6_3_state_back_to_drafting(self) -> None:
        """AC6.3: After publish_all, all teams have round_state=drafting."""
        activity, _config = await _make_wargame_activity_with_config("pub-state")
        await _bootstrap_round1(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "drafting"

    @pytest.mark.asyncio
    async def test_ac6_4_move_buffer_cleared(self) -> None:
        """AC6.4: After publish_all, move_buffer_crdt is None for all teams."""
        activity, _config = await _make_wargame_activity_with_config("pub-buffer")
        await _bootstrap_round1(activity.id)

        # Set move buffers before publish
        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                db_team = await session.get(WargameTeam, team.id)
                assert db_team is not None
                db_team.move_buffer_crdt = make_crdt_bytes("some move text")
                session.add(db_team)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.move_buffer_crdt is None

    @pytest.mark.asyncio
    async def test_ac6_5_deadline_set(self) -> None:
        """AC6.5: After publish_all, all teams have a future deadline."""
        activity, _config = await _make_wargame_activity_with_config("pub-deadline")
        await _bootstrap_round1(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        now = datetime.now(UTC)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_deadline is not None
            assert team.current_deadline > now

    @pytest.mark.asyncio
    async def test_ac2_4_wall_clock_rollover(self) -> None:
        """AC2.4: Wall-clock deadline past today rolls to tomorrow."""
        from datetime import time as dt_time

        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.wargames import create_teams
        from promptgrimoire.db.weeks import create_week

        code = f"TC{uuid4().hex[:6].upper()}"
        course = await create_course(
            code=code,
            name="Turn Cycle wall-clock",
            semester="2026-S1",
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")

        # Configure with wall_clock time that's already past (midnight)
        async with get_session() as session:
            activity = Activity(
                week_id=week.id,
                type="wargame",
                title="Wargame wall-clock",
            )
            session.add(activity)
            await session.flush()
            await session.refresh(activity)

            config = WargameConfig(
                activity_id=activity.id,
                system_prompt="Test GM prompt.",
                scenario_bootstrap="Welcome, team {codename}.",
                timer_wall_clock=dt_time(0, 1),  # 00:01 — already past
            )
            session.add(config)
            await session.flush()

        await create_teams(activity.id, 2)

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        now = datetime.now(UTC)
        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_deadline is not None
            # Deadline should be tomorrow since 00:01 is past
            assert team.current_deadline > now
            assert team.current_deadline.date() > now.date()

    @pytest.mark.asyncio
    async def test_ac8_2_duplicate_assistant_message_rejected(self) -> None:
        """AC8.2: Duplicate assistant message for same round raises ValueError.

        The DB unique constraint ``(team_id, sequence_no)`` makes true
        duplicates impossible in normal operation. This test bypasses the
        constraint via raw SQL to exercise the defense-in-depth check in
        ``publish_all()``.
        """
        activity, _config = await _make_wargame_activity_with_config("pub-dup")
        await _bootstrap_round1(activity.id)

        teams = await list_teams(activity.id)
        team = teams[0]

        # Insert a duplicate assistant message at seq=2 via raw SQL,
        # bypassing the ORM unique constraint.
        async with get_session() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO wargame_message "
                    "(id, team_id, sequence_no, role, content, created_at) "
                    "VALUES (gen_random_uuid(), :team_id, :seq, 'assistant', "
                    "'duplicate', now()) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"team_id": str(team.id), "seq": 2},
            )
            # The ON CONFLICT DO NOTHING means if the unique constraint
            # fires, nothing is inserted. We need to temporarily drop and
            # restore the constraint.
            await session.execute(
                sa.text(
                    "ALTER TABLE wargame_message "
                    "DROP CONSTRAINT uq_wargame_message_team_sequence"
                )
            )
            await session.execute(
                sa.text(
                    "INSERT INTO wargame_message "
                    "(id, team_id, sequence_no, role, content, created_at) "
                    "VALUES (gen_random_uuid(), :team_id, :seq, 'assistant', "
                    "'duplicate', now())"
                ),
                {"team_id": str(team.id), "seq": 2},
            )

        try:
            with (
                turn_agent.override(model=TestModel()),
                summary_agent.override(model=TestModel()),
                pytest.raises(ValueError, match="multiple assistant messages"),
            ):
                await publish_all(activity.id)
        finally:
            # Restore the unique constraint (delete duplicate row first)
            async with get_session() as session:
                await session.execute(
                    sa.text(
                        "DELETE FROM wargame_message a "
                        "USING wargame_message b "
                        "WHERE a.team_id = b.team_id "
                        "AND a.sequence_no = b.sequence_no "
                        "AND a.id > b.id"
                    )
                )
                await session.execute(
                    sa.text(
                        "ALTER TABLE wargame_message "
                        "ADD CONSTRAINT uq_wargame_message_team_sequence "
                        "UNIQUE (team_id, sequence_no)"
                    )
                )

    @pytest.mark.asyncio
    async def test_error_teams_skipped(self) -> None:
        """Error teams from preprocessing are skipped by publish_all."""
        activity, _config = await _make_wargame_activity_with_config("pub-errskip")
        await _bootstrap_round1(activity.id)

        # Mark one team as errored
        teams = await list_teams(activity.id)
        async with get_session() as session:
            db_team = await session.get(WargameTeam, teams[0].id)
            assert db_team is not None
            db_team.round_state = "error"
            session.add(db_team)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            # Should not raise — error teams should be skipped
            await publish_all(activity.id)

        # Only non-error team should have been advanced
        teams = await list_teams(activity.id)
        for team in teams:
            if team.round_state == "error":
                # Errored team stays in error, round unchanged
                assert team.current_round == 1
            else:
                assert team.current_round == 2
                assert team.round_state == "drafting"
