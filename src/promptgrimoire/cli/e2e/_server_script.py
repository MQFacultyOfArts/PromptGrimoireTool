"""E2E test server — launched as a subprocess by the CLI.

Near-duplicate of _SERVER_SCRIPT in tests/conftest.py — keep in sync.
Usage: python _server_script.py <port>
"""

import os
import sys
from pathlib import Path

for key in list(os.environ.keys()):
    if "PYTEST" in key or "NICEGUI" in key:
        del os.environ[key]

os.environ["DEV__AUTH_MOCK"] = "true"
os.environ["APP__STORAGE_SECRET"] = "test-secret-for-e2e"
# asyncio debug DISABLED — it causes event loop blocks (linecache.checkcache)
os.environ.setdefault("STYTCH__DEFAULT_ORG_ID", "mock-org-test")
os.environ.setdefault("STYTCH__SSO_CONNECTION_ID", "test-sso-connection-id")
os.environ.setdefault("STYTCH__PUBLIC_TOKEN", "test-public-token")
# Enable help button in mkdocs mode for E2E tests (no Algolia credentials needed)
os.environ.setdefault("HELP__HELP_ENABLED", "true")
os.environ.setdefault("HELP__HELP_BACKEND", "mkdocs")

port = int(sys.argv[1])

# Enable logging so pool events and diagnostics are visible
from promptgrimoire import _setup_logging

_setup_logging()

# --- Event loop watchdog (runs on a separate thread) ---
import asyncio
import structlog
import threading

_watchdog_logger = structlog.get_logger("e2e.watchdog")
_watchdog_loop_ref: asyncio.AbstractEventLoop | None = None


def _watchdog_loop():
    """Log event loop responsiveness every 2 seconds from a daemon thread."""
    import time

    global _watchdog_loop_ref
    while True:
        time.sleep(2)
        loop = _watchdog_loop_ref
        if loop is None:
            continue

        # Schedule a callback on the event loop and measure how long it takes
        event = threading.Event()
        t0 = time.monotonic()

        def _ping():
            event.set()

        try:
            loop.call_soon_threadsafe(_ping)
        except RuntimeError:
            _watchdog_logger.warning("WATCHDOG: event loop closed")
            break

        responded = event.wait(timeout=5.0)
        elapsed = time.monotonic() - t0

        if not responded:
            import sys as _sys
            import traceback as _tb

            _watchdog_logger.warning(
                "WATCHDOG: event loop DID NOT RESPOND in 5.0s"
                " — BLOCKED. Dumping stacks to file."
            )
            # Canary: does code after the log message run?
            with open("/tmp/wd-canary.txt", "w") as _f:
                _f.write("reached")
            dump_path = "/tmp/watchdog-stacks.log"
            try:
                import datetime as _dt

                fd = os.open(
                    dump_path,
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                    0o644,
                )

                def _w(s):
                    os.write(fd, s.encode())

                _w(f"\n=== BLOCKED at {_dt.datetime.now()} ===\n")
                frames = _sys._current_frames()
                _w(f"Threads: {len(frames)}\n")
                for tid, frame in frames.items():
                    tname = "unknown"
                    for t in threading.enumerate():
                        if t.ident == tid:
                            tname = t.name
                            break
                    _w(f"--- {tname} (tid={tid}) ---\n")
                    for entry in _tb.extract_stack(frame):
                        _w(
                            f"  {entry.filename}:{entry.lineno}"
                            f" in {entry.name}:"
                            f" {entry.line}\n"
                        )
                _w("=== END ===\n")
                os.close(fd)
            except Exception as exc:
                try:
                    efd = os.open(
                        dump_path,
                        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                        0o644,
                    )
                    os.write(
                        efd,
                        f"DUMP FAILED: {exc}\n".encode(),
                    )
                    os.close(efd)
                except Exception:
                    pass
        elif elapsed > 0.5:
            _watchdog_logger.warning(
                "WATCHDOG: event loop slow — responded in %.3fs", elapsed
            )
        else:
            _watchdog_logger.debug(
                "WATCHDOG: event loop OK — responded in %.3fs", elapsed
            )


