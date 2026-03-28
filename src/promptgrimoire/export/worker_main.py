"""Standalone export worker process.

Entry point for running the export worker outside the NiceGUI app process.
Invoked as: python -m promptgrimoire.export.worker_main

Initialises logging, database engine, runs the poll loop, and handles
SIGTERM by cancelling the current job and shutting down.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

import structlog

from promptgrimoire import sd_notify
from promptgrimoire.config import get_settings
from promptgrimoire.db import close_db, init_db
from promptgrimoire.export.worker import start_export_worker
from promptgrimoire.logging_config import setup_logging

logger = structlog.get_logger()

# Mutable container so _handle_signal can reference the event created
# inside main()'s event loop.  Avoids binding to a stale loop at import time.
_shutdown_event: asyncio.Event | None = None


def _handle_signal(sig: signal.Signals) -> None:
    """Set shutdown event on SIGTERM/SIGINT."""
    logger.info("shutdown_signal_received", signal=sig.name)
    if _shutdown_event is not None:
        _shutdown_event.set()


async def main() -> int:
    """Run the standalone export worker.

    Returns
    -------
    int
        Exit code (0 for clean shutdown).
    """
    global _shutdown_event  # noqa: PLW0603 -- module-level event, set once per process
    # Create the shutdown event before setup_logging() so that _handle_signal
    # can reference it immediately after signal handlers are registered.
    # setup_logging() may emit log records during configuration; if a signal
    # arrives between event creation and handler registration (below), the
    # module-level guard in _handle_signal safely ignores it.
    _shutdown_event = asyncio.Event()

    setup_logging()

    settings = get_settings()
    logger.info(
        "worker_starting",
        database_url=str(settings.database.url).split("@")[-1],  # hide credentials
    )

    await init_db()

    sd_notify.notify("READY=1")
    logger.info("worker_ready")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    worker_task = asyncio.create_task(
        start_export_worker(
            on_poll_cycle=lambda: sd_notify.notify("WATCHDOG=1"),
        ),
    )

    # Wait for shutdown signal
    await _shutdown_event.wait()

    sd_notify.notify("STOPPING=1")
    logger.info("worker_shutting_down")
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task

    await close_db()
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
