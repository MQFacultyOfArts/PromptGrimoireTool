"""Shared NiceGUI user-simulation helpers for integration tests.

These helpers bridge the gap between NiceGUI's marker-based ``ElementFilter``
and the codebase's ``data-testid`` prop convention.  All three NiceGUI
integration test modules import from here to avoid duplication.

Background
----------
NiceGUI's ``ElementFilter(marker=...)`` checks ``.mark()`` markers, not
``data-testid`` props.  Since this codebase sets ``data-testid`` via
``.props('data-testid="..."')``, we need custom helpers to locate elements
by their ``data-testid`` value.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import TYPE_CHECKING, cast

from nicegui import ElementFilter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui.element import Element
    from nicegui.elements.mixins.value_element import ValueElement
    from nicegui.testing.user import User


# ---------------------------------------------------------------------------
# Wait helpers
# ---------------------------------------------------------------------------


async def wait_for[T](
    condition: Callable[[], T | Awaitable[T]],
    timeout: float = 5.0,
    interval: float = 0.05,
) -> T:
    """Wait for condition to be truthy."""
    start = time.monotonic()
    is_async = inspect.iscoroutinefunction(condition)
    while True:
        _res = condition()
        if is_async:
            result = await cast("Awaitable[T]", _res)
        else:
            result = cast("T", _res)

        if result:
            return result
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Condition not met within {timeout}s")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Dialog-context helper
# ---------------------------------------------------------------------------


def _is_visible_element(el: Element) -> bool:
    """Return True if *el* should be included in query results.

    Returns False only when *el* lives inside a ``ui.dialog`` that is
    currently closed.  Elements not inside any dialog are always visible.
    """
    from nicegui import ui

    parent = el.parent_slot.parent if el.parent_slot else None
    while parent is not None:
        if isinstance(parent, ui.dialog):
            return parent.value  # True when open
        parent = parent.parent_slot.parent if parent.parent_slot else None
    return True  # Not inside a dialog — always "visible"


# ---------------------------------------------------------------------------
# Element lookup helpers
# ---------------------------------------------------------------------------


def _find_by_testid(user: User, testid: str) -> Element | None:
    """Return the first element whose ``data-testid`` prop matches *testid*.

    Skips elements inside closed dialogs so that hidden dialog content does
    not interfere with assertions made on the active page.
    """
    with user:
        for el in ElementFilter():
            if not el.visible:
                continue
            if el.props.get("data-testid") != testid:
                continue
            if not _is_visible_element(el):
                continue
            return el
    return None


def _find_all_by_testid(user: User, testid: str) -> list[Element]:
    """Return all visible elements whose ``data-testid`` prop matches *testid*.

    Skips elements inside closed dialogs so that hidden dialog content does
    not interfere with assertions made on the active page.

    Extracted here to avoid duplication across the three characterisation
    test modules (test_annotation_cards_charac.py, test_organise_charac.py,
    test_respond_charac.py). See: phase_01.md Task 3-5 (multi-doc-tabs-186).
    """
    results: list[Element] = []
    with user:
        for el in ElementFilter():
            if not el.visible:
                continue
            if el.props.get("data-testid") != testid:
                continue
            if not _is_visible_element(el):
                continue
            results.append(el)
    return results


def _find_value_element_by_testid(user: User, testid: str) -> ValueElement | None:
    """Return the first ``ValueElement`` whose ``data-testid`` matches *testid*.

    Same as ``_find_by_testid`` but returns a ``ValueElement`` so that
    ``.value`` is accessible without additional casts in the caller.
    """
    el = _find_by_testid(user, testid)
    if el is None:
        return None
    return cast("ValueElement", el)


# ---------------------------------------------------------------------------
# Annotation page readiness gate
# ---------------------------------------------------------------------------


async def wait_for_annotation_load(
    user: User,
    *,
    timeout: float = 15.0,
) -> None:
    """Wait for the annotation page's deferred background load to finish.

    The annotation page returns a spinner immediately and loads content
    via ``background_tasks.create()``.  NiceGUI's ``user.open()``
    returns before the background task completes.

    Polls for a hidden ``data-testid="annotation-ready"`` marker element
    that ``_load_workspace_content`` creates on both success and error
    paths.  This is deterministic — no timeout guessing.

    Args:
        user: NiceGUI test user.
        timeout: Maximum seconds to wait.
    """
    await wait_for(
        lambda: _find_by_testid(user, "annotation-ready") is not None,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


async def _should_see_testid(user: User, testid: str, *, retries: int = 10) -> None:
    """Assert that a visible element with the given ``data-testid`` exists.

    Polls up to *retries* times with a 100 ms delay between attempts.
    The default of 10 retries (1 s total) is intentionally generous because
    the annotation page and tag-management dialog involve multiple async
    refreshable rebuilds; 5 retries proved flaky for those paths.
    """
    for _ in range(retries):
        if _find_by_testid(user, testid) is not None:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"expected to see an element with data-testid={testid!r}")


async def _should_not_see_testid(user: User, testid: str, *, retries: int = 5) -> None:
    """Assert that no visible element with the given ``data-testid`` exists."""
    for _ in range(retries):
        if _find_by_testid(user, testid) is None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected NOT to see an element with data-testid={testid!r}")


# ---------------------------------------------------------------------------
# Interaction helpers
# ---------------------------------------------------------------------------


def _click_testid(user: User, testid: str) -> None:
    """Click the first visible element matching ``data-testid``.

    Mirrors NiceGUI's ``UserInteraction.click()`` logic: for checkboxes
    and switches the event args carry the toggled boolean value; for all
    other elements args is ``None``.

    TODO(2026-03): Replace with public API when NiceGUI exposes a click()
    method that works outside the User.find() marker-based lookup.  We use
    the same pattern as NiceGUI's UserInteraction.click() internally.
    See: https://github.com/zauberzeug/nicegui/issues/XXXX
    """
    from nicegui import events, ui

    el = _find_by_testid(user, testid)
    if el is None:
        raise AssertionError(
            f"cannot click: no visible element with data-testid={testid!r}"
        )

    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        # Switches/checkboxes need the toggled value as args
        if isinstance(el, (ui.checkbox, ui.switch)):
            args: bool | None = not cast("ValueElement", el).value
        else:
            args = None
        event_arguments = events.GenericEventArguments(
            sender=el, client=el.client, args=args
        )
        events.handle_event(listener.handler, event_arguments)


def _set_input_value(user: User, testid: str, value: str) -> None:
    """Set the value of an input element found by ``data-testid``."""
    el = _find_value_element_by_testid(user, testid)
    if el is None:
        raise AssertionError(
            f"cannot set value: no visible element with data-testid={testid!r}"
        )
    el.value = value


def _fire_event_listeners(el: Element, event_name: str) -> None:
    """Fire all event listeners matching *event_name* on *el*.

    NiceGUI stores listeners keyed by ``f'{element_id}:{event_name}'``
    (or similar).  We iterate all listeners and match by the event
    name suffix, then invoke the handler with a generic event.

    Useful for simulating ``change`` or ``blur`` events on input elements
    that save on user interaction rather than on explicit button press.

    NOTE: For async handlers, use ``_fire_event_listeners_async`` instead
    — this function schedules them as background tasks which may not
    complete before subsequent assertions.
    """
    from nicegui import events

    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        # Listener type is the event name (e.g. "change", "blur")
        if listener.type != event_name:
            continue
        event_arguments = events.GenericEventArguments(
            sender=el, client=el.client, args=None
        )
        events.handle_event(listener.handler, event_arguments)


async def _fire_event_listeners_async(el: Element, event_name: str) -> None:
    """Fire and await all event listeners matching *event_name*.

    Unlike ``_fire_event_listeners``, this directly awaits async
    handlers so their side-effects (DB writes, CRDT updates) are
    guaranteed complete before the caller continues.
    """
    import inspect
    import logging

    from nicegui import events, helpers

    log = logging.getLogger(__name__)
    fired = 0
    for listener in el._event_listeners.values():
        if listener.element_id != el.id:
            continue
        if listener.type != event_name:
            continue
        event_arguments = events.GenericEventArguments(
            sender=el, client=el.client, args=None
        )
        handler = listener.handler
        if handler is None:
            continue
        fired += 1
        if helpers.expects_arguments(handler):
            result = handler(event_arguments)
        else:
            result = handler()
        if inspect.isawaitable(result):
            log.debug("awaiting async handler %s", handler)
            await result
            log.debug("async handler completed")
    log.debug(
        "fired %d listener(s) for %s on %s",
        fired,
        event_name,
        type(el).__name__,
    )
