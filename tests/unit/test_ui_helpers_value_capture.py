"""Behavioural tests for the multi-field value-capture helper.

``on_submit_with_values`` is the multi-input counterpart of
``on_submit_with_value`` (docs/design-plans/
2026-03-11-value-capture-hardening.md § "Additional Considerations").
These tests drive the public API with duck-typed elements and assert
the handler-facing contract: what the Python handler receives for
well-formed, missing, and malformed client payloads, and that the
client-side reader is wired for every configured field.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from promptgrimoire.ui_helpers import on_submit_with_values

if TYPE_CHECKING:
    from collections.abc import Mapping

    from nicegui import ui


class _FakeElement(SimpleNamespace):
    """Stands in for a NiceGUI element: records the .on() wiring."""

    def __init__(self, html_id: str) -> None:
        super().__init__(html_id=html_id)
        self.wired: dict[str, Any] = {}

    def on(self, event: str, handler: Any, js_handler: str | None = None) -> None:
        self.wired = {"event": event, "handler": handler, "js_handler": js_handler}


def _wire(
    inputs: dict[str, _FakeElement],
) -> tuple[_FakeElement, list[dict[str, str]]]:
    """Wire a fake trigger and return it plus the handler's call log."""
    trigger = _FakeElement("trigger-1")
    received: list[dict[str, str]] = []
    # The helper touches only .html_id and .on(); the fakes satisfy
    # that contract structurally, so the cast is a test-double shim.
    on_submit_with_values(
        cast("ui.element", trigger),
        cast("Mapping[str, ui.element]", inputs),
        received.append,
    )
    return trigger, received


def _fire(trigger: _FakeElement, args: Any) -> None:
    """Invoke the wired async handler with a fake event."""
    event = SimpleNamespace(args=args)
    asyncio.run(trigger.wired["handler"](event))


def test_handler_receives_captured_values_by_key() -> None:
    trigger, received = _wire(
        {"title": _FakeElement("f1"), "week_number": _FakeElement("f2")}
    )

    _fire(trigger, {"title": "Marking Week", "week_number": "3"})

    assert received == [{"title": "Marking Week", "week_number": "3"}]


def test_missing_and_malformed_fields_capture_as_empty_string() -> None:
    trigger, received = _wire(
        {"title": _FakeElement("f1"), "description": _FakeElement("f2")}
    )

    # Client sent one key missing and one non-string value.
    _fire(trigger, {"description": 7})

    assert received == [{"title": "", "description": ""}]


def test_non_dict_payload_captures_all_fields_empty() -> None:
    trigger, received = _wire({"email": _FakeElement("f1")})

    _fire(trigger, "not-a-dict")

    assert received == [{"email": ""}]


def test_unknown_client_keys_are_dropped() -> None:
    trigger, received = _wire({"title": _FakeElement("f1")})

    _fire(trigger, {"title": "ok", "injected": "surprise"})

    assert received == [{"title": "ok"}]


def test_async_handler_is_awaited() -> None:
    trigger = _FakeElement("trigger-1")
    received: list[dict[str, str]] = []

    async def handler(values: dict[str, str]) -> None:
        await asyncio.sleep(0)
        received.append(values)

    on_submit_with_values(
        cast("ui.element", trigger),
        cast("Mapping[str, ui.element]", {"title": _FakeElement("f1")}),
        handler,
    )

    _fire(trigger, {"title": "async ok"})

    assert received == [{"title": "async ok"}]


def test_js_reader_covers_every_configured_field() -> None:
    """The client-side capture must read each field's element id.

    A field whose id never appears in the js_handler could not be
    captured at event time — its value would silently fall back to
    the racy server-side read this helper exists to remove.
    """
    trigger, _ = _wire(
        {"code": _FakeElement("id-code"), "semester": _FakeElement("id-sem")}
    )

    js = trigger.wired["js_handler"]
    assert trigger.wired["event"] == "click"
    assert "id-code" in js
    assert "id-sem" in js
    assert "emit(" in js
