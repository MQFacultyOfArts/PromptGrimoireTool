"""Tests for lane-aware E2E worker orchestration."""

from __future__ import annotations

import asyncio
import os
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
    assert calls[0]["env"]["DEV__TEST_DATABASE_URL"].endswith("/test_db")
    assert calls[0]["env"]["DEV__BRANCH_DB_SUFFIX"] == "0"
    assert calls[0]["start_new_session"] is True

    assert calls[1]["cmd"][2] == "pytest"
    assert str(Path("tests/e2e/test_browser_gate.py")) in calls[1]["cmd"]
    assert "-m" in calls[1]["cmd"]
    assert "e2e" in calls[1]["cmd"]
    assert "--junitxml=ignored.xml" not in calls[1]["cmd"]
    assert f"--junitxml={worker_dir / 'junit.xml'}" in calls[1]["cmd"]
    assert calls[1]["env"]["DATABASE__URL"].endswith("/test_db")
    assert calls[1]["env"]["DEV__TEST_DATABASE_URL"].endswith("/test_db")
    assert calls[1]["env"]["DEV__BRANCH_DB_SUFFIX"] == "0"
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
    assert calls[0]["env"]["DEV__TEST_DATABASE_URL"].endswith("/test_db")
    assert calls[0]["env"]["DEV__BRANCH_DB_SUFFIX"] == "0"
    assert "E2E_BASE_URL" not in calls[0]["env"]
    assert calls[0]["start_new_session"] is False

    assert result.file == Path("tests/integration/test_instructor_template_ui.py")
    assert result.exit_code == 0
    assert result.artifact_dir == worker_dir
    assert (worker_dir / "pytest.log").exists()
    assert (worker_dir / "worker.json").exists()


@pytest.mark.asyncio
async def test_run_nicegui_e2e_routes_command_to_nicegui_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The NiceGUI command wrapper dispatches the dedicated lane and worker."""
    from promptgrimoire.cli.e2e import _run_nicegui_e2e
    from promptgrimoire.cli.e2e._lanes import NICEGUI_LANE

    captured: dict[str, Any] = {}

    async def _fake_run_lane_files(
        lane: Any,
        worker: Any,
        *,
        user_args: list[str],
        worker_count: int | None = None,
        fail_fast: bool = False,
    ) -> int:
        captured["lane"] = lane
        captured["worker"] = worker
        captured["user_args"] = user_args
        captured["worker_count"] = worker_count
        captured["fail_fast"] = fail_fast
        return 0

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._parallel.run_lane_files",
        _fake_run_lane_files,
    )

    exit_code = await _run_nicegui_e2e(["-k", "tag_management"])

    assert exit_code == 0
    assert captured["lane"] == NICEGUI_LANE
    assert captured["lane"].name == "nicegui"
    assert captured["worker"].__name__ == "run_nicegui_file"
    assert captured["user_args"] == ["-k", "tag_management"]
    assert captured["worker_count"] == 1
    assert captured["fail_fast"] is False


@pytest.mark.asyncio
async def test_retry_failed_files_in_isolation_classifies_flaky_and_genuine(
    tmp_path: Path,
) -> None:
    """File-based retries classify flaky vs genuine and write retry subdirs."""
    from promptgrimoire.cli.e2e._lanes import NICEGUI_LANE, WorkerResult
    from promptgrimoire.cli.e2e._retry import retry_failed_files_in_isolation

    result_root = tmp_path / "run"
    failed_flaky = Path("tests/integration/test_instructor_template_ui.py")
    failed_genuine = Path("tests/integration/test_crud_management_ui.py")
    failed_files = [failed_flaky, failed_genuine]
    retry_dbs = [
        ("postgresql+asyncpg://user:pass@localhost/test_db_retry0", "test_db_retry0"),
        ("postgresql+asyncpg://user:pass@localhost/test_db_retry1", "test_db_retry1"),
    ]

    async def _fake_nicegui_worker(
        test_file: Path,
        _db_url: str,
        worker_dir: Path,
        _user_args: list[str],
    ) -> WorkerResult:
        exit_code = 0 if test_file == failed_flaky else 1
        return WorkerResult(
            file=test_file,
            exit_code=exit_code,
            duration_s=0.25,
            artifact_dir=worker_dir,
        )

    async def _fake_run_worker_for_lane(
        _lane: Any,
        worker: Any,
        *,
        test_file: Path,
        db_url: str,
        worker_dir: Path,
        user_args: list[str],
        port: int | None = None,
    ) -> WorkerResult:
        assert port is None
        return await worker(test_file, db_url, worker_dir, user_args)

    genuine_failures, flaky_files = await retry_failed_files_in_isolation(
        NICEGUI_LANE,
        _fake_nicegui_worker,
        failed_files=failed_files,
        result_root=result_root,
        user_args=[],
        retry_dbs=retry_dbs,
        retry_ports=[0, 0],
        run_worker_for_lane=_fake_run_worker_for_lane,
    )

    assert flaky_files == [failed_flaky]
    assert genuine_failures == [failed_genuine]
    assert (result_root / failed_flaky.stem / "retry").is_dir()
    assert (result_root / failed_genuine.stem / "retry").is_dir()


def test_run_serial_playwright_e2e_selects_only_playwright_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serial Playwright lane uses `tests/e2e` path boundary, never NiceGUI marker."""
    from promptgrimoire.cli.e2e import _run_serial_playwright_e2e

    captured: dict[str, Any] = {}

    def _fake_get_settings() -> object:
        return object()

    def _fake_pre_test_db_cleanup() -> None:
        return None

    def _fake_allocate_ports(_n: int) -> list[int]:
        return [4312]

    def _fake_start_server(_port: int) -> object:
        return object()

    def _fake_stop_server(_server: object) -> None:
        return None

    monkeypatch.setattr("promptgrimoire.config.get_settings", _fake_get_settings)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._pre_test_db_cleanup", _fake_pre_test_db_cleanup
    )
    monkeypatch.setattr("promptgrimoire.cli.e2e._allocate_ports", _fake_allocate_ports)
    monkeypatch.setattr("promptgrimoire.cli.e2e._start_e2e_server", _fake_start_server)
    monkeypatch.setattr("promptgrimoire.cli.e2e._stop_e2e_server", _fake_stop_server)

    def _fake_run_pytest(
        *,
        title: str,
        log_path: Path,
        default_args: list[str],
        extra_args: list[str] | None = None,
    ) -> int:
        captured["title"] = title
        captured["log_path"] = log_path
        captured["default_args"] = default_args
        captured["extra_args"] = extra_args
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    try:
        exit_code = _run_serial_playwright_e2e(
            ["-k", "test_annotation_nav_home_navigates_to_navigator"],
            use_pyspy=False,
            reruns=True,
        )
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert exit_code == 0
    assert captured["default_args"][0] == "tests/e2e"
    assert captured["default_args"][1:3] == ["-m", "e2e"]
    assert "nicegui_ui" not in captured["default_args"]
    assert "Playwright" in captured["title"]


