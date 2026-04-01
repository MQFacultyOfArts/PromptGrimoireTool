"""Go/no-go spike: validate NiceGUI custom Vue component wiring.

Validates 5 go/no-go criteria for the AnnotationSidebar component:

1. Component registration — element creation succeeds, JS file resolves
2. Python props arrive — items prop is set on the element
3. Vue emits reach Python — event handler fires (server-side validation)
4. Prop updates — set_items() updates the prop
5. DOM data-* attributes — verified via prop inspection (Vue rendering
   requires browser; full DOM validation deferred to E2E)

NiceGUI user simulation runs server-side only — Vue templates are not
rendered.  This test validates Python-side wiring.  Criteria 2 and 5
(Vue-rendered DOM) need Playwright for full validation.

NOTE: The plan specifies ``_should_see_testid`` and ``_find_all_by_testid``
for verifying rendered annotation cards.  These helpers search NiceGUI's
Python element tree, but Vue-rendered children (the ``v-for`` divs with
``data-testid="annotation-card"``) only exist in the browser's Vue
virtual DOM.  ``user_simulation`` has no Vue runtime, so those helpers
would return zero results.  Vue rendering is verified by Phase 4+ browser
tests and Phase 10's cross-tab E2E tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from nicegui import events, ui

from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar

from .nicegui_helpers import _find_by_testid

pytestmark = [pytest.mark.nicegui_ui, pytest.mark.asyncio]


def _register_spike_page() -> None:
    """Register the spike test page inside user_simulation context."""

    @ui.page("/spike-test")
    def _spike_page() -> None:
        sidebar = AnnotationSidebar(items=[{"id": "h1"}, {"id": "h2"}])
        sidebar.props('data-testid="spike-sidebar"')


@pytest.mark.asyncio
async def test_go1_component_registration(nicegui_user: Any) -> None:
    """GO1: Component registration works — page loads without error."""
    _register_spike_page()
    await nicegui_user.open("/spike-test")

    el = _find_by_testid(nicegui_user, "spike-sidebar")
    assert el is not None, "AnnotationSidebar not found in element tree"
    assert isinstance(el, AnnotationSidebar)


@pytest.mark.asyncio
async def test_go2_props_set_on_element(nicegui_user: Any) -> None:
    """GO2 (partial): items prop set correctly on the Python element.

    Validates the Python side of prop delivery.  Vue rendering of these
    props is unverified until Phase 4 browser tests.
    """
    _register_spike_page()
    await nicegui_user.open("/spike-test")

    el = _find_by_testid(nicegui_user, "spike-sidebar")
    assert el is not None
    items = el._props.get("items")
    assert items == [{"id": "h1"}, {"id": "h2"}], f"Expected 2 items, got {items}"


@pytest.mark.asyncio
async def test_go3_event_listener_registered_and_fires(nicegui_user: Any) -> None:
    """GO3 (partial): test_event listener is registered and fires correctly.

    Validates that ``self.on("test_event", ...)`` registers a listener
    under the correct key and that the callback receives the payload.
    Full Vue ``$emit`` -> Python validation requires a browser.
    """
    received: list[dict[str, Any]] = []

    @ui.page("/spike-event-test")
    def _event_page() -> None:
        AnnotationSidebar(
            items=[{"id": "h1"}],
            on_test_event=received.append,
        ).props('data-testid="spike-event-sidebar"')

    await nicegui_user.open("/spike-event-test")

    el = _find_by_testid(nicegui_user, "spike-event-sidebar")
    assert el is not None

    # Verify listener exists with correct type
    has_listener = any(
        ev.type == "test_event" and ev.element_id == el.id
        for ev in el._event_listeners.values()
    )
    assert has_listener, "no test_event listener registered on element"

    # Fire the listener directly
    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        if listener.type != "test_event":
            continue
        event_args = events.GenericEventArguments(
            sender=el, client=el.client, args={"id": "h1"}
        )
        events.handle_event(listener.handler, event_args)

    assert len(received) == 1, f"Expected 1 event, got {len(received)}"
    assert received[0] == {"id": "h1"}, f"Expected {{id: h1}}, got {received[0]}"


@pytest.mark.asyncio
async def test_go4_prop_dict_updated(nicegui_user: Any) -> None:
    """GO4 (partial): set_items() updates the Python prop dict.

    Validates that ``set_items()`` writes to ``_props["items"]`` and
    calls ``update()``.  Vue re-rendering is unverified until Phase 4.
    """
    _register_spike_page()
    await nicegui_user.open("/spike-test")

    el = _find_by_testid(nicegui_user, "spike-sidebar")
    assert el is not None
    assert isinstance(el, AnnotationSidebar)

    # Initial state
    assert len(el._props["items"]) == 2

    # Update
    el.set_items([{"id": "h3"}])
    assert el._props["items"] == [{"id": "h3"}], "set_items() did not update prop"


@pytest.mark.asyncio
async def test_go5_js_file_exists() -> None:
    """GO5: JS component file exists at the resolved path."""
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    assert _JS_PATH.exists(), f"JS file not found at {_JS_PATH}"
    content = _JS_PATH.read_text()
    assert "data-testid" in content, "JS template missing data-testid attributes"
    assert "data-highlight-id" in content, "JS template missing data-highlight-id"
    assert "test_event" in content, "JS template missing test_event emit"


@pytest.mark.asyncio
async def test_composition_api_hybrid_in_js() -> None:
    """Verify the JS file uses Composition API hybrid pattern.

    Structural check: the JS source contains setup(), ref, and watch —
    the Composition API features the design requires. Whether they
    actually work in Vue is validated by browser testing.
    """
    from promptgrimoire.pages.annotation.sidebar import _JS_PATH

    content = _JS_PATH.read_text()
    assert "setup(props)" in content, "Missing Composition API setup()"
    assert "ref(" in content, "Missing Composition API ref()"
    assert "watch(" in content, "Missing Composition API watch()"
