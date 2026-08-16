"""Tests for lane-aware E2E worker orchestration."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import click
import pytest
import typer


def test_perf_host_load_guard_waits_until_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy perf run queues in place until one-minute load is safe."""
    from promptgrimoire.cli.e2e import _wait_for_idle_perf_host

    loads = iter((18.0, 3.9))
    sleeps: list[int] = []
    monkeypatch.setattr(os, "getloadavg", lambda: (next(loads), 0.0, 0.0))
    monkeypatch.setattr("promptgrimoire.cli.e2e.time.sleep", sleeps.append)

    _wait_for_idle_perf_host()

    assert sleeps == [15]


def test_perf_queue_pool_removes_test_nullpool_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production-pool perf runs cross from forced NullPool to configured pooling."""
    from promptgrimoire.cli.e2e import _configure_perf_server

    monkeypatch.setenv("_PROMPTGRIMOIRE_USE_NULL_POOL", "1")
    monkeypatch.setenv(
        "E2E_PERF_DATABASE_URL", "postgresql+asyncpg://localhost:6432/test"
    )
    _configure_perf_server(queue_pool=True)
    assert "_PROMPTGRIMOIRE_USE_NULL_POOL" not in os.environ
    assert os.environ["DATABASE__URL"] == os.environ["E2E_PERF_DATABASE_URL"]
    assert os.environ["E2E_RECONNECT_TIMEOUT"] == "15"
    assert os.environ["E2E_INSTRUMENT_OUTBOX"] == "1"


def test_e2e_server_can_use_dedicated_cpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load-generator affinity does not leak into a production-shaped server."""
    from promptgrimoire.cli.e2e._server import _server_command

    monkeypatch.setenv("E2E_SERVER_CPU_LIST", "0-7")
    assert _server_command(4312)[:3] == ["taskset", "--cpu-list", "0-7"]


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


@pytest.fixture
def patch_serial_playwright_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch shared infra used by serial Playwright command helpers."""

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
    assert "nicegui_ui and not perf" in calls[0]["cmd"]
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
        browser: str | None = None,  # noqa: ARG001
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


@pytest.mark.asyncio
async def test_retry_forwards_browser_to_run_worker_for_lane(
    tmp_path: Path,
) -> None:
    """browser= must reach run_worker_for_lane during retry."""
    from promptgrimoire.cli.e2e._lanes import (
        PLAYWRIGHT_LANE,
        WorkerResult,
    )
    from promptgrimoire.cli.e2e._retry import (
        retry_failed_files_in_isolation,
    )

    result_root = tmp_path / "run"
    failed_file = Path("tests/e2e/test_card_layout.py")
    retry_dbs = [
        (
            "postgresql+asyncpg://u:p@localhost/retry0",
            "retry0",
        ),
    ]

    captured_browser: list[str | None] = []

    async def _fake_worker(
        *_a: object,
        **_kw: object,
    ) -> WorkerResult:
        return WorkerResult(
            file=failed_file,
            exit_code=0,
            duration_s=0.1,
            artifact_dir=tmp_path / "art",
        )

    async def _spy_run_worker(
        _lane: object,
        _worker: object,
        *,
        test_file: Path,  # noqa: ARG001
        db_url: str,  # noqa: ARG001
        worker_dir: Path,  # noqa: ARG001
        user_args: list[str],  # noqa: ARG001
        port: int | None = None,  # noqa: ARG001
        browser: str | None = None,
    ) -> WorkerResult:
        captured_browser.append(browser)
        return WorkerResult(
            file=failed_file,
            exit_code=0,
            duration_s=0.1,
            artifact_dir=tmp_path / "art",
        )

    await retry_failed_files_in_isolation(
        PLAYWRIGHT_LANE,
        _fake_worker,
        failed_files=[failed_file],
        result_root=result_root,
        user_args=[],
        retry_dbs=retry_dbs,
        retry_ports=[0],
        run_worker_for_lane=_spy_run_worker,
        browser="firefox",
    )

    assert captured_browser == ["firefox"], (
        f"browser='firefox' must reach run_worker_for_lane, got {captured_browser}"
    )


def test_run_serial_playwright_e2e_selects_only_playwright_path(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Serial Playwright lane uses `tests/e2e` path boundary, never NiceGUI marker."""
    from promptgrimoire.cli.e2e import _run_serial_playwright_e2e

    captured: dict[str, Any] = {}

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
        )
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert exit_code == 0
    assert captured["default_args"][0] == "tests/e2e"
    assert captured["default_args"][1:3] == ["-m", "e2e and not perf and not noci"]
    assert "nicegui_ui" not in captured["default_args"]
    assert "--reruns" not in captured["default_args"]
    assert "Playwright" in captured["title"]


