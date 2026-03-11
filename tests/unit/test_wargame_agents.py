"""Unit tests for PydanticAI wargame agent definitions.

Verifies:
- turn-cycle-296.AC5.1: turn_agent returns structured TurnResult
- turn-cycle-296.AC5.4: summary_agent returns structured StudentSummary
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel
from pydantic_core import to_jsonable_python

from promptgrimoire.wargame.agents import (
    StudentSummary,
    TurnResult,
    summary_agent,
    turn_agent,
)


class TestTurnAgent:
    """Tests for the turn_agent singleton."""

    @pytest.mark.asyncio
    async def test_returns_turn_result(self) -> None:
        """turn-cycle-296.AC5.1: turn_agent returns structured TurnResult."""
        with turn_agent.override(model=TestModel()):
            result = await turn_agent.run("test prompt")
            assert isinstance(result.output, TurnResult)
            assert isinstance(result.output.response_text, str)
            assert isinstance(result.output.game_state, str)

    @pytest.mark.asyncio
    async def test_with_custom_instructions(self) -> None:
        """turn_agent accepts runtime instructions (WargameConfig.system_prompt)."""
        with turn_agent.override(model=TestModel()):
            result = await turn_agent.run(
                "cadet orders here",
                instructions="You are the GM of a wargame scenario.",
            )
            assert isinstance(result.output, TurnResult)

    @pytest.mark.asyncio
    async def test_message_history_round_trip(self) -> None:
        """Message history can be serialised and restored for multi-turn calls."""
        with turn_agent.override(model=TestModel()):
            result1 = await turn_agent.run("first turn orders")
            history = result1.all_messages()

            # Serialise via pydantic_core
            serialised = to_jsonable_python(history)
            assert isinstance(serialised, list)

            # Deserialise via ModelMessagesTypeAdapter
            restored = ModelMessagesTypeAdapter.validate_python(serialised)

            # Second call with restored history succeeds
            result2 = await turn_agent.run(
                "second turn orders", message_history=restored
            )
            assert isinstance(result2.output, TurnResult)


class TestSummaryAgent:
    """Tests for the summary_agent singleton."""

    @pytest.mark.asyncio
    async def test_returns_student_summary(self) -> None:
        """turn-cycle-296.AC5.4: summary_agent returns structured StudentSummary."""
        with summary_agent.override(model=TestModel()):
            result = await summary_agent.run("summarise the situation")
            assert isinstance(result.output, StudentSummary)
            assert isinstance(result.output.summary, str)

    @pytest.mark.asyncio
    async def test_with_custom_instructions(self) -> None:
        """summary_agent accepts runtime instructions (summary_system_prompt)."""
        with summary_agent.override(model=TestModel()):
            result = await summary_agent.run(
                "assistant response to summarise",
                instructions="Produce only student-safe information.",
            )
            assert isinstance(result.output, StudentSummary)


class TestOutputTypes:
    """Tests for output type structure."""

    def test_turn_result_fields(self) -> None:
        """TurnResult has exactly the expected string fields."""
        tr = TurnResult(response_text="response", game_state="state")
        assert tr.response_text == "response"
        assert tr.game_state == "state"

    def test_student_summary_fields(self) -> None:
        """StudentSummary has exactly the expected string field."""
        ss = StudentSummary(summary="situation update")
        assert ss.summary == "situation update"
