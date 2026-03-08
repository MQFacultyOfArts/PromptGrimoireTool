"""Pure-domain helpers for wargame team management."""

from promptgrimoire.wargame.codenames import generate_codename
from promptgrimoire.wargame.roster import (
    RosterEntry,
    RosterParseError,
    auto_assign_teams,
    parse_roster,
)

__all__ = [
    "RosterEntry",
    "RosterParseError",
    "auto_assign_teams",
    "generate_codename",
    "parse_roster",
]
