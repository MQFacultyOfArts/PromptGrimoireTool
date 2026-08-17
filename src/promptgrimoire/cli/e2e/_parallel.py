"""Parallel E2E orchestration and database management."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from promptgrimoire.cli._shared import _pre_test_db_cleanup, console
from promptgrimoire.cli.e2e._artifacts import (
    create_lane_run_dir,
    create_worker_dir,
    write_summary_metadata,
)
from promptgrimoire.cli.e2e._lanes import (
    PLAYWRIGHT_LANE,
    LaneSpec,
    WorkerResult,
    discover_lane_files,
)
from promptgrimoire.cli.e2e._retry import retry_failed_files_in_isolation
from promptgrimoire.cli.e2e._workers import (
    _allocate_ports,
    _merge_junit_xml,
    _print_parallel_summary,
    _resolve_failed_task_file,
    _worker_status_label,
    run_playwright_file,
)
from promptgrimoire.config import get_settings
from promptgrimoire.db.bootstrap import clone_database, drop_database

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()

_POSTGRES_IDENTIFIER_MAX_BYTES = 63


@dataclass(frozen=True, slots=True)
class LaneRunContext:
    """Constants shared by every worker dispatched within one lane run."""

    lane: LaneSpec
    worker: Callable[..., Awaitable[WorkerResult]]
    user_args: list[str]
    browser: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerFleet:
    """Per-file collections threaded through parallel lane orchestration.

    ``files[i]`` pairs positionally with ``ports[i]`` and ``worker_dbs[i]``;
    ``worker_dirs`` is keyed by file path.
    """

    files: list[Path]
    ports: list[int]
    worker_dbs: list[tuple[str, str]]
    worker_dirs: dict[Path, Path]


@dataclass(frozen=True, slots=True)
class SourceDatabase:
    """The template database a lane run clones per-worker databases from."""

    url: str
    name: str


def _drop_database_with_debug(db_url: str, *, context: str) -> None:
    """Drop *db_url* and log cleanup failures at debug level."""
    try:
        drop_database(db_url)
    except Exception:
        logger.debug(
            "Failed to drop database during %s: %s",
            context,
            db_url,
            exc_info=True,
        )


def _worker_database_name(source_db_name: str, suffix: str, index: int) -> str:
    """Return a worker DB name without losing its suffix to PG truncation."""
    worker_suffix = f"_{suffix}{index}"
    candidate = f"{source_db_name}{worker_suffix}"
    if len(candidate.encode()) <= _POSTGRES_IDENTIFIER_MAX_BYTES:
        return candidate

    source_hash = hashlib.sha256(source_db_name.encode()).hexdigest()[:8]
    prefix_bytes = (
        _POSTGRES_IDENTIFIER_MAX_BYTES
        - len(worker_suffix.encode())
        - len(source_hash)
        - 1
    )
    return f"{source_db_name[:prefix_bytes]}_{source_hash}{worker_suffix}"


def _report_worker_progress(
    result: WorkerResult,
    done_count: int,
    total: int,
) -> None:
    """Print a single worker's completion status."""
    label = _worker_status_label(result.exit_code)
    console.print(
        f"  [{done_count}/{total}] {result.file.name}: "
        f"{label} ({result.duration_s:.1f}s)"
    )


def _all_results_passed(results: list[WorkerResult]) -> bool:
    """Return True when every worker exit code is a success or no-test match."""
    return len(results) > 0 and all(result.exit_code in (0, 5) for result in results)


