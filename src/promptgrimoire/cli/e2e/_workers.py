"""E2E worker execution, port allocation, and reporting."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys
import time
from pathlib import Path

from junitparser import JUnitXml

from promptgrimoire.cli._shared import console
from promptgrimoire.cli.e2e._server import _SERVER_SCRIPT_PATH


def _allocate_ports(n: int) -> list[int]:
    """Allocate *n* distinct free TCP ports from the OS.

    Opens *n* sockets simultaneously (to guarantee uniqueness), reads their
    OS-assigned ports, then closes them all.  The returned ports are not
    *reserved* -- a race is theoretically possible -- but holding them open
    together ensures no duplicates within the batch.
    """
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
            str(_SERVER_SCRIPT_PATH),
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
        assert pytest_proc.returncode is not None  # noqa: S101 — guaranteed after wait()
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
    merged = JUnitXml()
    for xml_path in sorted(result_dir.glob("*.xml")):
        if xml_path.name != "combined.xml":
            merged += JUnitXml.fromfile(str(xml_path))
    combined_path = result_dir / "combined.xml"
    merged.write(str(combined_path), pretty=True)
    return combined_path


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
