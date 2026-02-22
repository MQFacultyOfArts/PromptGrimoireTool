# Parallel E2E Test Runner - Phase 3: Parallel Orchestrator

**Goal:** Create the async orchestrator function that coordinates N workers, manages database lifecycle, merges results, and reports status.

**Architecture:** `_run_parallel_e2e()` is the top-level async function called from `test_e2e()` via `asyncio.run()`. It discovers test files, clones N worker databases from the branch test DB, allocates N ports, launches N `_run_e2e_worker` coroutines concurrently, merges JUnit XML results, prints a summary, and cleans up. `asyncio.gather()` for run-all mode; `asyncio.as_completed()` with cancellation for fail-fast mode.

**Tech Stack:** asyncio (stdlib), junitparser (new dev dependency), Rich Console (existing)

**Scope:** 3 of 5 phases from original design (phase 3)

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### parallel-e2e-runner-95.AC1: Parallel execution launches isolated workers
- **parallel-e2e-runner-95.AC1.1 Success:** `uv run test-e2e --parallel` discovers all `tests/e2e/test_*.py` files and launches one server+pytest pair per file
- **parallel-e2e-runner-95.AC1.2 Success:** Each server runs on a distinct port, each backed by its own PostgreSQL database
- **parallel-e2e-runner-95.AC1.3 Success:** All workers run concurrently (wall-clock time approximately equals slowest single file, not sum of all)
- **parallel-e2e-runner-95.AC1.4 Failure:** If a server fails to start, all other servers are killed, worker databases dropped, and exit code is non-zero

### parallel-e2e-runner-95.AC3: Result aggregation
- **parallel-e2e-runner-95.AC3.1 Success:** Per-worker JUnit XML files are merged into a single report
- **parallel-e2e-runner-95.AC3.2 Success:** Exit code is 0 only when all workers pass (exit code 5 "no tests collected" treated as pass)
- **parallel-e2e-runner-95.AC3.3 Success:** Summary output shows per-file pass/fail status and duration

### parallel-e2e-runner-95.AC4: Database lifecycle
- **parallel-e2e-runner-95.AC4.1 Success:** Worker databases are created automatically via `CREATE DATABASE ... TEMPLATE` from the branch test database
- **parallel-e2e-runner-95.AC4.2 Success:** Worker databases are dropped after successful test completion
- **parallel-e2e-runner-95.AC4.3 Success:** On test failure, worker databases are preserved and connection strings logged for debugging

### parallel-e2e-runner-95.AC5: Process cleanup
- **parallel-e2e-runner-95.AC5.1 Success:** All server process groups are terminated in teardown (no orphan processes)
- **parallel-e2e-runner-95.AC5.2 Success:** Fail-fast mode (test-e2e-debug) kills remaining workers on first failure
- **parallel-e2e-runner-95.AC5.3 Edge:** `-k` filter producing no matching tests in a file results in exit code 5, treated as pass

---

## Reference Files

The executor and its subagents should read these files for context:

- `src/promptgrimoire/cli.py` — existing CLI structure, `_pre_test_db_cleanup()`, `test_e2e()`, Rich console patterns
- `src/promptgrimoire/db/bootstrap.py` — `clone_database()`, `drop_database()`, `terminate_connections()` (added in Phase 1)
- `src/promptgrimoire/config.py` — `_suffix_db_url()`, `Settings` class, `get_settings()`
- `CLAUDE.md` — project conventions
- `.ed3d/implementation-plan-guidance.md` — UAT requirements, test commands
- `docs/implementation-plans/2026-02-20-parallel-e2e-runner-95/phase_02.md` — `_run_e2e_worker()` and `_allocate_ports()` signatures

---

## Codebase Verification Findings

- 16 E2E test files in `tests/e2e/test_*.py` (16 workers in parallel mode)
- `junitparser` is NOT a dependency yet. Must be added as dev dependency.
- `console = Console()` is module-level singleton at cli.py:24
- `asyncio.run()` bridge pattern used in cli.py: define local `async def _run()`, call `asyncio.run(_run())` from sync entrypoint. Used in `manage_users()`, `set_admin()`, `seed_data()`.
- No Rich Live or Progress usage exists in the codebase.
- `tempfile.TemporaryDirectory()` context manager pattern used in parsers/rtf.py.
- `_pre_test_db_cleanup()` runs Alembic migrations + truncation on branch test DB. Must run once before cloning.

---

<!-- START_TASK_1 -->
### Task 1: Add junitparser dev dependency

**Verifies:** None (infrastructure)

**Files:**
- Modify: `pyproject.toml` (add to `[dependency-groups] dev`)

**Implementation:**

Run: `uv add --dev junitparser`

This adds junitparser to the dev dependency group in pyproject.toml and updates uv.lock.

**Verification:**
Run: `uv run python -c "from junitparser import JUnitXml; print('junitparser OK')"`
Expected: `junitparser OK`

**Commit:** `deps: add junitparser for parallel E2E JUnit XML merging`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: `_run_parallel_e2e()` orchestrator — setup and worker launch

**Verifies:** parallel-e2e-runner-95.AC1.1, parallel-e2e-runner-95.AC1.2, parallel-e2e-runner-95.AC4.1

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add async function after `_run_e2e_worker`)

**Implementation:**

Add `_run_parallel_e2e()` as the orchestrator function. Full signature:

```python
async def _run_parallel_e2e(
    user_args: list[str],
    fail_fast: bool = False,
) -> int:
```

Returns the aggregate exit code (0 = all pass, non-zero = at least one failure).

**Phase 1: Setup (sequential, fast)**