# PLR0913 (too many arguments): every keyword here is part of the
# `run_worker_for_lane` callback contract that `_retry.py::
# retry_failed_files_in_isolation` invokes by this exact keyword shape
# (see test_retry_forwards_browser_to_run_worker_for_lane in
# tests/unit/test_cli_e2e_runner.py) -- `_retry.py` is owned by a different
# workstream in this cleanup, so its calling convention is not renegotiable
# here. Bundling these into a param object would have to happen on both
# sides at once.
async def _run_worker_for_lane(  # noqa: PLR0913
    lane: LaneSpec,
    worker: Callable[..., Awaitable[WorkerResult]],
    *,
    test_file: Path,
    db_url: str,
    worker_dir: Path,
    user_args: list[str],
    port: int | None = None,
    browser: str | None = None,
) -> WorkerResult:
    """Dispatch a lane-specific worker with the correct runtime contract."""
    if lane.needs_server:
        assert port is not None  # noqa: S101 - lane contract guarantees a port
        return await worker(
            test_file,
            port,
            db_url,
            worker_dir,
            user_args,
            browser=browser,
            marker_expr=lane.marker_expr or "e2e",
        )

    return await worker(test_file, db_url, worker_dir, user_args)


async def _run_all_workers(
    ctx: LaneRunContext,
    fleet: WorkerFleet,
    *,
    worker_count: int,
) -> list[WorkerResult]:
    """Run all lane workers with bounded concurrency and per-file progress."""
    total = len(fleet.files)
    results: list[WorkerResult] = []
    semaphore = asyncio.Semaphore(worker_count)

    async def _tracked_worker(i: int) -> WorkerResult:
        async with semaphore:
            return await _run_worker_for_lane(
                ctx.lane,
                ctx.worker,
                test_file=fleet.files[i],
                db_url=fleet.worker_dbs[i][0],
                worker_dir=fleet.worker_dirs[fleet.files[i]],
                user_args=ctx.user_args,
                port=fleet.ports[i] if ctx.lane.needs_server else None,
                browser=ctx.browser,
            )

    tasks: list[asyncio.Task[WorkerResult]] = [
        asyncio.create_task(_tracked_worker(i), name=f"e2e-{f.stem}")
        for i, f in enumerate(fleet.files)
    ]

    for done_count, future in enumerate(asyncio.as_completed(tasks), 1):
        try:
            result = await future
        except Exception as exc:
            fpath = _resolve_failed_task_file(tasks, exc, fleet.files)
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = WorkerResult(
                file=fpath,
                exit_code=1,
                duration_s=0.0,
                artifact_dir=fleet.worker_dirs[fpath],
            )

        results.append(result)
        _report_worker_progress(result, done_count, total)

    return results


async def _cancel_and_drain_tasks(
    tasks: list[asyncio.Task[WorkerResult]],
    completed_files: set[Path],
    files: list[Path],
    worker_dirs: dict[Path, Path],
) -> list[WorkerResult]:
    """Cancel pending tasks, await their cleanup, and return cancelled entries."""
    console.print("[red]  Fail-fast: cancelling remaining workers[/]")
    for t in tasks:
        if not t.done():
            t.cancel()

    # Await cancelled tasks so their finally blocks run
    for t in tasks:
        if t.cancelled() or not t.done():
            with contextlib.suppress(asyncio.CancelledError):
                await t

    # Return entries for files that never completed
    return [
        WorkerResult(
            file=f,
            exit_code=-1,
            duration_s=0.0,
            artifact_dir=worker_dirs[f],
        )
        for f in files
        if f not in completed_files
    ]


