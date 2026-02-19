"""Command-line utilities for PromptGrimoire development.

Provides pytest wrappers with logging and timing for debugging test failures.
Also includes admin bootstrap commands.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import IO

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _pre_test_db_cleanup() -> None:
    """Run Alembic migrations and truncate all tables before tests.

    This runs once in the CLI process before pytest is spawned,
    avoiding deadlocks when xdist workers try to truncate simultaneously.

    Uses Settings.dev.test_database_url (not database.url) to prevent
    accidentally truncating production or development databases.
    """
    from promptgrimoire.config import get_settings
    from promptgrimoire.db.bootstrap import ensure_database_exists

    test_database_url = get_settings().dev.test_database_url
    if not test_database_url:
        return  # No test database configured — skip

    # Auto-create the branch-specific database if it doesn't exist
    ensure_database_exists(test_database_url)

    # Override DATABASE__URL so Settings resolves to the test database
    os.environ["DATABASE__URL"] = test_database_url
    get_settings.cache_clear()

    # Run Alembic migrations
    project_root = Path(__file__).parent.parent.parent
    result = subprocess.run(  # nosec: B603, B607
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        console.print(f"[red]Alembic migration failed:[/]\n{result.stderr}")
        sys.exit(1)

    # Truncate all tables (sync connection, single process — no race)
    # Reference tables seeded by migrations are excluded — their data
    # is part of the schema, not transient test data.
    from sqlalchemy import create_engine, text

    _REFERENCE_TABLES = frozenset({"alembic_version", "permission", "course_role"})

    sync_url = test_database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        table_query = conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
            """)
        )
        tables = [
            row[0] for row in table_query.fetchall() if row[0] not in _REFERENCE_TABLES
        ]

        if tables:
            quoted_tables = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))

    engine.dispose()


def _build_test_header(
    title: str,
    branch: str | None,
    db_name: str,
    start_time: datetime,
    command_str: str,
) -> tuple[Text, str]:
    """Build Rich Text panel content and plain-text log header for test runs.

    Returns:
        (rich_text, log_header) tuple.
    """
    header_text = Text()
    header_text.append(f"{title}\n", style="bold")
    header_text.append(f"Branch: {branch or 'detached/unknown'}\n", style="dim")
    header_text.append(f"Test DB: {db_name}\n", style="dim")
    header_text.append(f"Started: {start_time.strftime('%H:%M:%S')}\n", style="dim")
    header_text.append(f"Command: {command_str}", style="cyan")

    log_header = f"""{"=" * 60}
{title}
Branch: {branch or "detached/unknown"}
Test DB: {db_name}
Started: {start_time.isoformat()}
Command: {command_str}
{"=" * 60}

"""
    return header_text, log_header


def _stream_plain(
    process: subprocess.Popen[str],
    log_file: IO[str],
) -> int:
    """Stream pytest output directly — for piped/CI use with rtk filtering."""
    for line in process.stdout or []:
        print(line, end="")
        log_file.write(line)
        log_file.flush()
    process.wait()
    return process.returncode


# ---------------------------------------------------------------------------
# Pytest output parsing for the Rich progress bar
# ---------------------------------------------------------------------------

