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
from pydantic_ai.output import ToolOutput

__all__ = [
    "TURN_OUTPUT_CONTRACT",
    "StudentSummary",
    "TurnResult",
    "summary_agent",
    "turn_agent",
]

_MODEL = "anthropic:claude-sonnet-4-6"

TURN_OUTPUT_CONTRACT = """\

## Input format

On the first turn you receive the scenario bootstrap text directly.

On subsequent turns you receive:

<game_state>
[The GM-only game state from the previous turn]
</game_state>

<cadet_orders>
[The team's submitted orders for this turn]
</cadet_orders>

## Output contract

You MUST always return BOTH fields via the structured output tool:

- response_text: Your narrative response to the team. This is the draft \
message the GM will review before showing to students.
- game_state: The complete updated GM-only game state artifact. This \
tracks all hidden information (unit positions, NPC states, event \
triggers, resource levels, trackers, etc.). It is injected into your \
next turn's prompt as the <game_state> block. Students never see it. \
On the first turn, create the full initial game state from the scenario. \
On subsequent turns, update it based on the team's orders and your \
narrative response. NEVER omit this field.
"""


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
    output_type=ToolOutput(
        TurnResult,
        description=(
            "Return the GM's draft response to the team's orders "
            "and the updated game state. Both fields are required."
        ),
    ),
    defer_model_check=True,
    retries=3,
)

summary_agent = Agent(
    _MODEL,
    output_type=ToolOutput(
        StudentSummary,
        description=(
            "Return a student-safe situation summary. "
            "Must contain only information safe for students to see."
        ),
    ),
    defer_model_check=True,
    retries=3,
)
