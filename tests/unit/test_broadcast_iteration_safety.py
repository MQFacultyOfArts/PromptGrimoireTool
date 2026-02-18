"""Test that broadcast dict iteration is safe under concurrent modification.

Regression test for RuntimeError: dictionary changed size during iteration
in _broadcast_js_to_others and related functions. The bug occurs when an
`await` inside a `for ... .items()` loop yields control, letting another
coroutine modify the dict (e.g., a client disconnecting mid-broadcast).

Traceability:
- Issue: #180 (NiceGUI upgrade tracking — also fix section)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from promptgrimoire.pages.annotation import _RemotePresence, _workspace_presence


def _make_presence(
    *,
    client: MagicMock | None = None,
    callback: AsyncMock | None = None,
) -> _RemotePresence:
    """Create a minimal _RemotePresence for testing."""
    return _RemotePresence(
        name="test-user",
        color="#ff0000",
        nicegui_client=client,
        callback=callback,
    )


@pytest.fixture(autouse=True)
def _clean_presence():
    """Ensure _workspace_presence is clean before/after each test."""
    _workspace_presence.clear()
    yield
    _workspace_presence.clear()


class TestBroadcastIterationSafety:
    """Verify that broadcast functions don't crash on concurrent dict mutation."""

    @pytest.mark.asyncio
    async def test_broadcast_js_to_others_survives_concurrent_delete(self) -> None:
        """_broadcast_js_to_others must not raise RuntimeError when a client
        disconnects (is removed from the dict) during iteration."""
        from promptgrimoire.pages.annotation.broadcast import _broadcast_js_to_others

        ws_key = "test-workspace"

        # Client A: its run_javascript will remove client B from the dict
        client_a = MagicMock()

        async def remove_b_on_call(*_args, **_kwargs):
            _workspace_presence[ws_key].pop("client-b", None)

        client_a.run_javascript = AsyncMock(side_effect=remove_b_on_call)

        # Client B: normal mock
        client_b = MagicMock()
        client_b.run_javascript = AsyncMock()

        _workspace_presence[ws_key] = {
            "client-a": _make_presence(client=client_a),
            "client-b": _make_presence(client=client_b),
        }

        # Must not raise RuntimeError — list() snapshot protects iteration
        await _broadcast_js_to_others(ws_key, "sender", "console.log('test')")

    @pytest.mark.asyncio
    async def test_notify_other_clients_survives_concurrent_delete(self) -> None:
        """_notify_other_clients must not crash when dict mutates during iteration."""
        from promptgrimoire.pages.annotation.broadcast import _notify_other_clients

        ws_key = "test-workspace"

        # Callback that removes client-b from presence
        async def remove_b():
            _workspace_presence[ws_key].pop("client-b", None)

        callback_a = AsyncMock(side_effect=remove_b)
        callback_b = AsyncMock()

        client_a = MagicMock()
        client_b = MagicMock()

        _workspace_presence[ws_key] = {
            "client-a": _RemotePresence(
                name="user-a",
                color="#ff0000",
                nicegui_client=client_a,
                callback=callback_a,
            ),
            "client-b": _RemotePresence(
                name="user-b",
                color="#00ff00",
                nicegui_client=client_b,
                callback=callback_b,
            ),
        }

        # Must not raise — list() snapshot protects iteration
        _notify_other_clients(ws_key, "sender")

        # Let tasks complete
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_broadcast_yjs_update_survives_concurrent_delete(self) -> None:
        """_broadcast_yjs_update must not crash when dict mutates during iteration."""
        from uuid import UUID

        from promptgrimoire.pages.annotation.broadcast import _broadcast_yjs_update

        workspace_uuid = UUID("00000000-0000-0000-0000-000000000001")
        # _broadcast_yjs_update converts UUID to str internally
        ws_key = str(workspace_uuid)

        # Client A: synchronous run_javascript that removes client B
        client_a = MagicMock()

        def remove_b_sync(*_args, **_kwargs):
            _workspace_presence[ws_key].pop("client-b", None)

        client_a.run_javascript = MagicMock(side_effect=remove_b_sync)

        # Client B: normal mock
        client_b = MagicMock()
        client_b.run_javascript = MagicMock()

        _workspace_presence[ws_key] = {
            "client-a": _RemotePresence(
                name="user-a",
                color="#ff0000",
                nicegui_client=client_a,
                callback=None,
                has_milkdown_editor=True,
            ),
            "client-b": _RemotePresence(
                name="user-b",
                color="#00ff00",
                nicegui_client=client_b,
                callback=None,
                has_milkdown_editor=True,
            ),
        }

        # Must not raise — list() snapshot protects iteration
        _broadcast_yjs_update(workspace_uuid, "sender", "base64data")
