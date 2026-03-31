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
from promptgrimoire.logging_config import setup_logging

setup_logging()

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
import promptgrimoire.export.download  # noqa: F401 — registers /export/{token}/download route

# BrowserStack Local tunnel doesn't reliably forward WebSocket upgrades.
# Force polling-only transport so Socket.IO connects through HTTP.
if os.environ.get("E2E_BROWSERSTACK"):
    app.config.socket_io_js_transports = ["polling"]

from promptgrimoire import __file__ as _pg_init

_static_dir = Path(_pg_init).parent / "static"
app.add_static_files("/static", str(_static_dir))


# Health check endpoint (mirrors promptgrimoire.__init__, supports HEAD + GET)
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def _healthz(_request):
    return PlainTextResponse("ok")


app.routes.insert(0, Route("/healthz", _healthz, methods=["GET", "HEAD"]))

# Queue page and status API (raw Starlette, zero NiceGUI overhead)
from promptgrimoire.queue_handlers import queue_page_handler, queue_status_handler

app.routes.insert(0, Route("/api/queue/status", queue_status_handler, methods=["GET"]))
app.routes.insert(0, Route("/queue", queue_page_handler, methods=["GET"]))

# Initialise admission gate so /queue and /api/queue/status work
from promptgrimoire.admission import init_admission
from promptgrimoire.config import get_settings

init_admission(get_settings().admission)

# Dev endpoints for admission gate testing
from promptgrimoire.dev_endpoints import admission_control_handler, block_loop_handler

app.routes.insert(
    0, Route("/api/dev/admission", admission_control_handler, methods=["POST"])
)
app.routes.insert(0, Route("/api/dev/block-loop", block_loop_handler, methods=["POST"]))


# Session identity page — exercises the full @ui.page -> background_tasks.create
# path.  Used by test_session_contamination.py to verify that concurrent page
# loads resolve the correct request_contextvar (and thus the correct user storage).
@ui.page("/test/session-identity")
async def _session_identity_page() -> None:
    # First read: capture identity immediately.
    auth_user = app.storage.user.get("auth_user")
    email_before = auth_user.get("email", "unknown") if auth_user else "unauthenticated"

    # Yield aggressively to maximise interleaving with concurrent requests.
    # In production, real page handlers yield many times (DB queries, CRDT loads).
    for _ in range(10):
        await asyncio.sleep(0)

    # Second read: check if identity is still the same after yielding.
    # If request_contextvar was overwritten by another request between yields,
    # this read would resolve a different user's storage.
    auth_user_after = app.storage.user.get("auth_user")
    email_after = (
        auth_user_after.get("email", "unknown")
        if auth_user_after
        else "unauthenticated"
    )

    # Render both: test checks email_before == email_after == expected.
    ui.label(email_before).props('data-testid="session-email"')
    ui.label(email_after).props('data-testid="session-email-after"')


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
    from promptgrimoire.diagnostics import _collect_memory

    mem = _collect_memory()
    all_tasks = asyncio.all_tasks()
    return {
        "pool": (_pool_status(pool) if pool else "no engine"),
        "engine_id": id(_state.engine),
        "engine_is_none": _state.engine is None,
        "rss_bytes": mem.get("current_rss_bytes"),
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
#
# mode parameter controls which cleanup actions run:
#   all (default) — all three actions (original behaviour)
#   clients_only  — force-delete NiceGUI clients + their SIDs only
#   eio_only      — disconnect orphan engine.io sessions only
#   events_only   — cancel orphan Event.wait tasks only
@app.post("/api/test/cleanup")
async def _cleanup(mode: str = "all"):
    from nicegui import Client, core

    _cleanup_logger = structlog.get_logger("e2e.cleanup")
    before = len(Client.instances)
    tasks_before = len(asyncio.all_tasks())
    t_total = _time.monotonic()
    deleted = 0
    sids_closed = 0
    eio_closed = 0
    orphan_wait = 0

    # Action 1: Force-delete NiceGUI clients and their socket.io SIDs
    if mode in ("all", "clients_only"):
        stale_ids = list(Client.instances.keys())
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

    # Action 2: Disconnect orphan engine.io sessions (WebSocket receive
    # tasks from connections whose NiceGUI client was already deleted
    # via the normal disconnect→delete_content→delete path).
    if mode in ("all", "eio_only"):
        for eio_sid in list(core.sio.eio.sockets.keys()):
            try:
                await core.sio.eio.disconnect(eio_sid)
                eio_closed += 1
            except Exception:
                pass

    # Action 3: Cancel orphan Event.wait tasks leaked by NiceGUI's page
    # handler. See handle_handshake() which CLEARS _waiting_for_connection
    # (not sets it), leaving the wait() task orphaned.
    if mode in ("all", "events_only"):
        from nicegui import background_tasks as _bt

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
    _cleanup_logger.debug(
        "CLEANUP[%s]: clients=%d/%d sids=%d eio=%d orphan_wait=%d"
        " tasks=%d->%d elapsed=%.3fs",
        mode,
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
        "mode": mode,
        "deleted": deleted,
        "before": before,
        "sids_closed": sids_closed,
        "eio_closed": eio_closed,
        "orphan_wait": orphan_wait,
        "tasks_before": tasks_before,
        "tasks_after": tasks_after,
        "elapsed": elapsed_total,
    }


# GC + malloc_trim endpoint for memory probe (#434).
# Forces Python gc.collect() and glibc malloc_trim(0), returns
# before/after RSS and collection counts.
@app.post("/api/test/gc")
async def _gc():
    import ctypes
    import gc

    from promptgrimoire.diagnostics import _collect_memory

    rss_before = _collect_memory().get("current_rss_bytes")
    collected_1 = gc.collect()
    collected_2 = gc.collect()  # second pass for weak ref callbacks
    rss_after_gc = _collect_memory().get("current_rss_bytes")
    trimmed = False
    try:
        libc = ctypes.CDLL("libc.so.6")
        trimmed = libc.malloc_trim(0) != 0
    except OSError:
        pass
    rss_after_trim = _collect_memory().get("current_rss_bytes")
    return {
        "rss_before": rss_before,
        "rss_after_gc": rss_after_gc,
        "rss_after_trim": rss_after_trim,
        "gc_collected": collected_1 + collected_2,
        "malloc_trimmed": trimmed,
    }


# Start the export worker so queue-based export jobs get processed (#402)
from promptgrimoire.export.worker import start_export_worker

_export_worker_task: asyncio.Task[None] | None = None


@app.on_startup
async def _start_export_worker() -> None:
    global _export_worker_task
    _export_worker_task = asyncio.create_task(start_export_worker())


@app.on_shutdown
async def _stop_export_worker() -> None:
    global _export_worker_task
    if _export_worker_task is not None:
        _export_worker_task.cancel()
        await asyncio.gather(_export_worker_task, return_exceptions=True)
        _export_worker_task = None


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
    _delete_logger.debug(
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
