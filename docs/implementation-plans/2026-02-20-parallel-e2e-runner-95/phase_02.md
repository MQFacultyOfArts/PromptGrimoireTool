# Parallel E2E Test Runner - Phase 2: Async Worker Coroutine

**Goal:** Create the async coroutine that manages one server+pytest pair lifecycle, and a port allocation utility. These are the building blocks for the parallel orchestrator in Phase 3.

**Architecture:** `_run_e2e_worker()` is an async coroutine using `asyncio.create_subprocess_exec` with `start_new_session=True` for process group isolation. It starts a server, health-checks it, runs pytest with per-file output, and kills the server process group in a `finally` block. `_allocate_ports()` binds N sockets simultaneously to get N distinct ports.

**Tech Stack:** asyncio (stdlib), os.killpg (stdlib), socket (stdlib)

**Scope:** 2 of 5 phases from original design (phase 2)

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase partially implements (building blocks, full verification in Phase 3):

### parallel-e2e-runner-95.AC1: Parallel execution launches isolated workers
- **parallel-e2e-runner-95.AC1.2 Success:** Each server runs on a distinct port, each backed by its own PostgreSQL database

### parallel-e2e-runner-95.AC5: Process cleanup
- **parallel-e2e-runner-95.AC5.1 Success:** All server process groups are terminated in teardown (no orphan processes)

---

## Reference Files

The executor and its subagents should read these files for context:

- `src/promptgrimoire/cli.py` — contains `_start_e2e_server()`, `_stop_e2e_server()`, `_E2E_SERVER_SCRIPT`, `_run_pytest()`, `test_e2e()` to understand existing patterns
- `src/promptgrimoire/export/pdf.py` — contains existing `asyncio.create_subprocess_exec` usage pattern
- `tests/conftest.py` — contains `app_server` fixture showing E2E_BASE_URL check
- `tests/e2e/conftest.py` — contains fixtures reading E2E_BASE_URL and DATABASE__URL from env
- `CLAUDE.md` — project conventions
- `.ed3d/implementation-plan-guidance.md` — UAT requirements, test commands

---

## Codebase Verification Findings

- `_start_e2e_server(port: int) -> subprocess.Popen[bytes]` exists at cli.py:612-653. Uses sync `subprocess.Popen`, does NOT use `start_new_session=True`. Health-check uses socket polling for 15s.
- `_stop_e2e_server(process)` at cli.py:656-663 only calls `process.terminate()`, no `os.killpg`. 5s grace then SIGKILL.
- `_E2E_SERVER_SCRIPT` at cli.py:298-609 receives port via `sys.argv[1]`, DATABASE__URL from caller's environment.
- `_run_pytest()` at cli.py:123-200 calls `sys.exit()` at the end, so cannot be reused for parallel workers. Phase 2's worker invokes pytest as a subprocess directly.
- Server log is hardcoded to `test-e2e-server.log` (single file). Parallel workers need per-worker logs.
- No existing `start_new_session` or `os.killpg` usage in the codebase.
- `asyncio.create_subprocess_exec` is used in export/pdf.py, export/pandoc.py.

---

<!-- START_TASK_1 -->
### Task 1: `_allocate_ports()` utility

**Verifies:** parallel-e2e-runner-95.AC1.2 (partial: distinct ports)

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add function, around line 610, before `_start_e2e_server`)
- Test: `tests/unit/test_cli_parallel.py` (create new file)

**Implementation:**

Add `_allocate_ports(n: int) -> list[int]` to `cli.py`.

Behaviour:
1. Create `n` sockets with `socket.socket(AF_INET, SOCK_STREAM)`.
2. Bind each to `("", 0)` to let the OS allocate a free port.
3. Enable `SO_REUSEADDR` on each socket.
4. Read port from `sock.getsockname()[1]` for all sockets.
5. Close all sockets together (hold all open simultaneously to guarantee uniqueness).
6. Return list of ports.

The key insight is holding all sockets open simultaneously. If you open-read-close one at a time, two calls might return the same port. The existing `test_e2e()` has a TOCTOU window (binds, reads, closes, then starts server); this function avoids that by allocating all at once.

Note: There is still a TOCTOU window between releasing the sockets and the server binding to the port, but this is inherent to the approach and acceptable.

**Testing:**

Unit test:
- Call `_allocate_ports(5)`, verify 5 distinct ports returned, all > 0
- Call `_allocate_ports(1)`, verify single port returned
- Call `_allocate_ports(0)`, verify empty list returned

**Verification:**
Run: `uv run pytest tests/unit/test_cli_parallel.py -v`
Expected: All tests pass

**Commit:** `feat: add _allocate_ports() utility for parallel E2E`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: `_run_e2e_worker()` async coroutine: server lifecycle

