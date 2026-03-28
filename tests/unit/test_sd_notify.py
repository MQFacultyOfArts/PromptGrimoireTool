"""Unit tests for the vendored sd_notify module.

Tests the minimal sd_notify protocol implementation used for systemd
watchdog integration in the standalone export worker.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

from promptgrimoire import sd_notify

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestNotifyWithoutSocket:
    """notify() is a silent no-op when NOTIFY_SOCKET is not set."""

    def test_returns_false_when_notify_socket_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns False when NOTIFY_SOCKET env var is absent."""
        monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
        assert sd_notify.notify("READY=1") is False

    def test_returns_false_when_notify_socket_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns False when NOTIFY_SOCKET is set but empty."""
        monkeypatch.setenv("NOTIFY_SOCKET", "")
        assert sd_notify.notify("READY=1") is False


class TestNotifyWithSocket:
    """notify() sends data to a real Unix datagram socket."""

    def test_sends_message_and_returns_true(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Sends encoded message to NOTIFY_SOCKET and returns True."""
        socket_path = str(tmp_path / "notify.sock")

        # Create a receiving datagram socket
        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        receiver.bind(socket_path)
        try:
            monkeypatch.setenv("NOTIFY_SOCKET", socket_path)

            result = sd_notify.notify("READY=1")

            assert result is True
            data = receiver.recv(256)
            assert data == b"READY=1"
        finally:
            receiver.close()

    def test_sends_watchdog_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """WATCHDOG=1 message is sent correctly."""
        socket_path = str(tmp_path / "notify.sock")

        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        receiver.bind(socket_path)
        try:
            monkeypatch.setenv("NOTIFY_SOCKET", socket_path)

            result = sd_notify.notify("WATCHDOG=1")

            assert result is True
            data = receiver.recv(256)
            assert data == b"WATCHDOG=1"
        finally:
            receiver.close()


class TestAbstractSocketHandling:
    """Abstract socket paths (@ prefix) are converted to null-byte prefix."""

    def test_abstract_socket_prefix_conversion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """@ prefix is replaced with \\0 for abstract socket namespace."""
        # We can't easily test actual abstract socket delivery in a unit test
        # without root or matching permissions, but we can verify the path
        # transformation by mocking the socket layer.
        from unittest.mock import MagicMock, patch

        mock_sock = MagicMock()
        mock_sock_class = MagicMock(return_value=mock_sock)
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        monkeypatch.setenv("NOTIFY_SOCKET", "@/run/systemd/notify")

        with patch("promptgrimoire.sd_notify.socket.socket", mock_sock_class):
            result = sd_notify.notify("READY=1")

        assert result is True
        mock_sock.sendto.assert_called_once_with(b"READY=1", "\0/run/systemd/notify")