_COLLECTED_RE = re.compile(r"collected (\d+) items?(?:\s*/\s*(\d+) deselected)?")
_XDIST_ITEMS_RE = re.compile(r"\[(\d+) items?\]")
_RESULT_KW_RE = re.compile(r"\b(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PCT_RE = re.compile(r"\[\s*(\d+)%\s*\]")
_SEPARATOR_RE = re.compile(r"^={5,}")


def _parse_collection(line: str) -> int | None:
    """Extract test count from a pytest collection line, or None."""
    m = _COLLECTED_RE.search(line)
    if m:
        collected = int(m.group(1))
        deselected = int(m.group(2)) if m.group(2) else 0
        return collected - deselected
    m = _XDIST_ITEMS_RE.search(line)
    if m:
        return int(m.group(1))
    return None


def _is_summary_boundary(line: str) -> bool:
    """True if *line* marks the start of pytest's post-execution output."""
    return bool(_SEPARATOR_RE.match(line)) or line in ("FAILURES", "ERRORS")


def _parse_result(line: str, total: int | None) -> tuple[int, bool]:
    """Return (advance_count, is_failure) for a pytest result line.

    Handles verbose mode (keyword per line) and quiet mode ([NN%]).
    Returns (0, False) when the line carries no result information.
    """
    if _RESULT_KW_RE.search(line):
        return 1, ("FAILED" in line or "ERROR" in line)
    m = _PCT_RE.search(line)
    if m and total:
        return total * int(m.group(1)) // 100, False
    return 0, False


def _stream_with_progress(
    process: subprocess.Popen[str],
    log_file: IO[str],
) -> int:
    """Stream pytest output with a Rich progress bar — for interactive TTY use."""
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    total: int | None = None
    completed = 0
    phase = "collecting"  # collecting → running → summary

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task("Collecting tests...", total=None)
    progress.start()

    try:
        for line in process.stdout or []:
            log_file.write(line)
            log_file.flush()
            stripped = line.rstrip()

            if phase == "summary":
                print(line, end="")
                continue

            # Collection phase → running
            count = _parse_collection(stripped)
            if count is not None:
                total = count
                desc = "No tests collected" if total == 0 else f"Running {total} tests"
                progress.update(task_id, total=total or None, description=desc)
                phase = "running"
                continue

            # End of execution → summary
            if phase == "running" and _is_summary_boundary(stripped):
                phase = "summary"
                progress.stop()
                print(line, end="")
                continue

            # Advance progress from result lines
            if phase == "running":
                advance, is_fail = _parse_result(stripped, total)
                if advance:
                    completed = (
                        max(completed, advance)
                        if total and advance > 1
                        else completed + advance
                    )
                    progress.update(task_id, completed=completed)
                    if is_fail:
                        progress.print(f"[red]{stripped}[/]")
    finally:
        if phase != "summary":
            progress.stop()

    process.wait()
    return process.returncode


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
) -> None:
    """Run pytest with Rich formatting and logging."""
    _pre_test_db_cleanup()

    from promptgrimoire.config import get_current_branch, get_settings

    branch = get_current_branch()
    test_db_url = get_settings().dev.test_database_url or ""
    db_name = (
        test_db_url.split("?")[0].rsplit("/", 1)[-1]
        if test_db_url
        else "not configured"
    )

    start_time = datetime.now()
    user_args = sys.argv[1:]

    # Interactive terminals get a Rich progress bar and no rtk.
    # Piped output (e.g. Claude Code) gets rtk filtering for token savings.
    interactive = sys.stdout.isatty()

    if not interactive and shutil.which("rtk") is not None:
        all_args = ["uv", "run", "rtk", "pytest", *default_args, *user_args]
    else:
        all_args = ["uv", "run", "pytest", *default_args, *user_args]
    command_str = " ".join(all_args[2:])

    header_text, log_header = _build_test_header(
        title, branch, db_name, start_time, command_str
    )
    if interactive:
        console.print(Panel(header_text, border_style="blue"))
    else:
        print(f"db={db_name} log={log_path}")

    with log_path.open("w") as log_file:
        log_file.write(log_header)
        log_file.flush()

        process = subprocess.Popen(  # nosec B603 — args from trusted CLI config
            all_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if interactive:
            exit_code = _stream_with_progress(process, log_file)
        else:
            exit_code = _stream_plain(process, log_file)

        end_time = datetime.now()
        duration = end_time - start_time

        # Footer always written to log
        log_footer = f"""
{"=" * 60}
Finished: {end_time.isoformat()}
Duration: {duration}
Exit code: {exit_code}
{"=" * 60}
"""
        log_file.write(log_footer)

    if interactive:
        # Rich footer panel
        console.print()
        if exit_code == 0:
            status = Text("PASSED", style="bold green")
            border = "green"
        else:
            status = Text("FAILED", style="bold red")
            border = "red"

        footer_text = Text()
        footer_text.append("Status: ")
        footer_text.append_text(status)
        footer_text.append(f"\nDuration: {duration}")
        footer_text.append(f"\nLog: {log_path}", style="dim")

        console.print(Panel(footer_text, border_style=border))

    sys.exit(exit_code)


def test_debug() -> None:
    """Run pytest on tests affected by recent changes, stopping on first failure.

    Uses pytest-depper for smart test selection based on code dependencies.
    Only tests that depend on changed files (vs main branch) will run.

    Excludes E2E tests (same as test-all) because Playwright's event loop
    contaminates xdist workers. See #121.

    Flags applied:
        --depper: Enable smart test selection based on changed files
        --depper-run-all-on-error: Fall back to all tests if analysis fails
        -m "not e2e": Exclude Playwright E2E tests by marker
        -n auto: Parallel execution with auto-detected workers
        --dist=worksteal: Workers steal tests from others for better load balancing
        -x: Stop on first failure
        --ff: Run failed tests first, then remaining tests
        --durations=10: Show 10 slowest tests
        --tb=short: Shorter tracebacks

    Output saved to: test-failures.log
    """
    _run_pytest(
        title="Test Debug Run (changed files only)",
        log_path=Path("test-failures.log"),
        default_args=[
            "--depper",
            "--depper-run-all-on-error",
            "-m",
            "not e2e",
            "-n",
            "auto",
            "--dist=worksteal",
            "-x",
            "--ff",
            "--durations=10",
            "--tb=short",
        ],
    )


def test_all() -> None:
    """Run unit and integration tests under xdist parallel execution.

    Excludes E2E tests because Playwright's event loop contaminates xdist
    workers, causing 'Runner.run() cannot be called from a running event loop'
    in async integration tests. See #121.

    E2E tests must run separately (they need a live app server anyway).

    Flags applied:
        -m "not e2e": Exclude Playwright E2E tests by marker
        -n auto: Parallel execution with auto-detected workers
        --dist=worksteal: Workers steal tests from others for better load balancing
        --durations=10: Show 10 slowest tests
        -v: Verbose output

    Output saved to: test-all.log
    """
    _run_pytest(
        title="Full Test Suite (unit + integration, excludes E2E)",
        log_path=Path("test-all.log"),
        default_args=[
            "-m",
            "not e2e",
            "-n",
            "auto",
            "--dist=worksteal",
            "--durations=10",
            "-v",
        ],
    )


def test_all_fixtures() -> None:
    """Run full test corpus including BLNS and slow tests.

    Runs pytest without marker filtering, enabling all tests
    including those marked with @pytest.mark.blns and @pytest.mark.slow.

    Flags applied:
        -m "": Empty marker filter = run all tests
        -v: Verbose output
        --tb=short: Shorter tracebacks

    Output saved to: test-all-fixtures.log
    """
    _run_pytest(
        title="Full Fixture Corpus (including BLNS/slow)",
        log_path=Path("test-all-fixtures.log"),
        default_args=["-m", "", "-v", "--tb=short"],
    )


# Near-duplicate of _SERVER_SCRIPT in tests/conftest.py — keep in sync.
_E2E_SERVER_SCRIPT = """\
import os
import sys
from pathlib import Path

for key in list(os.environ.keys()):
    if 'PYTEST' in key or 'NICEGUI' in key:
        del os.environ[key]

os.environ['DEV__AUTH_MOCK'] = 'true'
os.environ['APP__STORAGE_SECRET'] = 'test-secret-for-e2e'
# asyncio debug DISABLED — it causes event loop blocks (linecache.checkcache)
os.environ.setdefault('STYTCH__SSO_CONNECTION_ID', 'test-sso-connection-id')
os.environ.setdefault('STYTCH__PUBLIC_TOKEN', 'test-public-token')

port = int(sys.argv[1])

# Enable logging so pool events and diagnostics are visible
from promptgrimoire import _setup_logging
_setup_logging()

# --- Event loop watchdog (runs on a separate thread) ---
import asyncio
import logging
import threading

_watchdog_logger = logging.getLogger("e2e.watchdog")
_watchdog_loop_ref: asyncio.AbstractEventLoop | None = None

def _watchdog_loop():
    \"\"\"Log event loop responsiveness every 2 seconds from a daemon thread.\"\"\"
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
            open("/tmp/wd-canary.txt", "w").write("reached")
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
                _w(
                    f"\\n=== BLOCKED at"
                    f" {_dt.datetime.now()} ===\\n"
                )
                frames = _sys._current_frames()
                _w(f"Threads: {len(frames)}\\n")
                for tid, frame in frames.items():
                    tname = "unknown"
                    for t in threading.enumerate():
                        if t.ident == tid:
                            tname = t.name
                            break
                    _w(f"--- {tname} (tid={tid}) ---\\n")
                    for entry in _tb.extract_stack(frame):
                        _w(
                            f"  {entry.filename}:{entry.lineno}"
                            f" in {entry.name}:"
                            f" {entry.line}\\n"
                        )
                _w("=== END ===\\n")
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
                        f"DUMP FAILED: {exc}\\n".encode(),
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

from nicegui import app, ui
import promptgrimoire.pages  # noqa: F401

import promptgrimoire
_static_dir = Path(promptgrimoire.__file__).parent / "static"
app.add_static_files("/static", str(_static_dir))


# Diagnostic endpoint: pool + pg_stat + NiceGUI client stats
@app.get("/api/test/diagnostics")
async def _diagnostics():
    from nicegui import Client
    from promptgrimoire.crdt.persistence import (
        get_persistence_manager,
    )
    from promptgrimoire.db.engine import (
        _pool_status, _state, log_pool_and_pg_stats,
    )
    from promptgrimoire.pages.annotation import (
        _workspace_presence, _workspace_registry,
    )

    await log_pool_and_pg_stats()

    pool = (
        _state.engine.sync_engine.pool
        if _state.engine
        else None
    )
    pm = get_persistence_manager()
    all_tasks = asyncio.all_tasks()
    return {
        "pool": (
            _pool_status(pool) if pool else "no engine"
        ),
        "engine_id": id(_state.engine),
        "engine_is_none": _state.engine is None,
        "nicegui_clients": len(Client.instances),
        "nicegui_delete_tasks": sum(
            len(c._delete_tasks)
            for c in Client.instances.values()
        ),
        "crdt_docs": len(pm._doc_registry),
        "crdt_dirty": len(pm._workspace_dirty),
        "crdt_pending_saves": len(
            pm._workspace_pending_saves
        ),
        "presence_workspaces": len(_workspace_presence),
        "presence_total_clients": sum(
            len(v) for v in _workspace_presence.values()
        ),
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
            name = getattr(coro, '__qualname__', str(coro))
        else:
            name = t.get_name()
        # Keep last two segments for disambiguation (e.g. Event.wait vs
        # websocket_wait) instead of just the final name.
        parts = name.rsplit('.', 2)
        name = '.'.join(parts[-2:]) if len(parts) >= 2 else name
        names.append(name)
    return dict(Counter(names).most_common(10))

# Cleanup endpoint: force-delete stale NiceGUI clients and engine.io
# sessions between tests. Disconnects at both layers to prevent
# task accumulation. See docs/e2e-debugging.md.
@app.post("/api/test/cleanup")
async def _cleanup():
    from nicegui import Client, core
    _cleanup_logger = logging.getLogger("e2e.cleanup")
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
            qn = getattr(coro, '__qualname__', '') if coro else ''
            if qn == 'Event.wait':
                t.cancel()
                orphan_wait += 1
    await asyncio.sleep(0)  # let cancellations propagate
    elapsed_total = _time.monotonic() - t_total
    tasks_after = len(asyncio.all_tasks())
    _cleanup_logger.warning(
        "CLEANUP: clients=%d/%d sids=%d eio=%d orphan_wait=%d"
        " tasks=%d->%d elapsed=%.3fs",
        deleted, before, sids_closed, eio_closed, orphan_wait,
        tasks_before, tasks_after, elapsed_total,
    )
    return {
        "deleted": deleted, "before": before,
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

# Monkey-patch Outbox.stop() to wake the sleeping loop immediately.
# Without this, the outbox loop lingers for up to 1s in
# asyncio.wait_for(Event.wait(), timeout=1.0) after stop() is called.
from nicegui.outbox import Outbox as _Outbox
_orig_outbox_stop = _Outbox.stop
def _fast_outbox_stop(self):
    _orig_outbox_stop(self)
    if self._enqueue_event is not None:
        self._enqueue_event.set()
_Outbox.stop = _fast_outbox_stop

_orig_delete = _Client.delete
_delete_logger = logging.getLogger("e2e.client_delete")
def _timed_delete(self):
    n_elements = len(self.elements) if hasattr(self, 'elements') else -1
    t0 = _time.monotonic()
    _orig_delete(self)
    elapsed = _time.monotonic() - t0
    _delete_logger.warning(
        "CLIENT_DELETE: id=%s elements=%d elapsed=%.3fs",
        self.id[:8], n_elements, elapsed,
    )
_Client.delete = _timed_delete

ui.run(
    port=port, reload=False, show=False,
    storage_secret='test-secret-for-e2e',
    reconnect_timeout=0.5,
)
"""


def _start_e2e_server(port: int) -> subprocess.Popen[bytes]:
    """Start a NiceGUI server subprocess for E2E tests.

    Returns the Popen handle. Blocks until the server accepts connections
    or fails with ``sys.exit(1)`` on timeout/crash.
    """
    import socket
    import time

    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }

    console.print(f"[blue]Starting NiceGUI server on port {port}...[/]")
    server_log = Path("test-e2e-server.log")
    server_log_fh = server_log.open("w")
    process = subprocess.Popen(  # nosec B603 — hardcoded test server command
        [sys.executable, "-c", _E2E_SERVER_SCRIPT, str(port)],
        stdout=server_log_fh,
        stderr=subprocess.STDOUT,
        env=clean_env,
    )

    max_wait = 15
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if process.poll() is not None:
            server_log_fh.close()
            log_content = server_log.read_text()
            console.print(
                f"[red]Server died (exit {process.returncode}):[/]\n{log_content}"
            )
            sys.exit(1)
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return process
        except OSError:
            time.sleep(0.1)

    process.terminate()
    console.print(f"[red]Server failed to start within {max_wait}s[/]")
    sys.exit(1)


