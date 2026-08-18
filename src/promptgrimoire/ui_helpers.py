"""UI helpers for NiceGUI event handling.

Provides safe patterns for reading input values in event handlers,
working around a race condition where python-socketio's concurrent
event dispatch (``async_handlers=True``) can cause a button click
handler to read a sibling input's ``.value`` before the value-update
event has been processed.

See ``docs/design-plans/2026-03-11-value-capture-hardening.md``
for the full investigation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import structlog
from nicegui import ui  # noqa: TC002 — used at runtime (html_id, .on())
from nicegui.events import GenericEventArguments  # noqa: TC002 — used at runtime

logger = structlog.get_logger()


def _build_field_read_js(html_id: str) -> str:
    """JS expression reading one native input/textarea value by id.

    Evaluates to the field's current DOM string, or '' when the
    element (or its native field) is missing — the same loud-empty
    contract as ``on_submit_with_value``.
    """
    return (
        f"(() => {{"
        f"const el = document.getElementById('{html_id}');"
        f"if(!el){{return '';}}"
        f"const t = el.tagName.toLowerCase();"
        f"const f = (t==='input'||t==='textarea')"
        f"? el : el.querySelector('input,textarea');"
        f"return f ? f.value : '';"
        f"}})()"
    )


def _build_multi_capture_js(ids_by_key: Mapping[str, str]) -> str:
    """JS handler emitting ``{key: value}`` for the given field ids."""
    pairs = ",".join(
        f"{key!r}: {_build_field_read_js(html_id)}"
        for key, html_id in ids_by_key.items()
    )
    return f"() => {{emit({{{pairs}}});}}"


def on_submit_with_value(
    trigger: ui.element,
    input_el: ui.input,
    handler: Callable[[str], Any],
    *,
    event: str = "click",
) -> None:
    """Wire an event on *trigger* to call *handler* with
    *input_el*'s DOM value captured client-side.

    This avoids a server-side race where the value-update and
    click events are dispatched as concurrent asyncio tasks
    (python-socketio ``async_handlers=True``), so reading
    ``input_el.value`` in the handler may return stale data.

    The value is read from the DOM at event time via a
    ``js_handler`` and passed as ``e.args`` to the Python
    handler.

    Args:
        trigger: The element whose event fires the handler
            (e.g. a ``ui.button`` for click, or the input
            itself for ``keydown.enter``).
        input_el: The ``ui.input`` (or ``ui.textarea``) whose
            value to capture.
        handler: Called with the captured value string. May be
            sync or async.
        event: The event type (default ``"click"``).
    """
    # Build JS that reads the native field value.
    # NiceGUI puts html_id directly on the native <input>,
    # not a wrapper div, so getElementById returns the input
    # itself.  Fall back to querySelector for safety.
    hid = input_el.html_id
    js = (
        f"() => {{"
        f"const el = document.getElementById('{hid}');"
        f"if(!el){{emit('');return;}}"
        f"const t = el.tagName.toLowerCase();"
        f"const f = (t==='input'||t==='textarea')"
        f"? el : el.querySelector('input,textarea');"
        f"emit(f ? f.value : '');"
        f"}}"
    )

    async def _handle(e: GenericEventArguments) -> None:
        value = e.args if isinstance(e.args, str) else ""
        result = handler(value)
        if isinstance(result, Awaitable):
            await result

    # Simulation hook: NiceGUI's testing User cannot run the js_handler,
    # so simulated clicks (tests/integration/nicegui_helpers.py) read this
    # to emit what the browser-side capture would have sent.
    setattr(trigger, "_value_capture_inputs", input_el)  # noqa: B010 -- dynamic simulation-hook attribute
    trigger.on(event, _handle, js_handler=js)


def on_click_with_selection(
    trigger: ui.element,
    selection_state: Any,
    handler: Callable[[dict[str, Any] | None], Any],
    *,
    event: str = "click",
) -> None:
    """Wire an event on *trigger* to call *handler* with the browser's
    current annotation selection captured client-side at event time.

    The selection-capture counterpart of ``on_submit_with_value``: the
    payload is ``window._annotSel`` — written by
    ``setupAnnotationSelection()`` on mouseup (annotation-highlight.js)
    and cleared alongside ``selection_cleared`` — so the offsets ride
    the triggering event itself instead of racing the separate
    ``selection_made`` socket event (#502).

    Args:
        trigger: The element whose event fires the handler
            (e.g. a tag button).
        selection_state: Object carrying ``selection_start`` /
            ``selection_end`` (the annotation ``PageState``) — used only
            by the User-harness simulation hook, never by the live
            handler.
        handler: Called with ``{"start_char": int, "end_char": int}``
            or ``None`` when the browser had no selection.  May be sync
            or async.
        event: The event type (default ``"click"``).
    """
    js = "() => {emit(window._annotSel || null);}"

    async def _handle(e: GenericEventArguments) -> None:
        sel = e.args if isinstance(e.args, dict) else None
        result = handler(sel)
        if isinstance(result, Awaitable):
            await result

    # Simulation hook — see on_submit_with_value.  The harness emits the
    # server-side selection state, which in the User harness is exactly
    # what the browser-side capture would hold.
    setattr(trigger, "_value_capture_selection", selection_state)  # noqa: B010 -- dynamic simulation-hook attribute
    trigger.on(event, _handle, js_handler=js)


def on_submit_with_values(
    trigger: ui.element,
    inputs: Mapping[str, ui.element],
    handler: Callable[[dict[str, str]], Any],
    *,
    event: str = "click",
) -> None:
    """Wire an event on *trigger* to call *handler* with every input's
    DOM value captured client-side, keyed as in *inputs*.

    The multi-field counterpart of ``on_submit_with_value`` — the
    design doc's § "Additional Considerations" sketch for forms whose
    submit reads several fields (week/activity/course create and edit
    forms).  Each value is read from the DOM at event time, so no
    field read races the click's server-side dispatch.

    Args:
        trigger: The element whose event fires the handler.
        inputs: Mapping of handler-facing key to the ``ui.input`` /
            ``ui.textarea`` / ``ui.number`` element to capture.
        handler: Called with ``{key: captured_string}``.  Missing DOM
            fields capture as ``""``, mirroring the single-value
            helper's loud-empty contract.  May be sync or async.
        event: The event type (default ``"click"``).
    """
    js = _build_multi_capture_js({key: el.html_id for key, el in inputs.items()})

    async def _handle(e: GenericEventArguments) -> None:
        raw = e.args if isinstance(e.args, dict) else {}
        values = {
            key: v if isinstance(v := raw.get(key), str) else "" for key in inputs
        }
        result = handler(values)
        if isinstance(result, Awaitable):
            await result

    # Simulation hook — see on_submit_with_value.
    setattr(trigger, "_value_capture_inputs", dict(inputs))  # noqa: B010 -- dynamic simulation-hook attribute
    trigger.on(event, _handle, js_handler=js)