async def _run_fail_fast_workers(
    ctx: LaneRunContext,
    fleet: WorkerFleet,
    *,
    worker_count: int,
) -> list[WorkerResult]:
    """Run E2E workers with fail-fast: cancel remaining on first failure."""
    semaphore = asyncio.Semaphore(worker_count)

    async def _tracked_worker(i: int) -> WorkerResult:
        async with semaphore:
            return await _run_worker_for_lane(
                ctx.lane,
                ctx.worker,
                test_file=fleet.files[i],
                db_url=fleet.worker_dbs[i][0],
                worker_dir=fleet.worker_dirs[fleet.files[i]],
                user_args=ctx.user_args,
                port=fleet.ports[i] if ctx.lane.needs_server else None,
                browser=ctx.browser,
            )

    tasks: list[asyncio.Task[WorkerResult]] = [
        asyncio.create_task(_tracked_worker(i), name=f"e2e-{f.stem}")
        for i, f in enumerate(fleet.files)
    ]

    total = len(fleet.files)
    results: list[WorkerResult] = []
    completed_files: set[Path] = set()
    done_count = 0

    for future in asyncio.as_completed(tasks):
        try:
            result = await future
        except asyncio.CancelledError:
            continue
        except Exception as exc:
            fpath = _resolve_failed_task_file(tasks, exc, fleet.files)
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = WorkerResult(
                file=fpath,
                exit_code=1,
                duration_s=0.0,
                artifact_dir=fleet.worker_dirs[fpath],
            )

        results.append(result)
        completed_files.add(result.file)
        done_count += 1
        _report_worker_progress(result, done_count, total)

        if result.exit_code not in (0, 5):
            cancelled = await _cancel_and_drain_tasks(
                tasks, completed_files, fleet.files, fleet.worker_dirs
            )
            results.extend(cancelled)
            break

    return results


def _drop_all_worker_dbs(worker_dbs: list[tuple[str, str]], *, context: str) -> None:
    """Drop every worker database."""
    for db_url, _db_name in worker_dbs:
        _drop_database_with_debug(db_url, context=context)


def _advertise_failed_workers(
    results: list[WorkerResult],
    file_db_map: dict[Path, tuple[str, str]],
) -> None:
    """Print log/DB details for each failed worker."""
    for result in results:
        if result.exit_code in (0, 5, -1):
            continue
        _db_url, db_name = file_db_map.get(result.file, ("unknown", "unknown"))
        console.print(f"  [red]{result.file.name}[/]:")
        console.print(f"    Log:    {result.artifact_dir / 'pytest.log'}")
        server_log = result.artifact_dir / "server.log"
        if server_log.exists():
            console.print(f"    Server: {server_log}")
        console.print(f"    DB:     {db_name}")


def _cleanup_parallel_results(
    all_passed: bool,
    had_flaky: bool,
    fleet: WorkerFleet,
    run_dir: Path,
    results: list[WorkerResult],
) -> None:
    """Clean up or preserve worker databases and result directory.

    On failure, only preserves databases for failed workers and drops
    the rest.  On flaky-pass, preserves the artifact directory but
    drops all databases.
    """
    worker_dbs = fleet.worker_dbs
    file_db_map = dict(zip(fleet.files, worker_dbs, strict=False))

    if all_passed and not had_flaky:
        _drop_all_worker_dbs(worker_dbs, context="parallel result cleanup")
        shutil.rmtree(run_dir, ignore_errors=True)
        console.print("[green]All passed — cleaned up worker databases and results[/]")
        return

    if all_passed:
        _drop_all_worker_dbs(worker_dbs, context="parallel result cleanup")
        console.print(
            "[yellow]All passed (with flaky retries) — preserving artifacts:[/]"
        )
        console.print(f"  Results: {run_dir}")
        return

    console.print("[yellow]Some tests failed — preserving artifacts:[/]")
    console.print(f"  Results: {run_dir}")
    _advertise_failed_workers(results, file_db_map)
    # Drop databases for passing workers, keep failed ones.
    failed_files = {r.file for r in results if r.exit_code not in (0, 5, -1)}
    for f, (db_url, _db_name) in file_db_map.items():
        if f not in failed_files:
            _drop_database_with_debug(db_url, context="passing worker cleanup")


def _print_retry_summary(
    genuine_failures: list[Path],
    flaky_files: list[Path],
) -> None:
    """Print a summary of retry results (flaky vs genuine failures)."""
    console.print()
    if flaky_files:
        console.print(f"[yellow]Flaky ({len(flaky_files)}):[/] passed on retry")
        for f in flaky_files:
            console.print(f"  {f.name}")
    if genuine_failures:
        console.print(f"[red]Genuine failures ({len(genuine_failures)}):[/]")
        for f in genuine_failures:
            console.print(f"  {f.name}")


