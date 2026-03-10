"""Test that broadcast operations skip deleted NiceGUI clients.

Regression test for a bug where _handle_client_delete iterates remaining
clients and invokes their presence callbacks. If a remaining client has
also been deleted by the time its callback runs, invoke_callback enters
the deleted client's context and tries to create UI elements, triggering
NiceGUI's "Client has been deleted but is still being used" warning.

The fix: invoke_callback and run_javascript guards must check
``nicegui_client._deleted`` before entering the client context.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from promptgrimoire.pages.annotation import _RemotePresence


def _make_presence(*, deleted: bool = False) -> _RemotePresence:
    """Build a _RemotePresence with a mock NiceGUI client.

    Parameters
    ----------
    deleted
        If True, the mock client's ``_deleted`` attribute is set to True,
        simulating a client that has been removed but whose object still
        exists in memory.
    """
    mock_client = MagicMock()
    mock_client._deleted = deleted
    # The context manager (``with client:``) should still work for non-deleted
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    callback = AsyncMock()

    return _RemotePresence(
        name="Test User",
        color="#ff0000",
        nicegui_client=mock_client,
        callback=callback,
    )


@pytest.mark.asyncio
async def test_invoke_callback_skips_deleted_client() -> None:
    """invoke_callback must be a no-op when the NiceGUI client is deleted."""
    presence = _make_presence(deleted=True)

    await presence.invoke_callback()

    # The callback should NOT have been called
    presence.callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_invoke_callback_runs_for_live_client() -> None:
    """invoke_callback should still work for non-deleted clients."""
    presence = _make_presence(deleted=False)

    await presence.invoke_callback()

    # The callback SHOULD have been called
    presence.callback.assert_awaited_once()
