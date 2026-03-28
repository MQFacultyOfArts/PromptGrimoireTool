"""Test that cursor/selection JS defers until annotation scripts load.

Bug: renderRemoteCursor / renderRemoteSelection are emitted directly
via ui.run_javascript(). When a late-joining client's
annotation-highlight.js hasn't loaded yet (deferred-load / SPA path),
both functions are undefined and the calls silently fail.

Two affected code paths:
1. _replay_existing_cursors — one-shot replay on late join
2. _broadcast_cursor_update / _broadcast_selection_update — live
   broadcasts that can hit a client still in its loading window
   (registered in _workspace_presence before scripts load)

Fix: Replay wraps JS in a polling IIFE with max retries.
Live broadcasts wrap in a typeof guard (skip if not ready —
replay catches up with latest cursor_char).

Traceability:
- Issue: #377
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.pages.annotation import (
    PageState,
    _RemotePresence,
    _workspace_presence,
)
from promptgrimoire.pages.annotation.broadcast import (
    _broadcast_cursor_update,
    _broadcast_selection_update,
    _replay_existing_cursors,
)


def _make_presence(
    *,
    cursor_char: int | None = None,
    selection_start: int | None = None,
    selection_end: int | None = None,
) -> _RemotePresence:
    """Create a _RemotePresence with cursor/selection state."""
    return _RemotePresence(
        name="User A",
        color="#e91e63",
        nicegui_client=MagicMock(),
        callback=MagicMock(),
        cursor_char=cursor_char,
        selection_start=selection_start,
        selection_end=selection_end,
        user_id="user-a-id",
        viewer_is_privileged=False,
    )


def _make_state() -> PageState:
    """Create a minimal PageState for replay testing."""
    state = PageState.__new__(PageState)
    state.doc_container_id = "doc-container-test-123"
    state.user_id = "user-b-id"
    state.is_anonymous = False
    state.viewer_is_privileged = False
    state.client_id = "client-b"
    return state


@pytest.fixture(autouse=True)
def _clean_presence():
    _workspace_presence.clear()
    yield
    _workspace_presence.clear()


class TestReplayCursorDeferred:
    """Replay JS must defer execution until annotation scripts load."""

    def test_cursor_replay_defers_until_function_defined(self) -> None:
        """renderRemoteCursor call must poll for function availability.

        The emitted JS must NOT call renderRemoteCursor() directly.
        It must check typeof renderRemoteCursor before calling, and
        retry via setTimeout if the function isn't defined yet.
        """
        ws_key = "test-ws"
        _workspace_presence[ws_key] = {
            "client-a": _make_presence(cursor_char=10),
        }
        state = _make_state()
        captured_js: list[str] = []

        with patch("promptgrimoire.pages.annotation.broadcast.ui") as mock_ui:
            mock_ui.run_javascript = captured_js.append
            _replay_existing_cursors(ws_key, "client-b", state)

        assert len(captured_js) == 1, f"Expected 1 JS call, got {len(captured_js)}"
        js = captured_js[0]

        # Must check function availability before calling
        assert "typeof renderRemoteCursor" in js, (
            "Replay JS must check typeof renderRemoteCursor "
            "before calling — scripts may not be loaded yet"
        )
        # Must defer via setTimeout if not available
        assert "setTimeout" in js, (
            "Replay JS must retry via setTimeout when "
            "renderRemoteCursor is not yet defined"
        )

    def test_selection_replay_defers_until_function_defined(
        self,
    ) -> None:
        """renderRemoteSelection call must poll for function
        availability."""
        ws_key = "test-ws"
        _workspace_presence[ws_key] = {
            "client-a": _make_presence(selection_start=5, selection_end=15),
        }
        state = _make_state()
        captured_js: list[str] = []

        with patch("promptgrimoire.pages.annotation.broadcast.ui") as mock_ui:
            mock_ui.run_javascript = captured_js.append
            _replay_existing_cursors(ws_key, "client-b", state)

        assert len(captured_js) == 1
        js = captured_js[0]

        assert "typeof renderRemoteSelection" in js, (
            "Replay JS must check typeof renderRemoteSelection "
            "before calling — scripts may not be loaded yet"
        )
        assert "setTimeout" in js

    def test_cursor_replay_still_calls_function(self) -> None:
        """The deferred wrapper must still actually call
        renderRemoteCursor with the correct arguments."""
        ws_key = "test-ws"
        _workspace_presence[ws_key] = {
            "client-a": _make_presence(cursor_char=42),
        }
        state = _make_state()
        captured_js: list[str] = []

        with patch("promptgrimoire.pages.annotation.broadcast.ui") as mock_ui:
            mock_ui.run_javascript = captured_js.append
            _replay_existing_cursors(ws_key, "client-b", state)

        js = captured_js[0]
        # Must still call the function with the char index
        assert "renderRemoteCursor(" in js
        assert "42" in js
        assert state.doc_container_id in js

    def test_cursor_replay_has_max_retries(self) -> None:
        """Polling must stop after a bounded number of retries."""
        ws_key = "test-ws"
        _workspace_presence[ws_key] = {
            "client-a": _make_presence(cursor_char=10),
        }
        state = _make_state()
        captured_js: list[str] = []

        with patch("promptgrimoire.pages.annotation.broadcast.ui") as mock_ui:
            mock_ui.run_javascript = captured_js.append
            _replay_existing_cursors(ws_key, "client-b", state)

        js = captured_js[0]
        # Must have a retry counter or max-attempts guard
        # to prevent infinite 20Hz timer if scripts never load
        assert "100" in js or "retries" in js.lower(), (
            "Replay polling must have a max retry limit "
            "to prevent unbounded browser timers"
        )


class TestLiveBroadcastScriptGuard:
    """Live broadcasts must guard against undefined script functions.

    Between _setup_client_sync (registers client) and script load,
    a client is in _workspace_presence but has no annotation JS.
    Live broadcasts during this window must not crash silently.
    """

    @pytest.mark.asyncio
    async def test_cursor_broadcast_guards_typeof(self) -> None:
        """_broadcast_cursor_update JS must check typeof before
        calling renderRemoteCursor."""
        ws_key = "test-ws"
        receiver = MagicMock()
        captured_js: list[str] = []

        async def capture(js: str, **_kw: object) -> None:
            captured_js.append(js)

        receiver.run_javascript = AsyncMock(side_effect=capture)

        _workspace_presence[ws_key] = {
            "sender": _make_presence(),
            "receiver": _RemotePresence(
                name="User B",
                color="#2196f3",
                nicegui_client=receiver,
                callback=MagicMock(),
                user_id="user-b-id",
                viewer_is_privileged=False,
            ),
        }
        state = _make_state()
        state.user_name = "User A"
        state.user_color = "#e91e63"
        state.user_id = "user-a-id"

        await _broadcast_cursor_update(ws_key, "sender", state, char_index=15)

        assert len(captured_js) == 1
        js = captured_js[0]
        assert "typeof renderRemoteCursor" in js, (
            "Live cursor broadcast must check typeof "
            "renderRemoteCursor — receiver may still be "
            "loading scripts"
        )

    @pytest.mark.asyncio
    async def test_selection_broadcast_guards_typeof(self) -> None:
        """_broadcast_selection_update JS must check typeof before
        calling renderRemoteSelection."""
        ws_key = "test-ws"
        receiver = MagicMock()
        captured_js: list[str] = []

        async def capture(js: str, **_kw: object) -> None:
            captured_js.append(js)

        receiver.run_javascript = AsyncMock(side_effect=capture)

        _workspace_presence[ws_key] = {
            "sender": _make_presence(),
            "receiver": _RemotePresence(
                name="User B",
                color="#2196f3",
                nicegui_client=receiver,
                callback=MagicMock(),
                user_id="user-b-id",
                viewer_is_privileged=False,
            ),
        }
        state = _make_state()
        state.user_name = "User A"
        state.user_color = "#e91e63"
        state.user_id = "user-a-id"

        await _broadcast_selection_update(ws_key, "sender", state, start=5, end=20)

        assert len(captured_js) == 1
        js = captured_js[0]
        assert "typeof renderRemoteSelection" in js, (
            "Live selection broadcast must check typeof "
            "renderRemoteSelection — receiver may still be "
            "loading scripts"
        )