def test_shared_playwright_marks_concurrent_workers(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Concurrent workers must not run the destructive global cleanup fixture."""
    from promptgrimoire.cli.e2e import _run_shared_playwright_e2e

    observed: list[str | None] = []

    def _fake_run_pytest(**_kwargs: Any) -> int:
        observed.append(os.environ["E2E_SHARED_SERVER"])
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    _run_shared_playwright_e2e([], use_pyspy=False, worker_count=4)

    assert observed == ["1"]
    assert "E2E_SHARED_SERVER" not in os.environ


def test_parallel_playwright_reserves_cpu_for_shared_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four available CPUs yield two clients, leaving capacity for shared I/O."""
    from promptgrimoire.cli.e2e import run_playwright_lane

    captured: dict[str, int] = {}

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_getaffinity",
        lambda _pid: set(range(4)),
    )
    monkeypatch.setattr(
        "promptgrimoire.config.get_settings",
        object,
    )

    def _capture_worker_count(
        _args: list[str],
        *,
        use_pyspy: bool,
        worker_count: int,
        fail_fast: bool,
        browser: str | None,
    ) -> int:
        assert use_pyspy is False
        assert fail_fast is False
        assert browser == "chromium"
        captured["worker_count"] = worker_count
        return 0

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_shared_playwright_e2e",
        _capture_worker_count,
    )

    exit_code = run_playwright_lane(
        [],
        parallel=True,
        fail_fast=False,
        py_spy=False,
        browser="chromium",
    )

    assert exit_code == 0
    assert captured["worker_count"] == 2


@pytest.mark.parametrize(
    ("available_cpus", "expected_workers"),
    [(1, 1), (4, 2), (32, 4)],
)
def test_playwright_worker_budget_has_floor_and_cap(
    monkeypatch: pytest.MonkeyPatch,
    available_cpus: int,
    expected_workers: int,
) -> None:
    """The shared-service budget scales from one client to a cap of four."""
    from promptgrimoire.cli.e2e import _playwright_worker_count

    monkeypatch.delenv("GRIMOIRE_TEST_WORKERS", raising=False)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_getaffinity",
        lambda _pid: set(range(available_cpus)),
    )

    assert _playwright_worker_count() == expected_workers


def test_playwright_worker_budget_uses_cpu_count_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Platforms without affinity support still reserve half their CPUs."""
    from promptgrimoire.cli.e2e import _playwright_worker_count

    monkeypatch.delenv("GRIMOIRE_TEST_WORKERS", raising=False)
    monkeypatch.delattr("promptgrimoire.cli.e2e.os.sched_getaffinity")
    monkeypatch.setattr("promptgrimoire.cli.e2e.os.cpu_count", lambda: 6)

    assert _playwright_worker_count() == 3


def test_playwright_worker_budget_honours_operator_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit worker count remains authoritative."""
    from promptgrimoire.cli.e2e import _playwright_worker_count

    monkeypatch.setenv("GRIMOIRE_TEST_WORKERS", "3")
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_getaffinity",
        lambda _pid: {0},
    )

    assert _playwright_worker_count() == 3


