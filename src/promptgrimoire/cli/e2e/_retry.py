"""Serial retry logic for failed E2E tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from promptgrimoire.cli._shared import console
from promptgrimoire.cli.e2e._artifacts import create_retry_dir
from promptgrimoire.cli.e2e._lanes import LaneSpec, WorkerResult
from promptgrimoire.cli.e2e._workers import _worker_status_label

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def _get_last_failed() -> list[str]:
    """Read failed test node IDs from pytest's lastfailed cache."""
    cache_path = Path(".pytest_cache/v/cache/lastfailed")
    if not cache_path.exists():
        return []
    data = json.loads(cache_path.read_text())
    return [k for k, v in data.items() if v]


def _initialise_retry_log(retry_dir: Path | None) -> Path | None:
    """Create retry directory if needed and return its log path."""
    if retry_dir is None:
        return None
    retry_dir.mkdir(parents=True, exist_ok=True)
    return retry_dir / "retry.log"


def _write_retry_header(
    log_path: Path,
    retry_log_path: Path | None,
    count: int,
) -> None:
    """Write retry-run header to the primary and optional retry logs."""
    header = f"\n{'=' * 60}\nIsolation retry: {count} test(s)\n{'=' * 60}\n\n"
    with log_path.open("a") as log_file:
        log_file.write(header)
    if retry_log_path is not None:
        retry_log_path.write_text(header.lstrip("\n"))


def _append_log(path: Path, content: str) -> None:
    """Append *content* to *path*."""
    with path.open("a") as log_file:
        log_file.write(content)


def _append_retry_logs(
    *,
    log_path: Path,
    retry_log_path: Path | None,
    content: str,
) -> None:
    """Append content to the main log and optional per-retry log."""
    _append_log(log_path, content)
    if retry_log_path is not None:
        _append_log(retry_log_path, content)


def _retry_command(node_id: str) -> list[str]:
    """Build pytest command for re-running one node in isolation."""
    return [
        "uv",
        "run",
        "pytest",
        node_id,
        "--tb=short",
        "-v",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]


def _run_retry_node(node_id: str) -> subprocess.CompletedProcess[str]:
    """Execute one isolated retry invocation."""
    env = {**os.environ, "GRIMOIRE_TEST_HARNESS": "1"}
    return subprocess.run(
        _retry_command(node_id),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        env=env,
    )


def _record_retry_result(
    *,
    index: int,
    total: int,
    node_id: str,
    result: subprocess.CompletedProcess[str],
    flaky: list[str],
    genuine_failures: list[str],
) -> None:
    """Classify and report one retry result."""
    if result.returncode in (0, 5):
        flaky.append(node_id)
        console.print(
            f"  [{index}/{total}] {node_id}: [yellow]FLAKY[/] (passed in isolation)"
        )
        return

    genuine_failures.append(node_id)
    console.print(f"  [{index}/{total}] {node_id}: [red]FAILED[/] (genuine failure)")


def _print_retry_outcome(flaky: list[str], genuine_failures: list[str]) -> None:
    """Print flaky vs genuine failure summary after retry run."""
    console.print()
    if flaky:
        console.print(
            f"[yellow]Flaky ({len(flaky)}):[/] passed when re-run in isolation"
        )
        for node_id in flaky:
            console.print(f"  {node_id}")
    if genuine_failures:
        console.print(f"[red]Genuine failures ({len(genuine_failures)}):[/]")
        for node_id in genuine_failures:
            console.print(f"  {node_id}")


def _retry_e2e_tests_in_isolation(
    log_path: Path,
    retry_dir: Path | None = None,
) -> int:
    """Re-run failed E2E tests individually to distinguish flaky from genuine failures.

    Reads the pytest lastfailed cache for test node IDs, re-runs each one
    in its own pytest invocation (without ``--reruns``), and reports which
    passed (flaky due to test interaction) vs which still failed (genuine).

    Returns 0 if all failures were flaky, 1 if any genuinely failed.
    """
    failed_tests = _get_last_failed()
    if not failed_tests:
        return 1  # No cached failures -- can't retry, report original failure

    console.print(
        f"\n[blue]Re-running {len(failed_tests)} failed test(s) in isolation...[/]"
    )

    genuine_failures: list[str] = []
    flaky: list[str] = []
    retry_log_path = _initialise_retry_log(retry_dir)
    _write_retry_header(log_path, retry_log_path, len(failed_tests))

    total = len(failed_tests)
    for i, node_id in enumerate(failed_tests, 1):
        _append_retry_logs(
            log_path=log_path,
            retry_log_path=retry_log_path,
            content=f"--- Retry {i}/{total}: {node_id} ---\n",
        )
        result = _run_retry_node(node_id)
        _append_retry_logs(
            log_path=log_path,
            retry_log_path=retry_log_path,
            content=f"{result.stdout}Exit code: {result.returncode}\n\n",
        )
        _record_retry_result(
            index=i,
            total=total,
            node_id=node_id,
            result=result,
            flaky=flaky,
            genuine_failures=genuine_failures,
        )

    _print_retry_outcome(flaky, genuine_failures)

    # Flaky tests are failures when strict mode is active (CI default).
    strict = bool(os.environ.get("CI") or os.environ.get("GRIMOIRE_STRICT_FLAKY"))
    if genuine_failures:
        return 1
    if flaky and strict:
        return 1
    return 0


async def retry_failed_files_in_isolation(
    lane: LaneSpec,
    worker: Callable[..., Awaitable[WorkerResult]],
    *,
    failed_files: list[Path],
    result_root: Path,
    user_args: list[str],
    retry_dbs: list[tuple[str, str]],
    retry_ports: list[int],
    run_worker_for_lane: Callable[..., Awaitable[WorkerResult]],
    browser: str | None = None,
) -> tuple[list[Path], list[Path]]:
    """Re-run failed files in isolation and classify flaky vs genuine failures."""
    genuine_failures: list[Path] = []
    flaky_files: list[Path] = []
    total = len(failed_files)

    for i, failed_file in enumerate(failed_files):
        retry_dir = create_retry_dir(result_root / failed_file.stem)
        try:
            result = await run_worker_for_lane(
                lane,
                worker,
                test_file=failed_file,
                db_url=retry_dbs[i][0],
                worker_dir=retry_dir,
                user_args=user_args,
                port=retry_ports[i] if lane.needs_server else None,
                browser=browser,
            )
        except Exception as exc:
            console.print(f"[red]Retry worker {failed_file.name} raised: {exc}[/]")
            result = WorkerResult(
                file=failed_file,
                exit_code=1,
                duration_s=0.0,
                artifact_dir=retry_dir,
            )

        label = _worker_status_label(result.exit_code)
        console.print(
            f"  [retry {i + 1}/{total}] {result.file.name}: "
            f"{label} ({result.duration_s:.1f}s)"
        )

        if result.exit_code in (0, 5):
            flaky_files.append(failed_file)
        else:
            genuine_failures.append(failed_file)

    return genuine_failures, flaky_files
