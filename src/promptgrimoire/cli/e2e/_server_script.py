"""E2E test server — launched as a subprocess by the CLI.

Near-duplicate of _SERVER_SCRIPT in tests/conftest.py — keep in sync.
Usage: python _server_script.py <port>
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

for key in list(os.environ.keys()):
    if "PYTEST" in key or "NICEGUI" in key:
        del os.environ[key]

os.environ["DEV__AUTH_MOCK"] = "true"
os.environ["APP__STORAGE_SECRET"] = "test-secret-for-e2e"
# asyncio debug DISABLED — it causes event loop blocks (linecache.checkcache)
# Disable admission gate — production load-protection that interferes with
# latexmk tests (event loop lag triggers AIMD cap reduction, redirecting to /queue)
os.environ.setdefault("ADMISSION__ENABLED", "false")
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

import structlog

_attestation_logger = structlog.get_logger("e2e.attestation")


def _full_source_identity() -> str:
    """Return the full commit observed by the measured server process."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:
        _attestation_logger.exception("perf_source_identity_unavailable")
        return "unknown"
    return result.stdout.strip()


_SOURCE_IDENTITY = _full_source_identity()
_BOOT_ID = os.environ.get("E2E_PERF_BOOT_ID", "unmanaged")
_PREPARATION_ID = os.environ.get("_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID", "unmanaged")

# --- GC pause recorder ---
# Convicts or acquits gen-2 GC for the sub-second event-loop stalls seen
# at n=200 (spike magnitude tracked RSS growth; uninstrumented until now).
# The callback runs synchronously around every collection, so it must
# stay tiny. Drained by /api/test/diagnostics each poll.
import gc
import time as _time

# No lock: the callback fires on whichever thread triggers collection and
# the endpoint drains on the loop thread; a torn read misreports one
# sample of diagnostics, which is acceptable for this instrument.
_GC_NOTABLE_PAUSE_MS = 50.0

_gc_state: dict[str, Any] = {
    "start_ns": 0,
    "pause_max_ms": [0.0, 0.0, 0.0],
    "pauses_over_50ms": 0,
    "count": [0, 0, 0],
}


def _gc_callback(phase: str, info: dict[str, Any]) -> None:
    if phase == "start":
        _gc_state["start_ns"] = _time.perf_counter_ns()
        return
    gen = info.get("generation", 0)
    dur_ms = (_time.perf_counter_ns() - _gc_state["start_ns"]) / 1e6
    _gc_state["count"][gen] += 1
    _gc_state["pause_max_ms"][gen] = max(_gc_state["pause_max_ms"][gen], dur_ms)
    if dur_ms > _GC_NOTABLE_PAUSE_MS:
        _gc_state["pauses_over_50ms"] += 1


gc.callbacks.append(_gc_callback)


def _drain_gc_stats() -> dict[str, Any]:
    out = {
        "pause_max_ms": [round(v, 1) for v in _gc_state["pause_max_ms"]],
        "pauses_over_50ms": _gc_state["pauses_over_50ms"],
        "count": list(_gc_state["count"]),
    }
    _gc_state["pause_max_ms"] = [0.0, 0.0, 0.0]
    _gc_state["pauses_over_50ms"] = 0
    _gc_state["count"] = [0, 0, 0]
    return out


# --- Event loop watchdog (runs on a separate thread) ---
import asyncio
import structlog
import threading

_watchdog_logger = structlog.get_logger("e2e.watchdog")
_watchdog_loop_ref: asyncio.AbstractEventLoop | None = None
_WATCHDOG_SLOW_THRESHOLD_S = 0.5


def _ping_event_loop(
    loop: asyncio.AbstractEventLoop, *, timeout: float
) -> tuple[bool, float]:
    """Schedule a no-op callback on *loop* and time the round trip.

    Returns (responded, elapsed_seconds). May raise RuntimeError if the
    loop is already closed.
    """
    import time

    event = threading.Event()
    t0 = time.monotonic()

    def _ping():
        event.set()

    loop.call_soon_threadsafe(_ping)
    responded = event.wait(timeout=timeout)
    return responded, time.monotonic() - t0


