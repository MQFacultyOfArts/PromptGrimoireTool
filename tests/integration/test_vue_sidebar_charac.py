"""Characterisation tests for Vue sidebar serialisation behaviour.

These tests replace the deleted ``test_annotation_cards_charac.py`` which
inspected NiceGUI card elements built by the now-deleted ``cards.py``.
Equivalent coverage is provided by asserting on the output of
``serialise_items()`` — the functional core that feeds the Vue sidebar.

Tests 1-8 are pure (no NiceGUI).  Test 9 exercises ``refresh_from_state``
and requires the ``nicegui_ui`` marker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from promptgrimoire.pages.annotation.items_serialise import serialise_items
from promptgrimoire.pages.annotation.tags import TagInfo

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TAG_A = TagInfo(name="Issue", colour="#1f77b4", raw_key="tag-a")
_TAG_B = TagInfo(name="Ratio", colour="#ff7f0e", raw_key="tag-b")

_TAG_INFO_MAP: dict[str, TagInfo] = {"tag-a": _TAG_A, "tag-b": _TAG_B}
_TAG_COLOURS: dict[str, str] = {"tag-a": "#1f77b4", "tag-b": "#ff7f0e"}

_COMMON: dict[str, Any] = {
    "tag_info_map": _TAG_INFO_MAP,
    "tag_colours": _TAG_COLOURS,
    "user_id": "u-alice",
    "viewer_is_privileged": False,
    "privileged_user_ids": frozenset(),
    "can_annotate": True,
    "anonymous_sharing": False,
}


def _hl(
    *,
    hl_id: str = "hl-1",
    start_char: int = 10,
    end_char: int = 50,
    tag: str = "tag-a",
    text: str = "some highlighted text",
    author: str = "Alice",
    user_id: str = "u-alice",
    para_ref: str = "[3]",
    comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": hl_id,
        "start_char": start_char,
        "end_char": end_char,
        "tag": tag,
        "text": text,
        "author": author,
        "user_id": user_id,
        "para_ref": para_ref,
        "created_at": "2026-03-01T10:00:00",
        "comments": comments or [],
    }


def _comment(
    *,
    cid: str = "c-1",
    author: str = "Bob",
    user_id: str = "u-bob",
    text: str = "Good point",
    created_at: str = "2026-03-01T11:00:00",
) -> dict[str, Any]:
    return {
        "id": cid,
        "author": author,
        "user_id": user_id,
        "text": text,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# 1. Sort order by start_char
# ---------------------------------------------------------------------------


def test_items_preserve_start_char_values() -> None:
    """serialise_items preserves start_char for client-side sorting."""
    highlights = [
        _hl(hl_id="hl-c", start_char=100, end_char=120),
        _hl(hl_id="hl-a", start_char=0, end_char=20),
        _hl(hl_id="hl-b", start_char=50, end_char=70),
    ]
    result = serialise_items(highlights, **_COMMON)
    # Vue component sorts by start_char client-side; serialisation
    # preserves input order but must include start_char for sorting.
    chars = [(r["id"], r["start_char"]) for r in result]
    assert ("hl-c", 100) in chars
    assert ("hl-a", 0) in chars
    assert ("hl-b", 50) in chars


# ---------------------------------------------------------------------------
# 2. Add highlight → new item appears
# ---------------------------------------------------------------------------


def test_add_highlight_produces_new_item() -> None:
    """A new highlight dict added to the list appears in the next serialise."""
    base = [_hl(hl_id="hl-1", start_char=0, end_char=10)]
    result_before = serialise_items(base, **_COMMON)
    assert len(result_before) == 1

    updated = [*base, _hl(hl_id="hl-2", start_char=20, end_char=30)]
    result_after = serialise_items(updated, **_COMMON)
    assert len(result_after) == 2
    ids = {item["id"] for item in result_after}
    assert "hl-1" in ids
    assert "hl-2" in ids


# ---------------------------------------------------------------------------
# 3. Remove highlight → item gone
# ---------------------------------------------------------------------------


def test_remove_highlight_removes_item() -> None:
    """Removing a highlight from the list removes it from serialise output."""
    highlights = [
        _hl(hl_id="hl-1", start_char=0, end_char=10),
        _hl(hl_id="hl-2", start_char=20, end_char=30),
    ]
    result_full = serialise_items(highlights, **_COMMON)
    assert len(result_full) == 2

    result_reduced = serialise_items([highlights[0]], **_COMMON)
    assert len(result_reduced) == 1
    assert result_reduced[0]["id"] == "hl-1"


# ---------------------------------------------------------------------------
# 4. Tag change updates colour and display name
# ---------------------------------------------------------------------------


def test_tag_change_updates_colour_and_display() -> None:
    """Changing a highlight's tag key updates color and tag_display."""
    original = [_hl(hl_id="hl-1", tag="tag-a")]
    result_a = serialise_items(original, **_COMMON)
    assert result_a[0]["color"] == "#1f77b4"
    assert result_a[0]["tag_display"] == "Issue"

    changed = [_hl(hl_id="hl-1", tag="tag-b")]
    result_b = serialise_items(changed, **_COMMON)
    assert result_b[0]["color"] == "#ff7f0e"
    assert result_b[0]["tag_display"] == "Ratio"


