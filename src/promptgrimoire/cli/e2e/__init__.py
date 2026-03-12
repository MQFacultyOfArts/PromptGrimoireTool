"""E2E test commands — Typer sub-app and server management re-exports."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from promptgrimoire.cli._shared import (
    _pre_test_db_cleanup,
    _prepend_filter,
    _prepend_pytest_flags,
    console,
)
from promptgrimoire.cli.e2e._lanes import PLAYWRIGHT_LANE, LaneResult
from promptgrimoire.cli.e2e._retry import _retry_e2e_tests_in_isolation

if TYPE_CHECKING:
    import subprocess
from promptgrimoire.cli.e2e._server import (
    _check_ptrace_scope,
    _start_e2e_server,
    _start_pyspy,
    _stop_e2e_server,
    _stop_pyspy,
)
from promptgrimoire.cli.e2e._workers import _allocate_ports as _allocate_ports
from promptgrimoire.cli.testing import _run_pytest

e2e_app = typer.Typer(help="End-to-end test commands.")
_PLAYWRIGHT_TEST_PATH = str(PLAYWRIGHT_LANE.test_paths[0])


def _has_test_path(args: list[str]) -> bool:
    """Return True if args contains an explicit test file or directory path."""
    for arg in args:
        if arg.startswith("-"):
            continue
        path_part = arg.split("::")[0]
        if Path(path_part).exists():
            return True
    return False


async def _run_nicegui_e2e(user_args: list[str]) -> int:
    """Run only NiceGUI E2E files in isolated subprocesses."""
    from promptgrimoire.cli.e2e._lanes import NICEGUI_LANE
    from promptgrimoire.cli.e2e._parallel import run_lane_files
    from promptgrimoire.cli.e2e._workers import run_nicegui_file

    return await run_lane_files(
        NICEGUI_LANE,
        run_nicegui_file,
        user_args=user_args,
        worker_count=1,
    )


def run_playwright_lane(
    user_args: list[str],
    *,
    parallel: bool,
    fail_fast: bool,
    py_spy: bool,
    browser: str | None = None,
) -> int:
    """Run the Playwright lane and return its exit code."""
    from promptgrimoire.cli.e2e._parallel import _run_parallel_e2e
    from promptgrimoire.config import get_settings

    get_settings()

    if parallel:
        if py_spy:
            console.print(
                "[yellow]--py-spy is not supported in parallel mode, ignoring[/]"
            )
        try:
            return asyncio.run(
                _run_parallel_e2e(
                    user_args=user_args, fail_fast=fail_fast, browser=browser
                )
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted — cleaning up...[/]")
            return 130

    return _run_serial_playwright_e2e(
        user_args, use_pyspy=py_spy, reruns=True, browser=browser
    )


def run_nicegui_lane(user_args: list[str]) -> int:
    """Run the NiceGUI lane and return its exit code."""
    from promptgrimoire.config import get_settings

    get_settings()
    try:
        return asyncio.run(_run_nicegui_e2e(user_args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — cleaning up...[/]")
        return 130


def _print_all_lanes_summary(
    cwd: Path,
    branch: str,
    results: list[LaneResult],
) -> None:
    """Print a structured summary of all lane results."""
    console.print()
    console.print("[bold]── Summary ──────────────────────────────────────────[/]")
    console.print(f"  Dir:    {cwd}")
    console.print(f"  Branch: {branch}")
    console.print()
    console.print(f"  {'Lane':<14} {'Exit':<6} {'Log / Artifacts'}")
    console.print(f"  {'─' * 14} {'─' * 6} {'─' * 40}")
    for lr in results:
        status = "[green]PASS[/]" if lr.exit_code == 0 else "[red]FAIL[/]"
        path_info = str(lr.log_path or lr.artifact_dir or "—")
        console.print(f"  {lr.name:<14} {status}  {path_info}")
    console.print()

    any_failed = any(lr.exit_code != 0 for lr in results)
    if any_failed:
        console.print("[red]Some lanes failed.[/]")
    else:
        console.print("[green]All lanes passed.[/]")


def run_all_lanes(user_args: list[str]) -> int:
    """Run unit tests, then Playwright, then NiceGUI — always runs all three."""
    from promptgrimoire.cli.testing import _run_pytest, _xdist_worker_count
    from promptgrimoire.config import get_current_branch

    _clear_lastfailed_cache()

    branch = get_current_branch() or "unknown"
    cwd = Path.cwd()
    lane_results: list[LaneResult] = []

    # --- Unit / integration lane ---
    unit_log = Path("test-all.log")
    console.print(f"[blue]Running unit/integration lane...[/]  log: {unit_log}")
    unit_exit = _run_pytest(
        title="Unit + Integration (xdist)",
        log_path=unit_log,
        default_args=[
            "-m",
            "not e2e and not nicegui_ui and not latexmk_full",
            "-n",
            _xdist_worker_count(),
            "--dist=worksteal",
            "-v",
        ],
        extra_args=user_args,
        extra_env={"GRIMOIRE_TEST_SKIP_LATEXMK": "1"},
    )
    lane_results.append(LaneResult("unit", unit_exit, log_path=unit_log))

    # --- Playwright lane (parallel) ---
    console.print("[blue]Running Playwright lane (parallel)...[/]")
    playwright_exit = run_playwright_lane(
        user_args,
        parallel=True,
        fail_fast=False,
        py_spy=False,
    )
    lane_results.append(LaneResult("playwright", playwright_exit))

    # --- NiceGUI lane ---
    console.print("[blue]Running NiceGUI lane...[/]")
    nicegui_exit = run_nicegui_lane(user_args)
    lane_results.append(LaneResult("nicegui", nicegui_exit))

    # --- Summary ---
    _print_all_lanes_summary(cwd, branch, lane_results)

    return 0 if all(lr.exit_code == 0 for lr in lane_results) else 1


def _normalise_optional_lane_exit(exit_code: int, user_args: list[str]) -> int:
    """Treat filtered no-test outcomes as non-fatal for umbrella commands."""
    return 0 if user_args and exit_code == 5 else exit_code


def _run_latexmk_full_suite(user_args: list[str]) -> int:
    """Run the compiled-PDF validation suite in serial mode."""
    return _run_pytest(
        title="LuaLaTeX Compile Suite (serial)",
        log_path=Path("test-latexmk-full.log"),
        default_args=["-m", "latexmk_full", "-v", "--tb=short"],
        extra_args=user_args,
    )


def run_slow_lanes(user_args: list[str]) -> int:
    """Run Playwright slow lane, then compiled-PDF suites when applicable."""
    previous_skip_latexmk = os.environ.get("E2E_SKIP_LATEXMK")
    os.environ["E2E_SKIP_LATEXMK"] = "0"
    try:
        console.print("[blue]Running Playwright slow lane...[/]")
        playwright_exit = _normalise_optional_lane_exit(
            _run_serial_playwright_e2e(
                user_args,
                use_pyspy=False,
                reruns=True,
                clear_cache=True,
            ),
            user_args,
        )
    finally:
        if previous_skip_latexmk is None:
            os.environ.pop("E2E_SKIP_LATEXMK", None)
        else:
            os.environ["E2E_SKIP_LATEXMK"] = previous_skip_latexmk

    if _has_test_path(user_args):
        return playwright_exit

    console.print("[blue]Running LuaLaTeX compile lane...[/]")
    latexmk_exit = _normalise_optional_lane_exit(
        _run_latexmk_full_suite(user_args),
        user_args,
    )

    return 0 if playwright_exit == 0 and latexmk_exit == 0 else 1


@e2e_app.command(
    "run",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def run(
    ctx: typer.Context,
    serial: bool = typer.Option(
        False, "--serial", help="Run in serial mode (single server)"
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop on first failure (parallel only)",
    ),
    py_spy: bool = typer.Option(False, "--py-spy", help="Profile with py-spy"),
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
    browser: str | None = typer.Option(
        None, help="Browser engine: chromium, firefox (default: chromium)"
    ),
) -> None:
    """Run Playwright E2E tests (parallel by default, --serial for single server)."""
    args = _prepend_filter(ctx.args, filter_expr)
    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)
    sys.exit(
        run_playwright_lane(
            args,
            parallel=not serial,
            fail_fast=fail_fast,
            py_spy=py_spy,
            browser=browser,
        )
    )


def _check_firefox_installed(exit_code: int) -> None:
    """Print a hint if Firefox failed and Playwright's Firefox bundle is missing."""
    if exit_code == 0:
        return
    firefox_dirs = list((Path.home() / ".cache/ms-playwright").glob("firefox-*"))
    if not firefox_dirs:
        print(
            "Firefox not installed. Run: uv run playwright install firefox",
            file=sys.stderr,
        )


