"""E2E test commands — Typer sub-app and server management re-exports."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from promptgrimoire.cli._shared import _pre_test_db_cleanup, console
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
) -> None:
    """Run E2E tests (serial fail-fast by default)."""
    from promptgrimoire.cli.e2e._parallel import _run_parallel_e2e
    from promptgrimoire.config import get_settings

    get_settings()

    if parallel:
        if py_spy:
            console.print(
                "[yellow]--py-spy is not supported in parallel mode, ignoring[/]"
            )
        try:
            exit_code = asyncio.run(
                _run_parallel_e2e(user_args=ctx.args, fail_fast=fail_fast)
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted — cleaning up...[/]")
            exit_code = 130
        sys.exit(exit_code)

    _run_serial_e2e(ctx.args, use_pyspy=py_spy, reruns=True)


@e2e_app.command(
    "slow",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def slow(ctx: typer.Context) -> None:
    """Run E2E tests with full PDF compilation (latexmk)."""
    os.environ["E2E_SKIP_LATEXMK"] = "0"
    _run_serial_e2e(ctx.args, use_pyspy=False, reruns=True)


@e2e_app.command(
    "noretry",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def noretry(ctx: typer.Context) -> None:
    """Run E2E tests with no retries and fail-fast (-x)."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

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
            extra_args=ctx.args,
        )
    finally:
        _stop_e2e_server(server_process)
    sys.exit(exit_code)


@e2e_app.command(
    "changed",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def changed(ctx: typer.Context) -> None:
    """Run E2E tests affected by changes relative to main."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

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
            extra_args=ctx.args,
        )
        if exit_code not in (0, 5):
            exit_code = _retry_e2e_tests_in_isolation(log_path)
    finally:
        _stop_e2e_server(server_process)
    sys.exit(exit_code)


# -------------------------------------------------------------------
# Shared serial-mode helper (used by `run` and `slow`)
# -------------------------------------------------------------------


def _run_serial_e2e(
    extra_args: list[str],
    *,
    use_pyspy: bool,
    reruns: bool,
) -> None:
    """Run E2E tests in single-server serial mode, then exit."""
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
            title=(f"E2E Test Suite (Playwright, serial, fail-fast) — server {url}"),
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
    sys.exit(exit_code)
