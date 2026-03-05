"""Stable artifact helpers for isolated E2E lane execution."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptgrimoire.cli.e2e._lanes import WorkerResult

E2E_ARTIFACT_ROOT = Path("output/test_output/e2e")


def create_lane_run_dir(
    lane_name: str,
    *,
    root: Path = E2E_ARTIFACT_ROOT,
    run_id: str | None = None,
) -> Path:
    """Create and return a stable artifact directory for one lane run."""
    resolved_run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = root / lane_name / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def create_worker_dir(run_dir: Path, test_file: Path) -> Path:
    """Create and return a per-file worker artifact directory."""
    worker_dir = run_dir / test_file.stem
    worker_dir.mkdir(parents=True, exist_ok=True)
    return worker_dir


def create_retry_dir(worker_dir: Path) -> Path:
    """Create and return the retry subdirectory for one worker."""
    retry_dir = worker_dir / "retry"
    retry_dir.mkdir(parents=True, exist_ok=True)
    return retry_dir


def write_worker_metadata(
    worker_dir: Path,
    result: WorkerResult,
    *,
    lane_name: str | None = None,
) -> Path:
    """Write `worker.json` for one worker result."""
    payload = {
        "file": str(result.file),
        "exit_code": result.exit_code,
        "duration_s": result.duration_s,
        "artifact_dir": str(result.artifact_dir),
    }
    if lane_name is not None:
        payload["lane"] = lane_name

    worker_json = worker_dir / "worker.json"
    worker_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return worker_json


def write_summary_metadata(
    run_dir: Path,
    lane_name: str,
    results: list[WorkerResult],
    *,
    wall_clock_s: float,
    flaky_files: list[Path] | None = None,
    genuine_failures: list[Path] | None = None,
) -> Path:
    """Write `summary.json` for one lane run."""
    counts = {
        "total": len(results),
        "passed": sum(1 for result in results if result.exit_code in (0, 5)),
        "failed": sum(1 for result in results if result.exit_code not in (0, 5, -1)),
        "cancelled": sum(1 for result in results if result.exit_code == -1),
    }
    payload = {
        "lane": lane_name,
        "wall_clock_s": wall_clock_s,
        "counts": counts,
        "results": [
            {
                "file": str(result.file),
                "exit_code": result.exit_code,
                "duration_s": result.duration_s,
                "artifact_dir": str(result.artifact_dir),
            }
            for result in results
        ],
        "flaky_files": [str(path) for path in flaky_files or []],
        "genuine_failures": [str(path) for path in genuine_failures or []],
    }

    summary_json = run_dir / "summary.json"
    summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return summary_json