def _stop_e2e_server(process: subprocess.Popen[bytes]) -> None:
    """Terminate a server subprocess gracefully."""
    console.print("[dim]Stopping server...[/]")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _check_ptrace_scope() -> None:
    """Verify kernel.yama.ptrace_scope allows py-spy to attach."""
    try:
        scope = Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip()
        if scope != "0":
            console.print(
                "[red]py-spy requires ptrace access.[/]\n"
                "Run: sudo sysctl kernel.yama.ptrace_scope=0"
            )
            sys.exit(1)
    except FileNotFoundError:
        pass  # Non-Linux or no YAMA — assume OK


def _start_pyspy(pid: int) -> subprocess.Popen[bytes]:
    """Start py-spy recording against a server process."""
    pyspy = shutil.which("py-spy")
    if pyspy is None:
        console.print("[red]py-spy not found in PATH[/]")
        sys.exit(1)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = log_dir / f"py-spy-{ts}.json"

    console.print(f"[blue]py-spy recording PID {pid} → {out_path}[/]")
    proc = subprocess.Popen(  # nosec B603
        [
            pyspy,
            "record",
            "--pid",
            str(pid),
            "--output",
            str(out_path),
            "--format",
            "speedscope",
            "--subprocesses",
            "--rate",
            "100",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def _stop_pyspy(proc: subprocess.Popen[bytes]) -> None:
    """Stop py-spy recording and report output location."""
    import signal

    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    console.print("[blue]py-spy recording saved to logs/[/]")


def test_e2e() -> None:
    """Start a NiceGUI server and run Playwright E2E tests against it.

    Manages the full E2E lifecycle:
    1. Run Alembic migrations and truncate test database
    2. Start NiceGUI server on a random port (single instance)
    3. Run ``pytest -m e2e`` against the server
    4. Shut down the server when tests complete

    By default, tests run single-threaded with ``-x`` (fail-fast).
    Pass ``--parallel`` to use xdist (``-n auto --dist=loadfile``).
    Pass ``-v`` for verbose per-test output.

    The server URL is passed via ``E2E_BASE_URL`` env var. The
    ``app_server`` fixture checks this and yields it directly instead
    of starting its own server per xdist worker.

    Extra arguments forwarded to pytest (e.g. ``uv run test-e2e -k browser``).

    Output saved to: test-e2e.log
    """
    import socket

    # Consume flags before _run_pytest sees sys.argv
    parallel = "--parallel" in sys.argv
    if parallel:
        sys.argv.remove("--parallel")
    use_pyspy = "--py-spy" in sys.argv
    if use_pyspy:
        sys.argv.remove("--py-spy")

    if use_pyspy:
        _check_ptrace_scope()

    # Eagerly load settings so .env is read before subprocess spawning.
    from promptgrimoire.config import get_settings

    get_settings()

    _pre_test_db_cleanup()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    # All xdist workers inherit this and skip starting their own server
    os.environ["E2E_BASE_URL"] = url

    pyspy_process: subprocess.Popen[bytes] | None = None
    if use_pyspy:
        pyspy_process = _start_pyspy(server_process.pid)

    if parallel:
        mode_args: list[str] = ["-n", "auto", "--dist=loadfile"]
        mode_label = "parallel"
    else:
        mode_args = ["-x"]
        mode_label = "serial, fail-fast"

    try:
        _run_pytest(
            title=f"E2E Test Suite (Playwright, {mode_label}) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=[
                "-m",
                "e2e",
                *mode_args,
                "--ff",
                "--durations=10",
                "--tb=short",
                "--log-cli-level=WARNING",
            ],
        )
    finally:
        if pyspy_process is not None:
            _stop_pyspy(pyspy_process)
        _stop_e2e_server(server_process)


def test_e2e_debug() -> None:
    """Re-run last-failed E2E tests, or all if none failed previously.

    Same server lifecycle as ``test-e2e`` but optimised for iterating on
    failures: runs only previously-failed tests (``--lf``), stops on first
    failure (``-x``), and shows full tracebacks (``--tb=long``).

    If no prior failures exist, falls back to running all E2E tests.

    Extra arguments forwarded to pytest (e.g. ``uv run test-e2e-debug -k law``).

    Output saved to: test-e2e.log
    """
    import socket

    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    try:
        _run_pytest(
            title=f"E2E Debug (last-failed) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=[
                "-m",
                "e2e",
                "--lf",
                "-x",
                "--durations=10",
                "--tb=long",
                "--log-cli-level=WARNING",
                "-v",
            ],
        )
    finally:
        _stop_e2e_server(server_process)


