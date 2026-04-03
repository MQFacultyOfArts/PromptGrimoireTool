"""Unit/integration test commands."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import typer.core
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

    import click
    from rich.progress import TaskID


def _looks_like_test_path(arg: str) -> bool:
    """True if *arg* looks like a test file path, not a subcommand."""
    return (
        arg.endswith(".py")
        or arg.startswith("tests/")
        or arg.startswith("tests\\")
        or "::test_" in arg
    )


class _TestGroup(typer.core.TyperGroup):
    """Auto-redirect bare test paths to the ``run`` subcommand.

    ``grimoire test tests/unit/foo.py`` is treated as
    ``grimoire test run tests/unit/foo.py``.
    """

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args and _looks_like_test_path(args[0]):
            args = ["run", *args]
        return super().resolve_command(ctx, args)


test_app = typer.Typer(
    cls=_TestGroup,
    help=(
        "Unit and integration test commands.\n\n"
        "To bypass the conftest guard for debugging this harness, "
        "set GRIMOIRE_TEST_HARNESS=1."
    ),
)
_NON_UI_MARKER_EXPRESSION = "not e2e and not nicegui_ui"
_TEST_ALL_MARKER_EXPRESSION = (
    f"{_NON_UI_MARKER_EXPRESSION} and not latexmk_full and not smoke"
)
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
    """Run pytest --collect-only -q — lightweight, no DB cleanup or log files.

    Strips verbosity and traceback flags from *default_args* since ``--co -q``
    needs terse output.
    """
    _STRIP = {"-v", "-vv", "--verbose"}
    cleaned = [
        a
        for i, a in enumerate(default_args)
        if a not in _STRIP and not a.startswith("--tb=")
    ]
    user_args = extra_args or []
    all_args = ["uv", "run", "pytest", *cleaned, "--co", "-q", *user_args]
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
        "test_annotation_cards_charac.py",
        "test_annotation_pdf_export_filename_ui.py",
        "test_bulk_enrol_upload_ui.py",
        "test_crud_management_ui.py",
        "test_instructor_course_admin_ui.py",
        "test_instructor_template_ui.py",
        "test_multi_doc_tabs.py",
        "test_organise_charac.py",
        "test_page_load_query_count.py",
        "test_respond_charac.py",
        "test_slot_deletion_race_369.py",
        "test_tag_management_crdt_sync.py",
        "test_memory_leak_probe.py",
        "test_event_loop_render_lag.py",
        "test_lazy_card_detail.py",
        "test_vue_sidebar_spike.py",
        "test_vue_sidebar_dom_contract.py",
        "test_vue_sidebar_expand.py",
        "test_vue_sidebar_mutations.py",
        "test_vue_sidebar_interactions.py",
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

    # Unit / integration — serial, no retries, fail-fast for targeted runs.
    # Exclude nicegui_ui and e2e markers so directory-level runs
    # (e.g. tests/integration/) don't collect NiceGUI tests that
    # need the user_simulation harness.
    sys.exit(
        _run_pytest(
            title="Targeted Tests (no retries, fail-fast)",
            log_path=Path("test-run.log"),
            default_args=[
                "-x",
                "-v",
                "--tb=short",
                "-m",
                _NON_UI_MARKER_EXPRESSION,
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


def _run_js(*, verbose: bool = False) -> int:
    """Run JS unit tests (vitest) and return exit code.

    Skips gracefully when npx is not available (e.g. production server).
    """
    import shutil

    if not shutil.which("npx"):
        console.print("[yellow]npx not installed, skipping JS tests[/]")
        return 0

    cmd = ["npx", "vitest", "run"]
    if verbose:
        cmd.append("--reporter=verbose")
    return subprocess.run(cmd, check=False).returncode


def _run_bats() -> int:
    """Run BATS shell script tests and return exit code."""
    import shutil

    if not shutil.which("bats"):
        console.print("[yellow]bats not installed, skipping (sudo apt install bats)[/]")
        return 0

    bats_dir = Path("deploy/tests")
    if not bats_dir.exists():
        console.print("[yellow]No BATS test directory found, skipping[/]")
        return 0

    bats_files = sorted(bats_dir.glob("*.bats"))
    if not bats_files:
        console.print("[yellow]No .bats files found, skipping[/]")
        return 0

    result = subprocess.run(
        ["bats", *[str(f) for f in bats_files]],
        check=False,
    )
    return result.returncode


@test_app.command("bats")
def bats_tests() -> None:
    """Run BATS shell script tests (deploy/tests/*.bats)."""
    sys.exit(_run_bats())


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
    """Run BATS + unit tests under xdist parallel execution."""
    from promptgrimoire.cli._shared import _prepend_filter

    default_args = [
        "tests/unit",
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

    # Run BATS first, then unit tests
    console.print("[blue]Running BATS lane...[/]")
    bats_exit = _run_bats()
    if bats_exit != 0:
        console.print("[red]BATS failed — continuing to unit tests[/]")

    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)

    # --- JS (vitest) ---
    console.print("\n[bold blue]Running JS unit tests...[/]")
    js_exit = _run_js()

    if js_exit != 0 and exit_first:
        sys.exit(js_exit)

    unit_exit = _run_pytest(
        title="Unit Tests (excludes smoke, E2E, NiceGUI UI, latexmk)",
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

    sys.exit(1 if bats_exit != 0 or js_exit != 0 or unit_exit != 0 else 0)


@test_app.command(
    "smoke",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def smoke_tests(
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
    """Run toolchain smoke tests (pandoc, lualatex, tlmgr) serially."""
    from promptgrimoire.cli._shared import _prepend_filter

    default_args = ["-m", "smoke", "-v", "--tb=short", "-o", "addopts="]

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
            title="Smoke Tests (toolchain: pandoc, lualatex, tlmgr)",
            log_path=Path("test-smoke.log"),
            default_args=default_args,
            extra_args=args,
        )
    )


@test_app.command("js")
def js_tests() -> None:
    """Run JS unit tests (vitest)."""
    sys.exit(_run_js(verbose=True))


@test_app.command("smoke-export")
def smoke_export() -> None:
    """Compile a CJK + emoji test document to PDF.

    Post-deploy smoke test: exercises the full generate_tex_only() +
    compile_latex() pipeline with CJK text and emoji. Verifies that
    luaotfload's color-emoji PNG cache write succeeds in the current
    execution context (catches ProtectSystem=strict cwd issues).

    Usage on server after deploy:
        grimoire-run grimoire test smoke-export
    """
    import asyncio
    import tempfile
    from pathlib import Path

    from promptgrimoire.export.pdf import compile_latex
    from promptgrimoire.export.pdf_export import generate_tex_only

    # Exercises: CJK text, emoji, table with annotation in cell,
    # and non-table annotation. Tag colour "smoke" generates
    # tag-smoke, tag-smoke-light, tag-smoke-dark in the preamble.
    html = (
        "<p>日本語のテスト文書です。</p>\n"
        "<table><tr>"
        '<td><span data-hl="0" data-colors="tag-smoke-light"'
        ' data-annots="\\annot{tag-smoke-dark}'
        "{\\textbf{1.} Smoke test annotation}"
        '">注釈テキスト</span></td>'
        "<td>✅ 完了</td>"
        "</tr></table>\n"
        "<p>😊 よくできました</p>"
    )
    tag_colours: dict[str, str] = {"smoke": "#888888"}

    async def _run() -> Path:
        output_dir = Path(tempfile.mkdtemp(prefix="grimoire_smoke_export_"))
        tex_path = await generate_tex_only(
            html_content=html,
            highlights=[],
            tag_colours=tag_colours,
            output_dir=output_dir,
        )
        return await compile_latex(tex_path, output_dir)

    try:
        pdf_path = asyncio.run(_run())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)

    size = pdf_path.stat().st_size

    if size < 1000:
        print(f"FAIL: PDF too small ({size} bytes): {pdf_path}")
        sys.exit(1)

    print(f"OK: {pdf_path} ({size} bytes)")
    sys.exit(0)
