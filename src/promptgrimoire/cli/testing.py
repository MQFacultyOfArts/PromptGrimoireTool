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
    _prepend_pytest_flags,
    console,
)

if TYPE_CHECKING:
    from typing import IO

    from rich.progress import TaskID

test_app = typer.Typer(
    help=(
        "Unit and integration test commands.\n\n"
        "To bypass the conftest guard for debugging this harness, "
        "set GRIMOIRE_TEST_HARNESS=1."
    )
)
_NON_UI_MARKER_EXPRESSION = "not e2e and not nicegui_ui"
_TEST_ALL_MARKER_EXPRESSION = f"{_NON_UI_MARKER_EXPRESSION} and not latexmk_full"
_SKIP_LATEXMK_ENV_VAR = "GRIMOIRE_TEST_SKIP_LATEXMK"


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
    """Return xdist worker count string.

    Returns ``"auto"`` to let pytest-xdist use all available CPUs.
    The previous cap at ``cpu_count // 2`` (max 16) was a workaround
    for ``test_db_cloning.py`` calling ``pg_terminate_backend()`` on the
    shared test database.  That root cause is now fixed (private
    clone-source DB provisioned by ``_pre_test_db_cleanup()``).
    """
    return "auto"


def _run_collect_only(
    default_args: list[str],
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    """Run pytest --collect-only -q — lightweight, no DB cleanup or log files."""
    user_args = extra_args or []
    all_args = ["uv", "run", "pytest", *default_args, "--co", "-q", *user_args]
    result = subprocess.run(
        all_args,
        env={
            **os.environ,
            "GRIMOIRE_TEST_HARNESS": "1",
            **(extra_env or {}),
        },
        check=False,
    )
    return result.returncode


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
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

        harness_env = {
            **os.environ,
            "GRIMOIRE_TEST_HARNESS": "1",
            **(extra_env or {}),
        }
        process = subprocess.Popen(
            all_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=harness_env,
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


_NICEGUI_UI_FILES: frozenset[str] = frozenset(
    {
        "test_instructor_course_admin_ui.py",
        "test_instructor_template_ui.py",
        "test_crud_management_ui.py",
    }
)


def _detect_test_type(args: list[str]) -> str:
    """Classify test paths as 'e2e', 'nicegui', or 'unit'.

    Scans *args* for anything that looks like a test path (not a flag).
    Returns the detected type, defaulting to 'unit' when no paths match
    a special category.
    """
    for arg in args:
        if arg.startswith("-"):
            continue
        normalised = arg.split("::")[0]
        if "tests/e2e" in normalised or normalised.startswith("tests/e2e"):
            return "e2e"
        filename = Path(normalised).name
        if filename in _NICEGUI_UI_FILES:
            return "nicegui"
    return "unit"


@test_app.command(
    "run",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def run_tests(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run specific tests through the appropriate harness.

    Auto-detects whether the given paths are E2E (Playwright), NiceGUI UI,
    or unit/integration tests, then delegates to the correct runner.

    Examples:
        grimoire test run tests/unit/test_foo.py
        grimoire test run tests/e2e/test_happy_path.py -k "login"
        grimoire test run tests/integration/test_crud_management_ui.py
    """
    from promptgrimoire.cli._shared import _prepend_filter

    args = _prepend_filter(ctx.args, filter_expr)
    test_type = _detect_test_type(args)

    if test_type == "e2e":
        from promptgrimoire.cli.e2e import run_playwright_noretry_lane

        sys.exit(run_playwright_noretry_lane(args))

    if test_type == "nicegui":
        from promptgrimoire.cli.e2e import run_nicegui_lane

        sys.exit(run_nicegui_lane(args))

    # Unit / integration — serial, no retries, fail-fast for targeted runs
    sys.exit(
        _run_pytest(
            title="Targeted Tests (no retries, fail-fast)",
            log_path=Path("test-run.log"),
            default_args=[
                "-x",
                "-v",
                "--tb=short",
            ],
            extra_args=args,
        )
    )


def _depper_base_ref() -> str:
    """Find the best base ref for pytest-depper comparison.

    Returns the merge-base of ``origin/main`` and ``HEAD`` — the commit
    where the current branch diverged.  Falls back to ``"main"`` if the
    merge-base cannot be computed (e.g. shallow clone).
    """
    result = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "main"


@test_app.command(
    "changed",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def changed_tests(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run pytest on tests affected by changes relative to main.

    Uses ``git merge-base`` to find the fork point so depper compares
    against the commit where the branch diverged, not the current tip
    of origin/main.
    """
    from promptgrimoire.cli._shared import _prepend_filter

    base_ref = _depper_base_ref()

    sys.exit(
        _run_pytest(
            title=f"Changed Tests (vs {base_ref[:12]}, "
            "excludes browser E2E and NiceGUI UI)",
            log_path=Path("test-failures.log"),
            default_args=[
                "--depper",
                f"--depper-base-branch={base_ref}",
                "-m",
                _NON_UI_MARKER_EXPRESSION,
                "-n",
                "auto",
                "--dist=worksteal",
                "-x",
                "--ff",
                "--tb=short",
            ],
            extra_args=_prepend_filter(ctx.args, filter_expr),
        )
    )


@test_app.command(
    "all",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def all_tests(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
    collect_only: bool = typer.Option(
        False, "--co", "--collect-only", help="Only collect tests, don't run them"
    ),
) -> None:
    """Run unit and integration tests under xdist parallel execution."""
    from promptgrimoire.cli._shared import _prepend_filter

    default_args = [
        "-m",
        _TEST_ALL_MARKER_EXPRESSION,
    ]

    args = _prepend_filter(ctx.args, filter_expr)

    if collect_only:
        sys.exit(
            _run_collect_only(
                default_args=default_args,
                extra_args=args,
                extra_env={_SKIP_LATEXMK_ENV_VAR: "1"},
            )
        )

    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)

    sys.exit(
        _run_pytest(
            title=(
                "Full Test Suite (unit + integration, excludes browser E2E, "
                "NiceGUI UI, and latexmk compile-stage tests)"
            ),
            log_path=Path("test-all.log"),
            default_args=[
                *default_args,
                "-n",
                _xdist_worker_count(),
                "--dist=worksteal",
                "-v",
            ],
            extra_args=args,
            extra_env={_SKIP_LATEXMK_ENV_VAR: "1"},
        )
    )


@test_app.command(
    "all-fixtures",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def all_fixtures_tests(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
    collect_only: bool = typer.Option(
        False, "--co", "--collect-only", help="Only collect tests, don't run them"
    ),
) -> None:
    """Run full test corpus including BLNS and slow tests."""
    from promptgrimoire.cli._shared import _prepend_filter

    default_args = ["-m", _NON_UI_MARKER_EXPRESSION]

    args = _prepend_filter(ctx.args, filter_expr)

    if collect_only:
        sys.exit(
            _run_collect_only(
                default_args=default_args,
                extra_args=args,
            )
        )

    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)

    sys.exit(
        _run_pytest(
            title="Full Fixture Corpus (excluding browser E2E and NiceGUI UI)",
            log_path=Path("test-all-fixtures.log"),
            default_args=[*default_args, "-v", "--tb=short"],
            extra_args=args,
        )
    )
