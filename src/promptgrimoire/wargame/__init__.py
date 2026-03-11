"""Pure-domain helpers for wargame team management."""

from promptgrimoire.wargame.agents import (
    StudentSummary,
    TurnResult,
    summary_agent,
    turn_agent,
)
from promptgrimoire.wargame.codenames import generate_codename
from promptgrimoire.wargame.roster import (
    RosterEntry,
    RosterParseError,
    auto_assign_teams,
    parse_roster,
)
from promptgrimoire.wargame.turn_cycle import (
    NO_MOVE_SENTINEL,
    build_summary_prompt,
    build_turn_prompt,
    calculate_deadline,
    expand_bootstrap,
    extract_move_text,
    render_prompt,
)

__all__ = [
    "NO_MOVE_SENTINEL",
    "RosterEntry",
    "RosterParseError",
    "StudentSummary",
    "TurnResult",
    "auto_assign_teams",
    "build_summary_prompt",
    "build_turn_prompt",
    "calculate_deadline",
    "expand_bootstrap",
    "extract_move_text",
    "generate_codename",
    "parse_roster",
    "render_prompt",
    "summary_agent",
    "turn_agent",
]