**Verifies:** parallel-e2e-runner-95.AC5.1 (partial: process group cleanup)

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add async function after `_allocate_ports`)

**Implementation:**

Add `_run_e2e_worker()` as an async coroutine. This task focuses on the server subprocess lifecycle and process group management. The full signature:

```python
async def _run_e2e_worker(
    test_file: Path,
    port: int,
    db_url: str,
    result_dir: Path,
    user_args: list[str],
) -> tuple[Path, int, float]:
```

Returns `(test_file, exit_code, duration_seconds)`.

**Server subprocess setup:**
- Build `clean_env` dict from `os.environ`, stripping keys containing `"PYTEST"` or `"NICEGUI"` (same pattern as existing `_start_e2e_server`)
- Set `DATABASE__URL` to the worker's `db_url` in the env dict
- Open a log file at `result_dir / f"test-e2e-{test_file.stem}.log"` for writing
- Start server with `asyncio.create_subprocess_exec(sys.executable, "-c", _E2E_SERVER_SCRIPT, str(port), stdout=log_fh, stderr=STDOUT, env=clean_env, start_new_session=True)`
- `start_new_session=True` makes the server a process group leader

**Health check (async):**
- Poll `asyncio.open_connection("localhost", port)` in a loop with 0.1s sleep, 15s timeout
- On connection success, close the reader/writer immediately
- On server crash (returncode is not None), raise a RuntimeError with log file path
- On timeout, raise a RuntimeError with log file path

**Process group cleanup (in `finally` block):**
- `os.killpg(os.getpgid(server.pid), signal.SIGTERM)`
- `await asyncio.wait_for(server.wait(), timeout=5)` for graceful shutdown
- If timeout: `os.killpg(os.getpgid(server.pid), signal.SIGKILL)`
- Wrap in try/except ProcessLookupError (process may already be dead)
- Close the log file handle

**No tests for this task.** The coroutine is async subprocess orchestration code. It will be verified by the import check in Task 4, and fully exercised in Phase 3/4.

**Commit:** Do not commit yet. Combine with Task 3.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `_run_e2e_worker()`: pytest subprocess and result collection

**Verifies:** parallel-e2e-runner-95.AC1.2 (partial: per-worker database), parallel-e2e-runner-95.AC5.1 (partial: cleanup)

**Files:**
- Modify: `src/promptgrimoire/cli.py` (complete the `_run_e2e_worker` function from Task 2)

**Implementation:**

Complete the pytest invocation inside `_run_e2e_worker()`.

**Pytest subprocess:**
- Build JUnit XML path: `junit_path = result_dir / f"{test_file.stem}.xml"`
- Build command: `[sys.executable, "-m", "pytest", str(test_file), "-m", "e2e", "--tb=short", f"--junitxml={junit_path}", *filtered_user_args]`
- Filter `user_args`: strip any existing `--junitxml` argument (to avoid conflicting with the per-worker one). Iterate through `user_args` and skip both `--junitxml` and its value (handle both `--junitxml value` and `--junitxml=value` forms).
- Set env: same `clean_env` as server, plus `E2E_BASE_URL=http://localhost:{port}` and `DATABASE__URL={db_url}`
- Start with `asyncio.create_subprocess_exec(*cmd, stdout=log_fh, stderr=STDOUT, env=pytest_env)`. Write to same log file as server. No `start_new_session` needed for pytest.
- `await pytest_proc.wait()`

**Result collection:**
- Record `start_time = time.monotonic()` before server start
- Record `duration = time.monotonic() - start_time` after pytest completes
- Return `(test_file, pytest_proc.returncode, duration)`

**Exit code handling:**
- Return the raw exit code. The orchestrator (Phase 3) handles exit code 5 (no tests collected) as pass.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/cli.py && uv run ruff format src/promptgrimoire/cli.py`
Expected: No lint or format errors

Run: `uvx ty check`
Expected: No type errors in cli.py

**Commit:** `feat: add _run_e2e_worker() async coroutine for parallel E2E`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify worker coroutine imports and types

**Verifies:** None (operational verification)

**Files:** None (verification only)

**Implementation:**

This is an operational verification step. The worker coroutine is infrastructure for the test runner. It manages subprocesses, log files, and process groups. Meaningful automated testing requires starting real servers and running real pytest, which Phase 3/4 will do.

Verify the code is syntactically correct and imports resolve:

**Verification:**
Run: `uvx ty check`
Expected: No type errors in cli.py

Run: `uv run python -c "from promptgrimoire.cli import _run_e2e_worker, _allocate_ports; print('imports OK')"`
Expected: `imports OK`

**Commit:** No commit needed (verification only)
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
