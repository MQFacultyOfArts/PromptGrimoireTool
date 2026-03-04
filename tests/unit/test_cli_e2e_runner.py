"""Tests for lane-aware E2E worker orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest


class _DummyWriter:
    """Minimal asyncio stream writer for server readiness checks."""

    def close(self) -> None:
        """Close the fake writer."""

    async def wait_closed(self) -> None:
        """Wait for the fake writer to close."""


class _FakeAsyncProcess:
    """Minimal subprocess stand-in for asyncio worker tests."""

    def __init__(self, *, pid: int, returncode: int | None) -> None:
        self.pid = pid
        self.returncode = returncode

    async def wait(self) -> int:
        """Return the configured exit code."""
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.mark.asyncio
async def test_run_playwright_file_sets_server_then_pytest_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Playwright workers start the server first and pass both DB and base URL."""
    from promptgrimoire.cli.e2e._workers import run_playwright_file

    calls: list[dict[str, Any]] = []

    async def _fake_subprocess_exec(
        *cmd: str,
        stdout=None,
        stderr=None,
        env=None,
        start_new_session: bool = False,
    ) -> _FakeAsyncProcess:
        calls.append(
            {
                "cmd": cmd,
                "stdout": stdout,
                "stderr": stderr,
                "env": env,
                "start_new_session": start_new_session,
            }
        )
        if len(calls) == 1:
            return _FakeAsyncProcess(pid=101, returncode=None)
        return _FakeAsyncProcess(pid=202, returncode=0)

    async def _fake_open_connection(_host: str, _port: int):
        return object(), _DummyWriter()

    kill_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec)
    monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
    monkeypatch.setattr("promptgrimoire.cli.e2e._workers.os.getpgid", lambda pid: pid)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._workers.os.killpg",
        lambda pgid, sig: kill_calls.append((pgid, sig)),
    )

    worker_dir = tmp_path / "worker"
    result = await run_playwright_file(
        Path("tests/e2e/test_browser_gate.py"),
        4321,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        worker_dir,
        ["-k", "smoke", "--junitxml=ignored.xml"],
    )

    assert len(calls) == 2
    assert "promptgrimoire/cli/e2e/_server_script.py" in str(calls[0]["cmd"][1])
    assert calls[0]["env"]["DATABASE__URL"].endswith("/test_db")
    assert calls[0]["start_new_session"] is True

    assert calls[1]["cmd"][2] == "pytest"
    assert str(Path("tests/e2e/test_browser_gate.py")) in calls[1]["cmd"]
    assert "-m" in calls[1]["cmd"]
    assert "e2e" in calls[1]["cmd"]
    assert "--junitxml=ignored.xml" not in calls[1]["cmd"]
    assert f"--junitxml={worker_dir / 'junit.xml'}" in calls[1]["cmd"]
    assert calls[1]["env"]["DATABASE__URL"].endswith("/test_db")
    assert calls[1]["env"]["E2E_BASE_URL"] == "http://localhost:4321"

    assert result.file == Path("tests/e2e/test_browser_gate.py")
    assert result.exit_code == 0
    assert result.artifact_dir == worker_dir
    assert (worker_dir / "pytest.log").exists()
    assert (worker_dir / "server.log").exists()
    assert (worker_dir / "worker.json").exists()
    assert kill_calls


@pytest.mark.asyncio
async def test_run_nicegui_file_omits_server_and_base_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """NiceGUI workers run pytest directly without an external server."""
    from promptgrimoire.cli.e2e._workers import run_nicegui_file

    calls: list[dict[str, Any]] = []

    async def _fake_subprocess_exec(
        *cmd: str,
        stdout=None,
        stderr=None,
        env=None,
        start_new_session: bool = False,
    ) -> _FakeAsyncProcess:
        calls.append(
            {
                "cmd": cmd,
                "stdout": stdout,
                "stderr": stderr,
                "env": env,
                "start_new_session": start_new_session,
            }
        )
        return _FakeAsyncProcess(pid=202, returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec)

    worker_dir = tmp_path / "nicegui-worker"
    result = await run_nicegui_file(
        Path("tests/integration/test_instructor_template_ui.py"),
        "postgresql+asyncpg://user:pass@localhost/test_db",
        worker_dir,
        ["-k", "tag_management"],
    )

    assert len(calls) == 1
    assert "promptgrimoire/cli/e2e/_server_script.py" not in " ".join(calls[0]["cmd"])
    assert calls[0]["cmd"][2] == "pytest"
    assert "nicegui_ui" in calls[0]["cmd"]
    assert calls[0]["env"]["DATABASE__URL"].endswith("/test_db")
    assert "E2E_BASE_URL" not in calls[0]["env"]
    assert calls[0]["start_new_session"] is False

    assert result.file == Path("tests/integration/test_instructor_template_ui.py")
    assert result.exit_code == 0
    assert result.artifact_dir == worker_dir
    assert (worker_dir / "pytest.log").exists()
    assert (worker_dir / "worker.json").exists()
