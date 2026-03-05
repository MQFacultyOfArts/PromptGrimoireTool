# CLI Typer Migration Implementation Plan — Phase 5

**Goal:** Extract E2E test commands and all parallel worker orchestration into `e2e.py`, reducing cognitive complexity of `_run_all_workers` (18→≤15), `_run_fail_fast_workers` (19→≤15), and `_retry_parallel_failures` (23→≤15).

**Architecture:** `e2e.py` contains 4 Typer commands, 22+ helper functions, the `_E2E_SERVER_SCRIPT` constant (~318 lines), and all parallel/retry orchestration. Complexity is reduced by extracting `_resolve_completed_task()`, `_report_worker_progress()`, `_cancel_pending_tasks()`, `_prepare_retry_databases()`, `_classify_retry_results()`, and `_cleanup_retry_databases()`. Server management functions (`_start_e2e_server`, `_stop_e2e_server`) are also exported for `docs.py` to import.

**Tech Stack:** Typer, asyncio, Rich Console, subprocess, py-spy

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-03-02. Confirmed complexities: `_run_all_workers`=18, `_run_fail_fast_workers`=19, `_retry_parallel_failures`=23.

---

## Acceptance Criteria Coverage

### cli-typer-211.AC2: Typer Framework
- **cli-typer-211.AC2.1 Success:** All commands use `typer.Argument()` / `typer.Option()` for parameter declaration
- **cli-typer-211.AC2.4 Edge:** Pytest passthrough args (e.g., `-k test_foo -x`) are forwarded correctly via `ctx.args`

### cli-typer-211.AC4: Complexity Compliance
- **cli-typer-211.AC4.1 Success:** `complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` reports zero failures
- **cli-typer-211.AC4.3 Success:** `_run_all_workers` cognitive complexity ≤ 15
- **cli-typer-211.AC4.4 Success:** `_run_fail_fast_workers` cognitive complexity ≤ 15
- **cli-typer-211.AC4.5 Success:** `_retry_parallel_failures` cognitive complexity ≤ 15

### cli-typer-211.AC5: Tests Pass and Expand
- **cli-typer-211.AC5.2 Success:** `test_cli_parallel.py` passes with import from `promptgrimoire.cli.e2e`

---

<!-- START_TASK_1 -->
### Task 1: Populate cli/e2e.py with E2E Commands, Helpers, and Server Script

**Verifies:** cli-typer-211.AC2.1, cli-typer-211.AC2.4, cli-typer-211.AC5.2

**Files:**
- Modify: `src/promptgrimoire/cli/e2e.py` (replace placeholder)

**Implementation:**

Move ALL E2E-related code from `cli_legacy.py` into `e2e.py`. This is a large move — approximately 1300 lines.

**String constant (copy verbatim):**
- `_E2E_SERVER_SCRIPT` (lines 500-817, 318 lines)

**Helper functions (copy verbatim, adjust imports to use `_shared`):**

Port allocation and worker infrastructure:
- `_allocate_ports` (lines 820-843)
- `_filter_junitxml_args` (lines 846-860)
- `_run_e2e_worker` (lines 863-966, async)
- `_worker_status_label` (lines 969-975)
- `_print_parallel_summary` (lines 978-995)
- `_merge_junit_xml` (lines 997-1011)

Parallel orchestration (to be refactored in Task 2):
- `_run_all_workers` (lines 1013-1055, async)
- `_resolve_failed_task_file` (lines 1058-1073)
- `_run_fail_fast_workers` (lines 1076-1136, async)
- `_cleanup_parallel_results` (lines 1139-1165)
- `_retry_parallel_failures` (lines 1168-1252, async)

Database and server management:
- `_create_worker_databases` (lines 1255-1294)
- `_run_parallel_e2e` (lines 1297-1384)
- `_start_e2e_server` (lines 1385-1425)
- `_stop_e2e_server` (lines 1428-1435)

Profiling:
- `_check_ptrace_scope` (lines 1438-1449)
- `_start_pyspy` (lines 1452-1482)
- `_stop_pyspy` (lines 1485-1492)

Retry and changed detection:
- `_get_last_failed` (lines 1495-1503)
- `_retry_e2e_tests_in_isolation` (lines 1506-1586)

**Typer commands** (4 commands with pytest passthrough):

```python
@e2e_app.command(
    "run",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def run(
    ctx: typer.Context,
    parallel: bool = typer.Option(False, "--parallel", help="Run with xdist parallelism"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first failure (parallel only)"),
    py_spy: bool = typer.Option(False, "--py-spy", help="Profile with py-spy"),
) -> None:
    """Run E2E tests (serial fail-fast by default)."""
    ...
```

Similarly for `slow`, `noretry`, `changed` commands.

**Import shared infrastructure:**
```python
from promptgrimoire.cli._shared import console, _pre_test_db_cleanup
```

**Update `docs.py`** to import server functions from `e2e.py` instead of `cli_legacy`:
```python
# In docs.py, change:
from promptgrimoire.cli_legacy import _start_e2e_server, _stop_e2e_server
# To:
from promptgrimoire.cli.e2e import _start_e2e_server, _stop_e2e_server
```

