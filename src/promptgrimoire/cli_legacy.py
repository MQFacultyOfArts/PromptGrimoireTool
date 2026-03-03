"""Command-line utilities for PromptGrimoire development.

Provides pytest wrappers with logging and timing for debugging test failures.
Also includes admin bootstrap commands.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
import subprocess
import sys
import time
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
    # Signal engine module to use NullPool instead of QueuePool.
    # Inherited by all xdist workers.  Avoids asyncpg connection-state
    # leakage under parallel execution (asyncpg#784, SQLAlchemy#10226).
    os.environ["_PROMPTGRIMOIRE_USE_NULL_POOL"] = "1"
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
    """Stream pytest output with token-minimising filtering for piped/CI use.

    All lines go to the log file. Stdout suppresses everything until the
    post-results summary section, then prints from there. FAILED/ERROR
    lines are printed immediately regardless of phase.

    Pytest output structure:
    1. ``== test session starts ==``  (opening separator)
    2. header lines, collection info
    3. dot-progress or verbose results
    4. ``== warnings summary ==`` or ``== N passed ==``  (closing separator)
    5. summary details

    We skip phase 1-3, print from phase 4 onwards.
    """
    separator_count = 0
    in_summary = False

    for line in process.stdout or []:
        log_file.write(line)
        log_file.flush()
        stripped = line.rstrip()

        # Count ``=====`` separators; summary starts at the second one
        if not in_summary and _SEPARATOR_RE.match(stripped):
            separator_count += 1
            if separator_count >= 2:
                in_summary = True

        if in_summary:
            print(line, end="")
            continue

        # Before summary: only print FAILED/ERROR lines
        if "FAILED" in stripped or "ERROR" in stripped:
            print(line, end="")

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
    phase = "collecting"  # collecting -> running -> summary

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

            # Collection phase -> running
            count = _parse_collection(stripped)
            if count is not None:
                total = count
                desc = "No tests collected" if total == 0 else f"Running {total} tests"
                progress.update(task_id, total=total or None, description=desc)
                phase = "running"
                continue

            # End of execution -> summary
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
) -> int:
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

    # Interactive terminals get a Rich progress bar.
    # Piped output (e.g. Claude Code) uses _stream_plain filtering.
    interactive = sys.stdout.isatty()

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

    return exit_code


def test_changed() -> None:
    """Run pytest on tests affected by changes relative to main.

    Uses pytest-depper for smart test selection based on code dependencies.
    Only tests that depend on changed files (vs main branch) will run.

    Excludes E2E tests (same as test-all) because Playwright's event loop
    contaminates xdist workers. See #121.

    Flags applied:
        --depper: Enable smart test selection based on changed files
        -m "not e2e": Exclude Playwright E2E tests by marker
        -n auto: Parallel execution with auto-detected workers
        --dist=worksteal: Workers steal tests from others for better load balancing
        -x: Stop on first failure
        --ff: Run failed tests first, then remaining tests
        --reruns 3: Retry failed tests up to 3 times (asyncpg connection churn)
        --tb=short: Shorter tracebacks

    Output saved to: test-failures.log
    """
    sys.exit(
        _run_pytest(
            title="Changed Tests (vs main)",
            log_path=Path("test-failures.log"),
            default_args=[
                "--depper",
                "-m",
                "not e2e",
                "-n",
                "auto",
                "--dist=worksteal",
                "-x",
                "--ff",
                "--reruns",
                "3",
                "--tb=short",
            ],
        )
    )


def _xdist_worker_count() -> str:
    """Calculate reliable xdist worker count.

    Caps at half CPU count (max 16).  Higher counts cause intermittent
    asyncpg ``ConnectionResetError`` under NullPool connection churn —
    asyncpg's protocol handling has a low-probability race when many
    workers create/destroy Unix-socket connections simultaneously.

    Benchmarking shows half-CPU is also the fastest configuration:
    reduced process management overhead outweighs lost parallelism.
    """
    cpus = os.cpu_count() or 4
    return str(min(cpus // 2, 16))


def test_all() -> None:
    """Run unit and integration tests under xdist parallel execution.

    Excludes E2E tests because Playwright's event loop contaminates xdist
    workers, causing 'Runner.run() cannot be called from a running event loop'
    in async integration tests. See #121.

    E2E tests must run separately (they need a live app server anyway).

    Flags applied:
        -m "not e2e": Exclude Playwright E2E tests by marker
        -n <half-cpu>: Parallel execution with capped worker count
        --dist=worksteal: Workers steal tests from others for better load balancing
        --reruns 3: Retry failed tests up to 3 times (asyncpg connection churn)
        --durations=10: Show 10 slowest tests
        -v: Verbose output

    Output saved to: test-all.log
    """
    sys.exit(
        _run_pytest(
            title="Full Test Suite (unit + integration, excludes E2E)",
            log_path=Path("test-all.log"),
            default_args=[
                "-m",
                "not e2e",
                "-n",
                _xdist_worker_count(),
                "--dist=worksteal",
                "--reruns",
                "3",
                "-v",
            ],
        )
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
    sys.exit(
        _run_pytest(
            title="Full Fixture Corpus (including BLNS/slow)",
            log_path=Path("test-all-fixtures.log"),
            default_args=["-m", "", "-v", "--tb=short"],
        )
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
    _pdf_mod.compile_latex = _compile_latex_noop
    _pdf_export_mod.compile_latex = _compile_latex_noop
# --- End monkey-patch ---

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


def _allocate_ports(n: int) -> list[int]:
    """Allocate *n* distinct free TCP ports from the OS.

    Opens *n* sockets simultaneously (to guarantee uniqueness), reads their
    OS-assigned ports, then closes them all.  The returned ports are not
    *reserved* — a race is theoretically possible — but holding them open
    together ensures no duplicates within the batch.
    """
    import socket

    if n == 0:
        return []

    sockets: list[socket.socket] = []
    try:
        for _ in range(n):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", 0))
            sockets.append(s)
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()


def _filter_junitxml_args(user_args: list[str]) -> list[str]:
    """Strip ``--junitxml`` from *user_args* so per-worker paths take precedence."""
    filtered: list[str] = []
    skip_next = False
    for arg in user_args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--junitxml":
            skip_next = True
            continue
        if arg.startswith("--junitxml="):
            continue
        filtered.append(arg)
    return filtered


async def _run_e2e_worker(
    test_file: Path,
    port: int,
    db_url: str,
    result_dir: Path,
    user_args: list[str],
) -> tuple[Path, int, float]:
    """Run a single E2E test file against a dedicated server instance.

    Starts a NiceGUI server subprocess on *port* with *db_url*, waits for it
    to accept connections, then runs ``pytest -m e2e`` on *test_file*.  Server
    and pytest stdout/stderr are merged into a single log file under
    *result_dir*.

    Returns ``(test_file, pytest_exit_code, duration_seconds)``.

    The server process group is always cleaned up in the ``finally`` block,
    even on cancellation.
    """
    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }
    clean_env["DATABASE__URL"] = db_url

    log_path = result_dir / f"test-e2e-{test_file.stem}.log"
    log_fh = log_path.open("w")
    server: asyncio.subprocess.Process | None = None
    start_time = time.monotonic()

    try:
        # -- Start server subprocess --
        server = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            _E2E_SERVER_SCRIPT,
            str(port),
            stdout=log_fh,
            stderr=asyncio.subprocess.STDOUT,
            env=clean_env,
            start_new_session=True,
        )

        # -- Health check: poll until server accepts connections --
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if server.returncode is not None:
                raise RuntimeError(
                    f"Server for {test_file.name} died "
                    f"(exit {server.returncode}); see {log_path}"
                )
            try:
                _reader, writer = await asyncio.open_connection("localhost", port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.1)
        else:
            raise RuntimeError(
                f"Server for {test_file.name} did not start within 15 s; see {log_path}"
            )

        # -- Build pytest command --
        junit_path = result_dir / f"{test_file.stem}.xml"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-m",
            "e2e",
            "--tb=short",
            f"--junitxml={junit_path}",
            *_filter_junitxml_args(user_args),
        ]

        pytest_env = {**clean_env, "E2E_BASE_URL": f"http://localhost:{port}"}

        # -- Run pytest --
        pytest_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_fh,
            stderr=asyncio.subprocess.STDOUT,
            env=pytest_env,
        )
        await pytest_proc.wait()

        duration = time.monotonic() - start_time
        assert pytest_proc.returncode is not None  # guaranteed after wait()
        return (test_file, pytest_proc.returncode, duration)

    finally:
        # -- Process group cleanup --
        if server is not None and server.returncode is None:
            try:
                os.killpg(os.getpgid(server.pid), signal.SIGTERM)
                try:
                    await asyncio.wait_for(server.wait(), timeout=2)
                except TimeoutError:
                    os.killpg(os.getpgid(server.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        log_fh.close()


def _worker_status_label(exit_code: int) -> str:
    """Return a coloured PASS/FAIL/CANCEL label for a worker exit code."""
    if exit_code == -1:
        return "[yellow]CANCEL[/]"
    if exit_code in (0, 5):
        return "[green]PASS[/]"
    return "[red]FAIL[/]"


def _print_parallel_summary(
    results: list[tuple[Path, int, float]],
    wall_clock: float,
) -> None:
    """Print a compact summary of parallel E2E results (no borders)."""
    passed = sum(1 for _, c, _ in results if c in (0, 5))
    failed = sum(1 for _, c, _ in results if c not in (0, 5, -1))
    cancelled = sum(1 for _, c, _ in results if c == -1)

    total = len(results)
    parts = [f"{total} files: {passed} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if cancelled:
        parts.append(f"{cancelled} cancelled")
    parts.append(f"{wall_clock:.1f}s wall-clock")
    console.print(", ".join(parts))


def _merge_junit_xml(result_dir: Path) -> Path:
    """Merge per-worker JUnit XML files into a single ``combined.xml``.

    Returns the path to the combined file.
    """
    from junitparser import JUnitXml

    merged = JUnitXml()
    for xml_path in sorted(result_dir.glob("*.xml")):
        if xml_path.name != "combined.xml":
            merged += JUnitXml.fromfile(str(xml_path))
    combined_path = result_dir / "combined.xml"
    merged.write(str(combined_path), pretty=True)
    return combined_path


async def _run_all_workers(
    files: list[Path],
    ports: list[int],
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    user_args: list[str],
) -> list[tuple[Path, int, float]]:
    """Run all E2E workers concurrently, printing progress as each finishes."""
    total = len(files)
    done_count = 0
    results: list[tuple[Path, int, float]] = []

    async def _tracked_worker(i: int) -> tuple[Path, int, float]:
        return await _run_e2e_worker(
            files[i], ports[i], worker_dbs[i][0], result_dir, user_args
        )

    tasks = [asyncio.create_task(_tracked_worker(i)) for i in range(total)]

    for done_count, future in enumerate(asyncio.as_completed(tasks), 1):
        try:
            result = await future
        except Exception as exc:
            # Find which file this was — match by task identity
            fpath = files[0]  # fallback
            for j, t in enumerate(tasks):
                if t is future or (t.done() and not t.cancelled()):
                    try:
                        t.result()
                    except Exception as t_exc:
                        if t_exc is exc:
                            fpath = files[j]
                            break
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = (fpath, 1, 0.0)

        results.append(result)
        label = _worker_status_label(result[1])
        console.print(
            f"  [{done_count}/{total}] {result[0].name}: {label} ({result[2]:.1f}s)"
        )

    return results


def _resolve_failed_task_file(
    tasks: list[asyncio.Task[tuple[Path, int, float]]],
    exc: Exception,
    files: list[Path],
) -> Path:
    """Find which test file a failed task corresponds to."""
    for t in tasks:
        if not t.done() or t.cancelled():
            continue
        try:
            t.result()
        except Exception as t_exc:
            if t_exc is exc:
                stem = t.get_name().removeprefix("e2e-")
                return next((f for f in files if f.stem == stem), Path("unknown"))
    return Path("unknown")


async def _run_fail_fast_workers(
    files: list[Path],
    ports: list[int],
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    user_args: list[str],
) -> list[tuple[Path, int, float]]:
    """Run E2E workers with fail-fast: cancel remaining on first failure."""
    import contextlib

    tasks: list[asyncio.Task[tuple[Path, int, float]]] = [
        asyncio.create_task(
            _run_e2e_worker(f, ports[i], worker_dbs[i][0], result_dir, user_args),
            name=f"e2e-{f.stem}",
        )
        for i, f in enumerate(files)
    ]

    total = len(files)
    results: list[tuple[Path, int, float]] = []
    completed_files: set[Path] = set()
    done_count = 0

    for future in asyncio.as_completed(tasks):
        try:
            result = await future
        except asyncio.CancelledError:
            continue
        except Exception as exc:
            fpath = _resolve_failed_task_file(tasks, exc, files)
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = (fpath, 1, 0.0)

        results.append(result)
        completed_files.add(result[0])
        done_count += 1
        label = _worker_status_label(result[1])
        console.print(
            f"  [{done_count}/{total}] {result[0].name}: {label} ({result[2]:.1f}s)"
        )

        # Check for failure (exit code not 0 and not 5)
        if result[1] not in (0, 5):
            console.print("[red]  Fail-fast: cancelling remaining workers[/]")
            for t in tasks:
                if not t.done():
                    t.cancel()
            break

    # Await cancelled tasks so their finally blocks run
    for t in tasks:
        if t.cancelled() or not t.done():
            with contextlib.suppress(asyncio.CancelledError):
                await t

    # Add cancelled entries for files that never completed
    for f in files:
        if f not in completed_files:
            results.append((f, -1, 0.0))

    return results


def _cleanup_parallel_results(
    all_passed: bool,
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    results: list[tuple[Path, int, float]],
) -> None:
    """Clean up or preserve worker databases and result directory."""
    import contextlib
    import shutil

    from promptgrimoire.db.bootstrap import drop_database

    if all_passed:
        for db_url, _db_name in worker_dbs:
            with contextlib.suppress(Exception):
                drop_database(db_url)
        shutil.rmtree(result_dir, ignore_errors=True)
        console.print("[green]All passed — cleaned up worker databases and results[/]")
    else:
        console.print("[yellow]Some tests failed — preserving artifacts:[/]")
        console.print(f"  Results: {result_dir}")
        for db_url, db_name in worker_dbs:
            console.print(f"  DB: {db_name} ({db_url})")
        for test_file, exit_code, _duration in results:
            if exit_code not in (0, 5, -1):
                log_path = result_dir / f"test-e2e-{test_file.stem}.log"
                console.print(f"  Log: {log_path}")


async def _retry_parallel_failures(
    failed_files: list[Path],
    template_db_url: str,
    source_db_name: str,
    result_dir: Path,
    user_args: list[str],
) -> tuple[list[Path], list[Path]]:
    """Re-run failed E2E files with fresh servers and databases.

    Each failed file gets a new cloned database and server instance.
    Runs sequentially to maximise isolation.

    Returns ``(genuine_failures, flaky_files)``.
    """
    import contextlib

    from promptgrimoire.db.bootstrap import clone_database, drop_database

    console.print(
        f"\n[blue]Re-running {len(failed_files)} failed file(s) in isolation...[/]"
    )

    retry_ports = _allocate_ports(len(failed_files))
    retry_dbs: list[tuple[str, str]] = []

    try:
        # Prepare retry databases
        base_url = template_db_url.split("?", maxsplit=1)[0].rsplit("/", 1)[0]
        query = (
            ("?" + template_db_url.split("?", 1)[1]) if "?" in template_db_url else ""
        )
        for i in range(len(failed_files)):
            target_name = f"{source_db_name}_retry{i}"
            stale_url = f"{base_url}/{target_name}{query}"
            with contextlib.suppress(Exception):
                drop_database(stale_url)
            db_url = clone_database(template_db_url, target_name)
            retry_dbs.append((db_url, target_name))

        # Run each failed file sequentially
        genuine_failures: list[Path] = []
        flaky_files: list[Path] = []

        for i, fpath in enumerate(failed_files):
            try:
                result = await _run_e2e_worker(
                    fpath,
                    retry_ports[i],
                    retry_dbs[i][0],
                    result_dir,
                    user_args,
                )
            except Exception as exc:
                console.print(f"[red]Retry worker {fpath.name} raised: {exc}[/]")
                result = (fpath, 1, 0.0)

            label = _worker_status_label(result[1])
            console.print(
                f"  [retry {i + 1}/{len(failed_files)}] "
                f"{result[0].name}: {label} ({result[2]:.1f}s)"
            )

            if result[1] in (0, 5):
                flaky_files.append(fpath)
            else:
                genuine_failures.append(fpath)

        # Summary
        console.print()
        if flaky_files:
            console.print(f"[yellow]Flaky ({len(flaky_files)}):[/] passed on retry")
            for f in flaky_files:
                console.print(f"  {f.name}")
        if genuine_failures:
            console.print(f"[red]Genuine failures ({len(genuine_failures)}):[/]")
            for f in genuine_failures:
                console.print(f"  {f.name}")

        return genuine_failures, flaky_files

    finally:
        # Clean up retry databases
        for url, _ in retry_dbs:
            with contextlib.suppress(Exception):
                drop_database(url)


def _create_worker_databases(
    test_db_url: str,
    source_db_name: str,
    count: int,
    suffix: str = "w",
) -> list[tuple[str, str]]:
    """Clone *count* worker databases from *test_db_url*.

    Drops stale databases with matching names first, then clones fresh
    copies. On partial failure, cleans up any databases already created.

    Returns list of ``(db_url, db_name)`` tuples.
    """
    import contextlib

    from promptgrimoire.db.bootstrap import clone_database, drop_database

    base_url = test_db_url.split("?", maxsplit=1)[0].rsplit("/", 1)[0]
    query = ("?" + test_db_url.split("?", 1)[1]) if "?" in test_db_url else ""

    # Drop stale databases from interrupted previous runs
    for i in range(count):
        stale_url = f"{base_url}/{source_db_name}_{suffix}{i}{query}"
        with contextlib.suppress(Exception):
            drop_database(stale_url)

    # Clone fresh databases
    worker_dbs: list[tuple[str, str]] = []
    try:
        for i in range(count):
            target_name = f"{source_db_name}_{suffix}{i}"
            db_url = clone_database(test_db_url, target_name)
            worker_dbs.append((db_url, target_name))
    except Exception:
        for url, _ in worker_dbs:
            with contextlib.suppress(Exception):
                drop_database(url)
        raise

    return worker_dbs


async def _run_parallel_e2e(
    user_args: list[str],
    fail_fast: bool = False,
) -> int:
    """Orchestrate parallel E2E test execution with per-file isolation.

    Each test file gets its own cloned database and server instance.
    Returns 0 if all tests pass, 1 if any failed.
    """
    import contextlib
    import tempfile

    from promptgrimoire.config import get_settings

    # -- Discover test files --
    files = sorted(Path("tests/e2e").glob("test_*.py"))
    if not files:
        console.print("[yellow]No E2E test files found[/]")
        return 0
    console.print(f"[blue]Found {len(files)} test files[/]")

    # -- Get test database URL --
    test_db_url = get_settings().dev.test_database_url
    if not test_db_url:
        console.print("[red]DEV__TEST_DATABASE_URL not set[/]")
        return 1

    # -- Prepare template database --
    _pre_test_db_cleanup()

    # -- Extract source db name --
    source_db_name = test_db_url.split("?")[0].rsplit("/", 1)[1]

    # -- Create worker databases (drops stale ones first) --
    worker_dbs = _create_worker_databases(test_db_url, source_db_name, len(files))

    # -- Allocate ports and result directory --
    ports = _allocate_ports(len(files))
    result_dir = Path(tempfile.mkdtemp(prefix="e2e_parallel_"))

    wall_start = time.monotonic()
    results: list[tuple[Path, int, float]] = []
    all_passed = False  # safe default for finally if try raises early

    try:
        if fail_fast:
            results = await _run_fail_fast_workers(
                files, ports, worker_dbs, result_dir, user_args
            )
        else:
            results = await _run_all_workers(
                files, ports, worker_dbs, result_dir, user_args
            )

        # -- Compute aggregate exit code --
        # "all passed" for cleanup: only real results (0 or 5), not cancelled (-1)
        all_passed = len(results) > 0 and all(code in (0, 5) for _, code, _ in results)

        wall_clock = time.monotonic() - wall_start

        # -- Summary (printed before JUnit merge so it's visible even if merge fails) --
        _print_parallel_summary(results, wall_clock)

        # -- Retry failed files in isolation --
        if not all_passed:
            failed_files = [f for f, code, _ in results if code not in (0, 5, -1)]
            if failed_files:
                genuine, _flaky = await _retry_parallel_failures(
                    failed_files,
                    test_db_url,
                    source_db_name,
                    result_dir,
                    user_args,
                )
                all_passed = not genuine

        aggregate = 0 if all_passed else 1

        # -- Merge JUnit XML (best-effort) --
        with contextlib.suppress(Exception):
            _merge_junit_xml(result_dir)

        return aggregate

    finally:
        _cleanup_parallel_results(all_passed, worker_dbs, result_dir, results)


def _start_e2e_server(port: int) -> subprocess.Popen[bytes]:
    """Start a NiceGUI server subprocess for E2E tests.

    Returns the Popen handle. Blocks until the server accepts connections
    or fails with ``sys.exit(1)`` on timeout/crash.
    """
    import socket

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
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    console.print("[blue]py-spy recording saved to logs/[/]")


def _get_last_failed() -> list[str]:
    """Read failed test node IDs from pytest's lastfailed cache."""
    import json

    cache_path = Path(".pytest_cache/v/cache/lastfailed")
    if not cache_path.exists():
        return []
    data = json.loads(cache_path.read_text())
    return [k for k, v in data.items() if v]