def test_run_playwright_changed_lane_selects_only_playwright_path(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Changed lane stays Playwright-only by explicit path selection."""
    from promptgrimoire.cli.e2e import run_playwright_changed_lane

    captured: dict[str, Any] = {}

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
    assert captured["default_args"][1:3] == ["-m", "e2e and not perf and not noci"]
    assert "nicegui_ui" not in captured["default_args"]
    assert "Playwright" in captured["title"]


def test_run_playwright_noretry_lane_selects_only_playwright_path(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Noretry lane stays Playwright-only by explicit path selection."""
    from promptgrimoire.cli.e2e import run_playwright_noretry_lane

    captured: dict[str, Any] = {}

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
        exit_code = run_playwright_noretry_lane(["-k", "test_annotation_nav_home"])
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert exit_code == 0
    assert captured["default_args"][0] == "tests/e2e"
    assert captured["default_args"][1:3] == ["-m", "e2e and not perf and not noci"]
    assert "nicegui_ui" not in captured["default_args"]
    assert "Playwright" in captured["title"]


def test_artifact_dir_if_new_ignores_stale_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary helper must not report a stale artifact dir from an older run."""
    from promptgrimoire.cli.e2e import _artifact_dir_if_new

    old_dir = Path("output/test_output/e2e/playwright/old-run")
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._latest_artifact_dir",
        lambda lane_name: old_dir if lane_name == "playwright" else None,
    )

    assert _artifact_dir_if_new("playwright", old_dir) is None


def test_artifact_dir_if_new_returns_new_run_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary helper should report the artifact dir created by the current run."""
    from promptgrimoire.cli.e2e import _artifact_dir_if_new

    old_dir = Path("output/test_output/e2e/playwright/old-run")
    new_dir = Path("output/test_output/e2e/playwright/new-run")
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._latest_artifact_dir",
        lambda lane_name: new_dir if lane_name == "playwright" else None,
    )

    assert _artifact_dir_if_new("playwright", old_dir) == new_dir


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
        browser: str | None = None,
    ) -> int:
        assert parallel is True
        assert fail_fast is False
        assert py_spy is False
        assert browser is None
        calls.append(("playwright", user_args))
        return 1

    def _fake_nicegui(user_args: list[str]) -> int:
        calls.append(("nicegui", user_args))
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e.run_playwright_lane", _fake_playwright)
    monkeypatch.setattr("promptgrimoire.cli.e2e.run_nicegui_lane", _fake_nicegui)
    monkeypatch.setattr("promptgrimoire.cli.testing._run_pytest", lambda **_kw: 0)
    monkeypatch.setattr("promptgrimoire.cli.testing._run_bats", lambda: 0)
    monkeypatch.setattr("promptgrimoire.cli.testing._run_js", lambda: 0)

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
        browser: str | None = None,
    ) -> int:
        assert parallel is True
        assert fail_fast is False
        assert py_spy is False
        assert browser is None
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
    monkeypatch.setattr("promptgrimoire.cli.testing._run_pytest", lambda **_kw: 0)
    monkeypatch.setattr("promptgrimoire.cli.testing._run_bats", lambda: 0)
    monkeypatch.setattr("promptgrimoire.cli.testing._run_js", lambda: 0)
    assert run_all_lanes([]) == 0

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.run_nicegui_lane", _fake_nicegui_failure
    )
    assert run_all_lanes([]) == 1