# ---------------------------------------------------------------------------
# 5. Comment addition increments comment count
# ---------------------------------------------------------------------------


def test_comment_addition_increments_count() -> None:
    """Adding a comment to a highlight's list grows the comments output."""
    no_comments = [_hl(hl_id="hl-1", comments=[])]
    result_0 = serialise_items(no_comments, **_COMMON)
    assert len(result_0[0]["comments"]) == 0

    with_comment = [_hl(hl_id="hl-1", comments=[_comment()])]
    result_1 = serialise_items(with_comment, **_COMMON)
    assert len(result_1[0]["comments"]) == 1
    assert result_1[0]["comments"][0]["text"] == "Good point"


# ---------------------------------------------------------------------------
# 6. Rapid successive adds — all appear
# ---------------------------------------------------------------------------


def test_rapid_successive_adds_consistent() -> None:
    """Five highlights added in rapid succession all appear in output."""
    highlights = [
        _hl(hl_id=f"hl-{i}", start_char=i * 10, end_char=i * 10 + 5) for i in range(5)
    ]
    result = serialise_items(highlights, **_COMMON)
    assert len(result) == 5
    result_ids = {item["id"] for item in result}
    assert result_ids == {f"hl-{i}" for i in range(5)}


# ---------------------------------------------------------------------------
# 7. Add then immediately remove — net zero
# ---------------------------------------------------------------------------


def test_rapid_add_then_remove() -> None:
    """Adding then removing a highlight yields net zero change."""
    base = [_hl(hl_id="hl-1")]
    after_add = [*base, _hl(hl_id="hl-temp", start_char=200, end_char=210)]
    after_remove = [h for h in after_add if h["id"] != "hl-temp"]

    result = serialise_items(after_remove, **_COMMON)
    assert len(result) == 1
    assert result[0]["id"] == "hl-1"


# ---------------------------------------------------------------------------
# 8. Rapid tag changes reflect final value
# ---------------------------------------------------------------------------


def test_rapid_tag_changes_reflect_final() -> None:
    """After three successive tag changes, the final tag value is used."""
    # Simulate three successive states: tag-a → tag-b → tag-a
    state_1 = [_hl(hl_id="hl-1", tag="tag-a")]
    state_2 = [_hl(hl_id="hl-1", tag="tag-b")]
    state_3 = [_hl(hl_id="hl-1", tag="tag-a")]

    for state, expected_display, expected_color in [
        (state_1, "Issue", "#1f77b4"),
        (state_2, "Ratio", "#ff7f0e"),
        (state_3, "Issue", "#1f77b4"),
    ]:
        result = serialise_items(state, **_COMMON)
        assert result[0]["tag_display"] == expected_display
        assert result[0]["color"] == expected_color


# ---------------------------------------------------------------------------
# 9. refresh_from_state pushes items prop to sidebar
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
@pytest.mark.asyncio
async def test_invalidate_then_refresh_pushes_props(nicegui_user: Any) -> None:
    """refresh_from_state serialises highlights and updates items prop."""
    from nicegui import ui

    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar

    from .nicegui_helpers import _find_by_testid

    highlights = [
        _hl(hl_id="hl-x", start_char=0, end_char=20, tag="tag-a"),
    ]

    # Minimal crdt_doc mock: returns our highlight list
    mock_crdt = MagicMock()
    mock_crdt.get_highlights_for_document.return_value = highlights
    mock_crdt.get_all_highlights.return_value = highlights

    sidebar_ref: list[AnnotationSidebar] = []

    @ui.page("/charac-refresh-test")
    def _page() -> None:
        sidebar = AnnotationSidebar(
            items=[],
            tag_options={},
            permissions={"can_annotate": True},
        )
        sidebar.props('data-testid="charac-sidebar"')
        sidebar_ref.append(sidebar)

    await nicegui_user.open("/charac-refresh-test")
    el = _find_by_testid(nicegui_user, "charac-sidebar")
    assert el is not None
    assert el._props["items"] == []

    # Build a minimal PageState and call refresh_from_state
    state = PageState(
        workspace_id=UUID("00000000-0000-0000-0000-000000000001"),
        document_id=UUID("00000000-0000-0000-0000-000000000002"),
        effective_permission="peer",
        user_id="u-alice",
        crdt_doc=mock_crdt,
        tag_info_list=[_TAG_A, _TAG_B],
    )

    with nicegui_user:
        sidebar_ref[0].refresh_from_state(state)

    items = sidebar_ref[0]._props["items"]
    assert len(items) == 1
    assert items[0]["id"] == "hl-x"
    assert items[0]["tag_display"] == "Issue"
    assert items[0]["color"] == "#1f77b4"