_wd_thread = threading.Thread(target=_watchdog_loop, daemon=True)
_wd_thread.start()
# --- End watchdog ---

# --- Optionally monkey-patch compile_latex to skip latexmk ---
# When E2E_SKIP_LATEXMK=1 (the default for test-e2e), the Export PDF button
# produces a .tex file instead of a .pdf.  This exercises the EXACT same
# data-gathering path as real export (PageState with live CRDT) while
# avoiding the ~10s latexmk cost per test.
# Set E2E_SKIP_LATEXMK=0 for full PDF compilation (test-e2e-slow).
if os.environ.get("E2E_SKIP_LATEXMK", "1") == "1":

    async def _compile_latex_noop(tex_path, output_dir=None):
        return tex_path

    import promptgrimoire.export.pdf as _pdf_mod
    import promptgrimoire.export.pdf_export as _pdf_export_mod

    _pdf_mod.compile_latex = _compile_latex_noop  # type: ignore[assignment]  # intentional monkey-patch
    _pdf_export_mod.compile_latex = _compile_latex_noop  # type: ignore[assignment]  # intentional monkey-patch
# --- End monkey-patch ---

from nicegui import app, ui
import promptgrimoire.pages  # noqa: F401

# BrowserStack Local tunnel doesn't reliably forward WebSocket upgrades.
# Force polling-only transport so Socket.IO connects through HTTP.
if os.environ.get("E2E_BROWSERSTACK"):
    app.config.socket_io_js_transports = ["polling"]

from promptgrimoire import __file__ as _pg_init

_static_dir = Path(_pg_init).parent / "static"
app.add_static_files("/static", str(_static_dir))


# Diagnostic endpoint: pool + pg_stat + NiceGUI client stats
@app.get("/api/test/diagnostics")
async def _diagnostics():
    from nicegui import Client
    from promptgrimoire.crdt.persistence import (
        get_persistence_manager,
    )
    from promptgrimoire.db.engine import (
        _pool_status,
        _state,
        log_pool_and_pg_stats,
    )
    from promptgrimoire.pages.annotation import (
        _workspace_presence,
        _workspace_registry,
    )

    await log_pool_and_pg_stats()

    pool = _state.engine.sync_engine.pool if _state.engine else None
    pm = get_persistence_manager()
    all_tasks = asyncio.all_tasks()
    return {
        "pool": (_pool_status(pool) if pool else "no engine"),
        "engine_id": id(_state.engine),
        "engine_is_none": _state.engine is None,
        "nicegui_clients": len(Client.instances),
        "nicegui_delete_tasks": sum(
            len(c._delete_tasks) for c in Client.instances.values()
        ),
        "crdt_docs": len(pm._doc_registry),
        "crdt_dirty": len(pm._workspace_dirty),
        "crdt_pending_saves": len(pm._workspace_pending_saves),
        "presence_workspaces": len(_workspace_presence),
        "presence_total_clients": sum(len(v) for v in _workspace_presence.values()),
        "ws_registry": len(_workspace_registry._documents),
        "asyncio_tasks": len(all_tasks),
        "asyncio_task_names": _task_summary(all_tasks),
    }


def _task_summary(tasks):
    # Summarise asyncio tasks by coroutine/callback name.
    from collections import Counter

    names = []
    for t in tasks:
        coro = t.get_coro()
        if coro is not None:
            name = getattr(coro, "__qualname__", str(coro))
        else:
            name = t.get_name()
        # Keep last two segments for disambiguation (e.g. Event.wait vs
        # websocket_wait) instead of just the final name.
        parts = name.rsplit(".", 2)
        name = ".".join(parts[-2:]) if len(parts) >= 2 else name
        names.append(name)
    return dict(Counter(names).most_common(10))


