"""Serial retry logic for failed E2E tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from promptgrimoire.cli._shared import console


def _get_last_failed() -> list[str]:
    """Read failed test node IDs from pytest's lastfailed cache."""
    cache_path = Path(".pytest_cache/v/cache/lastfailed")
    if not cache_path.exists():
        return []
    data = json.loads(cache_path.read_text())
    return [k for k, v in data.items() if v]


def _retry_e2e_tests_in_isolation(log_path: Path) -> int:
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

    with log_path.open("a") as log_file:
        log_file.write(
            f"\n{'=' * 60}\n"
            f"Isolation retry: {len(failed_tests)} test(s)\n"
            f"{'=' * 60}\n\n"
        )

        for i, node_id in enumerate(failed_tests, 1):
            cmd = [
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

            log_file.write(f"--- Retry {i}/{len(failed_tests)}: {node_id} ---\n")
            log_file.flush()

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

            log_file.write(result.stdout)
            log_file.write(f"Exit code: {result.returncode}\n\n")
            log_file.flush()

            if result.returncode in (0, 5):
                flaky.append(node_id)
                console.print(
                    f"  [{i}/{len(failed_tests)}] {node_id}: "
                    f"[yellow]FLAKY[/] (passed in isolation)"
                )
            else:
                genuine_failures.append(node_id)
                console.print(
                    f"  [{i}/{len(failed_tests)}] {node_id}: "
                    f"[red]FAILED[/] (genuine failure)"
                )

    console.print()
    if flaky:
        console.print(
            f"[yellow]Flaky ({len(flaky)}):[/] passed when re-run in isolation"
        )
        for t in flaky:
            console.print(f"  {t}")
    if genuine_failures:
        console.print(f"[red]Genuine failures ({len(genuine_failures)}):[/]")
        for t in genuine_failures:
            console.print(f"  {t}")

    return 1 if genuine_failures else 0
