"""Integration tests for Vue sidebar para_ref edit, locate, and hover interactions.

NiceGUI ``user_simulation`` runs server-side only — Vue templates are not
rendered.  These tests validate:

1. AC1.8: Para_ref click-to-edit event wiring (edit_para_ref emitted with payload)
2. AC1.9: Locate button event wiring (locate_highlight emitted with char offsets)
3. AC1.10: Hover event handlers wired on card elements (mouseenter/mouseleave)

Vue rendering of the visual effects (scroll, throb, CSS highlights) is verified
by human UAT (CSS Highlight API is not DOM-observable).
"""

from __future__ import annotations

from typing import Any

import pytest
from nicegui import events, ui

from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar

from .nicegui_helpers import _find_by_testid

pytestmark = [pytest.mark.nicegui_ui, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_ITEMS: list[dict[str, Any]] = [
    {
        "id": "hl-1",
        "tag_key": "tag-a",
        "tag_display": "Issue",
        "color": "#1f77b4",
        "start_char": 0,
        "end_char": 10,
        "para_ref": "¶3",
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
        "comments": [],
    },
]


def _fire_event(el: Any, event_name: str, payload: dict[str, Any]) -> None:
    """Simulate a Vue event arriving at the Python element."""
    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        if listener.type != event_name:
            continue
        event_args = events.GenericEventArguments(
            sender=el, client=el.client, args=payload
        )
        events.handle_event(listener.handler, event_args)


def _has_listener(el: Any, event_name: str) -> bool:
    """Check if the element has a listener for the given event name."""
    return any(
        ev.type == event_name and ev.element_id == el.id
        for ev in el._event_listeners.values()
    )


# ---------------------------------------------------------------------------
# AC1.8 — Para_ref click-to-edit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_para_ref_event_fires(nicegui_user: Any) -> None:
    """edit_para_ref event fires with {id, value} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/interaction-para-ref-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_edit_para_ref=received.append,
        ).props('data-testid="int-sidebar"')

    await nicegui_user.open("/interaction-para-ref-test")
    el = _find_by_testid(nicegui_user, "int-sidebar")
    assert el is not None
    assert _has_listener(el, "edit_para_ref")

    _fire_event(el, "edit_para_ref", {"id": "hl-1", "value": "¶5"})
    assert len(received) == 1
    assert received[0] == {"id": "hl-1", "value": "¶5"}


@pytest.mark.asyncio
async def test_edit_para_ref_python_handler_always_fires(nicegui_user: Any) -> None:
    """Python handler fires for any edit_para_ref event, even same value.

    The no-change guard lives in the Vue component's ``finishParaRefEdit``
    (client-side). Python handler fires regardless — CRDT dedup is server-side.
    """
    received: list[dict[str, Any]] = []

    @ui.page("/interaction-para-ref-noop")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_edit_para_ref=received.append,
        ).props('data-testid="int-sidebar"')

    await nicegui_user.open("/interaction-para-ref-noop")
    el = _find_by_testid(nicegui_user, "int-sidebar")
    assert el is not None

    # Fire with same value as existing — handler should still fire at Python
    # level (the no-change guard is in Vue JS, not Python)
    _fire_event(el, "edit_para_ref", {"id": "hl-1", "value": "¶3"})
    assert len(received) == 1  # Python handler fires regardless


@pytest.mark.asyncio
async def test_edit_para_ref_not_wired_without_handler(nicegui_user: Any) -> None:
    """No edit_para_ref listener when no handler callback provided."""

    @ui.page("/interaction-para-ref-no-handler")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
        ).props('data-testid="int-sidebar"')

    await nicegui_user.open("/interaction-para-ref-no-handler")
    el = _find_by_testid(nicegui_user, "int-sidebar")
    assert el is not None
    assert not _has_listener(el, "edit_para_ref")


# ---------------------------------------------------------------------------
# AC1.9 — Locate button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_locate_highlight_event_fires(nicegui_user: Any) -> None:
    """locate_highlight event fires with {start_char, end_char} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/interaction-locate-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_locate_highlight=received.append,
        ).props('data-testid="int-sidebar"')

    await nicegui_user.open("/interaction-locate-test")
    el = _find_by_testid(nicegui_user, "int-sidebar")
    assert el is not None
    assert _has_listener(el, "locate_highlight")

    _fire_event(
        el,
        "locate_highlight",
        {"start_char": 0, "end_char": 10},
    )
    assert len(received) == 1
    assert received[0] == {"start_char": 0, "end_char": 10}