async def _retry_parallel_failures(
    ctx: LaneRunContext,
    failed_results: list[WorkerResult],
    source_db: SourceDatabase,
    run_dir: Path,
) -> tuple[list[Path], list[Path]]:
    """Re-run failed E2E files with fresh servers and databases.

    Each failed file gets a new cloned database and server instance.
    Runs sequentially to maximise isolation.

    Returns ``(genuine_failures, flaky_files)``.
    """
    console.print(
        f"\n[blue]Re-running {len(failed_results)} failed file(s) in isolation...[/]"
    )

    retry_ports = (
        _allocate_ports(len(failed_results))
        if ctx.lane.needs_server
        else [0] * len(failed_results)
    )
    retry_dbs = _create_worker_databases(
        source_db.url, source_db.name, len(failed_results), suffix="retry"
    )
    failed_files = [result.file for result in failed_results]

    try:
        genuine_failures, flaky_files = await retry_failed_files_in_isolation(
            ctx.lane,
            ctx.worker,
            failed_files=failed_files,
            result_root=run_dir,
            user_args=ctx.user_args,
            retry_dbs=retry_dbs,
            retry_ports=retry_ports,
            run_worker_for_lane=_run_worker_for_lane,
            browser=ctx.browser,
        )
        _print_retry_summary(genuine_failures, flaky_files)
        return genuine_failures, flaky_files

    finally:
        for url, _ in retry_dbs:
            _drop_database_with_debug(url, context="retry database cleanup")


def _create_worker_databases(
    test_db_url: str,
    source_db_name: str,
    count: int,
    suffix: str = "w",
) -> list[tuple[str, str]]:
    """Clone *count* worker databases from *test_db_url*.

    Drops stale databases with matching names first, then clones fresh
    copies. On partial failure, cleans up any databases already created.

    Returns list of ``(db_url, db_name)`` tuples.
    """
    base_url = test_db_url.split("?", maxsplit=1)[0].rsplit("/", 1)[0]
    query = ("?" + test_db_url.split("?", 1)[1]) if "?" in test_db_url else ""

    # Drop stale databases from interrupted previous runs
    for i in range(count):
        target_name = _worker_database_name(source_db_name, suffix, i)
        stale_url = f"{base_url}/{target_name}{query}"
        _drop_database_with_debug(stale_url, context="stale worker database cleanup")

    # Clone fresh databases
    worker_dbs: list[tuple[str, str]] = []
    try:
        for i in range(count):
            target_name = _worker_database_name(source_db_name, suffix, i)
            db_url = clone_database(test_db_url, target_name)
            worker_dbs.append((db_url, target_name))
    except Exception:
        for url, _ in worker_dbs:
            _drop_database_with_debug(url, context="worker database rollback")
        raise

    return worker_dbs


async def _finalise_parallel_results(
    ctx: LaneRunContext,
    results: list[WorkerResult],
    wall_start: float,
    source_db: SourceDatabase,
    run_dir: Path,
) -> tuple[bool, bool]:
    """Summarise, retry failures, merge JUnit XML.

    Returns ``(all_passed, had_flaky)``.
    """
    wall_clock = time.monotonic() - wall_start
    _print_parallel_summary(results, wall_clock)
    all_passed = _all_results_passed(results)
    flaky_files: list[Path] = []
    genuine_failures: list[Path] = []

    if not all_passed:
        failed_results = [
            result for result in results if result.exit_code not in (0, 5, -1)
        ]
        if failed_results:
            genuine_failures, flaky_files = await _retry_parallel_failures(
                ctx, failed_results, source_db, run_dir
            )
            # Retries are diagnostic only; preserve the initial failing result.

    try:
        _merge_junit_xml(run_dir)
    except Exception:
        logger.debug("Failed to merge JUnit XML in %s", run_dir, exc_info=True)
    write_summary_metadata(
        run_dir,
        ctx.lane.name,
        results,
        wall_clock_s=wall_clock,
        flaky_files=flaky_files,
        genuine_failures=genuine_failures,
    )

    return all_passed, bool(flaky_files)


