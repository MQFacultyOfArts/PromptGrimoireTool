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

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui  # noqa: TC002 — used at runtime (html_id, .on())
from nicegui.events import GenericEventArguments  # noqa: TC002 — used at runtime

logger = logging.getLogger(__name__)


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

    trigger.on(event, _handle, js_handler=js)
