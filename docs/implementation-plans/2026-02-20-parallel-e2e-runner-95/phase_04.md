# Parallel E2E Test Runner - Phase 4: CLI Integration

**Goal:** Wire the parallel orchestrator into `test_e2e()`, remove the xdist codepath from E2E, and keep serial modes unchanged.

**Architecture:** `test_e2e()` gains a new `--parallel` codepath that calls `asyncio.run(_run_parallel_e2e(...))` instead of passing xdist args to `_run_pytest()`. The xdist args (`-n auto --dist=loadfile`) are removed from `test_e2e()` only — pytest-xdist remains a dependency (used by `test_debug` and `test_all`). Serial mode and `test_e2e_debug()` are unchanged. Output is simple: tail worker log files to console, print summary at end.

**Tech Stack:** asyncio (stdlib), Rich Console (existing)

**Scope:** 4 of 5 phases from original design (phase 4)

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### parallel-e2e-runner-95.AC2: Serial mode unchanged
- **parallel-e2e-runner-95.AC2.1 Success:** `uv run test-e2e` (no flags) runs single-server serial mode exactly as before
- **parallel-e2e-runner-95.AC2.2 Success:** `uv run test-e2e-debug` runs single-server with `--lf` and `-x` exactly as before

### parallel-e2e-runner-95.AC5: Process cleanup (partial — fail-fast wiring)
- **parallel-e2e-runner-95.AC5.2 Success:** Fail-fast mode (test-e2e-debug) kills remaining workers on first failure

---

## Reference Files

The executor and its subagents should read these files for context:

- `src/promptgrimoire/cli.py` — `test_e2e()` at lines 727-807, `test_e2e_debug()` at lines 810-856, `_run_pytest()` at lines 123-200
- `docs/implementation-plans/2026-02-20-parallel-e2e-runner-95/phase_02.md` — `_run_e2e_worker()` signature
- `docs/implementation-plans/2026-02-20-parallel-e2e-runner-95/phase_03.md` — `_run_parallel_e2e()` signature
- `CLAUDE.md` — project conventions
- `.ed3d/implementation-plan-guidance.md` — UAT requirements, test commands

---

## Codebase Verification Findings

- `test_e2e()` at cli.py:727-807: parses `--parallel` and `--py-spy` from `sys.argv` manually, removes them. `--parallel` currently adds `["-n", "auto", "--dist=loadfile"]` to pytest args. Serial mode adds `["-x"]`.
- `test_e2e_debug()` at cli.py:810-856: no `--parallel` handling. Always serial with `--lf -x --tb=long -v`.
- `_run_pytest()` calls `_pre_test_db_cleanup()` internally (line 129). `test_e2e()` also calls `_pre_test_db_cleanup()` directly (line 766). Double-call in serial mode. The parallel orchestrator should call it once before cloning.
- pytest-xdist CANNOT be removed as a dependency — `test_debug` and `test_all` use `-n auto --dist=worksteal`.
- `user_args = sys.argv[1:]` inside `_run_pytest()` — remaining args after `--parallel`/`--py-spy` removal.
- No `sys.stdout.isatty()` usage in the codebase. User confirmed: just tail the logs, no Rich Live needed.

---

<!-- START_TASK_1 -->
### Task 1: Modify `test_e2e()` to use parallel orchestrator

**Verifies:** parallel-e2e-runner-95.AC2.1 (serial unchanged), parallel-e2e-runner-95.AC5.2 (fail-fast wiring)

**Files:**
- Modify: `src/promptgrimoire/cli.py` (rewrite the `--parallel` branch of `test_e2e()`)

**Implementation:**

Modify `test_e2e()` so the `--parallel` branch calls `asyncio.run(_run_parallel_e2e(...))` instead of passing xdist args to `_run_pytest()`.

The key change is: when `parallel` is True, skip the single-server setup (port allocation, `_start_e2e_server`, `_stop_e2e_server`) and instead call the orchestrator which handles its own servers.

Also add a `--fail-fast` flag for parallel mode. This wires `_run_parallel_e2e(fail_fast=True)`, which uses `asyncio.as_completed()` to kill remaining workers on first failure (AC5.2). The design's AC5.2 references "test-e2e-debug" but that stays serial. Instead, `--fail-fast` is an opt-in flag on `test-e2e --parallel`.

**Current structure (to be modified):**
```python
def test_e2e() -> None:
    # ... parse --parallel, --py-spy from sys.argv ...
    _pre_test_db_cleanup()
    # ... allocate port, start server ...
    os.environ["E2E_BASE_URL"] = url
    if parallel:
        mode_args = ["-n", "auto", "--dist=loadfile"]  # REMOVE THIS
    else:
        mode_args = ["-x"]
    try:
        _run_pytest(...)
    finally:
        _stop_e2e_server(server_process)
```