def _default_worker_count(file_count: int) -> int:
    """Return the bounded worker count for lane execution."""
    return max(1, min(file_count, 4, max(1, (os.cpu_count() or 4) // 2)))


# PLR0913 (6 > 5): this is the public entry point for both the parallel
# Playwright lane and the NiceGUI lane, called from e2e/__init__.py and
# tested only via a full monkeypatch replacement (test_cli_e2e_runner.py::
# test_run_nicegui_e2e_routes_command_to_nicegui_lane) rather than through
# its real body. Bundling worker_count/fail_fast/browser into a param
# object would touch this load-bearing signature and its mocked test for a
# one-argument reduction; left as-is per the harness caution in this
# cleanup's brief (conservative mechanical extraction only, flag the rest).
async def run_lane_files(  # noqa: PLR0913
    lane: LaneSpec,
    worker: Callable[..., Awaitable[WorkerResult]],
    *,
    user_args: list[str],
    worker_count: int | None = None,
    fail_fast: bool = False,
    browser: str | None = None,
) -> int:
    """Run files in *lane* using isolated per-file workers.

    When *user_args* contains specific test file paths, only those
    files are run (filtered against the lane's discovered files).
    When no file paths are in *user_args*, all lane files run.
    """
    all_files = discover_lane_files(lane)

    # Filter to requested files if user specified specific paths
    requested = {
        Path(a.split("::")[0]).name
        for a in user_args
        if not a.startswith("-") and a.split("::")[0].endswith(".py")
    }
    files = [f for f in all_files if f.name in requested] if requested else all_files

    if not files:
        console.print(f"[yellow]No {lane.name} test files found[/]")
        return 0
    console.print(f"[blue]Found {len(files)} {lane.name} test files[/]")

    test_db_url = get_settings().dev.test_database_url
    if not test_db_url:
        console.print("[red]DEV__TEST_DATABASE_URL not set[/]")
        return 1

    _pre_test_db_cleanup()
    source_db_name = test_db_url.split("?")[0].rsplit("/", 1)[1]
    worker_dbs = _create_worker_databases(test_db_url, source_db_name, len(files))
    ports = _allocate_ports(len(files)) if lane.needs_server else [0] * len(files)
    run_dir = create_lane_run_dir(lane.artifact_subdir)
    worker_dirs = {path: create_worker_dir(run_dir, path) for path in files}
    bounded_worker_count = min(
        worker_count or _default_worker_count(len(files)), len(files)
    )

    # Advertise artifact paths upfront so a second instance can tail them.
    console.print(f"  artifacts: {run_dir}")
    console.print(f"  workers:   {bounded_worker_count}  files: {len(files)}")

    ctx = LaneRunContext(lane=lane, worker=worker, user_args=user_args, browser=browser)
    fleet = WorkerFleet(
        files=files, ports=ports, worker_dbs=worker_dbs, worker_dirs=worker_dirs
    )
    source_db = SourceDatabase(url=test_db_url, name=source_db_name)

    wall_start = time.monotonic()
    results: list[WorkerResult] = []
    all_passed = False
    had_flaky = False

    try:
        if fail_fast:
            results = await _run_fail_fast_workers(
                ctx, fleet, worker_count=bounded_worker_count
            )
        else:
            results = await _run_all_workers(
                ctx, fleet, worker_count=bounded_worker_count
            )

        all_passed, had_flaky = await _finalise_parallel_results(
            ctx, results, wall_start, source_db, run_dir
        )
        return 0 if all_passed else 1

    finally:
        _cleanup_parallel_results(all_passed, had_flaky, fleet, run_dir, results)


async def _run_parallel_e2e(
    user_args: list[str],
    fail_fast: bool = False,
    browser: str | None = None,
) -> int:
    """Orchestrate parallel Playwright E2E execution with per-file isolation."""
    return await run_lane_files(
        PLAYWRIGHT_LANE,
        run_playwright_file,
        user_args=user_args,
        fail_fast=fail_fast,
        browser=browser,
    )
