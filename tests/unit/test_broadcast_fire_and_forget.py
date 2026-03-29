"""Test that broadcast functions are synchronous fire-and-forget.

Verifies eliminate-js-await-454.AC1.1 through AC1.5:
- AC1.1: Cursor broadcast is synchronous (no event loop blocking)
- AC1.2: Selection broadcast is synchronous
- AC1.3: Cursor/selection removal on client delete is fire-and-forget
- AC1.4: A disconnected/slow client does not block broadcasts to others
- AC1.5: A non-responding client doesn't cause timeout exceptions

Traceability: Issue #454
"""

from __future__ import annotations

import contextlib
import inspect
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from promptgrimoire.pages.annotation import (
    PageState,
    _RemotePresence,
    _workspace_presence,
)

_TEST_UUID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def _clean_presence():
    """Ensure _workspace_presence is clean before/after each test."""
    _workspace_presence.clear()
    yield
    _workspace_presence.clear()


def _make_state(*, client_id: str = "sender") -> PageState:
    """Create a minimal PageState for testing."""
    state = PageState(workspace_id=_TEST_UUID)
    state.client_id = client_id
    state.user_name = "Test User"
    state.user_id = "user-1"
    state.user_color = "#ff0000"
    state.doc_container_id = "doc-container-1"
    state.is_anonymous = False
    state.viewer_is_privileged = False
    return state


def _make_presence(
    *,
    client: MagicMock | None = None,
    deleted: bool = False,
    has_milkdown_editor: bool = False,
) -> _RemotePresence:
    """Create a _RemotePresence with a mock NiceGUI client."""
    if client is None:
        client = MagicMock()
        client._deleted = deleted
    return _RemotePresence(
        name="test-user",
        color="#ff0000",
        nicegui_client=client,
        callback=None,
        has_milkdown_editor=has_milkdown_editor,
    )


class TestBroadcastJsToOthersIsSync:
    """AC1.1 / AC1.2: Broadcast functions are synchronous."""

    def test_broadcast_js_to_others_is_not_coroutine(self) -> None:
        from promptgrimoire.pages.annotation.broadcast import _broadcast_js_to_others

        assert not inspect.iscoroutinefunction(_broadcast_js_to_others)

    def test_broadcast_cursor_update_is_not_coroutine(self) -> None:
        from promptgrimoire.pages.annotation.broadcast import _broadcast_cursor_update

        assert not inspect.iscoroutinefunction(_broadcast_cursor_update)

    def test_broadcast_selection_update_is_not_coroutine(self) -> None:
        from promptgrimoire.pages.annotation.broadcast import (
            _broadcast_selection_update,
        )

        assert not inspect.iscoroutinefunction(_broadcast_selection_update)


class TestBroadcastFireAndForget:
    """AC1.1 / AC1.2: run_javascript is called, not awaited."""

    def test_cursor_broadcast_calls_run_javascript_without_await(self) -> None:
        """AC1.1: Cursor broadcast calls run_javascript synchronously."""
        from promptgrimoire.pages.annotation.broadcast import _broadcast_cursor_update

        ws_key = "test-ws"
        client_a = MagicMock()
        client_a._deleted = False
        client_b = MagicMock()
        client_b._deleted = False

        _workspace_presence[ws_key] = {
            "sender": _make_presence(client=client_a),
            "receiver": _make_presence(client=client_b),
        }
        _workspace_presence[ws_key]["receiver"].user_id = "user-2"

        state = _make_state(client_id="sender")
        _broadcast_cursor_update(ws_key, "sender", state, 42)

        # run_javascript was called (not awaited — it's a sync call)
        client_b.run_javascript.assert_called_once()

    def test_selection_broadcast_calls_run_javascript_without_await(self) -> None:
        """AC1.2: Selection broadcast calls run_javascript synchronously."""
        from promptgrimoire.pages.annotation.broadcast import (
            _broadcast_selection_update,
        )

        ws_key = "test-ws"
        client_a = MagicMock()
        client_a._deleted = False
        client_b = MagicMock()
        client_b._deleted = False

        _workspace_presence[ws_key] = {
            "sender": _make_presence(client=client_a),
            "receiver": _make_presence(client=client_b),
        }
        _workspace_presence[ws_key]["receiver"].user_id = "user-2"

        state = _make_state(client_id="sender")
        _broadcast_selection_update(ws_key, "sender", state, 10, 20)

        client_b.run_javascript.assert_called_once()


class TestClientDeleteFireAndForget:
    """AC1.3: Cursor/selection removal on client delete is fire-and-forget."""

    @pytest.mark.asyncio
    async def test_handle_client_delete_calls_run_javascript_without_await(
        self,
    ) -> None:
        """_handle_client_delete calls run_javascript for removal JS synchronously."""
        from uuid import UUID

        from promptgrimoire.pages.annotation.broadcast import _handle_client_delete

        ws_key = "test-ws"
        workspace_id = UUID("00000000-0000-0000-0000-000000000001")

        remaining_client = MagicMock()
        remaining_client._deleted = False

        _workspace_presence[ws_key] = {
            "leaving": _make_presence(),
            "remaining": _make_presence(client=remaining_client),
        }

        # Mock the persistence manager
        with contextlib.suppress(Exception):
            await _handle_client_delete(ws_key, "leaving", workspace_id)

        # run_javascript should be called (not awaited) for removal
        remaining_client.run_javascript.assert_called_once()


class TestDisconnectedClientDoesNotBlock:
    """AC1.4: A disconnected/slow client does not block broadcasts to others."""

    def test_failing_client_does_not_prevent_other_broadcasts(self) -> None:
        """If one client's run_javascript raises, other clients still get called."""
        from promptgrimoire.pages.annotation.broadcast import _broadcast_js_to_others

        ws_key = "test-ws"

        # Client A: raises on run_javascript
        client_a = MagicMock()
        client_a._deleted = False
        client_a.run_javascript = MagicMock(side_effect=RuntimeError("disconnected"))

        # Client B: normal
        client_b = MagicMock()
        client_b._deleted = False

        _workspace_presence[ws_key] = {
            "sender": _make_presence(),
            "client-a": _make_presence(client=client_a),
            "client-b": _make_presence(client=client_b),
        }

        # Must not raise
        _broadcast_js_to_others(ws_key, "sender", "console.log('test')")

        # Client B should still have been called despite client A failing
        client_b.run_javascript.assert_called_once()


class TestNonRespondingClientNoTimeout:
    """AC1.5: A non-responding client doesn't cause timeout exceptions."""

    def test_broadcast_does_not_raise_on_timeout(self) -> None:
        """Fire-and-forget means no waiting for response, so no timeout."""
        from promptgrimoire.pages.annotation.broadcast import _broadcast_js_to_others

        ws_key = "test-ws"

        client = MagicMock()
        client._deleted = False
        # Simulate a client that would timeout if awaited
        client.run_javascript = MagicMock(side_effect=TimeoutError("timed out"))

        _workspace_presence[ws_key] = {
            "sender": _make_presence(),
            "receiver": _make_presence(client=client),
        }

        # Must not raise — the exception is suppressed
        _broadcast_js_to_others(ws_key, "sender", "console.log('test')")