def test_run_playwright_changed_lane_selects_only_playwright_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changed lane stays Playwright-only by explicit path selection."""
    from promptgrimoire.cli.e2e import run_playwright_changed_lane

    captured: dict[str, Any] = {}

    def _fake_get_settings() -> object:
        return object()

    def _fake_pre_test_db_cleanup() -> None:
        return None

    def _fake_allocate_ports(_n: int) -> list[int]:
        return [4312]

    def _fake_start_server(_port: int) -> object:
        return object()

    def _fake_stop_server(_server: object) -> None:
        return None

    monkeypatch.setattr("promptgrimoire.config.get_settings", _fake_get_settings)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._pre_test_db_cleanup", _fake_pre_test_db_cleanup
    )
    monkeypatch.setattr("promptgrimoire.cli.e2e._allocate_ports", _fake_allocate_ports)
    monkeypatch.setattr("promptgrimoire.cli.e2e._start_e2e_server", _fake_start_server)
    monkeypatch.setattr("promptgrimoire.cli.e2e._stop_e2e_server", _fake_stop_server)

    def _fake_run_pytest(
        *,
        title: str,
        log_path: Path,
        default_args: list[str],
        extra_args: list[str] | None = None,
    ) -> int:
        captured["title"] = title
        captured["log_path"] = log_path
        captured["default_args"] = default_args
        captured["extra_args"] = extra_args
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    try:
        exit_code = run_playwright_changed_lane(["-k", "test_annotation_nav_home"])
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert exit_code == 0
    assert captured["default_args"][0] == "tests/e2e"
    assert captured["default_args"][1:3] == ["-m", "e2e"]
    assert "nicegui_ui" not in captured["default_args"]
    assert "Playwright" in captured["title"]


def test_run_all_lanes_runs_playwright_then_nicegui_even_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Umbrella command is non-fail-fast and always runs both lanes."""
    from promptgrimoire.cli.e2e import run_all_lanes

    calls: list[tuple[str, list[str]]] = []

    def _fake_playwright(
        user_args: list[str],
        *,
        parallel: bool,
        fail_fast: bool,
        py_spy: bool,
    ) -> int:
        assert parallel is False
        assert fail_fast is False
        assert py_spy is False
        calls.append(("playwright", user_args))
        return 1

    def _fake_nicegui(user_args: list[str]) -> int:
        calls.append(("nicegui", user_args))
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e.run_playwright_lane", _fake_playwright)
    monkeypatch.setattr("promptgrimoire.cli.e2e.run_nicegui_lane", _fake_nicegui)

    exit_code = run_all_lanes(["-k", "combined_filter"])

    assert calls == [
        ("playwright", ["-k", "combined_filter"]),
        ("nicegui", ["-k", "combined_filter"]),
    ]
    assert exit_code == 1


def test_run_all_lanes_returns_zero_only_when_both_lanes_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Combined exit code is 0 only if both lane helpers return success."""
    from promptgrimoire.cli.e2e import run_all_lanes

    def _fake_playwright_success(
        _args: list[str],
        *,
        parallel: bool,
        fail_fast: bool,
        py_spy: bool,
    ) -> int:
        assert parallel is False
        assert fail_fast is False
        assert py_spy is False
        return 0

    def _fake_nicegui_success(_args: list[str]) -> int:
        return 0

    def _fake_nicegui_failure(_args: list[str]) -> int:
        return 1

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.run_playwright_lane",
        _fake_playwright_success,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.run_nicegui_lane", _fake_nicegui_success
    )
    assert run_all_lanes([]) == 0

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.run_nicegui_lane", _fake_nicegui_failure
    )
    assert run_all_lanes([]) == 1