# Cleanup endpoint: force-delete stale NiceGUI clients and engine.io
# sessions between tests. Disconnects at both layers to prevent
# task accumulation. See docs/e2e-debugging.md.
@app.post("/api/test/cleanup")
async def _cleanup():
    from nicegui import Client, core

    _cleanup_logger = structlog.get_logger("e2e.cleanup")
    before = len(Client.instances)
    tasks_before = len(asyncio.all_tasks())
    stale_ids = list(Client.instances.keys())
    deleted = 0
    sids_closed = 0
    t_total = _time.monotonic()
    for cid in stale_ids:
        c = Client.instances.get(cid)
        if c is not None:
            for sid in list(c._socket_to_document_id.keys()):
                try:
                    await core.sio.disconnect(sid)
                    sids_closed += 1
                except Exception:
                    pass
            c.delete()
            deleted += 1
            await asyncio.sleep(0)
    # Also disconnect any orphan engine.io sessions (WebSocket receive
    # tasks from connections whose NiceGUI client was already deleted
    # via the normal disconnect→delete_content→delete path).
    eio_closed = 0
    for eio_sid in list(core.sio.eio.sockets.keys()):
        try:
            await core.sio.eio.disconnect(eio_sid)
            eio_closed += 1
        except Exception:
            pass
    # Cancel orphan Event.wait tasks leaked by NiceGUI's page handler.
    # page.py creates background_tasks.create(client._waiting_for_connection.wait())
    # but never cancels it when the page result completes first.
    # See handle_handshake() which CLEARS _waiting_for_connection (not sets it).
    from nicegui import background_tasks as _bt

    orphan_wait = 0
    for t in list(_bt.running_tasks):
        if not t.done():
            coro = t.get_coro()
            qn = getattr(coro, "__qualname__", "") if coro else ""
            if qn == "Event.wait":
                t.cancel()
                orphan_wait += 1
    await asyncio.sleep(0)  # let cancellations propagate
    elapsed_total = _time.monotonic() - t_total
    tasks_after = len(asyncio.all_tasks())
    _cleanup_logger.warning(
        "CLEANUP: clients=%d/%d sids=%d eio=%d orphan_wait=%d"
        " tasks=%d->%d elapsed=%.3fs",
        deleted,
        before,
        sids_closed,
        eio_closed,
        orphan_wait,
        tasks_before,
        tasks_after,
        elapsed_total,
    )
    return {
        "deleted": deleted,
        "before": before,
        "sids_closed": sids_closed,
        "eio_closed": eio_closed,
        "orphan_wait": orphan_wait,
        "tasks_before": tasks_before,
        "tasks_after": tasks_after,
        "elapsed": elapsed_total,
    }


# Hand the running event loop to the watchdog thread
@app.on_startup
async def _hand_loop_to_watchdog():
    global _watchdog_loop_ref
    loop = asyncio.get_running_loop()
    _watchdog_loop_ref = loop
    # NOTE: loop.set_debug(True) CAUSES the event-loop block!
    # In debug mode, every create_task() calls traceback.extract_stack()
    # which calls linecache.checkcache() — O(n) filesystem stat() calls
    # per stack frame per task. With many modules and frequent task
    # creation, this blocks the event loop for 5-7 seconds.
    # See watchdog-stacks.log for evidence.
    _watchdog_logger.warning(
        "WATCHDOG: acquired loop ref, asyncio debug OFF (debug causes block)"
    )


# Instrument NiceGUI client.delete() to measure time and element count.
import time as _time
from nicegui import Client as _Client

_orig_delete = _Client.delete
_delete_logger = structlog.get_logger("e2e.client_delete")


def _timed_delete(self):
    n_elements = len(self.elements) if hasattr(self, "elements") else -1
    t0 = _time.monotonic()
    _orig_delete(self)
    elapsed = _time.monotonic() - t0
    _delete_logger.warning(
        "CLIENT_DELETE: id=%s elements=%d elapsed=%.3fs",
        self.id[:8],
        n_elements,
        elapsed,
    )


_Client.delete = _timed_delete  # type: ignore[assignment]  # intentional monkey-patch

ui.run(
    port=port,
    reload=False,
    show=False,
    storage_secret="test-secret-for-e2e",
    reconnect_timeout=0.5,
)
