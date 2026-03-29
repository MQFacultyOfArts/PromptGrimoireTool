"""Tests for auth.client_registry module."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from promptgrimoire.auth.client_registry import (
    _registry,
    deregister,
    disconnect_user,
    register,
)


def _make_client() -> MagicMock:
    """Create a mock NiceGUI Client with required interface."""
    client = MagicMock()
    client.id = str(uuid4())
    client.run_javascript = MagicMock()
    client.on_delete = MagicMock()
    return client


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Clear module-level registry between tests."""
    _registry.clear()


class TestRegister:
    def test_register_adds_client(self) -> None:
        user_id = uuid4()
        client = _make_client()

        register(user_id, client)

        assert user_id in _registry
        assert client in _registry[user_id]

    def test_register_sets_on_delete_callback(self) -> None:
        user_id = uuid4()
        client = _make_client()

        register(user_id, client)

        client.on_delete.assert_called_once()

    def test_register_multiple_clients_same_user(self) -> None:
        user_id = uuid4()
        c1 = _make_client()
        c2 = _make_client()

        register(user_id, c1)
        register(user_id, c2)

        assert len(_registry[user_id]) == 2


class TestDeregister:
    def test_deregister_removes_client(self) -> None:
        user_id = uuid4()
        client = _make_client()
        _registry[user_id] = {client}

        deregister(user_id, client)

        assert client not in _registry.get(user_id, set())

    def test_deregister_cleans_empty_user(self) -> None:
        user_id = uuid4()
        client = _make_client()
        _registry[user_id] = {client}

        deregister(user_id, client)

        assert user_id not in _registry

    def test_deregister_tolerates_unknown_user(self) -> None:
        deregister(uuid4(), _make_client())  # should not raise

    def test_deregister_tolerates_unknown_client(self) -> None:
        user_id = uuid4()
        c1 = _make_client()
        c2 = _make_client()
        _registry[user_id] = {c1}

        deregister(user_id, c2)  # c2 not in set

        assert c1 in _registry[user_id]


class TestDisconnectUser:
    def test_disconnect_calls_run_javascript(self) -> None:
        user_id = uuid4()
        c1 = _make_client()
        c2 = _make_client()
        _registry[user_id] = {c1, c2}

        disconnect_user(user_id)

        c1.run_javascript.assert_called_once_with(
            'window.location.href = "/banned"', timeout=2.0
        )
        c2.run_javascript.assert_called_once_with(
            'window.location.href = "/banned"', timeout=2.0
        )

    def test_disconnect_returns_count(self) -> None:
        user_id = uuid4()
        c1 = _make_client()
        c2 = _make_client()
        _registry[user_id] = {c1, c2}

        count = disconnect_user(user_id)

        assert count == 2

    def test_disconnect_removes_user_from_registry(self) -> None:
        user_id = uuid4()
        _registry[user_id] = {_make_client()}

        disconnect_user(user_id)

        assert user_id not in _registry

    def test_disconnect_unknown_user_returns_zero(self) -> None:
        count = disconnect_user(uuid4())

        assert count == 0

    def test_disconnect_tolerates_stale_client(self) -> None:
        """Stale client raises but is logged; only successes counted."""
        user_id = uuid4()
        good1 = _make_client()
        stale = _make_client()
        good2 = _make_client()
        stale.run_javascript = MagicMock(side_effect=RuntimeError("disconnected"))
        _registry[user_id] = {good1, stale, good2}

        count = disconnect_user(user_id)

        # Only the two successful sends are counted
        assert count == 2
        # All three were attempted
        good1.run_javascript.assert_called_once()
        stale.run_javascript.assert_called_once()
        good2.run_javascript.assert_called_once()