@e2e_app.command(
    "firefox",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def firefox(
    ctx: typer.Context,
    serial: bool = typer.Option(
        False, "--serial", help="Run in serial mode (single server)"
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop on first failure (parallel only)",
    ),
    py_spy: bool = typer.Option(False, "--py-spy", help="Profile with py-spy"),
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
) -> None:
    """Run Playwright E2E tests against Firefox."""
    args = _prepend_filter(ctx.args, filter_expr)
    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)
    exit_code = run_playwright_lane(
        args,
        parallel=not serial,
        fail_fast=fail_fast,
        py_spy=py_spy,
        browser="firefox",
    )
    _check_firefox_installed(exit_code)
    sys.exit(exit_code)


def run_all_browsers(
    user_args: list[str],
    *,
    fail_fast: bool = False,
) -> int:
    """Run Chromium then Firefox sequentially, reporting per-browser results."""
    from promptgrimoire.config import get_current_branch

    cwd = Path.cwd()
    branch = get_current_branch() or "unknown"
    browsers = ["chromium", "firefox"]
    lane_results: list[LaneResult] = []

    for browser_name in browsers:
        console.print(f"\n[blue]Running Playwright lane ({browser_name})...[/]")
        exit_code = run_playwright_lane(
            user_args,
            parallel=True,
            fail_fast=False,
            py_spy=False,
            browser=browser_name,
        )
        lane_results.append(LaneResult(f"playwright-{browser_name}", exit_code))
        if fail_fast and exit_code != 0:
            break

    _print_all_lanes_summary(cwd, branch, lane_results)
    return 0 if all(lr.exit_code == 0 for lr in lane_results) else 1


