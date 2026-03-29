"""Test editor_ready event handler for readiness gating.

Verifies eliminate-js-await-454.AC2.3, AC2.4, AC2.5:
- AC2.3: has_milkdown_editor is set only after editor_ready {status:'ok'}
- AC2.4: _broadcast_yjs_update skips clients without has_milkdown_editor
- AC2.5: editor_ready {status:'error'} logs and does NOT set the flag

Traceability: Issue #454
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from promptgrimoire.pages.annotation import (
    PageState,
    _RemotePresence,
    _workspace_presence,
)
from promptgrimoire.pages.annotation.respond import _handle_editor_ready

_TEST_UUID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def _clean_presence():
    _workspace_presence.clear()
    yield
    _workspace_presence.clear()


def _make_event(args: dict[str, Any]) -> MagicMock:
    """Create a mock NiceGUI GenericEventArguments."""
    e = MagicMock()
    e.args = args
    return e


class TestEditorReadyOk:
    """AC2.3: has_milkdown_editor set only after editor_ready ok."""

    def test_sets_flag_on_state(self) -> None:
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"
        assert not state.has_milkdown_editor

        ws_key = str(_TEST_UUID)
        _workspace_presence[ws_key] = {
            "client-1": _RemotePresence(
                name="test",
                color="#ff0000",
                nicegui_client=MagicMock(),
                callback=None,
            ),
        }

        _handle_editor_ready(
            _make_event({"status": "ok"}),
            state,
            ws_key,
            "client-1",
        )

        assert state.has_milkdown_editor is True

    def test_sets_flag_on_remote_presence(self) -> None:
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"

        ws_key = str(_TEST_UUID)
        presence = _RemotePresence(
            name="test",
            color="#ff0000",
            nicegui_client=MagicMock(),
            callback=None,
        )
        _workspace_presence[ws_key] = {"client-1": presence}

        _handle_editor_ready(
            _make_event({"status": "ok"}),
            state,
            ws_key,
            "client-1",
        )

        assert presence.has_milkdown_editor is True

    def test_sends_catchup_full_state_on_ready(self) -> None:
        """After editor_ready, a fresh full-state sync is sent to
        converge any Yjs updates missed during the init window."""
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"

        mock_crdt = MagicMock()
        mock_crdt.get_full_state.return_value = b"\x01\x02\x03"
        state.crdt_doc = mock_crdt

        ws_key = str(_TEST_UUID)
        mock_client = MagicMock()
        presence = _RemotePresence(
            name="test",
            color="#ff0000",
            nicegui_client=mock_client,
            callback=None,
        )
        _workspace_presence[ws_key] = {"client-1": presence}

        _handle_editor_ready(
            _make_event({"status": "ok"}),
            state,
            ws_key,
            "client-1",
        )

        # Catch-up full-state sync must have been sent
        mock_client.run_javascript.assert_called_once()
        call_js = mock_client.run_javascript.call_args[0][0]
        assert "_applyRemoteUpdate" in call_js

    def test_skips_catchup_when_crdt_empty(self) -> None:
        """No catch-up sync for empty CRDT docs (2 bytes = empty)."""
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"

        mock_crdt = MagicMock()
        mock_crdt.get_full_state.return_value = b"\x01\x00"
        state.crdt_doc = mock_crdt

        ws_key = str(_TEST_UUID)
        mock_client = MagicMock()
        presence = _RemotePresence(
            name="test",
            color="#ff0000",
            nicegui_client=mock_client,
            callback=None,
        )
        _workspace_presence[ws_key] = {"client-1": presence}

        _handle_editor_ready(
            _make_event({"status": "ok"}),
            state,
            ws_key,
            "client-1",
        )

        # No catch-up needed — doc is empty
        mock_client.run_javascript.assert_not_called()


class TestEditorReadyError:
    """AC2.5: error status logs and does NOT set has_milkdown_editor."""

    def test_does_not_set_flag_on_error(self) -> None:
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"

        ws_key = str(_TEST_UUID)
        presence = _RemotePresence(
            name="test",
            color="#ff0000",
            nicegui_client=MagicMock(),
            callback=None,
        )
        _workspace_presence[ws_key] = {"client-1": presence}

        _handle_editor_ready(
            _make_event({"status": "error", "error": "test failure"}),
            state,
            ws_key,
            "client-1",
        )

        assert state.has_milkdown_editor is False
        assert presence.has_milkdown_editor is False

    def test_logs_error_on_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC2.5: Error status is logged via structlog."""
        state = PageState(workspace_id=_TEST_UUID)
        state.client_id = "client-1"

        ws_key = str(_TEST_UUID)
        _workspace_presence[ws_key] = {
            "client-1": _RemotePresence(
                name="test",
                color="#ff0000",
                nicegui_client=MagicMock(),
                callback=None,
            ),
        }

        _handle_editor_ready(
            _make_event({"status": "error", "error": "JS exploded"}),
            state,
            ws_key,
            "client-1",
        )

        captured = capsys.readouterr()
        assert "editor_init_failed" in captured.out, (
            f"Expected structlog 'editor_init_failed' in stdout, got: {captured.out!r}"
        )


class TestYjsRelaySkipsUnready:
    """AC2.4: _broadcast_yjs_update skips clients without the flag."""

    def test_skips_client_without_milkdown_editor(self) -> None:
        from promptgrimoire.pages.annotation.broadcast import (
            _broadcast_yjs_update,
        )

        ws_key = str(_TEST_UUID)
        client_ready = MagicMock()
        client_not_ready = MagicMock()

        _workspace_presence[ws_key] = {
            "sender": _RemotePresence(
                name="sender",
                color="#ff0000",
                nicegui_client=MagicMock(),
                callback=None,
                has_milkdown_editor=True,
            ),
            "ready": _RemotePresence(
                name="ready",
                color="#00ff00",
                nicegui_client=client_ready,
                callback=None,
                has_milkdown_editor=True,
            ),
            "not-ready": _RemotePresence(
                name="not-ready",
                color="#0000ff",
                nicegui_client=client_not_ready,
                callback=None,
                has_milkdown_editor=False,
            ),
        }

        _broadcast_yjs_update(_TEST_UUID, "sender", "base64data")

        client_ready.run_javascript.assert_called_once()
        client_not_ready.run_javascript.assert_not_called()
