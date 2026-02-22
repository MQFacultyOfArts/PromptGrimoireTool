# Test Requirements: Parallel E2E Test Runner (#95)

Maps each acceptance criterion to specific automated tests or human verification steps.

**Convention:** Test file paths are relative to the repository root. Phase references indicate which implementation phase produces the test.

---

## AC1: Parallel execution launches isolated workers

### AC1.1 -- Discovers all test files and launches one server+pytest pair per file

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Verifying that N server+pytest pairs are launched concurrently requires observing live process creation against a running PostgreSQL instance with 16 real test files. The orchestrator's file discovery is a single `glob` call; the interesting property is that it fans out correctly into concurrent subprocesses. A unit test mocking all of `asyncio.create_subprocess_exec`, `clone_database`, and `_allocate_ports` would test the mock, not the system. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. Confirm console output shows `Found 16 test files` (or current count).
3. Confirm per-file result lines appear for every `tests/e2e/test_*.py` file -- no files skipped, no files duplicated.
4. While running, confirm with `ps aux | grep promptgrimoire` that multiple server processes exist simultaneously.

---

### AC1.2 -- Each server runs on a distinct port, each backed by its own PostgreSQL database

| Property | Value |
|----------|-------|
| Test type | Unit |
| File | `tests/unit/test_cli_parallel.py` |
| Phase | 2, Task 1 |
| What it verifies | `_allocate_ports(n)` returns `n` distinct positive integers. Ports are allocated simultaneously (not sequentially) to avoid OS-level reuse. |

**Automated tests:**

- `test_allocate_ports_returns_distinct_ports` -- call `_allocate_ports(5)`, assert `len(set(ports)) == 5` and all ports > 0.
- `test_allocate_ports_single` -- call `_allocate_ports(1)`, assert single port returned.
- `test_allocate_ports_zero` -- call `_allocate_ports(0)`, assert empty list.

| Property | Value |
|----------|-------|
| Test type | Integration |
| File | `tests/integration/test_db_cloning.py` |
| Phase | 1, Task 4 |
| What it verifies | Each worker database is a real PostgreSQL clone with the template's schema. Distinct database names are produced per worker. |

**Automated tests:**

- `test_clone_creates_database_with_source_schema` -- clone the branch test DB, connect to the clone, verify `information_schema.tables` matches the source.

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Confirming that port and database are correctly threaded through to each server+pytest subprocess pair requires running the full parallel pipeline. The unit tests verify the building blocks; the UAT confirms they compose correctly. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. Check worker log files (`test-e2e-{stem}.log`) for distinct port numbers in server startup messages.
3. Check `psql -l | grep _w` during execution to confirm multiple worker databases exist.

---

### AC1.3 -- All workers run concurrently (wall-clock approximately equals slowest file)

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Wall-clock timing comparison is inherently environmental -- it depends on hardware, database speed, and test complexity. An automated test would need arbitrary timing thresholds that break on slow CI machines. The property "concurrent, not sequential" is best verified by a human observing that total wall-clock is significantly less than the sum of individual durations shown in the summary table. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. Read the summary table. Sum the per-file durations. Compare to the reported total wall-clock time.
3. The total wall-clock time should be roughly equal to the maximum per-file duration, not the sum. A ratio of `sum / wall_clock > 2` for 16 files confirms concurrency.

---

### AC1.4 -- Server startup failure kills all servers, drops databases, exits non-zero

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Simulating a server startup failure requires either injecting a fault into `_E2E_SERVER_SCRIPT` or blocking a port. Both require runtime manipulation that is fragile to automate and risks leaving orphan processes or databases if the test itself fails. Code review of the `try/finally` structure in `_run_e2e_worker` and `_run_parallel_e2e` provides structural confidence; the UAT confirms the behavior. |

**Verification approach:**

1. Temporarily modify `_E2E_SERVER_SCRIPT` to `sys.exit(1)` immediately for a specific port or worker index, or pass an invalid `DATABASE__URL` to one worker.
2. Run `uv run test-e2e --parallel`.
3. Confirm exit code is non-zero.
4. Confirm `ps aux | grep promptgrimoire` shows no orphan server processes.
5. Confirm `psql -l | grep _w` shows no leftover worker databases.
6. Revert the deliberate fault.

