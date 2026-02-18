"""Tag-agnostic abstraction for annotation tag metadata.

Provides TagInfo dataclass and an async DB query to load workspace tags.
This module is the single point of coupling between the DB-backed tag
system and the Tab 2/Tab 3 rendering code, which only receives list[TagInfo].

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_03.md Task 1
- AC: three-tab-ui.AC2.1 (data structure for tag columns)
- Design: docs/implementation-plans/2026-02-18-95-annotation-tags/phase_04.md Task 1
- AC: 95-annotation-tags.AC5.1 (tag toolbar renders from DB-backed tag list)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class TagInfo:
    """Display metadata for an annotation tag.

    Attributes:
        name: Human-readable display name (e.g. "Jurisdiction", "Legal Issues").
        colour: Hex colour string (e.g. "#1f77b4").
        raw_key: Tag UUID as a string for CRDT highlight tag identifiers.
        group_name: Optional group name for toolbar visual grouping.
    """

    name: str
    colour: str
    raw_key: str
    group_name: str | None = None
    group_colour: str | None = None


async def workspace_tags(workspace_id: UUID) -> list[TagInfo]:
    """Load tags for a workspace from the database.

    Returns TagInfo instances ordered by group then order_index, with
    raw_key set to the Tag UUID string for use as CRDT highlight tag
    identifiers.  group_name is populated from the joined TagGroup.
    """
    from promptgrimoire.db.tags import (  # noqa: PLC0415  -- lazy import avoids circular dep
        list_tag_groups_for_workspace,
        list_tags_for_workspace,
    )

    tags = await list_tags_for_workspace(workspace_id)
    groups = await list_tag_groups_for_workspace(workspace_id)
    group_map = {g.id: g for g in groups}

    return [
        TagInfo(
            name=tag.name,
            colour=tag.color,
            raw_key=str(tag.id),
            group_name=group_map[tag.group_id].name
            if tag.group_id in group_map
            else None,
            group_colour=group_map[tag.group_id].color
            if tag.group_id in group_map
            else None,
        )
        for tag in tags
    ]
