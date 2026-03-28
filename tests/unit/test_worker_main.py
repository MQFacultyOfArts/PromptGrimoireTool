"""Unit tests for the standalone export worker entry point.

Acceptance Criteria:
- infra-split.AC1.1: main() calls init_db(), setup_logging(), start_export_worker()
  in correct order, then awaits shutdown event
- infra-split.AC1.3: When init_db() raises, the exception propagates (not swallowed)
- infra-split.AC1.4: Shutdown event cancels the worker task and calls close_db()
- infra-split.AC3.1: Worker sends READY=1 after init, WATCHDOG=1 per cycle
- infra-split.AC3.2: Watchdog heartbeat continues during long-running jobs
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest

import promptgrimoire.export.worker_main as worker_main_mod

if TYPE_CHECKING:
    from collections.abc import Callable


class TestWorkerMainStartup:
    """AC1.1: main() initialises logging, DB, and worker in correct order."""

    @pytest.mark.asyncio
    async def test_main_calls_setup_in_order(self) -> None:
        """setup_logging -> init_db -> start_export_worker, then awaits shutdown."""
        call_order: list[str] = []

        def mock_setup_logging() -> None:
            call_order.append("setup_logging")

        async def mock_init_db() -> None:
            call_order.append("init_db")

        async def mock_start_export_worker(**_kw: object) -> None:
            call_order.append("start_export_worker")
            # Simulate worker running until cancelled
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

        async def mock_close_db() -> None:
            call_order.append("close_db")

        # Trigger shutdown shortly after main starts
        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch(
                "promptgrimoire.export.worker_main.setup_logging",
                side_effect=mock_setup_logging,
            ),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                side_effect=mock_init_db,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                side_effect=mock_close_db,
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            exit_code = await worker_main_mod.main()
            await shutdown_task

        assert call_order[:3] == ["setup_logging", "init_db", "start_export_worker"]
        assert "close_db" in call_order
        assert exit_code == 0


class TestWorkerMainDbFailure:
    """AC1.3: init_db() failure propagates (not silently swallowed)."""

    @pytest.mark.asyncio
    async def test_init_db_failure_propagates(self) -> None:
        """When init_db() raises, main() lets the exception propagate."""

        async def mock_init_db() -> None:
            msg = "connection refused"
            raise ConnectionRefusedError(msg)

        with (
            patch("promptgrimoire.export.worker_main.setup_logging"),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                side_effect=mock_init_db,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                new_callable=AsyncMock,
            ),
            pytest.raises(ConnectionRefusedError, match="connection refused"),
        ):
            await worker_main_mod.main()


class TestWorkerMainShutdown:
    """AC1.4: Shutdown event cancels worker and calls close_db()."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_worker_and_closes_db(self) -> None:
        """Setting shutdown event cancels the worker task and disposes DB."""
        worker_was_cancelled = False

        async def mock_start_export_worker(**_kw: object) -> None:
            nonlocal worker_was_cancelled
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                worker_was_cancelled = True
                raise

        mock_close = AsyncMock()

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch("promptgrimoire.export.worker_main.setup_logging"),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                mock_close,
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            exit_code = await worker_main_mod.main()
            await shutdown_task

        assert worker_was_cancelled is True
        mock_close.assert_awaited_once()
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_handle_signal_sets_shutdown_event(self) -> None:
        """_handle_signal sets the module-level shutdown event."""
        import signal

        # main() creates the event; simulate that
        worker_main_mod._shutdown_event = asyncio.Event()
        assert not worker_main_mod._shutdown_event.is_set()

        worker_main_mod._handle_signal(signal.SIGTERM)

        assert worker_main_mod._shutdown_event.is_set()
        # Clean up
        worker_main_mod._shutdown_event = None


class TestWorkerWatchdogReady:
    """AC3.1: Worker sends READY=1 after DB init."""

    @pytest.mark.asyncio
    async def test_ready_sent_after_init_db(self) -> None:
        """sd_notify.notify('READY=1') is called after init_db()."""
        call_order: list[str] = []

        async def mock_init_db() -> None:
            call_order.append("init_db")

        def mock_notify(msg: str) -> bool:
            call_order.append(f"notify:{msg}")
            return True

        async def mock_start_export_worker(
            **_kwargs: object,
        ) -> None:
            call_order.append("start_export_worker")
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch(
                "promptgrimoire.export.worker_main.setup_logging",
            ),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                side_effect=mock_init_db,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.sd_notify",
                notify=mock_notify,
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            await worker_main_mod.main()
            await shutdown_task

        # READY=1 must come after init_db
        init_idx = call_order.index("init_db")
        ready_idx = call_order.index("notify:READY=1")
        assert ready_idx > init_idx

    @pytest.mark.asyncio
    async def test_stopping_sent_on_shutdown(self) -> None:
        """sd_notify.notify('STOPPING=1') is called during shutdown."""
        notifications: list[str] = []

        def mock_notify(msg: str) -> bool:
            notifications.append(msg)
            return True

        async def mock_start_export_worker(
            **_kwargs: object,
        ) -> None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch(
                "promptgrimoire.export.worker_main.setup_logging",
            ),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.sd_notify",
                notify=mock_notify,
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            await worker_main_mod.main()
            await shutdown_task

        assert "STOPPING=1" in notifications


class TestWorkerWatchdogHeartbeat:
    """AC3.1/AC3.2: WATCHDOG=1 sent via on_poll_cycle callback."""

    @pytest.mark.asyncio
    async def test_watchdog_callback_passed_to_worker(self) -> None:
        """main() passes an on_poll_cycle callback to start_export_worker."""
        captured_kwargs: dict[str, object] = {}

        async def mock_start_export_worker(
            **kwargs: object,
        ) -> None:
            captured_kwargs.update(kwargs)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch(
                "promptgrimoire.export.worker_main.setup_logging",
            ),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.sd_notify",
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            await worker_main_mod.main()
            await shutdown_task

        assert "on_poll_cycle" in captured_kwargs
        assert callable(captured_kwargs["on_poll_cycle"])

    @pytest.mark.asyncio
    async def test_watchdog_callback_sends_watchdog_notify(
        self,
    ) -> None:
        """The on_poll_cycle callback calls sd_notify('WATCHDOG=1')."""
        notifications: list[str] = []
        captured_callback: list[object] = []

        def mock_notify(msg: str) -> bool:
            notifications.append(msg)
            return True

        async def mock_start_export_worker(
            **kwargs: object,
        ) -> None:
            # Capture and invoke the callback to verify it works
            cb = kwargs.get("on_poll_cycle")
            if cb is not None:
                fn = cast("Callable[[], None]", cb)
                captured_callback.append(fn)
                fn()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(3600)

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            if worker_main_mod._shutdown_event is not None:
                worker_main_mod._shutdown_event.set()

        with (
            patch(
                "promptgrimoire.export.worker_main.setup_logging",
            ),
            patch(
                "promptgrimoire.export.worker_main.init_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.start_export_worker",
                side_effect=mock_start_export_worker,
            ),
            patch(
                "promptgrimoire.export.worker_main.close_db",
                new_callable=AsyncMock,
            ),
            patch(
                "promptgrimoire.export.worker_main.sd_notify",
                notify=mock_notify,
            ),
        ):
            shutdown_task = asyncio.create_task(trigger_shutdown())
            await worker_main_mod.main()
            await shutdown_task

        assert "WATCHDOG=1" in notifications