@e2e_app.command(
    "all-browsers",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def all_browsers(
    ctx: typer.Context,
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop after the first browser that fails",
    ),
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
) -> None:
    """Run E2E tests against all browsers (Chromium then Firefox)."""
    args = _prepend_filter(ctx.args, filter_expr)
    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)
    sys.exit(run_all_browsers(args, fail_fast=fail_fast))


@e2e_app.command(
    "browserstack",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def browserstack(
    ctx: typer.Context,
    profile: str | None = typer.Argument(
        None,
        help="Browser profile: safari, firefox, unsupported (default: supported)",
    ),
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
    exit_first: bool = typer.Option(
        False, "-x", "--exit-first", help="Stop on first failure (-x)"
    ),
    failed_first: bool = typer.Option(
        False, "--ff", "--failed-first", help="Run previously failed tests first (--ff)"
    ),
) -> None:
    """Run E2E tests against real browsers via BrowserStack.

    Requires BROWSERSTACK__USERNAME and BROWSERSTACK__ACCESS_KEY in .env
    (or BROWSERSTACK_USERNAME / BROWSERSTACK_ACCESS_KEY as env vars).
    """
    from promptgrimoire.cli.e2e._browserstack import (
        resolve_browserstack_config,
        run_browserstack_suite,
    )
    from promptgrimoire.config import get_settings

    bs = get_settings().browserstack
    if not bs.username or not bs.access_key.get_secret_value():
        console.print(
            "[red]BROWSERSTACK__USERNAME and BROWSERSTACK__ACCESS_KEY must be set[/]"
        )
        raise typer.Exit(1)

    config_path = resolve_browserstack_config(profile)
    marker_expr = "browser_gate" if profile == "unsupported" else "e2e"

    args = _prepend_filter(ctx.args, filter_expr)
    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)

    sys.exit(
        run_browserstack_suite(
            config_path=config_path,
            user_args=args,
            marker_expr=marker_expr,
        )
    )