# ---------------------------------------------------------------------------
# manage-users CLI
# ---------------------------------------------------------------------------


def _format_last_login(dt: datetime | None) -> str:
    """Format a last_login timestamp for display."""
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M")


def _build_user_parser():
    """Build argparse parser for manage-users subcommands."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="manage-users",
        description="Manage users, roles, and course enrollments.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    list_p = sub.add_parser("list", help="List all users")
    list_p.add_argument(
        "--all", action="store_true", help="Include users who haven't logged in"
    )

    # show
    show_p = sub.add_parser("show", help="Show user details and enrollments")
    show_p.add_argument("email", help="User email address")

    # admin
    admin_p = sub.add_parser("admin", help="Set or remove admin status")
    admin_p.add_argument("email", help="User email address")
    admin_p.add_argument("--remove", action="store_true", help="Remove admin status")

    # enroll
    enroll_p = sub.add_parser("enroll", help="Enroll user in a course")
    enroll_p.add_argument("email", help="User email address")
    enroll_p.add_argument("code", help="Course code (e.g. LAWS1100)")
    enroll_p.add_argument("semester", help="Semester (e.g. 2026-S1)")
    enroll_p.add_argument("--role", default="student", help="Role (default: student)")

    # unenroll
    unenroll_p = sub.add_parser("unenroll", help="Remove user from a course")
    unenroll_p.add_argument("email", help="User email address")
    unenroll_p.add_argument("code", help="Course code")
    unenroll_p.add_argument("semester", help="Semester")

    # role
    role_p = sub.add_parser("role", help="Change user's role in a course")
    role_p.add_argument("email", help="User email address")
    role_p.add_argument("code", help="Course code")
    role_p.add_argument("semester", help="Semester")
    role_p.add_argument("new_role", help="New role")

    # create
    create_p = sub.add_parser("create", help="Create a new user")
    create_p.add_argument("email", help="User email address")
    create_p.add_argument(
        "--name", default=None, help="Display name (default: derived from email)"
    )

    return parser


async def _find_course(code: str, semester: str):
    """Look up a course by code + semester. Returns None if not found."""
    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course

    async with get_session() as session:
        result = await session.exec(
            select(Course).where(Course.code == code).where(Course.semester == semester)
        )
        return result.first()


async def _require_user(email: str, con: Console):
    """Look up user by email or exit with error."""
    from promptgrimoire.db.users import get_user_by_email

    user = await get_user_by_email(email)
    if user is None:
        con.print(f"[red]Error:[/] no user found with email '{email}'")
        con.print("[dim]User must log in at least once.[/]")
        sys.exit(1)
    return user


async def _require_course(code: str, semester: str, con: Console):
    """Look up course by code+semester or exit with error."""
    course = await _find_course(code, semester)
    if course is None:
        con.print(f"[red]Error:[/] no course found: {code} {semester}")
        sys.exit(1)
    return course


async def _cmd_list(
    *,
    include_all: bool = False,
    console: Console | None = None,
) -> None:
    """List users as a Rich table."""
    from rich.table import Table

    from promptgrimoire.db.users import list_all_users, list_users

    con = console or globals()["console"]
    users = await list_all_users() if include_all else await list_users()

    if not users:
        con.print("[yellow]No users found.[/]")
        return

    table = Table(title="Users")
    table.add_column("Email", style="cyan")
    table.add_column("Name")
    table.add_column("Admin")
    table.add_column("Last Login")

    for u in users:
        table.add_row(
            u.email,
            u.display_name,
            "[green]Yes[/]" if u.is_admin else "No",
            _format_last_login(u.last_login),
        )

    con.print(table)


async def _cmd_create(
    email: str,
    *,
    name: str | None = None,
    console: Console | None = None,
) -> None:
    """Create a new user."""
    from promptgrimoire.db.users import find_or_create_user

    con = console or globals()["console"]
    display_name = name or email.split("@", maxsplit=1)[0].replace(".", " ").title()
    user, created = await find_or_create_user(email=email, display_name=display_name)
    if created:
        con.print(f"[green]Created[/] user '{email}' ({display_name}, id={user.id})")
    else:
        con.print(f"[yellow]Already exists:[/] '{email}' (id={user.id})")


async def _cmd_show(
    email: str,
    *,
    console: Console | None = None,
) -> None:
    """Show a single user's details and course enrollments."""
    from rich.table import Table

    from promptgrimoire.db.courses import get_course_by_id, list_user_enrollments

    con = console or globals()["console"]
    user = await _require_user(email, con)

    con.print(f"\n[bold]{user.display_name}[/] ({user.email})")
    con.print(f"  Admin: {'[green]Yes[/]' if user.is_admin else 'No'}")
    con.print(f"  Last login: {_format_last_login(user.last_login)}")
    con.print(f"  ID: [dim]{user.id}[/]")

    enrollments = await list_user_enrollments(user.id)
    if not enrollments:
        con.print("\n  [dim]No course enrollments.[/]")
        return

    table = Table(title="Enrollments")
    table.add_column("Course")
    table.add_column("Semester")
    table.add_column("Role")

    for e in enrollments:
        course = await get_course_by_id(e.course_id)
        if course:
            table.add_row(course.code, course.semester, e.role)
        else:
            table.add_row(f"[dim]{e.course_id}[/]", "?", e.role)

    con.print(table)


