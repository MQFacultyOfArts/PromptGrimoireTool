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

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument


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
    description: str | None = None


def workspace_tags_from_crdt(crdt_doc: AnnotationDocument) -> list[TagInfo]:
    """Build TagInfo list from CRDT maps instead of DB.

    Returns TagInfo instances ordered by group order_index then tag
    order_index, matching the same ordering as workspace_tags().
    """
    groups = crdt_doc.list_tag_groups()
    tags = crdt_doc.list_tags()

    if not tags:
        return []

    max_order = float("inf")

    def _sort_key(item: tuple[str, dict]) -> tuple[float, int]:  # type: ignore[type-arg]
        _tag_id, tag_data = item
        group_id = tag_data.get("group_id")
        grp = groups.get(group_id) if group_id else None
        group_order: float = grp["order_index"] if grp else max_order
        return (group_order, tag_data["order_index"])

    sorted_items = sorted(tags.items(), key=_sort_key)

    result: list[TagInfo] = []
    for tag_id, tag_data in sorted_items:
        group_id = tag_data.get("group_id")
        grp = groups.get(group_id) if group_id else None
        result.append(
            TagInfo(
                name=tag_data["name"],
                colour=tag_data["colour"],
                raw_key=tag_id,
                group_name=grp["name"] if grp else None,
                group_colour=grp["colour"] if grp else None,
                description=tag_data.get("description"),
            )
        )
    return result


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

    # Sort by (group order_index, tag order_index) so the flat list
    # matches toolbar display order.  Ungrouped tags sort last.
    max_order = float("inf")

    def _sort_key(tag: object) -> tuple[float, int]:
        # tag is always a Tag SQLModel instance; typed as object to satisfy
        # sorted()'s homogeneous key-callable signature without a runtime import.
        grp = group_map.get(tag.group_id) if tag.group_id else None  # type: ignore[attr-defined]  -- see above
        return (grp.order_index if grp else max_order, tag.order_index)  # type: ignore[attr-defined, return-value]  -- see above

    sorted_tags = sorted(tags, key=_sort_key)

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
            description=tag.description,
        )
        for tag in sorted_tags
    ]
