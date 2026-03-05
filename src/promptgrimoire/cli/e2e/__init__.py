"""E2E test commands — Typer sub-app and server management re-exports."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from promptgrimoire.cli._shared import _pre_test_db_cleanup, _prepend_filter, console
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
_PLAYWRIGHT_TEST_PATH = "tests/e2e"


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
                _run_parallel_e2e(user_args=user_args, fail_fast=fail_fast)
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted — cleaning up...[/]")
            return 130

    return _run_serial_playwright_e2e(user_args, use_pyspy=py_spy, reruns=True)


def run_nicegui_lane(user_args: list[str]) -> int:
    """Run the NiceGUI lane and return its exit code."""
    from promptgrimoire.config import get_settings

    get_settings()
    try:
        return asyncio.run(_run_nicegui_e2e(user_args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — cleaning up...[/]")
        return 130


def run_all_lanes(user_args: list[str]) -> int:
    """Run Playwright then NiceGUI lanes sequentially (always run both)."""
    console.print("[blue]Running Playwright lane...[/]")
    playwright_exit = run_playwright_lane(
        user_args,
        parallel=False,
        fail_fast=False,
        py_spy=False,
    )

    console.print("[blue]Running NiceGUI lane...[/]")
    nicegui_exit = run_nicegui_lane(user_args)

    return 0 if playwright_exit == 0 and nicegui_exit == 0 else 1


@e2e_app.command(
    "run",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def run(
    ctx: typer.Context,
    parallel: bool = typer.Option(
        False, "--parallel", help="Run with xdist parallelism"
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
) -> None:
    """Run Playwright E2E tests (serial fail-fast by default)."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(
        run_playwright_lane(
            args,
            parallel=parallel,
            fail_fast=fail_fast,
            py_spy=py_spy,
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
) -> None:
    """Run only NiceGUI lane files with per-file DB/process isolation."""
    args = _prepend_filter(ctx.args, filter_expr)
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
    """Run Playwright then NiceGUI lanes; always runs both for full diagnostics."""
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
    """Run Playwright E2E tests with full PDF compilation (latexmk)."""
    os.environ["E2E_SKIP_LATEXMK"] = "0"
    sys.exit(
        _run_serial_playwright_e2e(
            _prepend_filter(ctx.args, filter_expr),
            use_pyspy=False,
            reruns=True,
        )
    )


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

    try:
        exit_code = _run_pytest(
            title=f"Playwright Debug (no retries, -x) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=[
                _PLAYWRIGHT_TEST_PATH,
                "-m",
                "e2e",
                "-x",
                "-v",
                "--tb=short",
                "--log-cli-level=WARNING",
            ],
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

    try:
        log_path = Path("test-e2e.log")
        exit_code = _run_pytest(
            title=f"Playwright Changed Tests (vs main) — server {url}",
            log_path=log_path,
            default_args=[
                _PLAYWRIGHT_TEST_PATH,
                "-m",
                "e2e",
                "--ff",
                "--depper",
                "--tb=long",
                "--log-cli-level=WARNING",
                "-v",
            ],
            extra_args=user_args,
        )
        if exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        _stop_e2e_server(server_process)
    return exit_code


# -------------------------------------------------------------------
# Shared serial-mode helper (used by `run` and `slow`)
# -------------------------------------------------------------------


def _run_serial_playwright_e2e(
    extra_args: list[str],
    *,
    use_pyspy: bool,
    reruns: bool,
) -> int:
    """Run Playwright tests in single-server serial mode."""
    from promptgrimoire.config import get_settings

    get_settings()

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
        _PLAYWRIGHT_TEST_PATH,
        "-m",
        "e2e",
        "--ff",
        "-v",
        "--tb=short",
        "--log-cli-level=WARNING",
    ]
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
