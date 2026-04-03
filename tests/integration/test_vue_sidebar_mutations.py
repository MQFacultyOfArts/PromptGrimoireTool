"""Integration tests for Vue sidebar CRDT mutation events and permissions.

NiceGUI ``user_simulation`` runs server-side only — Vue templates are not
rendered.  These tests validate:

1. Events: mutation event handlers are registered and fire with correct payloads
2. Permissions: edit controls gated on can_annotate, delete buttons on can_delete
3. Structural: JS template wires all mutation events, comment draft pattern

All tests validate the Python-side event wiring.  Vue rendering of the
mutation effects (card disappears, comment appears, colour changes) is
verified by Phase 10 cross-tab E2E tests.
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
        "para_ref": "",
        "display_author": "Alice",
        "initials": "A",
        "user_id": "u1",
        "can_delete": True,
        "can_annotate": True,
        "text": "some text",
        "text_preview": "some text",
        "comments": [
            {
                "id": "c1",
                "display_author": "Alice",
                "text": "Good point",
                "created_at": "2026-01-01",
                "can_delete": True,
            },
        ],
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
# AC1.4 — Tag change event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_tag_event_fires(nicegui_user: Any) -> None:
    """change_tag event fires with {id, new_tag} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/mutation-tag-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            tag_options={"tag-a": "Issue", "tag-b": "Ratio"},
            permissions={"can_annotate": True},
            on_change_tag=received.append,
        ).props('data-testid="mut-sidebar"')

    await nicegui_user.open("/mutation-tag-test")
    el = _find_by_testid(nicegui_user, "mut-sidebar")
    assert el is not None

    _fire_event(el, "change_tag", {"id": "hl-1", "new_tag": "tag-b"})
    assert len(received) == 1
    assert received[0] == {"id": "hl-1", "new_tag": "tag-b"}


# ---------------------------------------------------------------------------
# AC1.5 — Comment submit event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_comment_event_fires(nicegui_user: Any) -> None:
    """submit_comment event fires with {id, text} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/mutation-comment-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_submit_comment=received.append,
        ).props('data-testid="mut-sidebar"')

    await nicegui_user.open("/mutation-comment-test")
    el = _find_by_testid(nicegui_user, "mut-sidebar")
    assert el is not None
    assert _has_listener(el, "submit_comment")

    _fire_event(el, "submit_comment", {"id": "hl-1", "text": "New comment"})
    assert len(received) == 1
    assert received[0] == {"id": "hl-1", "text": "New comment"}


# ---------------------------------------------------------------------------
# AC1.6 — Comment delete event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_comment_event_fires(nicegui_user: Any) -> None:
    """delete_comment event fires with {highlight_id, comment_id} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/mutation-delcomment-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_delete_comment=received.append,
        ).props('data-testid="mut-sidebar"')

    await nicegui_user.open("/mutation-delcomment-test")
    el = _find_by_testid(nicegui_user, "mut-sidebar")
    assert el is not None

    _fire_event(el, "delete_comment", {"highlight_id": "hl-1", "comment_id": "c1"})
    assert len(received) == 1
    assert received[0] == {"highlight_id": "hl-1", "comment_id": "c1"}


# ---------------------------------------------------------------------------
# AC1.7 — Highlight delete event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_highlight_event_fires(nicegui_user: Any) -> None:
    """delete_highlight event fires with {id} payload."""
    received: list[dict[str, Any]] = []

    @ui.page("/mutation-delhl-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
            on_delete_highlight=received.append,
        ).props('data-testid="mut-sidebar"')

    await nicegui_user.open("/mutation-delhl-test")
    el = _find_by_testid(nicegui_user, "mut-sidebar")
    assert el is not None

    _fire_event(el, "delete_highlight", {"id": "hl-1"})
    assert len(received) == 1
    assert received[0] == {"id": "hl-1"}


# ---------------------------------------------------------------------------
# AC4.1/AC4.2 — Permission gating (structural)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permissions_prop_can_annotate(nicegui_user: Any) -> None:
    """permissions.can_annotate is correctly forwarded to the component."""

    @ui.page("/perm-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": True},
        ).props('data-testid="perm-sidebar"')

    await nicegui_user.open("/perm-test")
    el = _find_by_testid(nicegui_user, "perm-sidebar")
    assert el is not None
    assert el._props["permissions"]["can_annotate"] is True