def _dump_watchdog_stacks(dump_path: str) -> None:
    """Best-effort dump of every thread's stack to *dump_path*."""
    import sys as _sys
    import traceback as _tb

    try:
        import datetime as _dt

        fd = os.open(dump_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)

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
                _w(f"  {entry.filename}:{entry.lineno} in {entry.name}: {entry.line}\n")
        _w("=== END ===\n")
        os.close(fd)
    except Exception as exc:
        try:
            efd = os.open(dump_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.write(efd, f"DUMP FAILED: {exc}\n".encode())
            os.close(efd)
        except Exception:
            pass


def _watchdog_loop():
    """Log event loop responsiveness every 2 seconds from a daemon thread."""
    import time

    global _watchdog_loop_ref
    while True:
        time.sleep(2)
        loop = _watchdog_loop_ref
        if loop is None:
            continue

        try:
            responded, elapsed = _ping_event_loop(loop, timeout=5.0)
        except RuntimeError:
            _watchdog_logger.warning("WATCHDOG: event loop closed")
            break

        if not responded:
            _watchdog_logger.warning(
                "WATCHDOG: event loop DID NOT RESPOND in 5.0s"
                " — BLOCKED. Dumping stacks to file."
            )
            # Canary: does code after the log message run?
            with open("/tmp/wd-canary.txt", "w") as _f:
                _f.write("reached")
            _dump_watchdog_stacks("/tmp/watchdog-stacks.log")
        elif elapsed > _WATCHDOG_SLOW_THRESHOLD_S:
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

    async def _compile_latex_noop(
        tex_path: Path, output_dir: Path | None = None
    ) -> Path:
        return tex_path

    import promptgrimoire.export.pdf as _pdf_mod
    import promptgrimoire.export.pdf_export as _pdf_export_mod

    # setattr() rather than attribute assignment: ty pins a module-level
    # `async def`'s inferred attribute type to that specific function
    # definition, so a same-signature replacement is rejected even though
    # it is runtime-identical to `_pdf_mod.compile_latex = _compile_latex_noop`.
    # setattr() isn't attribute-type-checked, so it expresses the same
    # intentional monkey-patch without a false-positive diagnostic. B010
    # (ruff's setattr-with-constant-name lint) would "fix" this straight
    # back to the assignment form ruff and ty disagree on -- suppressed here,
    # not on a type diagnostic.
    setattr(_pdf_mod, "compile_latex", _compile_latex_noop)  # noqa: B010
    setattr(_pdf_export_mod, "compile_latex", _compile_latex_noop)  # noqa: B010
# --- End monkey-patch ---

from nicegui import app, ui
import promptgrimoire.pages  # noqa: F401
import promptgrimoire.export.download  # noqa: F401 — registers /export/{token}/download route

if os.environ.get("E2E_INSTRUMENT_OUTBOX") == "1":
    import time as _time

    from engineio.async_drivers.asgi import WebSocket as _EngineIOWebSocket
    from nicegui.outbox import Outbox as _Outbox

    from promptgrimoire.diagnostics import record_load_metric as _record_load_metric

    _LARGE_SEND_THRESHOLD_BYTES = 100_000

    _original_enqueue_update = _Outbox.enqueue_update
    _original_emit = _Outbox._emit
    _original_websocket_send = _EngineIOWebSocket.send

    def _instrumented_enqueue_update(self: Any, element: Any) -> None:
        self._perf_last_update_enqueue = _time.monotonic()
        _original_enqueue_update(self, element)

    async def _instrumented_emit(self: Any, message: Any) -> None:
        _client_id, message_type, data = message
        if message_type != "update":
            await _original_emit(self, message)
            return

        if enqueued_at := getattr(self, "_perf_last_update_enqueue", None):
            _record_load_metric(
                "outbox_update_prepare_ms",
                round((_time.monotonic() - enqueued_at) * 1000, 1),
            )
        _record_load_metric("outbox_update_elements", len(data))
        started = _time.monotonic()
        try:
            await _original_emit(self, message)
        finally:
            _record_load_metric(
                "outbox_update_emit_ms",
                round((_time.monotonic() - started) * 1000, 1),
            )

    async def _instrumented_websocket_send(self: Any, message: Any) -> None:
        size = len(message.encode()) if isinstance(message, str) else len(message)
        started = _time.monotonic()
        try:
            await _original_websocket_send(self, message)
        finally:
            elapsed_ms = round((_time.monotonic() - started) * 1000, 1)
            _record_load_metric("engineio_websocket_send_ms", elapsed_ms)
            if size >= _LARGE_SEND_THRESHOLD_BYTES:
                _record_load_metric("engineio_large_send_ms", elapsed_ms)
                _record_load_metric("engineio_large_send_bytes", size)

    _Outbox.enqueue_update = _instrumented_enqueue_update  # type: ignore[assignment] -- perf-only NiceGUI instrumentation
    _Outbox._emit = _instrumented_emit  # type: ignore[assignment] -- perf-only NiceGUI instrumentation
    _EngineIOWebSocket.send = _instrumented_websocket_send  # type: ignore[assignment] -- perf-only Engine.IO instrumentation

from promptgrimoire import __file__ as _pg_init

_static_dir = Path(_pg_init).parent / "static"
app.add_static_files("/static", str(_static_dir))


# Health check endpoint (mirrors promptgrimoire.__init__, supports HEAD + GET)
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def _healthz(_request):
    return PlainTextResponse("ok")


app.routes.insert(0, Route("/healthz", _healthz, methods=["GET", "HEAD"]))

# Queue, paused, welcome pages and status API (raw Starlette)
from promptgrimoire.queue_handlers import (
    paused_page_handler,
    queue_page_handler,
    queue_status_handler,
    welcome_page_handler,
)

app.routes.insert(0, Route("/api/queue/status", queue_status_handler, methods=["GET"]))
app.routes.insert(0, Route("/queue", queue_page_handler, methods=["GET"]))
app.routes.insert(0, Route("/paused", paused_page_handler, methods=["GET"]))
app.routes.insert(0, Route("/welcome", welcome_page_handler, methods=["GET"]))

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


# Vue sidebar spike page — validates custom Vue component wiring in a real browser.
# Used by tests/e2e/test_vue_sidebar_spike_e2e.py to exercise Phase 3-4 go/no-go
# criteria that cannot be tested with NiceGUI user_simulation (no Vue runtime).
@ui.page("/test/vue-sidebar-spike")
def _vue_sidebar_spike_page() -> None:
    from promptgrimoire.pages.annotation.sidebar import AnnotationSidebar
    from promptgrimoire.pages.annotation.tags import TagInfo

    tag_map = {
        "tag-1": TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="tag-1"),
        "tag-2": TagInfo(name="Legal Issues", colour="#ff7f0e", raw_key="tag-2"),
    }
    tag_colours = {"tag-1": "#1f77b4", "tag-2": "#ff7f0e"}
    highlights = [
        {
            "id": "hl-1",
            "start_char": 10,
            "end_char": 50,
            "tag": "tag-1",
            "text": "highlighted text one",
            "author": "Alice",
            "user_id": "u-1",
            "para_ref": "[3]",
            "created_at": "2026-03-01T10:00:00",
            "comments": [
                {
                    "id": "c-1",
                    "author": "Bob",
                    "user_id": "u-2",
                    "text": "Good point",
                    "created_at": "2026-03-01T11:00:00",
                },
            ],
        },
        {
            "id": "hl-2",
            "start_char": 60,
            "end_char": 90,
            "tag": "tag-2",
            "text": "highlighted text two",
            "author": "Carol",
            "user_id": "u-3",
            "para_ref": "",
            "created_at": "2026-03-01T12:00:00",
            "comments": [],
        },
    ]

    received_events: list[dict] = []

    def _on_toggle_expand(payload: dict) -> None:
        received_events.append(payload)
        # Update a visible label so Playwright can observe the event
        event_label.set_text(f"event:{payload.get('id', '?')}")

    sidebar = AnnotationSidebar(on_toggle_expand=_on_toggle_expand)
    sidebar.props('data-testid="spike-sidebar"')
    sidebar.refresh_items(
        highlights=highlights,
        tag_info_map=tag_map,
        tag_colours=tag_colours,
        user_id="u-1",
        viewer_is_privileged=False,
        privileged_user_ids=frozenset(),
        can_annotate=True,
        anonymous_sharing=False,
    )

    # Label to observe toggle_expand payloads from Playwright
    event_label = ui.label("event:none")
    event_label.props('data-testid="spike-event-label"')

    # Button to trigger set_items with a single item (for prop update test)
    def _update_items() -> None:
        sidebar.set_items(
            [
                {
                    "id": "hl-3",
                    "tag_key": "tag-1",
                    "tag_display": "Jurisdiction",
                    "color": "#1f77b4",
                    "start_char": 100,
                    "end_char": 120,
                    "para_ref": "",
                    "author": "Dave",
                    "display_author": "Dave",
                    "initials": "D.",
                    "user_id": "u-4",
                    "can_delete": False,
                    "can_annotate": True,
                    "text": "updated text",
                    "text_preview": "updated text",
                    "comments": [],
                }
            ]
        )

    ui.button("Update Items", on_click=_update_items).props(
        'data-testid="spike-update-btn"'
    )


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
    from sqlalchemy import text
    from promptgrimoire.pages.annotation import (
        _workspace_presence,
        _workspace_registry,
    )

    await log_pool_and_pg_stats()

    pool = _state.engine.sync_engine.pool if _state.engine else None
    pm = get_persistence_manager()
    from promptgrimoire.diagnostics import _collect_memory, drain_load_metrics

    mem = _collect_memory()
    all_tasks = asyncio.all_tasks()
    database_name = None
    database_query_ok = False
    if _state.engine is not None:
        try:
            async with _state.engine.connect() as connection:
                result = await connection.execute(text("SELECT current_database()"))
                database_name = result.scalar_one()
            database_query_ok = True
        except Exception:
            _attestation_logger.exception("perf_database_attestation_failed")
    pool_mode_reason = (
        "pool_fidelity"
        if os.environ.get("_PROMPTGRIMOIRE_POOL_FIDELITY") == "1"
        else "test_null_pool"
        if os.environ.get("_PROMPTGRIMOIRE_USE_NULL_POOL") == "1"
        else "configured_queue_pool"
    )
    return {
        "boot_id": _BOOT_ID,
        "pid": os.getpid(),
        "source_identity": _SOURCE_IDENTITY,
        "database_name": database_name,
        "database_query_ok": database_query_ok,
        "preparation_id": _PREPARATION_ID,
        "pool_mode_reason": pool_mode_reason,
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
        "load_metrics": drain_load_metrics(),
        "gc": _drain_gc_stats(),
    }