async def _cmd_admin(
    email: str,
    *,
    remove: bool = False,
    console: Console | None = None,
) -> None:
    """Set or remove admin status for a user."""
    from promptgrimoire.db.users import set_admin as db_set_admin

    con = console or globals()["console"]
    user = await _require_user(email, con)

    if remove:
        await db_set_admin(user.id, False)
        con.print(f"[green]Removed[/] admin from '{email}'.")
    else:
        await db_set_admin(user.id, True)
        con.print(f"[green]Granted[/] admin to '{email}'.")


async def _cmd_enroll(
    email: str,
    code: str,
    semester: str,
    *,
    role: str = "student",
    console: Console | None = None,
) -> None:
    """Enroll a user in a course."""
    from promptgrimoire.db.courses import DuplicateEnrollmentError, enroll_user

    con = console or globals()["console"]
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    try:
        await enroll_user(course_id=course.id, user_id=user.id, role=role)
        con.print(f"[green]Enrolled[/] '{email}' in {code} {semester} as {role}.")
    except DuplicateEnrollmentError:
        con.print(f"[yellow]Already enrolled:[/] '{email}' in {code} {semester}.")


async def _cmd_unenroll(
    email: str,
    code: str,
    semester: str,
    *,
    console: Console | None = None,
) -> None:
    """Remove a user from a course."""
    from promptgrimoire.db.courses import unenroll_user

    con = console or globals()["console"]
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    removed = await unenroll_user(course_id=course.id, user_id=user.id)
    if removed:
        con.print(f"[green]Removed[/] '{email}' from {code} {semester}.")
    else:
        con.print(f"[yellow]Not enrolled:[/] '{email}' in {code} {semester}.")


