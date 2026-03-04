"""Tests for parallel E2E runner utilities and artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path

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