def _retry_e2e_tests_in_isolation(log_path: Path) -> int:
    """Re-run failed E2E tests individually to distinguish flaky from genuine failures.

    Reads the pytest lastfailed cache for test node IDs, re-runs each one
    in its own pytest invocation (without ``--reruns``), and reports which
    passed (flaky due to test interaction) vs which still failed (genuine).

    Returns 0 if all failures were flaky, 1 if any genuinely failed.
    """
    failed_tests = _get_last_failed()
    if not failed_tests:
        return 1  # No cached failures — can't retry, report original failure

    console.print(
        f"\n[blue]Re-running {len(failed_tests)} failed test(s) in isolation...[/]"
    )

    genuine_failures: list[str] = []
    flaky: list[str] = []

    with log_path.open("a") as log_file:
        log_file.write(
            f"\n{'=' * 60}\n"
            f"Isolation retry: {len(failed_tests)} test(s)\n"
            f"{'=' * 60}\n\n"
        )

        for i, node_id in enumerate(failed_tests, 1):
            cmd = [
                "uv",
                "run",
                "pytest",
                node_id,
                "--tb=short",
                "-v",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ]

            log_file.write(f"--- Retry {i}/{len(failed_tests)}: {node_id} ---\n")
            log_file.flush()

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

            log_file.write(result.stdout)
            log_file.write(f"Exit code: {result.returncode}\n\n")
            log_file.flush()

            if result.returncode in (0, 5):
                flaky.append(node_id)
                console.print(
                    f"  [{i}/{len(failed_tests)}] {node_id}: "
                    f"[yellow]FLAKY[/] (passed in isolation)"
                )
            else:
                genuine_failures.append(node_id)
                console.print(
                    f"  [{i}/{len(failed_tests)}] {node_id}: "
                    f"[red]FAILED[/] (genuine failure)"
                )

    console.print()
    if flaky:
        console.print(
            f"[yellow]Flaky ({len(flaky)}):[/] passed when re-run in isolation"
        )
        for t in flaky:
            console.print(f"  {t}")
    if genuine_failures:
        console.print(f"[red]Genuine failures ({len(genuine_failures)}):[/]")
        for t in genuine_failures:
            console.print(f"  {t}")

    return 1 if genuine_failures else 0