def test_run_slow_lanes_runs_all_lanes_then_latexmk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow lane runs all standard lanes first, then latexmk-specific lanes."""
    from promptgrimoire.cli.e2e import run_slow_lanes
    from promptgrimoire.cli.e2e._lanes import LaneResult

    captured: dict[str, object] = {}

    def _fake_all_lane_steps(user_args: list[str]) -> list[LaneResult]:
        captured["all_lanes_args"] = user_args
        return [LaneResult("unit", 0), LaneResult("playwright", 0)]

    def _fake_playwright(
        extra_args: list[str],
        *,
        use_pyspy: bool,
        marker_expr: str,
        test_timeout: int | None = None,
        log_file: Path | None = None,
    ) -> int:
        captured["playwright_args"] = extra_args
        captured["playwright_use_pyspy"] = use_pyspy
        captured["playwright_test_timeout"] = test_timeout
        captured["playwright_marker_expr"] = marker_expr
        captured["playwright_log_file"] = log_file
        captured["e2e_skip_latexmk"] = os.environ["E2E_SKIP_LATEXMK"]
        return 0

    def _fake_run_pytest(
        *,
        title: str,
        log_path: Path,
        default_args: list[str],
        extra_args: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> int:
        captured["latex_title"] = title
        captured["latex_log_path"] = log_path
        captured["latex_default_args"] = default_args
        captured["latex_extra_args"] = extra_args
        captured["latex_extra_env"] = extra_env
        return 0

    monkeypatch.delenv("E2E_SKIP_LATEXMK", raising=False)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_all_lane_steps", _fake_all_lane_steps
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_serial_playwright_e2e", _fake_playwright
    )
    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    exit_code = run_slow_lanes(["-k", "combined_filter"])

    assert exit_code == 0
    assert captured["all_lanes_args"] == ["-k", "combined_filter"]
    assert captured["playwright_args"] == ["-k", "combined_filter"]
    assert captured["playwright_use_pyspy"] is False
    assert captured["playwright_marker_expr"] == "e2e and not perf"
    assert captured["playwright_test_timeout"] == 120
    assert captured["playwright_log_file"] == Path("test-playwright-latexmk.log")
    assert captured["e2e_skip_latexmk"] == "0"
    assert captured["latex_default_args"] == ["-m", "latexmk_full", "-v", "--tb=short"]
    assert captured["latex_extra_args"] == ["-k", "combined_filter"]
    assert captured["latex_extra_env"] is None
    assert "E2E_SKIP_LATEXMK" not in os.environ


def test_passing_isolation_retry_keeps_initial_failure_red(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A successful diagnostic retry never changes the failed exit status."""
    import subprocess

    from promptgrimoire.cli.e2e import _retry

    node_id = "tests/e2e/test_flaky.py::test_flaky"
    monkeypatch.setattr(_retry, "_get_last_failed", lambda: [node_id])
    monkeypatch.setattr(
        _retry,
        "_run_retry_node",
        lambda _: subprocess.CompletedProcess(["pytest", node_id], 0, "passed"),
    )

    assert _retry._retry_e2e_tests_in_isolation(tmp_path / "retry.log") == 1


def test_slow_resource_policy_reserves_one_cpu_and_lowers_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Linux slow-run policy leaves one CPU free and is inherited by children."""
    from promptgrimoire.cli.e2e import _configure_slow_run_resources

    calls: dict[str, object] = {}

    monkeypatch.setattr("promptgrimoire.cli.e2e.sys.platform", "linux")
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_getaffinity", lambda _pid: {0, 1, 2, 3}
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_setaffinity",
        lambda pid, cpus: calls.update(affinity=(pid, cpus)),
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.setpriority",
        lambda which, who, priority: calls.update(priority=(which, who, priority)),
    )
    monkeypatch.setattr("promptgrimoire.cli.e2e.os.getpid", lambda: 4321)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.shutil.which",
        lambda command: "/usr/bin/ionice" if command == "ionice" else None,
    )

    def _fake_run(command: list[str], *, check: bool) -> None:
        calls["ionice"] = (command, check)

    monkeypatch.setattr("promptgrimoire.cli.e2e.subprocess.run", _fake_run)

    _configure_slow_run_resources()

    assert calls["affinity"] == (0, {1, 2, 3})
    assert calls["priority"] == (os.PRIO_PROCESS, 0, 19)
    assert calls["ionice"] == (
        ["/usr/bin/ionice", "-c", "3", "-p", "4321"],
        True,
    )


def test_slow_resource_policy_keeps_the_only_available_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-CPU environment remains runnable instead of reserving its sole CPU."""
    from promptgrimoire.cli.e2e import _configure_slow_run_resources

    affinity_calls: list[tuple[int, set[int]]] = []
    monkeypatch.setattr("promptgrimoire.cli.e2e.sys.platform", "linux")
    monkeypatch.setattr("promptgrimoire.cli.e2e.os.sched_getaffinity", lambda _pid: {7})
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.os.sched_setaffinity",
        lambda pid, cpus: affinity_calls.append((pid, cpus)),
    )
    monkeypatch.setattr("promptgrimoire.cli.e2e.os.setpriority", lambda *_: None)
    monkeypatch.setattr("promptgrimoire.cli.e2e.shutil.which", lambda _command: None)

    _configure_slow_run_resources()

    assert affinity_calls == []


