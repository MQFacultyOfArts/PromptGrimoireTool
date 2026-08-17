"""NiceGUI-free annotation functional core.

Pure data structures and transformations shared between the NiceGUI
annotation page and standalone processes (the snapshot delivery worker).
Relocated from ``pages/annotation/`` because that package's ``__init__``
imports NiceGUI at module level; standalone workers follow the
export-worker discipline of never importing NiceGUI
(``tests/unit/test_annotation_core.py`` guards this).

The original modules (``pages.annotation.tags``,
``pages.annotation.items_serialise``, ``pages.annotation.card_shared``)
re-export these names, so page-side callers are unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from promptgrimoire.auth.anonymise import anonymise_author

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument

_TEXT_PREVIEW_LIMIT = 80
_DEFAULT_COLOUR = "#999999"
_RECOVERED_TAG_LABEL = "⚠ recovered"


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

    def _sort_key(item: tuple[str, dict]) -> tuple[float, int]:
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


def author_initials(name: str) -> str:
    """Derive compact initials from a display name.

    Splits on whitespace and hyphens, takes first char of each segment,
    joins with dots.  "Brian Ballsun-Stanton" -> "B.B.S.", "Ada" -> "A."
    """
    segments = re.split(r"[\s\-]+", name)
    return ".".join(s[0].upper() for s in segments if s) + "."


def group_highlights_by_tag(
    highlights: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group highlight dicts by tag into the ``applyHighlights()`` shape.

    ``{tag: [{start_char, end_char, id}, ...], ...}`` — highlights with no
    tag fall into the ``"highlight"`` bucket.
    """
    by_tag: dict[str, list[dict[str, Any]]] = {}
    for hl in highlights:
        tag = hl.get("tag", "highlight")
        entry = {
            "start_char": int(hl.get("start_char", 0)),
            "end_char": int(hl.get("end_char", 0)),
            "id": hl.get("id", ""),
        }
        by_tag.setdefault(tag, []).append(entry)
    return by_tag


def serialise_items(
    highlights: list[dict[str, Any]],
    tag_info_map: dict[str, TagInfo],
    tag_colours: dict[str, str],
    user_id: str | None,
    viewer_is_privileged: bool,
    privileged_user_ids: frozenset[str],
    can_annotate: bool,
    anonymous_sharing: bool,
) -> list[dict[str, Any]]:
    """Transform CRDT highlight dicts into Vue sidebar item dicts.

    Parameters
    ----------
    highlights:
        Raw highlight dicts from the CRDT annotation document.
    tag_info_map:
        Mapping of tag UUID -> TagInfo for display metadata.
    tag_colours:
        Mapping of tag UUID -> hex colour string.
    user_id:
        The viewing user's Stytch user ID, or None if unauthenticated.
    viewer_is_privileged:
        Whether the viewer is an instructor or admin.
    privileged_user_ids:
        Set of user IDs that are instructors or admins.
    can_annotate:
        Whether the viewer has annotation permission.
    anonymous_sharing:
        Whether anonymisation is enabled for this workspace.

    Returns
    -------
    list[dict[str, Any]]
        Flat list of item dicts ready for the Vue sidebar component.
    """
    items: list[dict[str, Any]] = []
    for hl in highlights:
        tag_key: str = hl["tag"]
        tag_info = tag_info_map.get(tag_key)
        tag_display = tag_info.name if tag_info is not None else _RECOVERED_TAG_LABEL
        colour = tag_colours.get(tag_key, _DEFAULT_COLOUR)

        hl_user_id: str | None = hl.get("user_id")
        raw_author: str = hl["author"]

        display_author = anonymise_author(
            author=raw_author,
            user_id=hl_user_id,
            viewing_user_id=user_id,
            anonymous_sharing=anonymous_sharing,
            viewer_is_privileged=viewer_is_privileged,
            author_is_privileged=(
                hl_user_id is not None and hl_user_id in privileged_user_ids
            ),
        )
        initials = author_initials(display_author)

        can_delete_hl = viewer_is_privileged or (
            user_id is not None and hl_user_id == user_id
        )

        text: str = hl["text"]
        text_preview = (
            text[:_TEXT_PREVIEW_LIMIT] + "..."
            if len(text) > _TEXT_PREVIEW_LIMIT
            else text
        )

        comments = _serialise_comments(
            hl.get("comments", []),
            user_id=user_id,
            viewer_is_privileged=viewer_is_privileged,
            privileged_user_ids=privileged_user_ids,
            anonymous_sharing=anonymous_sharing,
        )

        items.append(
            {
                "id": hl["id"],
                "tag_key": tag_key,
                "tag_display": tag_display,
                "color": colour,
                "start_char": hl["start_char"],
                "end_char": hl["end_char"],
                "para_ref": hl.get("para_ref", ""),
                "author": raw_author,
                "display_author": display_author,
                "initials": initials,
                "user_id": hl_user_id,
                "can_delete": can_delete_hl,
                "can_annotate": can_annotate,
                "text": text,
                "text_preview": text_preview,
                "comments": comments,
            }
        )
    return items


def _serialise_comments(
    comments: list[dict[str, Any]],
    *,
    user_id: str | None,
    viewer_is_privileged: bool,
    privileged_user_ids: frozenset[str],
    anonymous_sharing: bool,
) -> list[dict[str, Any]]:
    """Serialise and sort comment dicts for a single highlight."""
    sorted_comments = sorted(comments, key=lambda c: c["created_at"])
    result: list[dict[str, Any]] = []
    for c in sorted_comments:
        c_user_id: str | None = c.get("user_id")
        c_author: str = c["author"]

        c_display_author = anonymise_author(
            author=c_author,
            user_id=c_user_id,
            viewing_user_id=user_id,
            anonymous_sharing=anonymous_sharing,
            viewer_is_privileged=viewer_is_privileged,
            author_is_privileged=(
                c_user_id is not None and c_user_id in privileged_user_ids
            ),
        )

        can_delete_c = viewer_is_privileged or (
            user_id is not None and c_user_id == user_id
        )

        result.append(
            {
                "id": c["id"],
                "author": c_author,
                "display_author": c_display_author,
                "text": c["text"],
                "created_at": c["created_at"],
                "can_delete": can_delete_c,
            }
        )
    return result
