"""Lane contracts and discovery helpers for isolated E2E execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PLAYWRIGHT_DEFAULT_MARKER_EXPR = "e2e and not perf and not noci"
PLAYWRIGHT_SLOW_MARKER_EXPR = "e2e and not perf"


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


@dataclass
class LaneResult:
    """Aggregated outcome for one lane in an umbrella run."""

    name: str
    exit_code: int
    passed: int = 0
    flaky: int = 0
    failed: int = 0
    wall_clock_s: float = 0.0
    log_path: Path | None = None
    artifact_dir: Path | None = None


PLAYWRIGHT_LANE = LaneSpec(
    name="playwright",
    test_paths=(Path("tests/e2e"),),
    marker_expr=PLAYWRIGHT_DEFAULT_MARKER_EXPR,
    needs_server=True,
    artifact_subdir="playwright",
)

NICEGUI_LANE = LaneSpec(
    name="nicegui",
    test_paths=(Path("tests/integration"),),
    marker_expr="nicegui_ui and not perf",
    needs_server=False,
    artifact_subdir="nicegui",
)

_NICEGUI_ALLOWLIST: tuple[str, ...] = (
    "test_annotation_cards_charac.py",
    "test_annotation_pdf_export_filename_ui.py",
    "test_bulk_enrol_upload_ui.py",
    "test_crud_management_ui.py",
    "test_instructor_course_admin_ui.py",
    "test_instructor_template_ui.py",
    "test_multi_doc_tabs.py",
    "test_organise_charac.py",
    "test_page_load_query_count.py",
    "test_respond_charac.py",
    "test_slot_deletion_race_369.py",
    "test_tag_management_crdt_sync.py",
    "test_memory_leak_probe.py",
    "test_event_loop_render_lag.py",
    "test_lazy_card_detail.py",
    "test_vue_sidebar_spike.py",
    "test_vue_sidebar_dom_contract.py",
    "test_vue_sidebar_expand.py",
)


def _discover_test_files(base_dir: Path) -> list[Path]:
    """Return sorted `test_*.py` files under *base_dir*."""
    return sorted(base_dir.glob("test_*.py"))


def discover_playwright_files(base_dir: Path = Path("tests/e2e")) -> list[Path]:
    """Discover Playwright E2E files by path."""
    return _discover_test_files(base_dir)


def discover_nicegui_files(base_dir: Path = Path("tests/integration")) -> list[Path]:
    """Discover NiceGUI UI files from the explicit allowlist."""
    # Phase 3 intentionally uses a fixed allowlist for lane stability.
    # Generalised marker/AST discovery can be revisited after the lane is proven stable.
    return [path for name in _NICEGUI_ALLOWLIST if (path := base_dir / name).exists()]


def discover_lane_files(lane: LaneSpec) -> list[Path]:
    """Discover test files for *lane* using its lane-specific rule."""
    if lane.name == PLAYWRIGHT_LANE.name:
        return discover_playwright_files(lane.test_paths[0])
    if lane.name == NICEGUI_LANE.name:
        return discover_nicegui_files(lane.test_paths[0])
    msg = f"unsupported lane: {lane.name}"
    raise ValueError(msg)
