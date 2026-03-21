"""Tests for parallel E2E runner utilities and artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptgrimoire.cli.e2e._workers import (
    _allocate_ports,
    _filter_junitxml_args,
)


def test_lane_specs_define_playwright_and_nicegui_contracts() -> None:
    """Lane specs encode the runtime split between Playwright and NiceGUI."""
    from promptgrimoire.cli.e2e._lanes import (
        NICEGUI_LANE,
        PLAYWRIGHT_LANE,
        WorkerResult,
    )

    assert PLAYWRIGHT_LANE.name == "playwright"
    assert PLAYWRIGHT_LANE.marker_expr == "e2e"
    assert PLAYWRIGHT_LANE.needs_server is True
    assert PLAYWRIGHT_LANE.artifact_subdir == "playwright"

    assert NICEGUI_LANE.name == "nicegui"
    assert NICEGUI_LANE.marker_expr == "nicegui_ui"
    assert NICEGUI_LANE.needs_server is False
    assert NICEGUI_LANE.artifact_subdir == "nicegui"

    result = WorkerResult(
        file=Path("tests/e2e/test_example.py"),
        exit_code=0,
        duration_s=1.25,
        artifact_dir=Path("output/test_output/e2e/playwright/run/test_example"),
    )
    assert result.file.name == "test_example.py"
    assert result.exit_code == 0
    assert result.duration_s == 1.25
    assert result.artifact_dir.name == "test_example"


def test_allocate_ports_returns_distinct_ports() -> None:
    """_allocate_ports(5) returns 5 distinct ports, all > 0."""
    ports = _allocate_ports(5)
    assert len(ports) == 5
    assert len(set(ports)) == 5, f"Ports are not distinct: {ports}"
    assert all(p > 0 for p in ports), f"All ports must be > 0: {ports}"


def test_allocate_ports_single() -> None:
    """_allocate_ports(1) returns a single port."""
    ports = _allocate_ports(1)
    assert len(ports) == 1
    assert ports[0] > 0


def test_allocate_ports_zero() -> None:
    """_allocate_ports(0) returns an empty list."""
    ports = _allocate_ports(0)
    assert ports == []


def test_filter_junitxml_args_strips_both_flag_styles() -> None:
    """Worker-local JUnit paths override user-provided global ones."""
    args = [
        "-k",
        "smoke",
        "--junitxml",
        "custom.xml",
        "--junitxml=other.xml",
        "-v",
    ]

    assert _filter_junitxml_args(args) == ["-k", "smoke", "-v"]


def test_artifact_helpers_create_stable_metadata(tmp_path: Path) -> None:
    """Lane runs and worker metadata are written under a stable root."""
    from promptgrimoire.cli.e2e._artifacts import (
        create_lane_run_dir,
        create_worker_dir,
        write_summary_metadata,
        write_worker_metadata,
    )
    from promptgrimoire.cli.e2e._lanes import WorkerResult

    run_dir = create_lane_run_dir("playwright", root=tmp_path, run_id="run-001")
    worker_dir = create_worker_dir(run_dir, Path("tests/e2e/test_annotation_canvas.py"))
    result = WorkerResult(
        file=Path("tests/e2e/test_annotation_canvas.py"),
        exit_code=5,
        duration_s=2.5,
        artifact_dir=worker_dir,
    )

    worker_meta = write_worker_metadata(worker_dir, result, lane_name="playwright")
    summary_meta = write_summary_metadata(
        run_dir, "playwright", [result], wall_clock_s=2.5
    )

    worker_payload = json.loads(worker_meta.read_text())
    summary_payload = json.loads(summary_meta.read_text())

    assert run_dir == tmp_path / "playwright" / "run-001"
    assert worker_dir == run_dir / "test_annotation_canvas"
    assert worker_payload["lane"] == "playwright"
    assert worker_payload["exit_code"] == 5
    assert summary_payload["lane"] == "playwright"
    assert summary_payload["counts"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "cancelled": 0,
    }


def test_all_results_passed_treats_exit_code_5_as_non_fatal(tmp_path: Path) -> None:
    """Pytest exit code 5 means no matching tests, not a worker failure."""
    from promptgrimoire.cli.e2e._lanes import WorkerResult
    from promptgrimoire.cli.e2e._parallel import _all_results_passed

    results = [
        WorkerResult(
            file=Path("tests/e2e/test_a.py"),
            exit_code=0,
            duration_s=1.0,
            artifact_dir=tmp_path / "a",
        ),
        WorkerResult(
            file=Path("tests/e2e/test_b.py"),
            exit_code=5,
            duration_s=1.1,
            artifact_dir=tmp_path / "b",
        ),
    ]

    assert _all_results_passed(results) is True


def test_discover_lane_files_uses_explicit_nicegui_allowlist(tmp_path: Path) -> None:
    """Lane discovery selects NiceGUI files via the fixed Phase 3 allowlist."""
    from promptgrimoire.cli.e2e._lanes import (
        NICEGUI_LANE,
        PLAYWRIGHT_LANE,
        LaneSpec,
        discover_lane_files,
        discover_nicegui_files,
    )

    e2e_dir = tmp_path / "e2e"
    e2e_dir.mkdir()
    playwright_a = e2e_dir / "test_a.py"
    playwright_b = e2e_dir / "test_b.py"
    playwright_a.write_text("def test_a() -> None:\n    assert True\n")
    playwright_b.write_text("def test_b() -> None:\n    assert True\n")
    (e2e_dir / "helpers.py").write_text("def helper() -> None:\n    pass\n")

    integration_dir = tmp_path / "integration"
    integration_dir.mkdir()
    # Create all allowlisted files + one excluded
    from promptgrimoire.cli.e2e._lanes import _NICEGUI_ALLOWLIST

    allowlisted = []
    for name in _NICEGUI_ALLOWLIST:
        path = integration_dir / name
        path.write_text("def test_stub() -> None:\n    assert True\n")
        allowlisted.append(path)
    excluded = integration_dir / "test_some_other_ui.py"
    excluded.write_text("def test_other() -> None:\n    assert True\n")

    result = discover_nicegui_files(integration_dir)
    assert sorted(result) == sorted(allowlisted)
    assert excluded not in result

    playwright_lane = LaneSpec(
        name=PLAYWRIGHT_LANE.name,
        test_paths=(e2e_dir,),
        marker_expr=PLAYWRIGHT_LANE.marker_expr,
        needs_server=PLAYWRIGHT_LANE.needs_server,
        artifact_subdir=PLAYWRIGHT_LANE.artifact_subdir,
    )
    nicegui_lane = LaneSpec(
        name=NICEGUI_LANE.name,
        test_paths=(integration_dir,),
        marker_expr=NICEGUI_LANE.marker_expr,
        needs_server=NICEGUI_LANE.needs_server,
        artifact_subdir=NICEGUI_LANE.artifact_subdir,
    )

    assert discover_lane_files(playwright_lane) == [playwright_a, playwright_b]
    assert sorted(discover_lane_files(nicegui_lane)) == sorted(allowlisted)


def test_discover_nicegui_files_handles_missing_allowlist_entries(
    tmp_path: Path,
) -> None:
    """Missing allowlist files are skipped rather than raising errors."""
    from promptgrimoire.cli.e2e._lanes import discover_nicegui_files

    integration_dir = tmp_path / "integration"
    integration_dir.mkdir()
    only_existing = integration_dir / "test_instructor_template_ui.py"
    only_existing.write_text("def test_other() -> None:\n    assert True\n")

    assert discover_nicegui_files(integration_dir) == [only_existing]

    only_existing.unlink()
    assert discover_nicegui_files(integration_dir) == []


@pytest.mark.asyncio
async def test_finalise_parallel_results_treats_flaky_retries_as_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed file that passes on retry is marked as flaky, not a final failure."""
    from promptgrimoire.cli.e2e import _parallel
    from promptgrimoire.cli.e2e._lanes import PLAYWRIGHT_LANE, WorkerResult

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    failed_result = WorkerResult(
        file=Path("tests/e2e/test_flaky.py"),
        exit_code=1,
        duration_s=0.4,
        artifact_dir=tmp_path / "worker-flaky",
    )

    async def _fake_retry_parallel_failures(
        *_args, **_kwargs
    ) -> tuple[list[Path], list[Path]]:
        return [], [failed_result.file]

    async def _unused_worker(*_args, **_kwargs) -> WorkerResult:
        raise AssertionError("worker should not be invoked by this test")

    monkeypatch.setattr(
        _parallel, "_retry_parallel_failures", _fake_retry_parallel_failures
    )
    monkeypatch.setattr(
        _parallel, "_merge_junit_xml", lambda _run_dir: _run_dir / "combined.xml"
    )

    all_passed, had_flaky = await _parallel._finalise_parallel_results(
        PLAYWRIGHT_LANE,
        _unused_worker,
        [failed_result],
        0.0,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        "test_db",
        run_dir,
        [],
    )

    assert all_passed is True
    assert had_flaky is True