Similarly update `test_make_docs.py` patches.

**Verification:**

Run: `uv run grimoire e2e run --help`
Expected: Shows E2E options (--parallel, --fail-fast, --py-spy).

**Commit:** `feat: populate e2e.py with all E2E commands and orchestration`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Reduce Complexity of Three E2E Orchestration Functions

**Verifies:** cli-typer-211.AC4.3, cli-typer-211.AC4.4, cli-typer-211.AC4.5

**Files:**
- Modify: `src/promptgrimoire/cli/e2e.py`

**Implementation:**

**Reduce `_run_all_workers` (18 → ≤15):**

Extract `_resolve_completed_task(done_future, task_map, files)` to handle the await-and-match-exception logic that adds complexity. Extract `_report_worker_progress(file, exit_code, duration, done_count, total)` to handle the formatted output.

**Reduce `_run_fail_fast_workers` (19 → ≤15):**

Extract `_cancel_pending_tasks(tasks)` to handle the cancellation loop and cleanup. This function iterates over tasks, cancels undone ones, and suppresses `CancelledError`. Also reuse `_resolve_completed_task` and `_report_worker_progress` from above.

**Reduce `_retry_parallel_failures` (23 → ≤15):**

Extract three helpers:
1. `_prepare_retry_databases(failed_files, template_db_url, source_db_name)` — handles drop-stale + clone-fresh loop, returns list of `(db_url, db_name)` tuples
2. `_classify_retry_results(exit_code, file)` — returns whether a file is "flaky" (exit 0 or 5) or "genuine failure"
3. `_cleanup_retry_databases(retry_dbs, template_db_url)` — drops all retry databases (the `finally` cleanup)

The refactored `_retry_parallel_failures` becomes a simple loop calling these three helpers.

**Verification:**

Run: `uv run complexipy src/promptgrimoire/cli/e2e.py --max-complexity-allowed 15`
Expected: Zero failures. All three functions ≤ 15.

**Commit:** `refactor: reduce E2E orchestration complexity to ≤15`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update test_cli_parallel.py Import

**Verifies:** cli-typer-211.AC5.2

**Files:**
- Modify: `tests/unit/test_cli_parallel.py`

**Implementation:**

Change the import at line 10:
```python
# From:
from promptgrimoire.cli import _allocate_ports
# To:
from promptgrimoire.cli.e2e import _allocate_ports
```

**Testing:**

Tests must verify:
- cli-typer-211.AC5.2: All 3 test_cli_parallel tests pass with import from `promptgrimoire.cli.e2e`

**Verification:**

Run: `uv run pytest tests/unit/test_cli_parallel.py -v`
Expected: All 3 tests pass.

**Commit:** `test: update test_cli_parallel.py import to cli.e2e`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Remove Migrated E2E Functions from cli_legacy.py

**Files:**
- Modify: `src/promptgrimoire/cli_legacy.py`
- Modify: `pyproject.toml`

**Implementation:**

1. In `pyproject.toml`, remove these entry points:
   - `test-e2e = "promptgrimoire.cli_legacy:test_e2e"`
   - `test-e2e-slow = "promptgrimoire.cli_legacy:test_e2e_slow"`
   - `test-e2e-noretry = "promptgrimoire.cli_legacy:test_e2e_noretry"`
   - `test-e2e-changed = "promptgrimoire.cli_legacy:test_e2e_changed"`

2. In `cli_legacy.py`, delete ALL remaining functions that were migrated to `e2e.py`.

3. Verify zero remaining imports of `cli_legacy`:
   ```bash
   grep -r "cli_legacy" src/ tests/
   ```
   Expected: Zero results. If any remain, update them before proceeding.

4. If zero remaining references, delete the file:
   ```bash
   git rm src/promptgrimoire/cli_legacy.py
   ```
   If references remain, do NOT delete — fix the imports first, then delete.

5. Run `uv sync`.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass via new grimoire commands.

Run: `uv run complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15`
Expected: Zero failures across entire cli/ package.

**Commit:** `refactor: delete cli_legacy.py — all functions migrated to cli/ package`
<!-- END_TASK_4 -->

## UAT Steps

1. [ ] Run `uv run grimoire e2e run --help` — shows E2E options
2. [ ] Run `uv run grimoire e2e slow --help` — shows slow E2E help
3. [ ] Run `uv run grimoire e2e noretry --help` — shows noretry help
4. [ ] Run `uv run grimoire e2e changed --help` — shows changed help
5. [ ] Run `uv run complexipy src/promptgrimoire/cli/e2e.py --max-complexity-allowed 15` — zero failures
6. [ ] Run `uv run pytest tests/unit/test_cli_parallel.py -v` — all 3 tests pass
7. [ ] Run `uv run grimoire test all` — full suite passes

## Evidence Required

- [ ] complexipy output showing all three functions ≤ 15
- [ ] `grep -r "cli_legacy" src/ tests/` returning nothing (no remaining references)