@app.post("/api/test/persist-crdt")
async def _persist_crdt():
    """Provide an exact persistence barrier for E2E durability assertions."""
    from promptgrimoire.crdt.persistence import get_persistence_manager

    manager = get_persistence_manager()
    dirty_before = len(manager._workspace_dirty)
    await manager.persist_all_dirty_workspaces()
    return {
        "dirty_before": dirty_before,
        "dirty_after": len(manager._workspace_dirty),
    }


_QUALNAME_TAIL_SEGMENTS = 2


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
        parts = name.rsplit(".", _QUALNAME_TAIL_SEGMENTS)
        name = (
            ".".join(parts[-_QUALNAME_TAIL_SEGMENTS:])
            if len(parts) >= _QUALNAME_TAIL_SEGMENTS
            else name
        )
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


async def _cleanup_stale_clients() -> tuple[int, int]:
    """Force-delete stale NiceGUI clients and their socket.io SIDs.

    Returns (deleted, sids_closed).
    """
    from nicegui import Client, core

    deleted = 0
    sids_closed = 0
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
    return deleted, sids_closed


async def _cleanup_orphan_eio_sessions() -> int:
    """Disconnect orphan engine.io sessions (WebSocket receive tasks from
    connections whose NiceGUI client was already deleted via the normal
    disconnect→delete_content→delete path).

    Returns eio_closed.
    """
    from nicegui import core

    eio_closed = 0
    for eio_sid in list(core.sio.eio.sockets.keys()):
        try:
            await core.sio.eio.disconnect(eio_sid)
            eio_closed += 1
        except Exception:
            pass
    return eio_closed