@e2e_app.command(
    "nicegui",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def nicegui(
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
) -> None:
    """Run only NiceGUI lane files with per-file DB/process isolation."""
    args = _prepend_filter(ctx.args, filter_expr)
    args = _prepend_pytest_flags(args, exit_first=exit_first, failed_first=failed_first)
    sys.exit(run_nicegui_lane(args))


@e2e_app.command(
    "all",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def all_lanes(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run unit tests, Playwright E2E, and NiceGUI lanes — always runs all three."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(run_all_lanes(args))


@e2e_app.command(
    "slow",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def slow(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run Playwright slow E2E plus serial compiled-PDF validation suites."""
    sys.exit(run_slow_lanes(_prepend_filter(ctx.args, filter_expr)))


@e2e_app.command(
    "noretry",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def noretry(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run Playwright E2E tests with no retries and fail-fast (-x)."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(run_playwright_noretry_lane(args))


def run_playwright_noretry_lane(user_args: list[str]) -> int:
    """Run Playwright lane with no retries and fail-fast semantics."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    default_args = [
        "-m",
        "e2e",
        "-x",
        "-v",
        "--tb=short",
        "--log-cli-level=WARNING",
    ]
    if not _has_test_path(user_args):
        default_args.insert(0, _PLAYWRIGHT_TEST_PATH)

    try:
        exit_code = _run_pytest(
            title=f"Playwright Debug (no retries, -x) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=default_args,
            extra_args=user_args,
        )
    finally:
        _stop_e2e_server(server_process)
    return exit_code


@e2e_app.command(
    "changed",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def changed(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run Playwright E2E tests affected by changes relative to main."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(run_playwright_changed_lane(args))


def run_playwright_changed_lane(user_args: list[str]) -> int:
    """Run changed Playwright tests, with isolation retry on failure."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    default_args = [
        "-m",
        "e2e",
        "--ff",
        "--depper",
        "--tb=long",
        "--log-cli-level=WARNING",
        "-v",
    ]
    if not _has_test_path(user_args):
        default_args.insert(0, _PLAYWRIGHT_TEST_PATH)

    try:
        log_path = Path("test-e2e.log")
        exit_code = _run_pytest(
            title=f"Playwright Changed Tests (vs main) — server {url}",
            log_path=log_path,
            default_args=default_args,
            extra_args=user_args,
        )
        if exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        _stop_e2e_server(server_process)
    return exit_code


@e2e_app.command(
    "cards",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def cards(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run card-touching E2E tests (marked with @pytest.mark.cards)."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(run_playwright_cards_lane(args))


def run_playwright_cards_lane(user_args: list[str]) -> int:
    """Run card-touching Playwright tests in serial mode."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    default_args = [
        "-m",
        "e2e and cards",
        "-v",
        "--tb=short",
        "--log-cli-level=WARNING",
    ]
    if not _has_test_path(user_args):
        default_args.insert(0, _PLAYWRIGHT_TEST_PATH)

    try:
        exit_code = _run_pytest(
            title=f"Playwright Card Tests (-m cards) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=default_args,
            extra_args=user_args,
        )
    finally:
        _stop_e2e_server(server_process)
    return exit_code


# -------------------------------------------------------------------
# Shared serial-mode helper (used by `run` and `slow`)
# -------------------------------------------------------------------


def _clear_lastfailed_cache() -> None:
    """Remove stale pytest lastfailed cache.

    The cache persists across runs with different markers (-m "e2e" vs
    unmarked).  When ``e2e slow`` or ``e2e all`` re-runs failures in
    isolation, stale entries from previous ``test all`` runs bleed
    through and cause spurious "genuine failures".  Clearing the cache
    before big runs ensures the retry only sees failures from *this* run.
    """
    cache_file = Path(".pytest_cache/v/cache/lastfailed")
    if cache_file.exists():
        cache_file.unlink()


def _run_serial_playwright_e2e(
    extra_args: list[str],
    *,
    use_pyspy: bool,
    reruns: bool,
    clear_cache: bool = False,
    browser: str | None = None,
) -> int:
    """Run Playwright tests in single-server serial mode."""
    from promptgrimoire.config import get_settings

    get_settings()

    if clear_cache:
        _clear_lastfailed_cache()

    if use_pyspy:
        _check_ptrace_scope()

    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    pyspy_process: subprocess.Popen[bytes] | None = None
    if use_pyspy:
        pyspy_process = _start_pyspy(server_process.pid)

    default_args = [
        "-m",
        "e2e",
        "--ff",
        "-v",
        "--tb=short",
        "--log-cli-level=WARNING",
    ]
    if browser is not None:
        default_args += ["--browser", browser]
    if not _has_test_path(extra_args):
        default_args.insert(0, _PLAYWRIGHT_TEST_PATH)

    if reruns:
        default_args += ["--reruns", "3"]

    exit_code = 1
    try:
        log_path = Path("test-e2e.log")
        exit_code = _run_pytest(
            title=(f"Playwright Test Suite (serial, fail-fast) — server {url}"),
            log_path=log_path,
            default_args=default_args,
            extra_args=extra_args,
        )
        if reruns and exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        if pyspy_process is not None:
            _stop_pyspy(pyspy_process)
        _stop_e2e_server(server_process)
    return exit_code
