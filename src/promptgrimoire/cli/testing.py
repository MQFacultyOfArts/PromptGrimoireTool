"""Unit/integration test commands."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from promptgrimoire.cli._shared import (
    _COLLECTED_RE,
    _PCT_RE,
    _RESULT_KW_RE,
    _SEPARATOR_RE,
    _XDIST_ITEMS_RE,
    _build_test_header,
    _pre_test_db_cleanup,
    console,
)

if TYPE_CHECKING:
    from typing import IO

    from rich.progress import TaskID

test_app = typer.Typer(help="Unit and integration test commands.")


# ---------------------------------------------------------------------------
# Pytest output parsing helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase-dispatch helpers for _stream_with_progress
# ---------------------------------------------------------------------------


def _handle_collecting_phase(line: str, count: int | None) -> tuple[int | None, bool]:
    """Process a line during the collecting phase.

    Returns:
        (new_count, transition_to_running) tuple.
    """
    parsed = _parse_collection(line)
    if parsed is not None:
        return parsed, True
    return count, False


def _activate_running_phase(
    count: int | None,
    progress: Progress,
    task_id: TaskID,
) -> None:
    """Update the progress bar when transitioning from collecting to running."""
    desc = "No tests collected" if count == 0 else f"Running {count} tests"
    progress.update(task_id, total=count or None, description=desc)


def _handle_running_phase(
    line: str,
    progress: Progress | None,
    task_id: TaskID | None,
    total: int | None,
    done_count: int,
) -> tuple[int, bool]:
    """Process a line during the running phase.

    Returns:
        (new_done_count, transition_to_summary) tuple.
    """
    if _is_summary_boundary(line):
        return done_count, True

    advance, is_fail = _parse_result(line, total)
    if advance:
        new_done = (
            max(done_count, advance) if total and advance > 1 else done_count + advance
        )
        if progress is not None and task_id is not None:
            progress.update(task_id, completed=new_done)
        if is_fail and progress is not None:
            progress.print(f"[red]{line}[/]")
        return new_done, False

    return done_count, False


# ---------------------------------------------------------------------------
# Output streaming
# ---------------------------------------------------------------------------


def _stream_plain(
    process: subprocess.Popen[str],
    log_file: IO[str],
) -> int:
    """Stream pytest output with token-minimising filtering for piped/CI use.

    All lines go to the log file. Stdout suppresses everything until the
    post-results summary section, then prints from there. FAILED/ERROR
    lines are printed immediately regardless of phase.
    """
    separator_count = 0
    in_summary = False

    for line in process.stdout or []:
        log_file.write(line)
        log_file.flush()
        stripped = line.rstrip()

        if not in_summary and _SEPARATOR_RE.match(stripped):
            separator_count += 1
            if separator_count >= 2:
                in_summary = True

        if in_summary:
            print(line, end="")
            continue

        if "FAILED" in stripped or "ERROR" in stripped:
            print(line, end="")

    process.wait()
    return process.returncode


def _dispatch_progress_line(
    stripped: str,
    raw_line: str,
    phase: str,
    count: int | None,
    done: int,
    progress: Progress,
    task_id: TaskID,
) -> tuple[str, int | None, int]:
    """Dispatch a single line through the phase state machine.

    Returns:
        (new_phase, new_count, new_done) tuple.
    """
    if phase == "summary":
        print(raw_line, end="")
        return phase, count, done

    if phase == "collecting":
        count, start_running = _handle_collecting_phase(stripped, count)
        if start_running:
            _activate_running_phase(count, progress, task_id)
            return "running", count, done
        return "collecting", count, done

    done, enter_summary = _handle_running_phase(
        stripped, progress, task_id, count, done
    )
    if enter_summary:
        progress.stop()
        print(raw_line, end="")
        return "summary", count, done
    return "running", count, done


def _stream_with_progress(
    process: subprocess.Popen[str],
    log_file: IO[str],
) -> int:
    """Stream pytest output with a Rich progress bar -- for interactive TTY use."""
    phase = "collecting"
    count: int | None = None
    done = 0

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
        for raw_line in process.stdout or []:
            log_file.write(raw_line)
            log_file.flush()
            phase, count, done = _dispatch_progress_line(
                raw_line.rstrip(), raw_line, phase, count, done, progress, task_id
            )
    finally:
        if phase != "summary":
            progress.stop()

    process.wait()
    return process.returncode


# ---------------------------------------------------------------------------
# Core pytest runner
# ---------------------------------------------------------------------------


def _xdist_worker_count() -> str:
    """Calculate reliable xdist worker count.

    Caps at half CPU count (max 16).  Higher counts cause intermittent
    asyncpg ``ConnectionResetError`` under NullPool connection churn.
    """
    cpus = os.cpu_count() or 4
    return str(min(cpus // 2, 16))


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
    extra_args: list[str] | None = None,
) -> int:
    """Run pytest with Rich formatting and logging.

    The ``promptgrimoire.config`` import is deferred because it triggers
    pydantic-settings environment loading, which must not happen at
    module-import time (breaks test isolation and import-guard tests).
    """
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
    user_args = extra_args or []

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

        process = subprocess.Popen(  # nosec B603 -- args from trusted CLI config
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

        log_footer = f"""
{"=" * 60}
Finished: {end_time.isoformat()}
Duration: {duration}
Exit code: {exit_code}
{"=" * 60}
"""
        log_file.write(log_footer)

    if interactive:
        _print_footer(exit_code, duration, log_path)

    return exit_code


def _print_footer(exit_code: int, duration: object, log_path: Path) -> None:
    """Print a Rich footer panel summarising the test run."""
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


# ---------------------------------------------------------------------------
# Typer commands
# ---------------------------------------------------------------------------


@test_app.command(
    "changed",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def changed_tests(ctx: typer.Context) -> None:
    """Run pytest on tests affected by changes relative to main."""
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
            extra_args=ctx.args,
        )
    )


@test_app.command(
    "all",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def all_tests(ctx: typer.Context) -> None:
    """Run unit and integration tests under xdist parallel execution."""
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
            extra_args=ctx.args,
        )
    )


@test_app.command(
    "all-fixtures",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def all_fixtures_tests(ctx: typer.Context) -> None:
    """Run full test corpus including BLNS and slow tests."""
    sys.exit(
        _run_pytest(
            title="Full Fixture Corpus (including BLNS/slow)",
            log_path=Path("test-all-fixtures.log"),
            default_args=["-m", "", "-v", "--tb=short"],
            extra_args=ctx.args,
        )
    )
