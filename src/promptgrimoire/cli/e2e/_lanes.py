"""Lane contracts and discovery helpers for isolated E2E execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaneSpec:
    """Static runtime contract for one E2E execution lane."""

    name: str
    test_paths: tuple[Path, ...]
    marker_expr: str | None
    needs_server: bool
    artifact_subdir: str


@dataclass(frozen=True)
class WorkerResult:
    """Structured result for a single isolated test-file worker."""

    file: Path
    exit_code: int
    duration_s: float
    artifact_dir: Path


PLAYWRIGHT_LANE = LaneSpec(
    name="playwright",
    test_paths=(Path("tests/e2e"),),
    marker_expr="e2e",
    needs_server=True,
    artifact_subdir="playwright",
)

NICEGUI_LANE = LaneSpec(
    name="nicegui",
    test_paths=(Path("tests/integration"),),
    marker_expr="nicegui_ui",
    needs_server=False,
    artifact_subdir="nicegui",
)


def _discover_test_files(base_dir: Path) -> list[Path]:
    """Return sorted `test_*.py` files under *base_dir*."""
    return sorted(base_dir.glob("test_*.py"))


def discover_playwright_files(base_dir: Path = Path("tests/e2e")) -> list[Path]:
    """Discover Playwright E2E files by path."""
    return _discover_test_files(base_dir)


def discover_nicegui_files(base_dir: Path = Path("tests/integration")) -> list[Path]:
    """Discover NiceGUI UI files by marker annotation."""
    nicegui_files: list[Path] = []
    for path in _discover_test_files(base_dir):
        if "pytest.mark.nicegui_ui" in path.read_text():
            nicegui_files.append(path)
    return nicegui_files


def discover_lane_files(lane: LaneSpec) -> list[Path]:
    """Discover test files for *lane* using its lane-specific rule."""
    if lane.name == PLAYWRIGHT_LANE.name:
        return discover_playwright_files(lane.test_paths[0])
    if lane.name == NICEGUI_LANE.name:
        return discover_nicegui_files(lane.test_paths[0])
    msg = f"unsupported lane: {lane.name}"
    raise ValueError(msg)