**Supplementary confidence:** Code review of `_run_e2e_worker` `finally` block (Phase 2, Task 2) confirms `os.killpg` is called unconditionally. Code review of `_run_parallel_e2e` confirms `clone_database` rollback on partial setup failure.

---

## AC2: Serial mode unchanged

### AC2.1 -- `uv run test-e2e` (no flags) runs single-server serial mode exactly as before

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 2 |
| Justification | "Exactly as before" is a behavioral regression check against the pre-existing serial mode. Automating this would require a meta-test that runs the CLI and inspects its behavior, which is the same as running the E2E suite itself. The serial codepath is unchanged -- the risk is that the `test_e2e()` refactor accidentally broke the branch condition. |

**Verification approach:**

1. Run `uv run test-e2e -k test_browser_gate` (fast single test, serial mode).
2. Confirm: one server starts on one port (visible in `test-e2e-server.log`).
3. Confirm: test runs with `-x` (fail-fast) semantics.
4. Confirm: server stops after tests complete.
5. Confirm: exit code matches test result.

---

### AC2.2 -- `uv run test-e2e-debug` runs single-server with `--lf` and `-x` exactly as before

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 2 |
| Justification | `test_e2e_debug()` is not modified in any phase. The risk is zero unless an import or module-level change in `cli.py` has side effects. A quick manual run confirms no regression. |

**Verification approach:**

1. Run `uv run test-e2e-debug -k test_browser_gate`.
2. Confirm: verbose output (`-v`, `--tb=long`).
3. Confirm: `--lf` flag present (pytest output shows "run only last failures" or runs all if no prior failures).
4. Confirm: single server starts and stops.

---

## AC3: Result aggregation

### AC3.1 -- Per-worker JUnit XML files are merged into a single report

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | JUnit XML merging uses `junitparser`, a well-tested library. The merge logic is three lines of code. An automated test would need to generate mock XML files and call the merge function, but the merge is inline in `_run_parallel_e2e` -- not a standalone testable function. The UAT confirms the output file exists and contains results from all workers. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. On success, confirm the summary mentions the merged JUnit XML path.
3. On failure (to preserve temp dir), open the `combined.xml` file in the preserved result directory.
4. Verify it contains `<testsuite>` entries from multiple test files (check `name` attributes).

**Possible future improvement:** Extract JUnit merge into a standalone function and unit test it. Low priority given the simplicity.

---

### AC3.2 -- Exit code is 0 only when all workers pass (exit code 5 treated as pass)

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Exit code logic depends on the return values from real pytest subprocesses. Testing this in isolation would require mocking `_run_e2e_worker` return values, but the logic is a simple comprehension (`all(code in (0, 5) for ...)`). The UAT exercises both the pass and `-k` filter (exit code 5) paths. |

**Verification approach -- all pass:**

1. Run `uv run test-e2e --parallel` (assuming all tests pass).
2. Confirm exit code is 0: `echo $?` (bash) or `echo $status` (fish).

**Verification approach -- exit code 5 treated as pass:**

1. Run `uv run test-e2e --parallel -k test_browser_gate`.
2. Most workers will have no matching tests (exit code 5). One worker will run `test_browser_gate`.
3. Confirm overall exit code is 0.
4. Confirm summary shows pass status for exit-code-5 workers.

**Verification approach -- failure produces non-zero:**

1. Introduce a deliberate test failure (e.g., add `assert False` to one test).
2. Run `uv run test-e2e --parallel`.
3. Confirm exit code is non-zero.
4. Revert the deliberate failure.

---

### AC3.3 -- Summary output shows per-file pass/fail status and duration

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Output formatting is visual. Automated testing of Rich table output requires capturing and parsing terminal escape sequences, which is fragile and low-value. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. Confirm the summary table shows:
   - One row per test file with file name, PASS/FAIL status, and duration in seconds.
   - A totals row with pass/fail counts and wall-clock time.
3. Confirm PASS is green and FAIL is red (if terminal supports color).

---

## AC4: Database lifecycle

### AC4.1 -- Worker databases created via `CREATE DATABASE ... TEMPLATE`

| Property | Value |
|----------|-------|
| Test type | Unit |
| File | `tests/unit/test_db_schema.py` |
| Phase | 1, Task 2 |
| What it verifies | `clone_database()` executes the correct `CREATE DATABASE {target} TEMPLATE {source}` SQL with safe identifier quoting. Input validation rejects invalid target names. `terminate_connections()` is called before cloning. |