async def _cmd_role(
    email: str,
    code: str,
    semester: str,
    new_role: str,
    *,
    console: Console | None = None,
) -> None:
    """Change a user's role in a course."""
    from promptgrimoire.db.courses import update_user_role

    con = console or globals()["console"]
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    result = await update_user_role(
        course_id=course.id,
        user_id=user.id,
        role=new_role,
    )
    if result:
        con.print(
            f"[green]Updated[/] '{email}' role to {new_role} in {code} {semester}."
        )
    else:
        con.print(f"[yellow]Not enrolled:[/] '{email}' in {code} {semester}.")


def manage_users() -> None:
    """Manage users, roles, and course enrollments.

    Usage:
        uv run manage-users <command> [options]

    Commands:
        list              List all users
        show <email>      Show user details and enrollments
        create <email>    Create a new user (--name for display name)
        admin <email>     Set user as admin (--remove to unset)
        enroll <email> <code> <semester>  Enroll user in course
        unenroll <email> <code> <semester>  Remove from course
        role <email> <code> <semester> <role>  Change role
    """
    from promptgrimoire.config import get_settings

    parser = _build_user_parser()
    args = parser.parse_args(sys.argv[1:])

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    async def _run() -> None:
        from promptgrimoire.db.engine import init_db

        await init_db()

        match args.command:
            case "list":
                await _cmd_list(include_all=args.all)
            case "show":
                await _cmd_show(args.email)
            case "admin":
                await _cmd_admin(args.email, remove=args.remove)
            case "enroll":
                await _cmd_enroll(
                    args.email,
                    args.code,
                    args.semester,
                    role=args.role,
                )
            case "unenroll":
                await _cmd_unenroll(args.email, args.code, args.semester)
            case "role":
                await _cmd_role(
                    args.email,
                    args.code,
                    args.semester,
                    args.new_role,
                )
            case "create":
                await _cmd_create(args.email, name=args.name)

    asyncio.run(_run())