@pytest.mark.asyncio
async def test_finalise_parallel_results_keeps_cancelled_workers_as_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cancelled workers are not retried and keep the lane in a failing state."""
    from promptgrimoire.cli.e2e import _parallel
    from promptgrimoire.cli.e2e._lanes import PLAYWRIGHT_LANE, WorkerResult

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    failed_result = WorkerResult(
        file=Path("tests/e2e/test_flaky.py"),
        exit_code=1,
        duration_s=0.4,
        artifact_dir=tmp_path / "worker-flaky",
    )
    cancelled_result = WorkerResult(
        file=Path("tests/e2e/test_cancelled.py"),
        exit_code=-1,
        duration_s=0.0,
        artifact_dir=tmp_path / "worker-cancelled",
    )

    async def _fake_retry_parallel_failures(
        *_args, **_kwargs
    ) -> tuple[list[Path], list[Path]]:
        return [], [failed_result.file]

    async def _unused_worker(*_args, **_kwargs) -> WorkerResult:
        raise AssertionError("worker should not be invoked by this test")

    monkeypatch.setattr(
        _parallel, "_retry_parallel_failures", _fake_retry_parallel_failures
    )
    monkeypatch.setattr(
        _parallel, "_merge_junit_xml", lambda _run_dir: _run_dir / "combined.xml"
    )

    all_passed, had_flaky = await _parallel._finalise_parallel_results(
        PLAYWRIGHT_LANE,
        _unused_worker,
        [failed_result, cancelled_result],
        0.0,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        "test_db",
        run_dir,
        [],
    )

    assert all_passed is False
    assert had_flaky is True


@pytest.mark.asyncio
async def test_finalise_parallel_results_forwards_browser_to_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """browser= must reach _retry_parallel_failures."""
    from promptgrimoire.cli.e2e import _parallel
    from promptgrimoire.cli.e2e._lanes import PLAYWRIGHT_LANE, WorkerResult

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    failed_result = WorkerResult(
        file=Path("tests/e2e/test_card_layout.py"),
        exit_code=1,
        duration_s=0.4,
        artifact_dir=tmp_path / "worker-card",
    )

    captured_browser: list[str | None] = []

    async def _spy_retry(
        _lane: object,
        _worker: object,
        _failed: object,
        _db_url: object,
        _src_db: object,
        _run_dir: object,
        _user_args: object,
        *,
        browser: str | None = None,
    ) -> tuple[list[Path], list[Path]]:
        captured_browser.append(browser)
        return [], [failed_result.file]

    async def _unused_worker(
        *_args: object,
        **_kwargs: object,
    ) -> WorkerResult:
        msg = "worker should not be invoked"
        raise AssertionError(msg)

    monkeypatch.setattr(
        _parallel,
        "_retry_parallel_failures",
        _spy_retry,
    )
    monkeypatch.setattr(
        _parallel,
        "_merge_junit_xml",
        lambda _run_dir: _run_dir / "combined.xml",
    )

    await _parallel._finalise_parallel_results(
        PLAYWRIGHT_LANE,
        _unused_worker,
        [failed_result],
        0.0,
        "postgresql+asyncpg://user:pass@localhost/test_db",
        "test_db",
        run_dir,
        [],
        browser="firefox",
    )

    assert captured_browser == ["firefox"], (
        f"browser='firefox' must reach _retry, got {captured_browser}"
    )