def _cleanup_orphan_event_waits() -> int:
    """Cancel orphan Event.wait tasks leaked by NiceGUI's page handler.

    See handle_handshake() which CLEARS _waiting_for_connection (not sets
    it), leaving the wait() task orphaned. Returns orphan_wait.
    """
    from nicegui import background_tasks as _bt

    orphan_wait = 0
    for t in list(_bt.running_tasks):
        if not t.done():
            coro = t.get_coro()
            qn = getattr(coro, "__qualname__", "") if coro else ""
            if qn == "Event.wait":
                t.cancel()
                orphan_wait += 1
    return orphan_wait


@app.post("/api/test/cleanup")
async def _cleanup(mode: str = "all"):
    from nicegui import Client

    _cleanup_logger = structlog.get_logger("e2e.cleanup")
    before = len(Client.instances)
    tasks_before = len(asyncio.all_tasks())
    t_total = _time.monotonic()
    deleted = 0
    sids_closed = 0
    eio_closed = 0
    orphan_wait = 0

    if mode in ("all", "clients_only"):
        deleted, sids_closed = await _cleanup_stale_clients()

    if mode in ("all", "eio_only"):
        eio_closed = await _cleanup_orphan_eio_sessions()

    if mode in ("all", "events_only"):
        orphan_wait = _cleanup_orphan_event_waits()

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
_diagnostic_logger_task: asyncio.Task[None] | None = None


@app.on_startup
async def _start_export_worker() -> None:
    global _export_worker_task
    _export_worker_task = asyncio.create_task(start_export_worker())


@app.on_startup
async def _start_diagnostic_logger() -> None:
    """Run production diagnostics during performance probes."""
    global _diagnostic_logger_task
    from promptgrimoire.diagnostics import start_diagnostic_logger

    interval = get_settings().app.diagnostic_interval_seconds
    _diagnostic_logger_task = asyncio.create_task(
        start_diagnostic_logger(
            interval_seconds=interval,
            memory_restart_threshold_mb=0,
        )
    )


@app.on_shutdown
async def _stop_export_worker() -> None:
    global _diagnostic_logger_task, _export_worker_task
    if _diagnostic_logger_task is not None:
        _diagnostic_logger_task.cancel()
        await asyncio.gather(_diagnostic_logger_task, return_exceptions=True)
        _diagnostic_logger_task = None
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
    reconnect_timeout=float(os.environ.get("E2E_RECONNECT_TIMEOUT", "0.5")),
)
