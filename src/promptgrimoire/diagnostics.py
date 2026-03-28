"""Runtime diagnostics for PromptGrimoire.

Collection functions ported from NiceGUI PR #5660 (draft, not yet merged).
When #5660 merges upstream and the NiceGUI pin bumps, replace the NiceGUI-generic
portions with ``from nicegui import diagnostics``.

Source: nicegui/.worktrees/diagnostics-5660/nicegui/diagnostics.py
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path
from typing import Any

import structlog

# resource module is POSIX-only; gracefully degrade on other platforms
_resource: Any = None
with contextlib.suppress(ImportError):
    import resource as _resource

logger = structlog.get_logger()


async def measure_event_loop_lag() -> float:
    """Measure event-loop lag in milliseconds.

    Schedules a no-op callback via ``call_soon`` and measures how long
    the event loop takes to execute it. On an idle loop this is <1 ms;
    under saturation it grows proportionally to queue depth.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[float] = loop.create_future()
    t0 = loop.time()

    def _resolve() -> None:
        future.set_result((loop.time() - t0) * 1000.0)

    loop.call_soon(_resolve)
    return await future


def _collect_memory() -> dict[str, Any]:
    """Collect memory usage metrics.

    Ported from NiceGUI #5660 ``diagnostics.py:43-70``.
    """
    result: dict[str, Any] = {}

    if _resource is not None:
        peak_rss_raw = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
        # On Linux ru_maxrss is in KB; on macOS it is in bytes
        result["peak_rss_bytes"] = (
            peak_rss_raw * 1024 if sys.platform == "linux" else peak_rss_raw
        )
    else:
        result["peak_rss_bytes"] = None

    result["current_rss_bytes"] = None
    with (
        contextlib.suppress(OSError),
        Path("/proc/self/status").open(encoding="utf-8") as f,
    ):
        for line in f:
            if line.startswith("VmRSS:"):
                result["current_rss_bytes"] = int(line.split()[1]) * 1024
                break

    return result


def collect_snapshot() -> dict[str, Any]:
    """Collect a flattened diagnostics snapshot for structlog emission.

    Includes NiceGUI client counts, memory metrics, asyncio task count,
    and PromptGrimoire-specific CRDT registry/presence sizes.
    """
    from nicegui import Client  # noqa: PLC0415 -- lazy to avoid import-time cost

    memory = _collect_memory()

    # Reuse the canonical lazy accessor from restart.py to avoid
    # duplicating fragile sys.modules attribute access.
    from promptgrimoire.pages.restart import _get_annotation_state  # noqa: PLC0415

    workspace_presence, workspace_registry = _get_annotation_state()
    ws_registry_size = (
        len(workspace_registry._documents) if workspace_registry is not None else 0
    )
    ws_presence_workspaces = len(workspace_presence)
    ws_presence_clients = sum(len(v) for v in workspace_presence.values())

    return {
        # Memory
        "current_rss_bytes": memory["current_rss_bytes"],
        "peak_rss_bytes": memory["peak_rss_bytes"],
        # NiceGUI clients
        "clients_total": len(Client.instances),
        "clients_connected": sum(
            1 for c in Client.instances.values() if c.has_socket_connection
        ),
        # Asyncio tasks
        "asyncio_tasks_total": len(asyncio.all_tasks()),
        # PromptGrimoire application state
        "app_ws_registry": ws_registry_size,
        "app_ws_presence_workspaces": ws_presence_workspaces,
        "app_ws_presence_clients": ws_presence_clients,
        # Event loop responsiveness (filled by async caller)
        "event_loop_lag_ms": None,
    }


def _check_memory_threshold(snapshot: dict[str, Any], *, threshold_mb: int) -> bool:
    """Return True if current RSS exceeds *threshold_mb*.

    Returns False when:
    - threshold_mb is 0 (feature disabled)
    - current_rss_bytes is None (e.g. no /proc on non-Linux)
    - RSS is below the threshold
    """
    if threshold_mb <= 0:
        return False
    rss_bytes = snapshot.get("current_rss_bytes")
    if rss_bytes is None:
        return False
    return rss_bytes > threshold_mb * 1024 * 1024


