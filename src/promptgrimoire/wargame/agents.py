"""PydanticAI agent definitions for the wargame turn cycle.

Two module-level agent singletons:

- ``turn_agent`` generates draft assistant responses and updated game state
  from cadet orders + prior game state.
- ``summary_agent`` produces student-safe situation summaries from approved
  assistant responses.

Both use ``anthropic:claude-sonnet-4-6``. Tests override via
``agent.override(model=TestModel(...))``.

This module diverges from the direct ``ClaudeClient`` used for roleplay.
PydanticAI provides structured output validation and message history
serialisation needed by the wargame turn cycle.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent

__all__ = [
    "StudentSummary",
    "TurnResult",
    "summary_agent",
    "turn_agent",
]

_MODEL = "anthropic:claude-sonnet-4-6"


class TurnResult(BaseModel):
    """Structured output from the turn agent.

    Attributes
    ----------
    response_text:
        Draft message for the team (may include XML projection tags).
        Reviewed by GM before publication.
    game_state:
        Updated GM-only game state artifact. Injected into the next
        turn's prompt; not visible to students.
    """

    response_text: str
    game_state: str


class StudentSummary(BaseModel):
    """Structured output from the summary agent.

    Attributes
    ----------
    summary:
        Student-facing situation update. Must contain only information
        safe for students to see.
    """

    summary: str


turn_agent = Agent(
    _MODEL,
    output_type=TurnResult,
    defer_model_check=True,
)

summary_agent = Agent(
    _MODEL,
    output_type=StudentSummary,
    defer_model_check=True,
)
