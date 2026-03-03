"""E2E server lifecycle and profiling."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from promptgrimoire.cli._shared import console

_SERVER_SCRIPT_PATH = Path(__file__).parent / "_server_script.py"


def _start_e2e_server(port: int) -> subprocess.Popen[bytes]:
    """Start a NiceGUI server subprocess for E2E tests.

    Returns the Popen handle. Blocks until the server accepts connections
    or fails with ``sys.exit(1)`` on timeout/crash.
    """
    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }

    console.print(f"[blue]Starting NiceGUI server on port {port}...[/]")
    server_log = Path("test-e2e-server.log")
    server_log_fh = server_log.open("w")
    process = subprocess.Popen(
        [sys.executable, str(_SERVER_SCRIPT_PATH), str(port)],
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
    proc = subprocess.Popen(
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
