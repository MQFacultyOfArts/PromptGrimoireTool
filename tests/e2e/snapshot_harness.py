"""Start/stop the standalone snapshot service for E2E and perf runs.

Shared between tests/e2e/test_snapshot_delivery.py (functional boundary)
and tests/e2e/test_independent_workspace_load.py (perf candidate arm).
See docs/design-notes/2026-08-16-initial-snapshot-delivery.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

_SERVICE_LOG = Path("test-snapshot-service.log")


def healthz_answers(port: int) -> bool:
    """True when something already answers the service health endpoint."""
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=1):
            return True
    except OSError:
        return False


def start_snapshot_service(
    *,
    port: int,
    allow_origin: str,
    cpu_list: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start the snapshot service and wait for its health endpoint.

    Refuses to start over an occupied port: a stale service from an
    earlier run would answer the health probe with the wrong CORS origin
    and database — a false-positive readiness signal.

    ``cpu_list`` pins the service to the same CPU budget as the app
    server (production-faithful: both would share the host's allocation).
    """
    if healthz_answers(port):
        pytest.fail(
            f"port {port} already serving — stale snapshot service? "
            "Kill it before running this file."
        )

    env = os.environ | {
        "APP__STORAGE_SECRET": "test-secret-for-e2e",
        "SNAPSHOT__ALLOW_ORIGIN": allow_origin,
    }
    command = [sys.executable, "-m", "promptgrimoire.snapshot_service"]
    if cpu_list:
        command = ["taskset", "--cpu-list", cpu_list, *command]

    log_handle = _SERVICE_LOG.open("w")
    process = subprocess.Popen(
        command,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(
                f"snapshot service died (exit {process.returncode}): "
                f"{_SERVICE_LOG.read_text()}"
            )
        if healthz_answers(port):
            return process
        time.sleep(0.2)

    process.terminate()
    pytest.fail("snapshot service did not become healthy within 15s")


def stop_snapshot_service(process: subprocess.Popen[bytes]) -> None:
    """Terminate the service, escalating to SIGKILL after 5 seconds."""
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
