"""Tests for event-carried selection in tag application (#502).

``selection_made`` and the tag-apply event are dispatched as concurrent
tasks by python-socketio, so the apply could be processed before its
selection arrived and read missing or stale ``state.selection_*``.
The fix makes every tag-application path carry the selection offsets
captured client-side at trigger time (the value-capture idiom from
``ui_helpers``): ``_add_highlight`` reads the event payload only and
never the server-side selection state.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.test_add_highlight_timeout import (
    _JS_PATCH,
    _LOOKUP_PATCH,
    _PM_PATCH,
    _PUSH_PATCH,
    _make_state,
)

_NOTIFY_PATCH = "promptgrimoire.pages.annotation.highlights.ui.notify"


def _patches() -> tuple:
    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()
    return (
        patch(_PM_PATCH, return_value=mock_pm),
        patch(_JS_PATCH),
        patch(_PUSH_PATCH),
        patch(_LOOKUP_PATCH, return_value=""),
    )


@pytest.mark.asyncio
async def test_payload_offsets_used_when_state_has_none() -> None:
    """The regression: apply delivered before selection_made still works.

    Server-side selection state is empty (the ``selection_made`` event
    has not been processed yet), but the apply event carries the offsets
    captured in the browser at click time.  Exactly one highlight must be
    created at those offsets.
    """
    state = _make_state()
    state.selection_start = None
    state.selection_end = None

    pm, js, push, lookup = _patches()
    with pm, js, push, lookup:
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag", {"start_char": 10, "end_char": 50})

    add_mock = cast("MagicMock", state.crdt_doc).add_highlight
    assert add_mock.call_count == 1, "exactly one highlight expected"
    kwargs = add_mock.call_args.kwargs
    assert kwargs["start_char"] == 10
    assert kwargs["end_char"] == 50


@pytest.mark.asyncio
async def test_none_payload_rejected_even_with_stale_state() -> None:
    """A payload-less apply is 'No selection' — stale state is never read."""
    state = _make_state(selection_start=10, selection_end=50)

    with patch(_NOTIFY_PATCH) as notify:
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag", None)

    cast("MagicMock", state.crdt_doc).add_highlight.assert_not_called()
    notify.assert_called_once()
    assert "No selection" in notify.call_args.args[0]


@pytest.mark.asyncio
async def test_reversed_payload_normalised() -> None:
    """Backwards drag (end before start) is normalised to start < end."""
    state = _make_state()

    pm, js, push, lookup = _patches()
    with pm, js, push, lookup:
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag", {"start_char": 50, "end_char": 10})

    kwargs = cast("MagicMock", state.crdt_doc).add_highlight.call_args.kwargs
    assert kwargs["start_char"] == 10
    assert kwargs["end_char"] == 50


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"start_char": 10, "end_char": 10},  # collapsed selection
        {"start_char": "10", "end_char": 50},  # non-int from client
        {"end_char": 50},  # missing key
        {},
        "not-a-dict",
    ],
)
async def test_invalid_payload_rejected(payload: object) -> None:
    """Malformed or empty payloads notify instead of creating a highlight."""
    state = _make_state()

    with patch(_NOTIFY_PATCH) as notify:
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag", cast("Any", payload))

    cast("MagicMock", state.crdt_doc).add_highlight.assert_not_called()
    notify.assert_called_once()


@pytest.mark.asyncio
async def test_keydown_passes_selection_payload() -> None:
    """The keyboard path carries the selection from its own event args."""
    state = _make_state()
    tag = MagicMock()
    tag.raw_key = "tag-key-1"
    state.tag_info_list = [tag]

    event = MagicMock()
    event.args = {"key": "1", "selection": {"start_char": 3, "end_char": 9}}

    with patch(
        "promptgrimoire.pages.annotation.document._add_highlight",
        new_callable=AsyncMock,
    ) as add:
        from promptgrimoire.pages.annotation.document import _handle_keydown

        await _handle_keydown(state, event)

    add.assert_awaited_once_with(state, "tag-key-1", {"start_char": 3, "end_char": 9})