**Automated tests:**

- `test_clone_database_executes_create_template` -- mock `psycopg.connect`, verify the SQL contains `CREATE DATABASE` and `TEMPLATE` with correct identifiers.
- `test_clone_database_returns_target_url` -- verify the returned URL has the target database name.
- `test_clone_database_rejects_invalid_name` -- `clone_database(url, "bad-name!")` raises `ValueError`.
- `test_clone_database_terminates_connections_first` -- verify `terminate_connections()` is called before the `CREATE DATABASE` statement.

| Property | Value |
|----------|-------|
| Test type | Integration |
| File | `tests/integration/test_db_cloning.py` |
| Phase | 1, Task 4 |
| What it verifies | End-to-end clone against real PostgreSQL: cloned database exists, has same tables as source. |

**Automated tests:**

- `test_clone_creates_database_with_source_schema` -- clone the branch test DB, connect to clone, query `information_schema.tables`, compare to source.

---

### AC4.2 -- Worker databases dropped after successful test completion

| Property | Value |
|----------|-------|
| Test type | Unit |
| File | `tests/unit/test_db_schema.py` |
| Phase | 1, Task 3 |
| What it verifies | `drop_database()` executes the correct `DROP DATABASE IF EXISTS` SQL. Input validation rejects invalid names. `terminate_connections()` is called before drop. Idempotent (no error on non-existent database). |

**Automated tests:**

- `test_drop_database_executes_drop` -- mock `psycopg.connect`, verify SQL contains `DROP DATABASE IF EXISTS` with correct identifier.
- `test_drop_database_rejects_invalid_name` -- `drop_database("postgresql://host/bad-name!")` raises `ValueError`.
- `test_drop_database_terminates_connections_first` -- verify `terminate_connections()` is called before `DROP`.
- `test_drop_database_idempotent` -- no exception when database does not exist (mocked `IF EXISTS`).

| Property | Value |
|----------|-------|
| Test type | Integration |
| File | `tests/integration/test_db_cloning.py` |
| Phase | 1, Task 4 |
| What it verifies | End-to-end drop against real PostgreSQL: database no longer exists after drop. |

**Automated tests:**

- `test_drop_removes_cloned_database` -- clone, then drop, verify database no longer appears in `pg_database`.

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | The orchestrator's teardown logic (drop on success, preserve on failure) is wired in `_run_parallel_e2e` which is not independently testable without running the full pipeline. |

**Verification approach:**

1. Run `uv run test-e2e --parallel` (all tests passing).
2. After completion, run `psql -l | grep _w`.
3. Confirm no `{branch_db}_wN` databases remain.

---

### AC4.3 -- On test failure, worker databases preserved and connection strings logged

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | This criterion tests the failure path of the orchestrator's teardown. Automating it requires inducing a real test failure and then querying PostgreSQL and parsing console output. The failure path is a simple branch (`if any_failed: print URLs, else: drop DBs`) -- code review plus one manual verification is sufficient. |

**Verification approach:**

1. Introduce a deliberate test failure (e.g., `assert False` in one test file).
2. Run `uv run test-e2e --parallel`.
3. Confirm console output includes `Preserved worker DB:` lines with connection strings for ALL workers (not just the failing one).
4. Confirm `psql -l | grep _w` shows the worker databases still exist.
5. Connect to one preserved worker database using the logged connection string. Confirm tables and data are present.
6. Manually clean up: `DROP DATABASE {branch_db}_wN;` for each worker database.
7. Revert the deliberate test failure.

---

## AC5: Process cleanup

### AC5.1 -- All server process groups terminated in teardown (no orphan processes)

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Process group cleanup (`os.killpg` with `start_new_session=True`) is OS-level behavior. Automated testing would require spawning real subprocesses and checking the process table, which is a system-level integration test. The `_run_e2e_worker` `finally` block is the mechanism; code review confirms it runs unconditionally. |

**Verification approach:**

1. Run `uv run test-e2e --parallel`.
2. Wait for completion.
3. Run `ps aux | grep "[p]romptgrimoire"` (bracketed grep avoids matching itself).
4. Confirm no server processes remain.
5. Repeat with a failure scenario (deliberate test failure or server crash) to verify cleanup on error paths.