def set_admin() -> None:
    """Set a user as admin by email (legacy — delegates to manage-users admin).

    Usage:
        uv run set-admin user@example.com
    """
    from promptgrimoire.config import get_settings

    if len(sys.argv) < 2:
        console.print("[red]Usage:[/] uv run set-admin <email>")
        console.print("[dim]Consider using: uv run manage-users admin <email>[/]")
        sys.exit(1)

    email = sys.argv[1]

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    async def _run() -> None:
        from promptgrimoire.db.engine import init_db

        await init_db()
        await _cmd_admin(email)

    console.print("[dim]Tip: use 'uv run manage-users admin' instead.[/]")
    asyncio.run(_run())


async def _seed_user_and_course() -> tuple:
    """Create instructor user and course. Returns (user, course)."""
    from sqlmodel import select

    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course
    from promptgrimoire.db.users import find_or_create_user

    user, user_created = await find_or_create_user(
        email="instructor@uni.edu",
        display_name="Test Instructor",
    )
    status = "[green]Created" if user_created else "[yellow]Exists"
    console.print(f"{status}:[/] instructor@uni.edu (id={user.id})")

    # Check for existing course first (code is not unique — same
    # code may appear in different semesters)
    async with get_session() as session:
        result = await session.exec(
            select(Course)
            .where(Course.code == "LAWS1100")
            .where(Course.semester == "2026-S1")
        )
        course = result.first()

    if course:
        console.print(f"[yellow]Course exists:[/] LAWS1100 (id={course.id})")
    else:
        course = await create_course(code="LAWS1100", name="Torts", semester="2026-S1")
        console.print(f"[green]Created course:[/] LAWS1100 (id={course.id})")

    return user, course


