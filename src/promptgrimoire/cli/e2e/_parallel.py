"""Parallel E2E orchestration and database management."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
import time
from pathlib import Path

from promptgrimoire.cli._shared import _pre_test_db_cleanup, console
from promptgrimoire.cli.e2e._workers import (
    _allocate_ports,
    _merge_junit_xml,
    _print_parallel_summary,
    _resolve_failed_task_file,
    _run_e2e_worker,
    _worker_status_label,
)
from promptgrimoire.config import get_settings
from promptgrimoire.db.bootstrap import clone_database, drop_database


def _resolve_exception_file(
    tasks: list[asyncio.Task[tuple[Path, int, float]]],
    exc: Exception,
    files: list[Path],
) -> Path:
    """Find which test file raised *exc* by matching across indexed tasks."""
    for j, t in enumerate(tasks):
        if not t.done() or t.cancelled():
            continue
        try:
            t.result()
        except Exception as t_exc:
            if t_exc is exc:
                return files[j]
    return files[0]  # fallback


def _report_worker_progress(
    result: tuple[Path, int, float],
    done_count: int,
    total: int,
) -> None:
    """Print a single worker's completion status."""
    label = _worker_status_label(result[1])
    console.print(
        f"  [{done_count}/{total}] {result[0].name}: {label} ({result[2]:.1f}s)"
    )


async def _run_all_workers(
    files: list[Path],
    ports: list[int],
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    user_args: list[str],
) -> list[tuple[Path, int, float]]:
    """Run all E2E workers concurrently, printing progress as each finishes."""
    total = len(files)
    results: list[tuple[Path, int, float]] = []

    async def _tracked_worker(i: int) -> tuple[Path, int, float]:
        return await _run_e2e_worker(
            files[i], ports[i], worker_dbs[i][0], result_dir, user_args
        )

    tasks = [asyncio.create_task(_tracked_worker(i)) for i in range(total)]

    for done_count, future in enumerate(asyncio.as_completed(tasks), 1):
        try:
            result = await future
        except Exception as exc:
            fpath = _resolve_exception_file(tasks, exc, files)
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = (fpath, 1, 0.0)

        results.append(result)
        _report_worker_progress(result, done_count, total)

    return results


async def _cancel_and_drain_tasks(
    tasks: list[asyncio.Task[tuple[Path, int, float]]],
    completed_files: set[Path],
    files: list[Path],
) -> list[tuple[Path, int, float]]:
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
    return [(f, -1, 0.0) for f in files if f not in completed_files]


async def _run_fail_fast_workers(
    files: list[Path],
    ports: list[int],
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    user_args: list[str],
) -> list[tuple[Path, int, float]]:
    """Run E2E workers with fail-fast: cancel remaining on first failure."""
    tasks: list[asyncio.Task[tuple[Path, int, float]]] = [
        asyncio.create_task(
            _run_e2e_worker(f, ports[i], worker_dbs[i][0], result_dir, user_args),
            name=f"e2e-{f.stem}",
        )
        for i, f in enumerate(files)
    ]

    total = len(files)
    results: list[tuple[Path, int, float]] = []
    completed_files: set[Path] = set()
    done_count = 0

    for future in asyncio.as_completed(tasks):
        try:
            result = await future
        except asyncio.CancelledError:
            continue
        except Exception as exc:
            fpath = _resolve_failed_task_file(tasks, exc, files)
            console.print(f"[red]Worker {fpath.name} raised: {exc}[/]")
            result = (fpath, 1, 0.0)

        results.append(result)
        completed_files.add(result[0])
        done_count += 1
        _report_worker_progress(result, done_count, total)

        if result[1] not in (0, 5):
            cancelled = await _cancel_and_drain_tasks(tasks, completed_files, files)
            results.extend(cancelled)
            break

    return results


def _cleanup_parallel_results(
    all_passed: bool,
    worker_dbs: list[tuple[str, str]],
    result_dir: Path,
    results: list[tuple[Path, int, float]],
) -> None:
    """Clean up or preserve worker databases and result directory."""
    if all_passed:
        for db_url, _db_name in worker_dbs:
            with contextlib.suppress(Exception):
                drop_database(db_url)
        shutil.rmtree(result_dir, ignore_errors=True)
        console.print("[green]All passed — cleaned up worker databases and results[/]")
    else:
        console.print("[yellow]Some tests failed — preserving artifacts:[/]")
        console.print(f"  Results: {result_dir}")
        for db_url, db_name in worker_dbs:
            console.print(f"  DB: {db_name} ({db_url})")
        for test_file, exit_code, _duration in results:
            if exit_code not in (0, 5, -1):
                log_path = result_dir / f"test-e2e-{test_file.stem}.log"
                console.print(f"  Log: {log_path}")


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