1. **Discover test files:** `sorted(Path("tests/e2e").glob("test_*.py"))`. Print count: `console.print(f"[blue]Found {len(files)} test files[/]")`.

2. **Run _pre_test_db_cleanup():** Call it once to run Alembic migrations and truncate the branch test database. This prepares the template for cloning.

3. **Create worker databases:** For each worker `i`, call `clone_database(source_url=test_db_url, target_name=f"{source_db_name}_w{i}")` from `bootstrap.py` (Phase 1). The `source_db_name` is extracted from `test_db_url`. Store the list of `(worker_db_url, worker_db_name)` tuples. This is sequential because PostgreSQL requires no connections on the template during cloning.

4. **Allocate ports:** Call `_allocate_ports(len(files))` (Phase 2).

5. **Create result directory:** `tempfile.mkdtemp(prefix="e2e_parallel_")` for JUnit XML and log files. Store the path for cleanup in teardown.

**Phase 2: Run (concurrent)**

For run-all mode (`fail_fast=False`):
- Create coroutines: `[_run_e2e_worker(file, port, db_url, result_dir, user_args) for file, port, db_url in zip(files, ports, worker_db_urls)]`
- Run with `results = await asyncio.gather(*coros, return_exceptions=True)`
- Collect `(file, exit_code, duration)` tuples. If any coroutine raised an exception, treat it as exit code 1 and log the exception.

For fail-fast mode (`fail_fast=True`):
- Create `asyncio.Task` objects for each coroutine
- Use `asyncio.as_completed(tasks)` to process completions
- On first non-pass result (exit code not 0 and not 5), cancel remaining tasks
- Cancelled tasks should handle `asyncio.CancelledError` gracefully in their `finally` blocks (the worker's process group cleanup runs regardless)

**Phase 3: Teardown (always runs, try/finally)**

See Task 3 for teardown, JUnit merge, summary, and database cleanup.

**Error handling for setup failures (AC1.4):**
- If any `clone_database()` fails, drop all already-created worker databases and re-raise.
- If any server fails to start (worker raises RuntimeError during health check), the orchestrator catches it in the gather results and proceeds to teardown.

**No tests for this task.** The orchestrator is infrastructure. Verification is operational via Phase 4.

**Commit:** Do not commit yet. Combine with Task 3.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `_run_parallel_e2e()` — teardown, JUnit merge, summary output

**Verifies:** parallel-e2e-runner-95.AC3.1, parallel-e2e-runner-95.AC3.2, parallel-e2e-runner-95.AC3.3, parallel-e2e-runner-95.AC4.2, parallel-e2e-runner-95.AC4.3, parallel-e2e-runner-95.AC5.3

**Files:**
- Modify: `src/promptgrimoire/cli.py` (complete `_run_parallel_e2e` from Task 2)

**Implementation:**

Complete the teardown phase of `_run_parallel_e2e()`.

**JUnit XML merging (AC3.1):**
- Collect all `*.xml` files from `result_dir` using `Path(result_dir).glob("*.xml")`
- Merge using junitparser: iterate files, `JUnitXml.fromfile(str(path))`, accumulate with `merged += xml`
- Write merged result to `result_dir / "combined.xml"` with `merged.write(str(output), pretty=True)`
- Print path to merged report

**Exit code computation (AC3.2, AC5.3):**
- For each worker result `(file, exit_code, duration)`:
  - Exit code 0 = pass
  - Exit code 5 = pass (no tests collected, e.g. `-k` filter matched nothing)
  - Any other non-zero = failure
- Aggregate exit code: 0 if all workers pass, 1 if any worker failed

**Summary output (AC3.3):**

Print a Rich table showing per-file results:

```
 File                              Result   Duration
 test_law_student.py               PASS     42.3s
 test_annotation_highlight_api.py  FAIL     18.7s
 test_browser_gate.py              PASS     5.2s
 ...
 ─────────────────────────────────────────────────
 16 files: 15 passed, 1 failed      Total: 45.1s
```

Use `rich.table.Table` (already imported in cli.py functions). Colour PASS green, FAIL red.
Show total wall-clock time (time from orchestrator start to end, not sum of worker durations).

**Database cleanup (AC4.2, AC4.3):**
- If all workers passed: drop all worker databases using `drop_database()` from Phase 1.
- If any worker failed: preserve ALL worker databases (not just the failing one) and print connection strings to console so the developer can inspect state. Format: `console.print(f"[yellow]Preserved worker DB: {db_url}[/]")`
- Database cleanup is in the `finally` block, so it runs even if the orchestrator itself crashes.

**Log file locations:**
- On failure, print the path to each failing worker's log file: `console.print(f"[red]Log: {result_dir}/test-e2e-{stem}.log[/]")`

**Result directory cleanup:**
- If all workers passed: remove the temp directory with `shutil.rmtree(result_dir)` after printing the summary (JUnit XML has been merged and printed, logs are no longer needed).
- If any worker failed: preserve the result directory and print its path so log files can be inspected: `console.print(f"[yellow]Logs preserved at: {result_dir}[/]")`

**Verification:**
Run: `uv run ruff check src/promptgrimoire/cli.py && uv run ruff format src/promptgrimoire/cli.py`
Expected: No lint or format errors

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add _run_parallel_e2e() orchestrator for parallel E2E test runner`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Verify orchestrator imports and types

**Verifies:** None (operational verification)

**Files:** None (verification only)

**Implementation:**

Verify the orchestrator code is syntactically correct and all imports resolve.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run python -c "from promptgrimoire.cli import _run_parallel_e2e; print('orchestrator import OK')"`
Expected: `orchestrator import OK`

**Commit:** No commit needed (verification only)
<!-- END_TASK_4 -->