async def _seed_enrolment_and_weeks(course) -> None:
    """Enrol mock users and create weeks with activities."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import (
        DuplicateEnrollmentError,
        enroll_user,
        update_course,
    )
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.weeks import create_week

    # Seed all mock users and enrol them
    mock_users = [
        ("instructor@uni.edu", "Test Instructor", "coordinator"),
        ("admin@example.com", "Admin User", "coordinator"),
        ("student@uni.edu", "Test Student", "student"),
        ("test@example.com", "Test User", "student"),
    ]

    from promptgrimoire.db.engine import get_session

    for email, name, role in mock_users:
        u, created = await find_or_create_user(email=email, display_name=name)
        if email == "admin@example.com" and not u.is_admin:
            u.is_admin = True
            async with get_session() as session:
                session.add(u)
                await session.commit()
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"{status}:[/] {email}")

        try:
            await enroll_user(course_id=course.id, user_id=u.id, role=role)
            console.print(f"  [green]Enrolled:[/] {email} as {role}")
        except DuplicateEnrollmentError:
            console.print(f"  [yellow]Already enrolled:[/] {email}")

    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Week

    async with get_session() as session:
        result = await session.exec(select(Week).where(Week.course_id == course.id))
        existing_weeks = list(result.all())

    if existing_weeks:
        console.print(f"[yellow]Weeks exist:[/] {len(existing_weeks)} in course")
        return

    week1 = await create_week(course_id=course.id, week_number=1, title="Introduction")
    # Publish week 1; week 2 stays draft (is_published defaults to False)
    week1.is_published = True
    async with get_session() as session:
        session.add(week1)
        await session.commit()
    week2 = await create_week(
        course_id=course.id, week_number=2, title="Client Interviews"
    )
    console.print(f"[green]Created weeks:[/] 1, 2 (ids={week1.id}, {week2.id})")

    desc = "Read the interview transcript and annotate key issues."
    activity = await create_activity(
        week_id=week1.id,
        title="Annotate Becky Bennett Interview",
        description=desc,
        copy_protection=True,
    )
    console.print(f"[green]Created activity:[/] {activity.title} (id={activity.id})")

    await update_course(course.id, default_copy_protection=True)
    console.print("[green]Enabled:[/] default copy protection on course")


def seed_data() -> None:
    """Seed the database with test data for development.

    Creates an instructor user, a course with two weeks, and an activity.
    Idempotent: safe to run multiple times. Existing data is reused.

    Usage:
        uv run seed-data
    """
    from promptgrimoire.config import get_settings

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    async def _seed() -> None:
        from promptgrimoire.db.engine import init_db

        await init_db()

        _user, course = await _seed_user_and_course()
        await _seed_enrolment_and_weeks(course)

        console.print()
        console.print(
            Panel(
                f"[bold]Login:[/] http://localhost:8080/login\n"
                f"[bold]Email:[/] instructor@uni.edu\n"
                f"[bold]Course:[/] http://localhost:8080/courses/{course.id}",
                title="Seed Data Ready",
            )
        )

    asyncio.run(_seed())


def _find_export_dir(user_id: str | None) -> Path:
    """Find the export directory for a user or most recent."""
    import tempfile

    tmp_dir = Path(tempfile.gettempdir())

    if user_id:
        export_dir = tmp_dir / f"promptgrimoire_export_{user_id}"
        if not export_dir.exists():
            console.print(f"[red]Error:[/] Export directory not found: {export_dir}")
            sys.exit(1)
        return export_dir

    export_dirs = list(tmp_dir.glob("promptgrimoire_export_*"))
    if not export_dirs:
        console.print("[red]Error:[/] No export directories found in temp folder")
        console.print(f"[dim]Searched in: {tmp_dir}[/]")
        sys.exit(1)

    return max(export_dirs, key=lambda p: p.stat().st_mtime)


def _show_error_context(log_file: Path, tex_file: Path) -> None:
    """Show LaTeX error with context from both log and tex file."""
    import re

    from rich.syntax import Syntax

    log_content = log_file.read_text()
    tex_lines = tex_file.read_text().splitlines()

    # Find error line number from log (pattern: "l.123")
    error_line_match = re.search(r"^l\.(\d+)", log_content, re.MULTILINE)
    error_line = int(error_line_match.group(1)) if error_line_match else None

    # Show last part of log (where errors appear)
    console.print("\n[bold red]LaTeX Error (last 100 lines of log):[/]")
    for line in log_content.splitlines()[-100:]:
        if line.startswith("!") or "Error" in line:
            console.print(f"[red]{line}[/]")
        elif line.startswith("l."):
            console.print(f"[yellow]{line}[/]")
        else:
            console.print(line)

    # Show tex context around error line
    if error_line:
        console.print(f"\n[bold yellow]TeX Source around line {error_line}:[/]")
        start = max(0, error_line - 15)
        end = min(len(tex_lines), error_line + 10)
        context = "\n".join(tex_lines[start:end])
        console.print(
            Syntax(
                context,
                "latex",
                line_numbers=True,
                start_line=start + 1,
                highlight_lines={error_line},
            )
        )
    else:
        console.print("\n[dim]Could not find error line number in log[/]")


def show_export_log() -> None:
    """Show the most recent PDF export LaTeX log and/or source.

    Usage:
        uv run show-export-log [--tex | --both] [user_id]

    Options:
        --tex   Show the .tex source file instead of the log
        --both  Show error context from both log and tex files
    """
    from rich.syntax import Syntax

    # Parse arguments
    args = sys.argv[1:]
    show_tex = "--tex" in args
    show_both = "--both" in args
    positional = [a for a in args if not a.startswith("--")]
    user_id = positional[0] if positional else None

    export_dir = _find_export_dir(user_id)
    log_file = export_dir / "annotated_document.log"
    tex_file = export_dir / "annotated_document.tex"

    # Print file paths for easy access
    console.print(
        Panel(
            f"[bold]Export Directory:[/] {export_dir}\n"
            f"[bold]TeX Source:[/] {tex_file}\n"
            f"[bold]LaTeX Log:[/] {log_file}",
            title="PDF Export Debug Files",
            border_style="blue",
        )
    )

    if show_both:
        if not tex_file.exists() or not log_file.exists():
            console.print("[red]Error:[/] Missing .tex or .log file")
            sys.exit(1)
        _show_error_context(log_file, tex_file)
    elif show_tex:
        if not tex_file.exists():
            console.print(f"[red]Error:[/] TeX file not found: {tex_file}")
            sys.exit(1)
        with console.pager():
            console.print(Syntax(tex_file.read_text(), "latex", line_numbers=True))
    else:
        if not log_file.exists():
            console.print(f"[red]Error:[/] Log file not found: {log_file}")
            sys.exit(1)
        with console.pager():
            console.print(log_file.read_text())
