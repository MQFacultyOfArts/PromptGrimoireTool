"""Standalone export worker process.

Entry point for running the export worker outside the NiceGUI app process.
Invoked as: python -m promptgrimoire.export.worker_main

Initialises logging, database engine, runs the poll loop, and handles
SIGTERM for graceful shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

import structlog

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
    _shutdown_event = asyncio.Event()

    setup_logging()

    settings = get_settings()
    logger.info(
        "worker_starting",
        database_url=str(settings.database.url).split("@")[-1],  # hide credentials
    )

    await init_db()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    worker_task = asyncio.create_task(start_export_worker())

    # Wait for shutdown signal
    await _shutdown_event.wait()

    logger.info("worker_shutting_down")
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task

    await close_db()
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