def test_slow_command_applies_resource_policy_before_running_lanes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public slow command applies the policy before dispatching the lanes."""
    from promptgrimoire.cli.e2e import slow

    events: list[str] = []
    context = typer.Context(click.Command("slow"))

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._configure_slow_run_resources",
        lambda: events.append("resources"),
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e.run_slow_lanes",
        lambda _args: events.append("lanes") or 0,
    )

    with pytest.raises(SystemExit) as exc_info:
        slow(context, None)

    assert exc_info.value.code == 0
    assert events == ["resources", "lanes"]


def test_run_slow_lanes_skips_latexmk_suite_for_explicit_test_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit test paths skip phase 2 and only run standard lanes."""
    from promptgrimoire.cli.e2e import run_slow_lanes
    from promptgrimoire.cli.e2e._lanes import LaneResult

    def _fake_all_lane_steps(_user_args: list[str]) -> list[LaneResult]:
        return [LaneResult("unit", 0)]

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_all_lane_steps", _fake_all_lane_steps
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_serial_playwright_e2e",
        lambda *_, **__: pytest.fail("phase 2 should not run for explicit paths"),
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_pytest",
        lambda **_: pytest.fail("latexmk suite should not run for explicit paths"),
    )

    exit_code = run_slow_lanes(["tests/e2e/test_browser_gate.py"])

    assert exit_code == 0


def test_run_slow_lanes_treats_filtered_no_tests_as_non_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A filtered latexmk suite with no matches should not fail the slow command."""
    from promptgrimoire.cli.e2e import run_slow_lanes
    from promptgrimoire.cli.e2e._lanes import LaneResult

    def _fake_all_lane_steps(_user_args: list[str]) -> list[LaneResult]:
        return [LaneResult("unit", 0)]

    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_all_lane_steps", _fake_all_lane_steps
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_serial_playwright_e2e",
        lambda *_, **__: 5,
    )
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._run_pytest",
        lambda **_: 5,
    )

    assert run_slow_lanes(["-k", "playwright_only_name"]) == 0


@pytest.mark.asyncio
async def test_run_playwright_file_includes_browser_flag_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Passing browser='firefox' inserts --browser firefox into the pytest cmd."""
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

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec)
    monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
    monkeypatch.setattr("promptgrimoire.cli.e2e._workers.os.getpgid", lambda pid: pid)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._workers.os.killpg", lambda _pgid, _sig: None
    )

    worker_dir = tmp_path / "worker"
    result = await run_playwright_file(
        Path("tests/e2e/test_browser_gate.py"),
        4321,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        worker_dir,
        [],
        browser="firefox",
    )

    assert result.exit_code == 0
    pytest_cmd = calls[1]["cmd"]
    assert "--browser" in pytest_cmd
    browser_idx = pytest_cmd.index("--browser")
    assert pytest_cmd[browser_idx + 1] == "firefox"