**Supplementary confidence:** Code review of `_run_e2e_worker` confirms:
- Server started with `start_new_session=True` (process group leader).
- `finally` block calls `os.killpg(os.getpgid(server.pid), signal.SIGTERM)`.
- 5-second grace period, then `SIGKILL` escalation.
- `ProcessLookupError` caught (process may already be dead).

---

### AC5.2 -- Fail-fast mode kills remaining workers on first failure

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | Fail-fast behavior requires observing that remaining workers are cancelled promptly after one fails. This is timing-dependent and requires real concurrent processes. The mechanism is `asyncio.as_completed()` with task cancellation. |

**Verification approach:**

1. Introduce a deliberate early failure in one test file (e.g., `assert False` as the first test in `test_browser_gate.py`, which is fast).
2. Run `uv run test-e2e --parallel --fail-fast`.
3. Confirm: wall-clock time is significantly less than running all files (indicates remaining workers were killed, not awaited).
4. Confirm: summary shows the failing file and `CANCELLED` status for remaining workers.
5. Confirm: exit code is non-zero.
6. Confirm: no orphan processes (`ps aux | grep "[p]romptgrimoire"`).
7. Revert the deliberate failure.

---

### AC5.3 -- `-k` filter producing no matching tests treated as pass (exit code 5)

| Property | Value |
|----------|-------|
| Test type | Human verification (UAT) |
| Phase | 4, Task 3 |
| Justification | This is a specific case of AC3.2. The exit code 5 handling is a single condition in the orchestrator's result processing. The UAT for AC3.2 already exercises this path with a `-k` filter. Listed separately here for traceability. |

**Verification approach:**

1. Run `uv run test-e2e --parallel -k test_browser_gate`.
2. Confirm: summary shows most files as PASS (exit code 5, no tests collected).
3. Confirm: overall exit code is 0.
4. Run `uv run test-e2e --parallel -k nonexistent_test_that_matches_nothing`.
5. Confirm: ALL files show exit code 5 (no tests collected).
6. Confirm: overall exit code is 0 (all exit-code-5 results treated as pass).

---

## Summary Matrix

| AC | Automated Unit | Automated Integration | Human UAT | Phase |
|----|:-:|:-:|:-:|:---:|
| AC1.1 | | | X | P4 |
| AC1.2 | X (`test_cli_parallel.py`) | X (`test_db_cloning.py`) | X | P1, P2, P4 |
| AC1.3 | | | X | P4 |
| AC1.4 | | | X | P4 |
| AC2.1 | | | X | P4 |
| AC2.2 | | | X | P4 |
| AC3.1 | | | X | P4 |
| AC3.2 | | | X | P4 |
| AC3.3 | | | X | P4 |
| AC4.1 | X (`test_db_schema.py`) | X (`test_db_cloning.py`) | | P1 |
| AC4.2 | X (`test_db_schema.py`) | X (`test_db_cloning.py`) | X | P1, P4 |
| AC4.3 | | | X | P4 |
| AC5.1 | | | X | P4 |
| AC5.2 | | | X | P4 |
| AC5.3 | | | X | P4 |

**Totals:** 4 unit test files, 2 integration test files, 15 UAT verification steps.

### Automated test files

| File | Tests | ACs covered |
|------|-------|-------------|
| `tests/unit/test_db_schema.py` | `terminate_connections`, `clone_database`, `drop_database` mocked tests | AC4.1, AC4.2 |
| `tests/unit/test_cli_parallel.py` | `_allocate_ports` tests | AC1.2 |
| `tests/integration/test_db_cloning.py` | Clone round-trip, drop verification against real PostgreSQL | AC1.2, AC4.1, AC4.2 |

### UAT-only criteria with justification summary

| AC | Why not automated |
|----|-------------------|
| AC1.1 | Requires observing concurrent process creation against live infrastructure |
| AC1.3 | Wall-clock timing comparisons are environment-dependent |
| AC1.4 | Fault injection into server startup is fragile to automate |
| AC2.1, AC2.2 | Behavioral regression checks on unchanged codepaths |
| AC3.1 | JUnit merge is inline, not an independently testable function |
| AC3.2, AC3.3 | Exit code and output formatting depend on real pytest subprocess results |
| AC4.3 | Failure-path database preservation requires induced failures |
| AC5.1, AC5.2, AC5.3 | Process lifecycle and OS-level cleanup verification |