async def _run_sequential_retries(
    failed_files: list[Path],
    retry_ports: list[int],
    retry_dbs: list[tuple[str, str]],
    result_dir: Path,
    user_args: list[str],
) -> tuple[list[Path], list[Path]]:
    """Execute retry workers sequentially, classifying results as flaky or genuine."""
    genuine_failures: list[Path] = []
    flaky_files: list[Path] = []
    total = len(failed_files)

    for i, fpath in enumerate(failed_files):
        try:
            result = await _run_e2e_worker(
                fpath, retry_ports[i], retry_dbs[i][0], result_dir, user_args
            )
        except Exception as exc:
            console.print(f"[red]Retry worker {fpath.name} raised: {exc}[/]")
            result = (fpath, 1, 0.0)

        label = _worker_status_label(result[1])
        console.print(
            f"  [retry {i + 1}/{total}] {result[0].name}: {label} ({result[2]:.1f}s)"
        )

        if result[1] in (0, 5):
            flaky_files.append(fpath)
        else:
            genuine_failures.append(fpath)

    return genuine_failures, flaky_files


async def _retry_parallel_failures(
    failed_files: list[Path],
    template_db_url: str,
    source_db_name: str,
    result_dir: Path,
    user_args: list[str],
) -> tuple[list[Path], list[Path]]:
    """Re-run failed E2E files with fresh servers and databases.

    Each failed file gets a new cloned database and server instance.
    Runs sequentially to maximise isolation.

    Returns ``(genuine_failures, flaky_files)``.
    """
    console.print(
        f"\n[blue]Re-running {len(failed_files)} failed file(s) in isolation...[/]"
    )

    retry_ports = _allocate_ports(len(failed_files))
    retry_dbs = _create_worker_databases(
        template_db_url, source_db_name, len(failed_files), suffix="retry"
    )

    try:
        genuine_failures, flaky_files = await _run_sequential_retries(
            failed_files, retry_ports, retry_dbs, result_dir, user_args
        )
        _print_retry_summary(genuine_failures, flaky_files)
        return genuine_failures, flaky_files

    finally:
        for url, _ in retry_dbs:
            with contextlib.suppress(Exception):
                drop_database(url)


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
        stale_url = f"{base_url}/{source_db_name}_{suffix}{i}{query}"
        with contextlib.suppress(Exception):
            drop_database(stale_url)

    # Clone fresh databases
    worker_dbs: list[tuple[str, str]] = []
    try:
        for i in range(count):
            target_name = f"{source_db_name}_{suffix}{i}"
            db_url = clone_database(test_db_url, target_name)
            worker_dbs.append((db_url, target_name))
    except Exception:
        for url, _ in worker_dbs:
            with contextlib.suppress(Exception):
                drop_database(url)
        raise

    return worker_dbs


async def _finalise_parallel_results(
    results: list[tuple[Path, int, float]],
    wall_start: float,
    test_db_url: str,
    source_db_name: str,
    result_dir: Path,
    user_args: list[str],
) -> bool:
    """Summarise, retry failures, merge JUnit XML. Returns all_passed."""
    all_passed = len(results) > 0 and all(code in (0, 5) for _, code, _ in results)

    wall_clock = time.monotonic() - wall_start
    _print_parallel_summary(results, wall_clock)

    if not all_passed:
        failed_files = [f for f, code, _ in results if code not in (0, 5, -1)]
        if failed_files:
            genuine, _flaky = await _retry_parallel_failures(
                failed_files,
                test_db_url,
                source_db_name,
                result_dir,
                user_args,
            )
            all_passed = not genuine

    with contextlib.suppress(Exception):
        _merge_junit_xml(result_dir)

    return all_passed


async def _run_parallel_e2e(
    user_args: list[str],
    fail_fast: bool = False,
) -> int:
    """Orchestrate parallel E2E test execution with per-file isolation.

    Each test file gets its own cloned database and server instance.
    Returns 0 if all tests pass, 1 if any failed.
    """
    files = sorted(Path("tests/e2e").glob("test_*.py"))
    if not files:
        console.print("[yellow]No E2E test files found[/]")
        return 0
    console.print(f"[blue]Found {len(files)} test files[/]")

    test_db_url = get_settings().dev.test_database_url
    if not test_db_url:
        console.print("[red]DEV__TEST_DATABASE_URL not set[/]")
        return 1

    _pre_test_db_cleanup()
    source_db_name = test_db_url.split("?")[0].rsplit("/", 1)[1]
    worker_dbs = _create_worker_databases(test_db_url, source_db_name, len(files))
    ports = _allocate_ports(len(files))
    result_dir = Path(tempfile.mkdtemp(prefix="e2e_parallel_"))

    wall_start = time.monotonic()
    results: list[tuple[Path, int, float]] = []
    all_passed = False

    try:
        if fail_fast:
            results = await _run_fail_fast_workers(
                files, ports, worker_dbs, result_dir, user_args
            )
        else:
            results = await _run_all_workers(
                files, ports, worker_dbs, result_dir, user_args
            )

        all_passed = await _finalise_parallel_results(
            results,
            wall_start,
            test_db_url,
            source_db_name,
            result_dir,
            user_args,
        )
        return 0 if all_passed else 1

    finally:
        _cleanup_parallel_results(all_passed, worker_dbs, result_dir, results)
