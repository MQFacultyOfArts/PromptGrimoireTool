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
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from promptgrimoire.admission import AdmissionState

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

    from promptgrimoire.auth.client_registry import (  # noqa: PLC0415
        _registry as auth_registry,
    )

    # Count authenticated users (distinct user_ids with non-deleted clients;
    # deregistration is on Client.on_delete, not on socket disconnect)
    authed_users = sum(1 for clients in auth_registry.values() if clients)
    authed_clients = sum(len(clients) for clients in auth_registry.values())

    return {
        # Memory
        "current_rss_bytes": memory["current_rss_bytes"],
        "peak_rss_bytes": memory["peak_rss_bytes"],
        # NiceGUI clients
        "clients_total": len(Client.instances),
        "clients_connected": sum(
            1 for c in Client.instances.values() if c.has_socket_connection
        ),
        "clients_authenticated": authed_clients,
        "users_authenticated": authed_users,
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

    NiceGUI's ``FilePersistentDict.backup()`` uses
    ``background_tasks.create_lazy()`` — an async task that may never
    flush to disk before ``systemctl restart`` kills the process.  To
    guarantee the invalidation survives process death, we write each
    modified storage file **synchronously** after clearing the key.
    """
    from nicegui import app  # noqa: PLC0415
    from nicegui import json as nicegui_json  # noqa: PLC0415
    from nicegui.persistence.file_persistent_dict import (  # noqa: PLC0415
        FilePersistentDict,
    )

    user_stores = app.storage._users  # pyright: ignore[reportPrivateUsage]
    flushed = 0
    for user_storage in user_stores.values():
        if "auth_user" not in user_storage:
            continue
        # Remove the key from the in-memory ObservableDict.  Use
        # dict.pop to bypass the on_change hook (which would schedule
        # another lazy backup we can't await).
        dict.pop(user_storage, "auth_user", None)
        # Sync-write the file directly so the change survives SIGTERM.
        if isinstance(user_storage, FilePersistentDict):
            user_storage.filepath.write_text(
                nicegui_json.dumps(user_storage),
                encoding=user_storage.encoding,
            )
        flushed += 1
    logger.info("sessions_invalidated", count=len(user_stores), flushed=flushed)


def invalidate_sessions_on_disk(storage_dir: Path | None = None) -> None:
    """Clear auth_user from all NiceGUI storage files on disk.

    Called at app startup to guarantee no stale sessions survive
    regardless of how the previous process died (SIGTERM, OOM, crash).
    Operates on the raw JSON files, not in-memory PersistentDict
    instances (which are empty at startup).

    Args:
        storage_dir: Directory containing ``storage-user-*.json`` files.
            Defaults to NiceGUI's configured storage path, falling back
            to ``.nicegui`` in the working directory.
    """
    import json  # noqa: PLC0415

    if storage_dir is None:
        from nicegui import core  # noqa: PLC0415

        raw = core.app.storage.path if hasattr(core.app.storage, "path") else None
        storage_dir = Path(".nicegui") if raw is None else Path(raw)

    if not storage_dir.exists():
        logger.debug("startup_invalidation_skipped", reason="no storage directory")
        return

    cleared = 0
    for path in storage_dir.glob("storage-user-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "auth_user" in data:
                del data["auth_user"]
                path.write_text(json.dumps(data), encoding="utf-8")
                cleared += 1
        except Exception:
            logger.warning(
                "startup_invalidation_file_error", path=str(path), exc_info=True
            )

    if cleared:
        logger.info("startup_sessions_invalidated", cleared=cleared)


async def _navigate_clients_to_restarting() -> None:
    """Navigate all connected NiceGUI clients to /restarting."""
    from nicegui import Client  # noqa: PLC0415

    for client in list(Client.instances.values()):
        if not client.has_socket_connection:
            continue
        try:
            client.run_javascript(
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
    # Navigate BEFORE invalidating — clients still rendering pages will
    # hit `assert auth_user is not None` if sessions vanish mid-load.
    await _navigate_clients_to_restarting()
    await _invalidate_all_sessions()
    logger.info("memory_restart_complete", rss_mb=rss_mb)
    raise SystemExit(MEMORY_RESTART_EXIT_CODE)


def _enrich_snapshot_with_admission(
    snapshot: dict[str, Any],
    admission: AdmissionState,
    admitted_count: int,
) -> None:
    """Run admission gate cycle and add fields to *snapshot*.

    Performs AIMD cap update, batch admission, and expiry sweep, then
    writes ``admission_cap``, ``admission_admitted``,
    ``admission_queue_depth``, and ``admission_tickets`` into *snapshot*
    so they appear in the ``memory_diagnostic`` structlog event.
    """
    admission.update_cap(
        lag_ms=snapshot["event_loop_lag_ms"],
        admitted_count=admitted_count,
    )
    admission.admit_batch(admitted_count=admitted_count)
    admission.sweep_expired()

    snapshot["admission_cap"] = admission.cap
    snapshot["admission_admitted"] = admitted_count
    snapshot["admission_queue_depth"] = len(admission._queue)
    snapshot["admission_tickets"] = len(admission._tickets)


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
    from promptgrimoire.admission import get_admission_state  # noqa: PLC0415
    from promptgrimoire.auth import client_registry  # noqa: PLC0415

    while True:
        try:
            snapshot = collect_snapshot()
            snapshot["event_loop_lag_ms"] = await measure_event_loop_lag()

            # Admission gate: AIMD cap adjustment + batch admission
            _admission = get_admission_state()
            _admitted_count = len(client_registry._registry)
            _enrich_snapshot_with_admission(
                snapshot,
                _admission,
                _admitted_count,
            )

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
