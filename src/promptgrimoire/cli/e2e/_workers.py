"""E2E worker execution, port allocation, and reporting."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import socket
import sys
import time
from pathlib import Path

from junitparser import JUnitXml

from promptgrimoire.cli._shared import console
from promptgrimoire.cli.e2e._artifacts import write_worker_metadata
from promptgrimoire.cli.e2e._lanes import WorkerResult
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


def _clean_test_env() -> dict[str, str]:
    """Return a subprocess environment stripped of pytest/NiceGUI state."""
    env = {
        key: value
        for key, value in os.environ.items()
        if "PYTEST" not in key and "NICEGUI" not in key
    }
    env["GRIMOIRE_TEST_HARNESS"] = "1"
    return env


def _apply_worker_database_env(clean_env: dict[str, str], db_url: str) -> None:
    """Configure worker DB env so branch suffixing doesn't rewrite clone names."""
    clean_env["DATABASE__URL"] = db_url
    clean_env["DEV__TEST_DATABASE_URL"] = db_url
    # "0" disables per-branch URL suffixing in subprocess settings resolution.
    # Without this, cloned names like "..._w0" become "..._w0_<branch>" and fail.
    clean_env["DEV__BRANCH_DB_SUFFIX"] = "0"


async def _wait_for_server_ready(
    server: asyncio.subprocess.Process,
    *,
    test_file: Path,
    port: int,
    server_log_path: Path,
) -> None:
    """Wait for a worker server to accept connections or raise a startup error."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if server.returncode is not None:
            msg = (
                f"Server for {test_file.name} died "
                f"(exit {server.returncode}); see {server_log_path}"
            )
            raise RuntimeError(msg)
        try:
            _reader, writer = await asyncio.open_connection("localhost", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)

    msg = (
        f"Server for {test_file.name} did not start within 15 s; see {server_log_path}"
    )
    raise RuntimeError(msg)


def _collect_playwright_artifacts(worker_dir: Path) -> None:
    """Copy known Playwright artifact directories into *worker_dir* if present.

    Best-effort: failures are logged but never propagated.  The shared
    ``tests/e2e/screenshots/`` directory is mutated by parallel workers
    (e.g. ``test_para_screenshot.py``), so TOCTOU races on ``copytree``
    are expected.
    """
    playwright_dir = worker_dir / "playwright"
    known_paths = [
        Path("test-results"),
        Path("tests/e2e/screenshots"),
    ]

    for source in known_paths:
        if not source.exists():
            continue
        target = playwright_dir / source.name
        try:
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        except shutil.Error:
            # TOCTOU race: file listed then removed by another worker.
            pass
        except OSError:
            # Permissions, disk full, etc. — don't mask test results.
            pass


async def _run_pytest_subprocess(
    cmd: list[str],
    *,
    env: dict[str, str],
    log_path: Path,
) -> int:
    """Run one pytest subprocess, streaming output into *log_path*."""
    with log_path.open("w") as log_file:
        pytest_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        await pytest_proc.wait()
        assert pytest_proc.returncode is not None  # noqa: S101 - guaranteed after wait()
        return pytest_proc.returncode


def _build_worker_result(
    *,
    test_file: Path,
    exit_code: int,
    start_time: float,
    worker_dir: Path,
    lane_name: str,
) -> WorkerResult:
    """Create and persist a `WorkerResult` for one worker."""
    result = WorkerResult(
        file=test_file,
        exit_code=exit_code,
        duration_s=time.monotonic() - start_time,
        artifact_dir=worker_dir,
    )
    write_worker_metadata(worker_dir, result, lane_name=lane_name)
    return result


async def run_playwright_file(
    test_file: Path,
    port: int,
    db_url: str,
    worker_dir: Path,
    user_args: list[str],
    *,
    browser: str | None = None,
) -> WorkerResult:
    """Run one Playwright-backed E2E file with a dedicated server and DB."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    clean_env = _clean_test_env()
    _apply_worker_database_env(clean_env, db_url)

    server_log_path = worker_dir / "server.log"
    pytest_log_path = worker_dir / "pytest.log"
    junit_path = worker_dir / "junit.xml"
    server: asyncio.subprocess.Process | None = None
    start_time = time.monotonic()

    with server_log_path.open("w") as server_log:
        try:
            server = await asyncio.create_subprocess_exec(
                sys.executable,
                str(_SERVER_SCRIPT_PATH),
                str(port),
                stdout=server_log,
                stderr=asyncio.subprocess.STDOUT,
                env=clean_env,
                start_new_session=True,
            )
            await _wait_for_server_ready(
                server,
                test_file=test_file,
                port=port,
                server_log_path=server_log_path,
            )

            browser_args = ["--browser", browser] if browser is not None else []
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(test_file),
                "-m",
                "e2e",
                *browser_args,
                "--tb=short",
                f"--junitxml={junit_path}",
                *_filter_junitxml_args(user_args),
            ]
            pytest_env = {**clean_env, "E2E_BASE_URL": f"http://localhost:{port}"}
            exit_code = await _run_pytest_subprocess(
                cmd,
                env=pytest_env,
                log_path=pytest_log_path,
            )
            _collect_playwright_artifacts(worker_dir)
            return _build_worker_result(
                test_file=test_file,
                exit_code=exit_code,
                start_time=start_time,
                worker_dir=worker_dir,
                lane_name="playwright",
            )
        finally:
            if server is not None and server.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(os.getpgid(server.pid), signal.SIGTERM)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(server.wait(), timeout=2)
                if server.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(os.getpgid(server.pid), signal.SIGKILL)


async def run_nicegui_file(
    test_file: Path,
    db_url: str,
    worker_dir: Path,
    user_args: list[str],
) -> WorkerResult:
    """Run one NiceGUI UI file without starting an external server."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    clean_env = _clean_test_env()
    _apply_worker_database_env(clean_env, db_url)

    junit_path = worker_dir / "junit.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-m",
        "nicegui_ui",
        "--tb=short",
        f"--junitxml={junit_path}",
        *_filter_junitxml_args(user_args),
    ]
    start_time = time.monotonic()
    exit_code = await _run_pytest_subprocess(
        cmd,
        env=clean_env,
        log_path=worker_dir / "pytest.log",
    )
    return _build_worker_result(
        test_file=test_file,
        exit_code=exit_code,
        start_time=start_time,
        worker_dir=worker_dir,
        lane_name="nicegui",
    )


def _worker_status_label(exit_code: int) -> str:
    """Return a coloured PASS/FAIL/CANCEL label for a worker exit code."""
    if exit_code == -1:
        return "[yellow]CANCEL[/]"
    if exit_code in (0, 5):
        return "[green]PASS[/]"
    return "[red]FAIL[/]"


def _print_parallel_summary(
    results: list[WorkerResult],
    wall_clock: float,
) -> None:
    """Print a compact summary of parallel E2E results (no borders)."""
    passed = sum(1 for result in results if result.exit_code in (0, 5))
    failed = sum(1 for result in results if result.exit_code not in (0, 5, -1))
    cancelled = sum(1 for result in results if result.exit_code == -1)

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
    for xml_path in sorted(result_dir.rglob("junit.xml")):
        if xml_path.name != "combined.xml":
            merged += JUnitXml.fromfile(str(xml_path))
    combined_path = result_dir / "combined.xml"
    merged.write(str(combined_path), pretty=True)
    return combined_path


def _resolve_failed_task_file(
    tasks: list[asyncio.Task[WorkerResult]],
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
