"""Unit tests for diagnostics collection."""

from __future__ import annotations

import sys
from typing import Any

import pytest


class TestCollectMemory:
    """Tests for _collect_memory() RSS collection."""

    @pytest.mark.skipif(sys.platform != "linux", reason="VmRSS only available on Linux")
    def test_returns_rss_on_linux(self) -> None:
        """AC5.2: current_rss_bytes is a positive integer on Linux."""
        from promptgrimoire.diagnostics import _collect_memory

        result = _collect_memory()
        assert isinstance(result["current_rss_bytes"], int)
        assert result["current_rss_bytes"] > 0
        assert isinstance(result["peak_rss_bytes"], int)
        assert result["peak_rss_bytes"] > 0

    def test_handles_missing_proc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC5.2: _collect_memory handles missing /proc gracefully."""
        from pathlib import Path

        from promptgrimoire.diagnostics import _collect_memory

        original_path_open = Path.open

        def patched_path_open(self: Path, *args: Any, **kwargs: Any) -> Any:
            if str(self) == "/proc/self/status":
                raise OSError("No such file")
            return original_path_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", patched_path_open)

        result = _collect_memory()
        assert result["current_rss_bytes"] is None
        # peak_rss_bytes should still work (via resource module)
        if sys.platform != "win32":
            assert result["peak_rss_bytes"] is not None


class TestCollectSnapshot:
    """Tests for collect_snapshot() full snapshot."""

    def test_returns_all_expected_keys(self) -> None:
        """AC5.2: snapshot contains all required fields."""
        from unittest.mock import MagicMock, patch

        mock_client_class = MagicMock()
        mock_client_class.instances = {}

        with (
            patch("nicegui.Client", mock_client_class),
            patch("promptgrimoire.diagnostics.asyncio.all_tasks", return_value=set()),
        ):
            from promptgrimoire.diagnostics import collect_snapshot

            snapshot = collect_snapshot()

        expected_keys = {
            "current_rss_bytes",
            "peak_rss_bytes",
            "clients_total",
            "clients_connected",
            "asyncio_tasks_total",
            "app_ws_registry",
            "app_ws_presence_workspaces",
            "app_ws_presence_clients",
        }
        assert expected_keys == set(snapshot.keys())

    def test_client_counts_reflect_instances(self) -> None:
        """AC5.2: client counts match NiceGUI Client.instances."""
        from unittest.mock import MagicMock, patch

        connected = MagicMock(has_socket_connection=True)
        disconnected = MagicMock(has_socket_connection=False)
        mock_client_class = MagicMock()
        mock_client_class.instances = {
            "c1": connected,
            "c2": disconnected,
            "c3": connected,
        }
        mock_tasks = {MagicMock() for _ in range(5)}

        with (
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.diagnostics.asyncio.all_tasks",
                return_value=mock_tasks,
            ),
        ):
            from promptgrimoire.diagnostics import collect_snapshot

            snapshot = collect_snapshot()

        assert snapshot["clients_total"] == 3
        assert snapshot["clients_connected"] == 2
        assert snapshot["asyncio_tasks_total"] == 5
