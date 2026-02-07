"""Tag-agnostic abstraction for annotation tag metadata.

Provides TagInfo dataclass and a mapper from BriefTag enum to TagInfo list.
This module is the single point of coupling between BriefTag (domain model)
and the Tab 2/Tab 3 rendering code, which only receives list[TagInfo].

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 1
- AC: three-tab-ui.AC2.1 (data structure for tag columns)
"""

from __future__ import annotations

from dataclasses import dataclass

from promptgrimoire.models.case import TAG_COLORS, BriefTag


@dataclass(frozen=True, slots=True)
class TagInfo:
    """Display metadata for an annotation tag.

    Attributes:
        name: Human-readable display name (e.g. "Jurisdiction", "Legal Issues").
        colour: Hex colour string (e.g. "#1f77b4").
        raw_key: The raw enum value as a string (e.g. "jurisdiction"). Derived from
                 name.lower().replace(" ", "_") for CRDT lookups and tag_order calls.
    """

    name: str
    colour: str
    raw_key: str


def brief_tags_to_tag_info() -> list[TagInfo]:
    """Convert BriefTag enum members to a list of TagInfo instances.

    Iterates BriefTag in declaration order, producing display names via
    ``tag.value.replace("_", " ").title()`` and colours from TAG_COLORS.
    The raw_key is the enum value (lowercase underscore-delimited).

    Returns:
        List of TagInfo in enum declaration order, one per BriefTag member.
    """
    return [
        TagInfo(
            name=tag.value.replace("_", " ").title(),
            colour=TAG_COLORS[tag],
            raw_key=tag.value,
        )
        for tag in BriefTag
    ]