@pytest.mark.asyncio
async def test_locate_highlight_second_item(nicegui_user: Any) -> None:
    """locate_highlight works for different items with different offsets."""
    received: list[dict[str, Any]] = []

    @ui.page("/interaction-locate-second")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_locate_highlight=received.append,
        ).props('data-testid="int-sidebar"')

    await nicegui_user.open("/interaction-locate-second")
    el = _find_by_testid(nicegui_user, "int-sidebar")
    assert el is not None

    _fire_event(
        el,
        "locate_highlight",
        {"start_char": 20, "end_char": 40},
    )
    assert len(received) == 1
    assert received[0] == {"start_char": 20, "end_char": 40}


# ---------------------------------------------------------------------------
# AC1.10 — Hover highlight wiring (structural)
# ---------------------------------------------------------------------------


def test_hover_handlers_in_js_template() -> None:
    """Vue template wires mouseenter/mouseleave for hover highlights.

    NiceGUI user simulation doesn't render Vue templates, so we verify
    structurally that the JS source contains the hover event bindings.
    The actual CSS Highlight API rendering requires human UAT.
    """
    import re
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "promptgrimoire"
        / "static"
        / "annotationsidebar.js"
    )
    js_source = js_path.read_text()

    # Template must wire mouseenter to onCardHover
    assert re.search(r"@mouseenter\s*=\s*\"onCardHover\(item\)\"", js_source), (
        'Missing @mouseenter="onCardHover(item)" in template'
    )
    # Template must wire mouseleave to onCardLeave
    assert re.search(r"@mouseleave\s*=\s*\"onCardLeave\(\)\"", js_source), (
        'Missing @mouseleave="onCardLeave()" in template'
    )

    # onCardHover must call showHoverHighlight
    assert "showHoverHighlight" in js_source, (
        "onCardHover does not call showHoverHighlight"
    )
    # onCardLeave must call clearHoverHighlight
    assert "clearHoverHighlight" in js_source, (
        "onCardLeave does not call clearHoverHighlight"
    )


# ---------------------------------------------------------------------------
# Structural: JS template wires locate button and para_ref edit
# ---------------------------------------------------------------------------


def test_locate_button_in_template() -> None:
    """Vue template includes locate button with data-testid."""
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "promptgrimoire"
        / "static"
        / "annotationsidebar.js"
    )
    js_source = js_path.read_text()

    assert 'data-testid="locate-btn"' in js_source, (
        "Missing locate-btn data-testid in template"
    )
    assert "onLocate(item.start_char, item.end_char)" in js_source, (
        "Missing onLocate call in template"
    )


def test_para_ref_edit_in_template() -> None:
    """Vue template includes para_ref display/edit toggle elements."""
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "promptgrimoire"
        / "static"
        / "annotationsidebar.js"
    )
    js_source = js_path.read_text()

    assert 'data-testid="para-ref-label"' in js_source, (
        "Missing para-ref-label data-testid in template"
    )
    assert 'data-testid="para-ref-input"' in js_source, (
        "Missing para-ref-input data-testid in template"
    )
    assert "startParaRefEdit" in js_source, (
        "Missing startParaRefEdit in template/methods"
    )
    assert "finishParaRefEdit" in js_source, (
        "Missing finishParaRefEdit in template/methods"
    )


def test_para_ref_readonly_for_viewer() -> None:
    """Vue template gates para_ref click-to-edit behind permissions.can_annotate.

    Structural check: the template uses v-if="permissions.can_annotate" on the
    clickable para-ref-label and shows a non-clickable span for viewers.
    """
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "promptgrimoire"
        / "static"
        / "annotationsidebar.js"
    )
    js_source = js_path.read_text()

    # Clickable label gated on can_annotate
    assert "!paraRefEditMode.get(item.id) && permissions.can_annotate" in js_source, (
        "Clickable para-ref-label not gated on permissions.can_annotate"
    )
    # Read-only label for viewers
    assert "!permissions.can_annotate && item.para_ref" in js_source, (
        "Read-only para-ref-label not shown for viewers"
    )
