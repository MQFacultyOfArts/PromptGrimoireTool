"""Prop data contract tests for AnnotationSidebar Vue component.

NiceGUI ``user_simulation`` runs server-side only -- Vue templates are not
rendered, so we cannot inspect Vue-rendered DOM elements.  These tests
validate the **prop data contract**: that the ``AnnotationSidebar``
element's ``_props`` contain the correct data for the Vue template to
render.  The Vue template's use of these props for ``data-testid``
attributes is verified structurally (by reading the JS source).
"""

from __future__ import annotations

from typing import Any

import pytest
from nicegui import ui

from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar
from promptgrimoire.pages.annotation.tags import TagInfo

from .nicegui_helpers import _find_by_testid

pytestmark = [pytest.mark.nicegui_ui, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Fixtures / shared data
# ---------------------------------------------------------------------------

TAG_MAP: dict[str, TagInfo] = {
    "tag-1": TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="tag-1"),
    "tag-2": TagInfo(name="Legal Issues", colour="#ff7f0e", raw_key="tag-2"),
}
TAG_COLOURS: dict[str, str] = {"tag-1": "#1f77b4", "tag-2": "#ff7f0e"}

_HIGHLIGHTS: list[dict[str, Any]] = [
    {
        "id": "hl-1",
        "start_char": 10,
        "end_char": 50,
        "tag": "tag-1",
        "text": "some highlighted text",
        "author": "Alice",
        "user_id": "viewer-user",
        "para_ref": "[3]",
        "created_at": "2026-03-01T10:00:00",
        "comments": [
            {
                "id": "c-1",
                "author": "Bob",
                "user_id": "user-bob",
                "text": "Good",
                "created_at": "2026-03-01T11:00:00",
            },
            {
                "id": "c-2",
                "author": "Carol",
                "user_id": "user-carol",
                "text": "Agreed",
                "created_at": "2026-03-01T10:30:00",
            },
        ],
    },
    {
        "id": "hl-2",
        "start_char": 60,
        "end_char": 90,
        "tag": "tag-2",
        "text": "another passage",
        "author": "Dave",
        "user_id": "user-dave",
        "para_ref": "",
        "created_at": "2026-03-01T12:00:00",
        "comments": [],
    },
    {
        "id": "hl-3",
        "start_char": 100,
        "end_char": 120,
        "tag": "tag-unknown",
        "text": "recovered text",
        "author": "Eve",
        "user_id": "user-eve",
        "para_ref": "",
        "created_at": "2026-03-01T13:00:00",
        "comments": [],
    },
]


def _make_page(highlights: list[dict[str, Any]] | None = None) -> None:
    """Register a test page that creates a sidebar with refresh_items().

    Called per-test because ``nicegui_user`` resets the NiceGUI app
    between tests — module-level ``@ui.page`` is cleared by
    ``user_simulation``.  Each call registers against a fresh app.
    """

    @ui.page("/dom-contract-test")
    def _page() -> None:
        sidebar = AnnotationSidebar()
        sidebar.props('data-testid="contract-sidebar"')
        sidebar.refresh_items(
            highlights=highlights or _HIGHLIGHTS,
            tag_info_map=TAG_MAP,
            tag_colours=TAG_COLOURS,
            user_id="viewer-user",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )


# ---------------------------------------------------------------------------
# AC2.1 -- Items have correct DOM-contract fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_items_have_dom_contract_fields(nicegui_user: Any) -> None:
    """Items contain id, start_char, end_char, tag_display, color for Vue template."""
    _make_page()
    await nicegui_user.open("/dom-contract-test")

    el = _find_by_testid(nicegui_user, "contract-sidebar")
    assert el is not None, "sidebar not found"
    items = el._props["items"]
    assert len(items) == 3

    hl1 = items[0]
    assert hl1["id"] == "hl-1"
    assert hl1["start_char"] == 10
    assert hl1["end_char"] == 50
    assert hl1["tag_display"] == "Jurisdiction"
    assert hl1["color"] == "#1f77b4"

    hl2 = items[1]
    assert hl2["id"] == "hl-2"
    assert hl2["start_char"] == 60
    assert hl2["end_char"] == 90
    assert hl2["tag_display"] == "Legal Issues"
    assert hl2["color"] == "#ff7f0e"


# ---------------------------------------------------------------------------
# AC2.2 -- Detail section data present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_items_have_detail_section_fields(nicegui_user: Any) -> None:
    """Items contain comments, text_preview, can_annotate, can_delete."""
    _make_page()
    await nicegui_user.open("/dom-contract-test")

    el = _find_by_testid(nicegui_user, "contract-sidebar")
    assert el is not None
    items = el._props["items"]

    hl1 = items[0]
    assert "comments" in hl1
    assert "text_preview" in hl1
    assert hl1["can_annotate"] is True
    # viewer-user owns hl-1, so can_delete should be True
    assert hl1["can_delete"] is True

    hl2 = items[1]
    # viewer-user does NOT own hl-2 and is not privileged
    assert hl2["can_delete"] is False


# ---------------------------------------------------------------------------
# Comment badge data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_badge_data(nicegui_user: Any) -> None:
    """Item with 2 comments has length-2 list; item with 0 has empty list."""
    _make_page()
    await nicegui_user.open("/dom-contract-test")

    el = _find_by_testid(nicegui_user, "contract-sidebar")
    assert el is not None
    items = el._props["items"]

    # hl-1 has 2 comments
    assert len(items[0]["comments"]) == 2
    # comments should be sorted by created_at
    assert items[0]["comments"][0]["id"] == "c-2"  # 10:30 < 11:00
    assert items[0]["comments"][1]["id"] == "c-1"

    # hl-2 has no comments
    assert items[1]["comments"] == []


# ---------------------------------------------------------------------------
# Para ref data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_para_ref_data(nicegui_user: Any) -> None:
    """Item with para_ref '[3]' has it present; item without has empty string."""
    _make_page()
    await nicegui_user.open("/dom-contract-test")

    el = _find_by_testid(nicegui_user, "contract-sidebar")
    assert el is not None
    items = el._props["items"]

    assert items[0]["para_ref"] == "[3]"
    assert items[1]["para_ref"] == ""


# ---------------------------------------------------------------------------
# Tag recovery data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_recovery_data(nicegui_user: Any) -> None:
    """Item with unknown tag_key gets recovered label and default colour."""
    _make_page()
    await nicegui_user.open("/dom-contract-test")

    el = _find_by_testid(nicegui_user, "contract-sidebar")
    assert el is not None
    items = el._props["items"]

    # hl-3 uses "tag-unknown" which is not in TAG_MAP
    hl3 = items[2]
    assert hl3["tag_display"] == "\u26a0 recovered"
    assert hl3["color"] == "#999999"


# ---------------------------------------------------------------------------
# JS template structural check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_template_has_required_testids() -> None:
    """Vue template contains all required data-testid attributes."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()

    required_testids = [
        "annotation-card",
        "card-detail",
        "tag-select",
        "comment-input",
        "post-comment-btn",
        "comment-count",
    ]
    for testid in required_testids:
        assert f'data-testid="{testid}"' in content, (
            f'Vue template missing data-testid="{testid}"'
        )