async def _flush_milkdown_to_crdt() -> None:
    """Delegate to restart.py's flush implementation."""
    from promptgrimoire.pages.restart import (  # noqa: PLC0415
        _flush_milkdown_to_crdt as _flush,
    )

    await _flush()


async def _persist_dirty_workspaces() -> None:
    """Persist all dirty CRDT state to database."""
    from promptgrimoire.crdt.persistence import get_persistence_manager  # noqa: PLC0415

    await get_persistence_manager().persist_all_dirty_workspaces()


async def _invalidate_all_sessions() -> None:
    """Clear auth_user from all client storage to prevent session leakage.

    Must run before restart to ensure no stale sessions survive the
    reconnection thundering herd.  Users will need to re-authenticate
    after the server comes back up.
    """
    from nicegui import app  # noqa: PLC0415

    # _users is the server-side dict of all per-user PersistentDict
    # instances, keyed by the browser-level storage ID.
    user_stores = app.storage._users  # pyright: ignore[reportPrivateUsage]
    for user_storage in user_stores.values():
        user_storage.pop("auth_user", None)
    logger.info("sessions_invalidated", count=len(user_stores))


async def _navigate_clients_to_restarting() -> None:
    """Navigate all connected NiceGUI clients to /restarting."""
    from nicegui import Client  # noqa: PLC0415

    for client in list(Client.instances.values()):
        if not client.has_socket_connection:
            continue
        try:
            await client.run_javascript(
                'window.location.href = "/restarting?manual=1&return="'
                " + encodeURIComponent("
                "location.pathname + location.search + location.hash)",
                timeout=2.0,
            )
        except Exception:
            logger.warning(
                "memory_restart_navigate_failed",
                client_id=client.id,
                exc_info=True,
            )


# Exit code for memory-threshold restart. Distinctive so it's identifiable
# in journal logs and systemd status (not 0, not 1, not a signal).
MEMORY_RESTART_EXIT_CODE = 75


async def graceful_memory_shutdown(*, rss_mb: int, threshold_mb: int) -> None:
    """Flush state, navigate clients, and exit with a non-zero code.

    Uses exit code 75 so systemd treats it as a failure (triggers
    ``Restart=on-failure``) and the journal shows a distinctive status.
    Logs at CRITICAL level so the Discord webhook processor fires.
    """
    logger.critical(
        "memory_threshold_exceeded_restarting",
        current_rss_mb=rss_mb,
        threshold_mb=threshold_mb,
    )
    await _flush_milkdown_to_crdt()
    await _persist_dirty_workspaces()
    await _invalidate_all_sessions()
    await _navigate_clients_to_restarting()
    logger.info("memory_restart_complete", rss_mb=rss_mb)
    raise SystemExit(MEMORY_RESTART_EXIT_CODE)


async def start_diagnostic_logger(
    *,
    interval_seconds: float = 300.0,
    memory_restart_threshold_mb: int = 3072,
) -> None:
    """Emit ``memory_diagnostic`` structlog event at regular intervals.

    When *memory_restart_threshold_mb* > 0 and current RSS exceeds that
    value, triggers a graceful shutdown: flush CRDT state, navigate
    clients to ``/restarting``, then ``sys.exit(0)`` so systemd restarts
    the process cleanly.
    """
    while True:
        try:
            snapshot = collect_snapshot()
            snapshot["event_loop_lag_ms"] = await measure_event_loop_lag()
            logger.info("memory_diagnostic", **snapshot)
            if _check_memory_threshold(
                snapshot, threshold_mb=memory_restart_threshold_mb
            ):
                rss_bytes = snapshot["current_rss_bytes"]
                await graceful_memory_shutdown(
                    rss_mb=rss_bytes // (1024 * 1024),
                    threshold_mb=memory_restart_threshold_mb,
                )
        except SystemExit:
            raise
        except Exception:
            logger.exception("diagnostic_snapshot_failed")
        await asyncio.sleep(interval_seconds)
