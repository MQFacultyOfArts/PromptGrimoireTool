"""Full round trip integration test for the wargame turn cycle.

Exercises two complete rounds of the turn cycle end-to-end:
    start_game -> publish_all (round 1) ->
    on_deadline_fired -> publish_all (round 2)

Uses real database with TestModel for all AI calls.

Verifies:
- turn-cycle-296.AC1.1-AC1.4: Game start bootstrap
- turn-cycle-296.AC2.1-AC2.3: Timer management (schedule_deadline monkeypatched)
- turn-cycle-296.AC3.1-AC3.3: Hard-deadline lock
- turn-cycle-296.AC4.1-AC4.3: Snapshot pipeline (CRDT extraction in round 2)
- turn-cycle-296.AC5.1-AC5.3: AI pre-processing (history accumulation)
- turn-cycle-296.AC6.1-AC6.5: Publish pipeline
- turn-cycle-296.AC7.1-AC7.2: Completion gating
- turn-cycle-296.AC8.1-AC8.3: One-response invariant
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
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
    list_teams,
    on_deadline_fired,
    publish_all,
    start_game,
)
from promptgrimoire.wargame.agents import summary_agent, turn_agent
from tests.integration.conftest import make_crdt_bytes

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_wargame_activity_with_config(
    suffix: str,
) -> tuple[Activity, WargameConfig]:
    """Create a persisted wargame activity with config and 2 teams."""
    from datetime import timedelta

    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.wargames import create_teams
    from promptgrimoire.db.weeks import create_week

    code = f"E2E{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"E2E Round Trip {suffix}",
        semester="2026-S1",
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")

    async with get_session() as session:
        activity = Activity(
            week_id=week.id,
            type="wargame",
            title=f"Wargame E2E {suffix}",
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


async def _get_messages_for_team(
    session: Any,
    team_id: Any,
) -> list[WargameMessage]:
    """Return all messages for a team ordered by sequence number."""
    result = await session.exec(
        select(WargameMessage)
        .where(WargameMessage.team_id == team_id)
        .order_by(WargameMessage.sequence_no)  # type: ignore[arg-type]  -- SQLAlchemy column expression
    )
    return list(result.all())


async def _set_teams_to_drafting(activity_id: Any) -> None:
    """Set all teams to drafting state with a future deadline."""
    from datetime import timedelta

    async with get_session() as session:
        result = await session.exec(
            select(WargameTeam).where(WargameTeam.activity_id == activity_id)
        )
        teams = list(result.all())
        for team in teams:
            team.round_state = "drafting"
            team.current_deadline = datetime.now(UTC) + timedelta(hours=1)
            session.add(team)


async def _assert_bootstrap_state(
    teams: list[WargameTeam],
) -> None:
    """Verify state after start_game (AC1.1-AC1.3)."""
    assert len(teams) == 2

    for team in teams:
        assert team.current_round == 1
        assert team.round_state == "locked"
        assert team.game_state_text is not None

    async with get_session() as session:
        for team in teams:
            msgs = await _get_messages_for_team(session, team.id)
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].sequence_no == 1
            assert team.codename in msgs[0].content

            assert msgs[1].role == "assistant"
            assert msgs[1].sequence_no == 2
            assert msgs[1].metadata_json is not None
            restored = ModelMessagesTypeAdapter.validate_python(msgs[1].metadata_json)
            assert len(restored) > 0


async def _assert_publish_state(
    teams: list[WargameTeam],
    *,
    expected_round: int,
) -> None:
    """Verify state after publish_all (AC6.1-AC6.5)."""
    now = datetime.now(UTC)
    for team in teams:
        assert team.current_round == expected_round
        assert team.round_state == "drafting"
        assert team.student_summary_text is not None
        assert team.student_summary_text != ""
        assert team.move_buffer_crdt is None
        assert team.current_deadline is not None
        assert team.current_deadline > now


async def _assert_round2_messages(
    teams: list[WargameTeam],
    move_texts: list[str],
) -> None:
    """Verify 4 messages per team after round 2 preprocessing."""
    async with get_session() as session:
        for i, team in enumerate(teams):
            msgs = await _get_messages_for_team(session, team.id)
            assert len(msgs) == 4

            assert msgs[0].role == "user"
            assert msgs[0].sequence_no == 1
            assert msgs[1].role == "assistant"
            assert msgs[1].sequence_no == 2

            assert msgs[2].role == "user"
            assert msgs[2].sequence_no == 3
            assert move_texts[i] in msgs[2].content

            assert msgs[3].role == "assistant"
            assert msgs[3].sequence_no == 4
            assert msgs[3].metadata_json is not None
            restored = ModelMessagesTypeAdapter.validate_python(msgs[3].metadata_json)
            assert len(restored) > 2


class TestFullRoundTrip:
    """End-to-end test exercising two complete rounds of the turn cycle."""

    @pytest.mark.asyncio
    async def test_two_full_rounds(self) -> None:
        """Walk through start_game -> publish -> deadline -> publish."""
        activity, _config = await _make_wargame_activity_with_config("full-roundtrip")

        # Step 1: start_game
        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        teams = await list_teams(activity.id)
        await _assert_bootstrap_state(teams)

        # Step 2: publish_all — publishes round 1
        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        await _assert_publish_state(teams, expected_round=2)

        # Step 3: Simulate player moves
        move_texts = [
            "Deploy forces to sector 7",
            "Fortify position at hill 42",
        ]
        async with get_session() as session:
            for i, team in enumerate(teams):
                db_team = await session.get(WargameTeam, team.id)
                assert db_team is not None
                db_team.move_buffer_crdt = make_crdt_bytes(move_texts[i])
                session.add(db_team)

        # Step 4: on_deadline_fired — locks + preprocesses
        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.round_state == "locked"
            assert team.game_state_text is not None

        await _assert_round2_messages(teams, move_texts)

        # Step 5: publish_all — publishes round 2
        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        await _assert_publish_state(teams, expected_round=3)

        # AC8.3: no duplicate assistant messages
        async with get_session() as session:
            for team in teams:
                msgs = await _get_messages_for_team(session, team.id)
                assert len(msgs) == 4
                assistant_msgs = [m for m in msgs if m.role == "assistant"]
                assert len(assistant_msgs) == 2
                seq_nos = [m.sequence_no for m in assistant_msgs]
                assert len(seq_nos) == len(set(seq_nos))


class TestEdgeCases:
    """Edge case tests for round trip scenarios."""

    @pytest.mark.asyncio
    async def test_empty_moves_all_teams(self) -> None:
        """All teams have no move when deadline fires."""
        activity, _config = await _make_wargame_activity_with_config("empty-moves")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        # move_buffer_crdt is None by default — simulate deadline with no moves
        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        # Verify user messages contain "No move submitted"
        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                msgs = await _get_messages_for_team(session, team.id)
                # Round 2 user message (seq=3)
                user_msg = [m for m in msgs if m.sequence_no == 3]
                assert len(user_msg) == 1
                assert user_msg[0].content == "No move submitted"

        # Full publish still succeeds
        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_round == 3
            assert team.round_state == "drafting"

    @pytest.mark.asyncio
    async def test_mixed_moves(self) -> None:
        """One team has content, another has None."""
        activity, _config = await _make_wargame_activity_with_config("mixed-moves")

        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        # Set move buffer on first team only
        teams = await list_teams(activity.id)
        async with get_session() as session:
            db_team = await session.get(WargameTeam, teams[0].id)
            assert db_team is not None
            db_team.move_buffer_crdt = make_crdt_bytes("Attack the fortress")
            session.add(db_team)
            # Second team has no move (move_buffer_crdt remains None)

        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        # Verify messages
        async with get_session() as session:
            # Team with move
            msgs_0 = await _get_messages_for_team(session, teams[0].id)
            user_msg_0 = [m for m in msgs_0 if m.sequence_no == 3]
            assert len(user_msg_0) == 1
            assert "Attack the fortress" in user_msg_0[0].content

            # Team without move
            msgs_1 = await _get_messages_for_team(session, teams[1].id)
            user_msg_1 = [m for m in msgs_1 if m.sequence_no == 3]
            assert len(user_msg_1) == 1
            assert user_msg_1[0].content == "No move submitted"

        # Both teams processed correctly — publish succeeds
        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        teams = await list_teams(activity.id)
        for team in teams:
            assert team.current_round == 3

    @pytest.mark.asyncio
    async def test_ac8_3_no_duplicate_assistants_across_rounds(self) -> None:
        """AC8.3: After two full rounds, no duplicate assistant messages exist."""
        activity, _config = await _make_wargame_activity_with_config("no-dupes")

        # Round 1: start + publish
        with turn_agent.override(model=TestModel()):
            await start_game(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        # Round 2: deadline + publish
        with turn_agent.override(model=TestModel()):
            await on_deadline_fired(activity.id)

        with (
            turn_agent.override(model=TestModel()),
            summary_agent.override(model=TestModel()),
        ):
            await publish_all(activity.id)

        # Verify invariant: exactly 2 assistant messages per team
        teams = await list_teams(activity.id)
        async with get_session() as session:
            for team in teams:
                result = await session.exec(
                    select(WargameMessage)
                    .where(
                        WargameMessage.team_id == team.id,
                        WargameMessage.role == "assistant",
                    )
                    .order_by(WargameMessage.sequence_no)  # type: ignore[arg-type]
                )
                assistant_msgs = list(result.all())
                assert len(assistant_msgs) == 2, (
                    f"Expected exactly 2 assistant messages for team "
                    f"{team.codename}, got {len(assistant_msgs)}"
                )
                # Verify sequence numbers are unique and correct
                assert assistant_msgs[0].sequence_no == 2  # bootstrap
                assert assistant_msgs[1].sequence_no == 4  # round 2
