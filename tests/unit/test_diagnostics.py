"""Unit tests for diagnostics collection."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestMemoryThresholdRestart:
    """Tests for memory-threshold-based graceful restart."""

    @pytest.fixture
    def _mock_snapshot(self) -> dict[str, Any]:
        return {
            "current_rss_bytes": 2_000_000_000,  # 2GB — below default 3GB threshold
            "peak_rss_bytes": 2_500_000_000,
            "clients_total": 50,
            "clients_connected": 45,
            "asyncio_tasks_total": 200,
            "app_ws_registry": 30,
            "app_ws_presence_workspaces": 20,
            "app_ws_presence_clients": 40,
        }

    async def test_no_restart_when_below_threshold(
        self, _mock_snapshot: dict[str, Any]
    ) -> None:
        """Diagnostic loop does not trigger restart when RSS < threshold."""
        from promptgrimoire.diagnostics import _check_memory_threshold

        result = _check_memory_threshold(_mock_snapshot, threshold_mb=3072)
        assert result is False

    async def test_restart_triggered_when_above_threshold(
        self, _mock_snapshot: dict[str, Any]
    ) -> None:
        """Diagnostic loop triggers restart when RSS > threshold."""
        from promptgrimoire.diagnostics import _check_memory_threshold

        _mock_snapshot["current_rss_bytes"] = 4_000_000_000  # 4GB > 3GB threshold
        result = _check_memory_threshold(_mock_snapshot, threshold_mb=3072)
        assert result is True

    async def test_no_restart_when_rss_is_none(
        self, _mock_snapshot: dict[str, Any]
    ) -> None:
        """No restart when RSS is unavailable (e.g. no /proc)."""
        from promptgrimoire.diagnostics import _check_memory_threshold

        _mock_snapshot["current_rss_bytes"] = None
        result = _check_memory_threshold(_mock_snapshot, threshold_mb=3072)
        assert result is False

    async def test_no_restart_when_threshold_is_zero(
        self, _mock_snapshot: dict[str, Any]
    ) -> None:
        """Threshold of 0 disables the feature."""
        from promptgrimoire.diagnostics import _check_memory_threshold

        _mock_snapshot["current_rss_bytes"] = 4_000_000_000
        result = _check_memory_threshold(_mock_snapshot, threshold_mb=0)
        assert result is False

    async def test_graceful_shutdown_calls_pre_restart_flow(self) -> None:
        """When threshold exceeded, graceful_memory_shutdown runs the
        pre-restart flow (flush CRDT, navigate clients) then exits."""
        from promptgrimoire.diagnostics import graceful_memory_shutdown

        mock_flush = AsyncMock()
        mock_persist = AsyncMock()
        mock_navigate = AsyncMock()

        with (
            patch(
                "promptgrimoire.diagnostics._flush_milkdown_to_crdt",
                mock_flush,
            ),
            patch(
                "promptgrimoire.diagnostics._persist_dirty_workspaces",
                mock_persist,
            ),
            patch(
                "promptgrimoire.diagnostics._navigate_clients_to_restarting",
                mock_navigate,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            await graceful_memory_shutdown(rss_mb=4000, threshold_mb=3072)

        from promptgrimoire.diagnostics import MEMORY_RESTART_EXIT_CODE

        assert exc_info.value.code == MEMORY_RESTART_EXIT_CODE
        mock_flush.assert_awaited_once()
        mock_persist.assert_awaited_once()
        mock_navigate.assert_awaited_once()
