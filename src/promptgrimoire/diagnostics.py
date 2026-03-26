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

    # Access annotation module state without importing (avoids NiceGUI page
    # registration side effects). Same pattern as pages/restart.py.
    mod = sys.modules.get("promptgrimoire.pages.annotation")
    ws_registry_size = 0
    ws_presence_workspaces = 0
    ws_presence_clients = 0
    if mod is not None:
        ws_registry_size = len(mod._workspace_registry._documents)
        ws_presence = mod._workspace_presence
        ws_presence_workspaces = len(ws_presence)
        ws_presence_clients = sum(len(v) for v in ws_presence.values())

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
    }


async def start_diagnostic_logger(*, interval_seconds: float = 300.0) -> None:
    """Emit ``memory_diagnostic`` structlog event at regular intervals."""
    while True:
        try:
            snapshot = collect_snapshot()
            logger.info("memory_diagnostic", **snapshot)
        except Exception:
            logger.exception("diagnostic_snapshot_failed")
        await asyncio.sleep(interval_seconds)
