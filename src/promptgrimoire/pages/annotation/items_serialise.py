"""Pure serialisation of CRDT highlights into Vue sidebar item dicts.

Functional core -- no NiceGUI imports, no side effects.  Transforms
raw highlight data from the CRDT layer into the flat list of dicts
consumed by the Vue annotation sidebar component.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.pages.annotation.card_shared import author_initials

if TYPE_CHECKING:
    from promptgrimoire.pages.annotation.tags import TagInfo

_TEXT_PREVIEW_LIMIT = 80
_DEFAULT_COLOUR = "#999999"
_RECOVERED_TAG_LABEL = "\u26a0 recovered"


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