**New structure:**
```python
def test_e2e() -> None:
    # ... parse --parallel, --py-spy, --fail-fast from sys.argv ...

    from promptgrimoire.config import get_settings
    get_settings()

    if parallel:
        # Parallel mode: orchestrator handles everything
        user_args = sys.argv[1:]
        exit_code = asyncio.run(
            _run_parallel_e2e(user_args=user_args, fail_fast=fail_fast)
        )
        sys.exit(exit_code)

    # Serial mode: unchanged from here down
    _pre_test_db_cleanup()
    # ... allocate port, start server, _run_pytest with ["-x"], finally stop server ...
```

Parse `--fail-fast` the same way as `--parallel`: check `sys.argv`, remove if present. Only meaningful in parallel mode — in serial mode, `-x` already provides fail-fast semantics.

**Important details:**
- The orchestrator calls `_pre_test_db_cleanup()` internally (in Phase 3's Task 2), so serial mode's call stays but parallel mode doesn't double-call.
- `user_args = sys.argv[1:]` captures remaining args after `--parallel` removal. These are forwarded to each pytest subprocess by the orchestrator.
- `sys.exit(exit_code)` ensures the CLI exits with the aggregate exit code from the orchestrator.
- `--py-spy` is NOT supported in parallel mode (it attaches to a single server PID). If both `--parallel` and `--py-spy` are specified, print a warning and ignore `--py-spy`, or raise an error. Suggest printing a warning: `console.print("[yellow]--py-spy is not supported in parallel mode, ignoring[/]")`
- The `get_settings()` call stays before the branch — it eagerly loads `.env` for both modes.

**Testing:**

This is a CLI integration change. Verification is operational:
- `uv run test-e2e --help` should still work (no crash)
- `uv run test-e2e` (no flags) should run serial mode exactly as before

Full E2E verification of parallel mode happens in the UAT step.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run ruff check src/promptgrimoire/cli.py && uv run ruff format src/promptgrimoire/cli.py`
Expected: No lint or format errors

**Commit:** `feat: wire parallel orchestrator into test_e2e --parallel`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify serial modes are unchanged

**Verifies:** parallel-e2e-runner-95.AC2.1, parallel-e2e-runner-95.AC2.2

**Files:** None (verification only)

**Implementation:**

Verify that the serial modes still work exactly as before:

1. **`uv run test-e2e` (serial mode):** Should start one server, run all E2E tests with `-x` (fail-fast), stop server. No behavioural change.

2. **`uv run test-e2e-debug` (debug mode):** Should start one server, run with `--lf -x --tb=long -v`, stop server. No behavioural change.

The `test_e2e_debug()` function is NOT modified in this phase — it was confirmed unchanged at cli.py:810-856.

**Verification:**
Run: `uv run test-e2e -k test_browser_gate` (serial, single quick test)
Expected: Server starts, test runs, server stops. Exit code 0 if test passes.

Run: `uv run test-e2e-debug -k test_browser_gate` (debug, single quick test)
Expected: Server starts, test runs with verbose output, server stops.

**Commit:** No commit needed (verification only)
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: UAT — parallel mode end-to-end

**Verifies:** All AC1, AC3, AC4, AC5 criteria (end-to-end validation)

**Files:** None (verification only)

**Implementation:**

This is the full end-to-end UAT for the parallel orchestrator.

**UAT Steps:**

1. Run: `uv run test-e2e --parallel`
2. Verify: Console output shows "Found N test files" (expect 16)
3. Verify: Console output shows worker databases being created
4. Verify: Console output shows per-file results (PASS/FAIL with duration)
5. Verify: Console output shows summary line with counts and total wall-clock time
6. Verify: Wall-clock time is roughly equal to the slowest individual test file, NOT the sum of all
7. Verify: Worker databases are cleaned up (check with `psql -l | grep _w`)
8. Verify: No orphan server processes remain (check with `ps aux | grep promptgrimoire`)

**With -k filter:**
1. Run: `uv run test-e2e --parallel -k test_browser_gate`
2. Verify: Most workers show exit code 5 (no tests collected), treated as pass
3. Verify: Only the matching test file actually runs tests
4. Verify: Overall exit code is 0

**Fail-fast mode (AC5.2):**
1. Run: `uv run test-e2e --parallel --fail-fast`
2. If any test file fails, verify: remaining workers are killed promptly (not waiting for all to finish)
3. Verify: Summary shows which file failed and which were cancelled
4. Verify: Exit code is non-zero

**Failure handling (AC1.4):**
1. Deliberately cause a server startup failure. The simplest approach: temporarily modify `_E2E_SERVER_SCRIPT` to exit immediately for one worker, or pass an invalid `DATABASE__URL` to one worker. Alternatively, block a port that a worker will try to bind to.
2. Verify: The orchestrator detects the startup failure
3. Verify: All other running servers are killed (check `ps aux | grep promptgrimoire`)
4. Verify: Worker databases are dropped (check `psql -l | grep _w`)
5. Verify: Exit code is non-zero
6. Revert the deliberate failure after testing.

Note: This is difficult to automate reliably. Code review of the `try/finally` structure in `_run_e2e_worker` and `_run_parallel_e2e` provides additional confidence. The health-check timeout (15s) and process group kill (`os.killpg`) are the key mechanisms.

**Commit:** No commit needed (UAT)
<!-- END_TASK_3 -->