@pytest.mark.asyncio
async def test_run_playwright_file_omits_browser_flag_when_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default browser=None produces no --browser flag (Chromium default)."""
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

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec)
    monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
    monkeypatch.setattr("promptgrimoire.cli.e2e._workers.os.getpgid", lambda pid: pid)
    monkeypatch.setattr(
        "promptgrimoire.cli.e2e._workers.os.killpg", lambda _pgid, _sig: None
    )

    worker_dir = tmp_path / "worker"
    await run_playwright_file(
        Path("tests/e2e/test_browser_gate.py"),
        4321,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        worker_dir,
        [],
    )

    pytest_cmd = calls[1]["cmd"]
    assert "--browser" not in pytest_cmd


def test_serial_playwright_includes_browser_flag(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Serial mode inserts --browser into default_args when specified."""
    from promptgrimoire.cli.e2e import _run_serial_playwright_e2e

    captured: dict[str, Any] = {}

    def _fake_run_pytest(
        *,
        _title: str = "",
        _log_path: Path = Path(),
        default_args: list[str],
        _extra_args: list[str] | None = None,
        **_kwargs: Any,
    ) -> int:
        captured["default_args"] = default_args
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    try:
        _run_serial_playwright_e2e([], use_pyspy=False, browser="firefox")
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert "--browser" in captured["default_args"]
    idx = captured["default_args"].index("--browser")
    assert captured["default_args"][idx + 1] == "firefox"


def test_serial_playwright_omits_browser_flag_by_default(
    monkeypatch: pytest.MonkeyPatch,
    patch_serial_playwright_infra: None,  # noqa: ARG001 - fixture side effects
) -> None:
    """Serial mode without browser param produces no --browser flag."""
    from promptgrimoire.cli.e2e import _run_serial_playwright_e2e

    captured: dict[str, Any] = {}

    def _fake_run_pytest(
        *,
        _title: str = "",
        _log_path: Path = Path(),
        default_args: list[str],
        _extra_args: list[str] | None = None,
        **_kwargs: Any,
    ) -> int:
        captured["default_args"] = default_args
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e._run_pytest", _fake_run_pytest)

    try:
        _run_serial_playwright_e2e([], use_pyspy=False)
    finally:
        os.environ.pop("E2E_BASE_URL", None)

    assert "--browser" not in captured["default_args"]


def test_run_all_browsers_runs_chromium_then_firefox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """all-browsers runs Chromium then Firefox in order."""
    from promptgrimoire.cli.e2e import run_all_browsers

    calls: list[str | None] = []

    def _fake_playwright(
        _args: list[str],
        *,
        _parallel: bool = True,
        _fail_fast: bool = False,
        _py_spy: bool = False,
        browser: str | None = None,
        **_kwargs: Any,
    ) -> int:
        calls.append(browser)
        return 0

    monkeypatch.setattr("promptgrimoire.cli.e2e.run_playwright_lane", _fake_playwright)

    exit_code = run_all_browsers([])
    assert exit_code == 0
    assert calls == ["chromium", "firefox"]


def test_run_all_browsers_fail_fast_stops_on_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--fail-fast stops iteration after the first browser failure."""
    from promptgrimoire.cli.e2e import run_all_browsers

    calls: list[str | None] = []

    def _fake_playwright(
        _args: list[str],
        *,
        _parallel: bool = True,
        _fail_fast: bool = False,
        _py_spy: bool = False,
        browser: str | None = None,
        **_kwargs: Any,
    ) -> int:
        calls.append(browser)
        return 1  # Chromium fails

    monkeypatch.setattr("promptgrimoire.cli.e2e.run_playwright_lane", _fake_playwright)

    exit_code = run_all_browsers([], fail_fast=True)
    assert exit_code == 1
    assert calls == ["chromium"]  # Firefox never ran


def test_run_all_browsers_continues_past_failure_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default mode continues to Firefox even if Chromium fails."""
    from promptgrimoire.cli.e2e import run_all_browsers

    calls: list[str | None] = []

    def _fake_playwright(
        _args: list[str],
        *,
        _parallel: bool = True,
        _fail_fast: bool = False,
        _py_spy: bool = False,
        browser: str | None = None,
        **_kwargs: Any,
    ) -> int:
        calls.append(browser)
        return 1 if browser == "chromium" else 0

    monkeypatch.setattr("promptgrimoire.cli.e2e.run_playwright_lane", _fake_playwright)

    exit_code = run_all_browsers([])
    assert exit_code == 1  # Overall failure because Chromium failed
    assert calls == ["chromium", "firefox"]  # Both ran
