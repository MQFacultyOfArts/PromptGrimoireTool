"""Pure-domain helpers for wargame team management."""

from promptgrimoire.wargame.codenames import generate_codename
from promptgrimoire.wargame.roster import (
    RosterEntry,
    RosterParseError,
    parse_roster,
)

__all__ = [
    "RosterEntry",
    "RosterParseError",
    "generate_codename",
    "parse_roster",
]