@pytest.mark.asyncio
async def test_permissions_prop_viewer(nicegui_user: Any) -> None:
    """permissions.can_annotate=False is correctly forwarded."""

    @ui.page("/perm-viewer-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": False},
        ).props('data-testid="perm-sidebar"')

    await nicegui_user.open("/perm-viewer-test")
    el = _find_by_testid(nicegui_user, "perm-sidebar")
    assert el is not None
    assert el._props["permissions"]["can_annotate"] is False


# ---------------------------------------------------------------------------
# AC4.3 — Delete button gating (data contract)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_delete_in_items(nicegui_user: Any) -> None:
    """can_delete flag is present in item data for Vue template gating."""

    @ui.page("/del-gate-test")
    def _page() -> None:
        AnnotationSidebar(items=_ITEMS).props('data-testid="del-sidebar"')

    await nicegui_user.open("/del-gate-test")
    el = _find_by_testid(nicegui_user, "del-sidebar")
    assert el is not None
    items = el._props["items"]
    assert items[0]["can_delete"] is True  # owner
    assert items[1]["can_delete"] is False  # not owner


# ---------------------------------------------------------------------------
# AC4.4 — Unauthorized delete_highlight event still emits (server rejects)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_highlight_emits_unconditionally(nicegui_user: Any) -> None:
    """delete_highlight event fires even for items with can_delete=False.

    The Vue emit is unconditional — server-side auth is the call site's
    responsibility (check can_delete before mutating CRDT). This test
    verifies the event contract: the Python handler receives the payload
    regardless of client-side gating, so server-side guards are mandatory.
    AC4.4 server-side rejection is verified at the call site level in
    Phase 9-10 integration, not in this UI-component test.
    """
    received: list[dict[str, Any]] = []

    @ui.page("/ac44-test")
    def _page() -> None:
        AnnotationSidebar(
            items=_ITEMS,
            permissions={"can_annotate": False},
            on_delete_highlight=received.append,
        ).props('data-testid="ac44-sidebar"')

    await nicegui_user.open("/ac44-test")
    el = _find_by_testid(nicegui_user, "ac44-sidebar")
    assert el is not None

    # Fire delete_highlight for hl-2 (can_delete=False) — simulates crafted event
    _fire_event(el, "delete_highlight", {"id": "hl-2"})
    assert len(received) == 1, "Event must arrive at handler for server-side rejection"
    assert received[0] == {"id": "hl-2"}


# ---------------------------------------------------------------------------
# AC1.11 — Empty comment rejection (structural, client-side only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_empty_comment_guard() -> None:
    """onSubmitComment guards against empty/whitespace text client-side.

    The actual guard (trim + early return) runs in Vue and cannot be
    exercised in NiceGUI user_simulation. This structural check confirms
    the guard exists. Full behavioural validation requires a Playwright
    E2E test (Phase 10).
    """
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()
    # The guard pattern: trim then check for empty
    assert ".trim()" in content, "onSubmitComment must trim whitespace"
    assert "if (!text)" in content, "onSubmitComment must reject empty text"


# ---------------------------------------------------------------------------
# Structural: JS template has all mutation events wired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_has_mutation_events() -> None:
    """Vue component defines all mutation event emits and handlers."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()

    for event in ["change_tag", "submit_comment", "delete_comment", "delete_highlight"]:
        assert event in content, f"Missing event: {event}"

    # Comment draft pattern
    assert "commentDrafts" in content, "Missing commentDrafts reactive Map"
    assert "onSubmitComment" in content, "Missing onSubmitComment handler"
    assert "onDeleteComment" in content, "Missing onDeleteComment handler"
    assert "onTagChange" in content, "Missing onTagChange handler"
    assert "onDeleteHighlight" in content, "Missing onDeleteHighlight handler"
    # Highlight delete button uses @click.stop to prevent expand toggle
    assert "@click.stop" in content, "Delete buttons must use @click.stop"


@pytest.mark.asyncio
async def test_js_comment_delete_button_gated() -> None:
    """Vue template gates comment delete button on comment.can_delete."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()
    assert "comment.can_delete" in content, (
        "Comment delete button must be gated on comment.can_delete"
    )
    assert 'data-testid="comment-delete"' in content, (
        "Comment delete button must have data-testid"
    )
