"""Integration tests for Vue sidebar expand/collapse and lazy detail.

NiceGUI ``user_simulation`` runs server-side only — Vue templates are not
rendered. These tests validate:

1. Props: ``expanded_ids`` forwarded correctly to the component
2. Events: ``toggle_expand`` event handler fires with correct payload
3. Structural: JS template uses ``v-if`` (lazy build) + ``v-show`` (toggle)
   pattern for detail sections, chevron state toggles

Actual DOM rendering of expanded/collapsed state requires Playwright
browser tests (Phase 10).
"""

from __future__ import annotations

from typing import Any

import pytest
from nicegui import events, ui

from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar

from .nicegui_helpers import _find_by_testid

pytestmark = [pytest.mark.nicegui_ui, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sidebar(
    nicegui_user: Any,  # noqa: ARG001 — triggers app reset
    *,
    expanded_ids: list[str] | None = None,
    on_toggle_expand: Any = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Register a test page with sidebar and return (route, items)."""
    items = [
        {
            "id": "hl-1",
            "tag_key": "tag-a",
            "tag_display": "Issue",
            "color": "#1f77b4",
            "start_char": 0,
            "end_char": 10,
            "para_ref": "[1]",
            "display_author": "Alice",
            "initials": "A",
            "user_id": "u1",
            "can_delete": True,
            "can_annotate": True,
            "text": "some text",
            "text_preview": "some text",
            "comments": [],
        },
        {
            "id": "hl-2",
            "tag_key": "tag-b",
            "tag_display": "Ratio",
            "color": "#ff7f0e",
            "start_char": 20,
            "end_char": 40,
            "para_ref": "",
            "display_author": "Bob",
            "initials": "B",
            "user_id": "u2",
            "can_delete": False,
            "can_annotate": True,
            "text": "other text",
            "text_preview": "other text",
            "comments": [
                {
                    "id": "c1",
                    "display_author": "Carol",
                    "text": "Nice",
                    "created_at": "2026-01-01",
                    "can_delete": False,
                },
            ],
        },
    ]

    route = "/expand-test"

    @ui.page(route)
    def _page() -> None:
        sidebar = AnnotationSidebar(
            items=items,
            tag_options={"tag-a": "Issue", "tag-b": "Ratio"},
            permissions={"can_annotate": True},
            expanded_ids=expanded_ids or [],
            on_toggle_expand=on_toggle_expand,
        )
        sidebar.props('data-testid="expand-sidebar"')

    return route, items


# ---------------------------------------------------------------------------
# AC1.3 — Pre-expanded cards have expanded_ids set in props
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_expanded_ids_prop(nicegui_user: Any) -> None:
    """expanded_ids=['hl-1'] is correctly set in props on load."""
    route, _ = _make_sidebar(nicegui_user, expanded_ids=["hl-1"])
    await nicegui_user.open(route)

    el = _find_by_testid(nicegui_user, "expand-sidebar")
    assert el is not None
    assert el._props["expanded_ids"] == ["hl-1"]


@pytest.mark.asyncio
async def test_empty_expanded_ids_default(nicegui_user: Any) -> None:
    """No expanded_ids means empty list in props."""
    route, _ = _make_sidebar(nicegui_user)
    await nicegui_user.open(route)

    el = _find_by_testid(nicegui_user, "expand-sidebar")
    assert el is not None
    assert el._props["expanded_ids"] == []


# ---------------------------------------------------------------------------
# AC1.1 / AC1.2 — toggle_expand event fires with correct payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_expand_event_registered(nicegui_user: Any) -> None:
    """toggle_expand event listener is registered on the sidebar element."""
    received: list[dict[str, Any]] = []
    route, _ = _make_sidebar(nicegui_user, on_toggle_expand=received.append)
    await nicegui_user.open(route)

    el = _find_by_testid(nicegui_user, "expand-sidebar")
    assert el is not None

    has_listener = any(
        ev.type == "toggle_expand" and ev.element_id == el.id
        for ev in el._event_listeners.values()
    )
    assert has_listener, "no toggle_expand listener registered on element"


@pytest.mark.asyncio
async def test_toggle_expand_callback_receives_payload(nicegui_user: Any) -> None:
    """toggle_expand callback receives {id, expanded} payload."""
    received: list[dict[str, Any]] = []
    route, _ = _make_sidebar(nicegui_user, on_toggle_expand=received.append)
    await nicegui_user.open(route)

    el = _find_by_testid(nicegui_user, "expand-sidebar")
    assert el is not None

    # Simulate the event as it would arrive from Vue
    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        if listener.type != "toggle_expand":
            continue
        event_args = events.GenericEventArguments(
            sender=el, client=el.client, args={"id": "hl-1", "expanded": True}
        )
        events.handle_event(listener.handler, event_args)

    assert len(received) == 1
    assert received[0] == {"id": "hl-1", "expanded": True}


# ---------------------------------------------------------------------------
# Structural: JS template uses lazy detail pattern
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_template_lazy_detail_pattern() -> None:
    """Vue template uses v-if for lazy detail build and v-show for toggle."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()

    # v-if on detailBuiltIds (lazy build — only create DOM on first expand)
    assert "detailBuiltIds.has(item.id)" in content, (
        "Template must use detailBuiltIds.has() for lazy v-if"
    )
    # v-show on expandedIds (toggle visibility without destroying DOM)
    assert "expandedIds.has(item.id)" in content, (
        "Template must use expandedIds.has() for v-show toggle"
    )
    # Chevron toggle
    assert "expand-btn" in content, "Template must have expand-btn data-testid"
    # card-header testid for click target
    assert "card-header" in content, "Template must have card-header data-testid"


@pytest.mark.asyncio
async def test_js_has_toggle_expand_emit() -> None:
    """Vue component emits toggle_expand event on expand/collapse."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()
    assert "toggle_expand" in content, "Component must emit toggle_expand"
    assert "toggleExpand" in content, "Component must define toggleExpand function"