def test_e2e() -> None:
    """Start NiceGUI server(s) and run Playwright E2E tests.

    By default, runs single-server serial mode.
    Pass ``--parallel`` for per-file parallelism with isolated servers
    and databases. Pass ``--fail-fast`` with ``--parallel`` to kill
    remaining workers on first failure.

    Extra arguments forwarded to pytest (e.g. ``uv run test-e2e -k browser``).
    """
    import socket

    # Consume custom flags before _run_pytest sees sys.argv
    parallel = "--parallel" in sys.argv
    if parallel:
        sys.argv.remove("--parallel")
    fail_fast = "--fail-fast" in sys.argv
    if fail_fast:
        sys.argv.remove("--fail-fast")
    use_pyspy = "--py-spy" in sys.argv
    if use_pyspy:
        sys.argv.remove("--py-spy")

    # Eagerly load settings so .env is read before subprocess spawning.
    from promptgrimoire.config import get_settings

    get_settings()

    if parallel:
        # Parallel mode: orchestrator handles servers, DBs, and pytest
        if use_pyspy:
            console.print(
                "[yellow]--py-spy is not supported in parallel mode, ignoring[/]"
            )
        user_args = sys.argv[1:]
        try:
            exit_code = asyncio.run(
                _run_parallel_e2e(user_args=user_args, fail_fast=fail_fast)
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted — cleaning up...[/]")
            exit_code = 130  # conventional SIGINT exit code
        sys.exit(exit_code)

    # --- Serial mode (unchanged) ---
    if use_pyspy:
        _check_ptrace_scope()

    _pre_test_db_cleanup()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    pyspy_process: subprocess.Popen[bytes] | None = None
    if use_pyspy:
        pyspy_process = _start_pyspy(server_process.pid)

    exit_code = 1
    try:
        log_path = Path("test-e2e.log")
        exit_code = _run_pytest(
            title=f"E2E Test Suite (Playwright, serial, fail-fast) — server {url}",
            log_path=log_path,
            default_args=[
                "-m",
                "e2e",
                "--ff",
                "--reruns",
                "3",
                "-v",
                "--tb=short",
                "--log-cli-level=WARNING",
            ],
        )
        if exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        if pyspy_process is not None:
            _stop_pyspy(pyspy_process)
        _stop_e2e_server(server_process)
    sys.exit(exit_code)


def test_e2e_slow() -> None:
    """Run E2E tests with full PDF compilation (latexmk).

    Same as ``test-e2e`` but sets ``E2E_SKIP_LATEXMK=0`` so the server
    runs real latexmk.  Tests that click Export PDF will receive actual
    PDF files. Requires TinyTeX.

    Extra arguments forwarded to pytest.
    """
    os.environ["E2E_SKIP_LATEXMK"] = "0"
    test_e2e()


def test_e2e_noretry() -> None:
    """Run E2E tests with no retries and fail-fast (-x).

    Same server lifecycle as ``test-e2e`` but skips ``--reruns`` and
    ``_retry_e2e_tests_in_isolation``.  Useful for debugging failing
    tests where retries waste time.

    Extra arguments forwarded to pytest.
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

    exit_code = 1
    try:
        exit_code = _run_pytest(
            title=f"E2E Debug (no retries, -x) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=[
                "-m",
                "e2e",
                "-x",
                "-v",
                "--tb=short",
                "--log-cli-level=WARNING",
            ],
        )
    finally:
        _stop_e2e_server(server_process)
    sys.exit(exit_code)


def test_e2e_changed() -> None:
    """Run E2E tests affected by changes relative to main.

    Same server lifecycle as ``test-e2e`` but uses pytest-depper for
    smart test selection. Only E2E tests that depend on changed files
    (vs main branch) will run. Doesn't stop on first failure, because
    the retryer will just get stuck.

    Extra arguments forwarded to pytest
    (e.g. ``uv run test-e2e-changed -k law``).

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

    exit_code = 1
    try:
        log_path = Path("test-e2e.log")
        exit_code = _run_pytest(
            title=f"E2E Changed Tests (vs main) — server {url}",
            log_path=log_path,
            default_args=[
                "-m",
                "e2e",
                "--ff",
                "--depper",
                "--tb=long",
                "--log-cli-level=WARNING",
                "-v",
            ],
        )
        if exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        _stop_e2e_server(server_process)
    sys.exit(exit_code)
