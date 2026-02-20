# Parallel E2E Test Runner Design

**GitHub Issue:** #95

## Summary

The current `test-e2e --parallel` mode passes `-n auto` to pytest-xdist, which attempts to parallelise individual test cases but shares a single NiceGUI server and database. This collapses under database or server state mutations, and xdist's event-loop management conflicts with Playwright's async internals. This design replaces that approach entirely with a custom asyncio orchestrator that gives each E2E test *file* its own isolated NiceGUI server process and its own PostgreSQL database, cloned from the branch test database via `CREATE DATABASE ... TEMPLATE`. Concurrency happens at the file level, not the test level, and no xdist involvement is required.

The orchestrator lives in `src/promptgrimoire/cli.py` and runs in three phases: setup (clone N databases, allocate N ports, start N server processes), run (launch N pytest subprocesses concurrently and collect results), and teardown (kill all server process groups, merge JUnit XML reports, drop worker databases). Each subprocess pair writes to its own log file, keeping output separate. The serial `uv run test-e2e` and `uv run test-e2e-debug` modes are unchanged.

## Definition of Done

A parallel E2E test runner that replaces the current `--parallel` (xdist) mode in `test-e2e`. Each E2E test file gets its own NiceGUI server process on a distinct port, backed by its own PostgreSQL database. All files run concurrently, results aggregated at the end. `test-e2e-debug` keeps fail-fast semantics (kill on first failure).

**Success criteria:**
- `uv run test-e2e --parallel` launches N servers (one per test file), N databases, runs all files to completion, reports aggregate pass/fail
- `uv run test-e2e` (no flags) remains serial single-server as today
- `uv run test-e2e-debug` uses fail-fast: stops all workers when any file fails
- Wall-clock time approximately equals the slowest single test file
- No pytest-xdist involvement
- Worker databases are created automatically and cleaned up (or at least not left dangling indefinitely)

**Out of scope:**
- Changing the test files themselves
- Changing the NiceGUI server script internals
- Smart test distribution (e.g. load-balancing by duration) — just 1 file = 1 worker

## Acceptance Criteria

### parallel-e2e-runner-95.AC1: Parallel execution launches isolated workers
- **parallel-e2e-runner-95.AC1.1 Success:** `uv run test-e2e --parallel` discovers all `tests/e2e/test_*.py` files and launches one server+pytest pair per file
- **parallel-e2e-runner-95.AC1.2 Success:** Each server runs on a distinct port, each backed by its own PostgreSQL database
- **parallel-e2e-runner-95.AC1.3 Success:** All workers run concurrently (wall-clock time approximately equals slowest single file, not sum of all)
- **parallel-e2e-runner-95.AC1.4 Failure:** If a server fails to start, all other servers are killed, worker databases dropped, and exit code is non-zero

### parallel-e2e-runner-95.AC2: Serial mode unchanged
- **parallel-e2e-runner-95.AC2.1 Success:** `uv run test-e2e` (no flags) runs single-server serial mode exactly as before
- **parallel-e2e-runner-95.AC2.2 Success:** `uv run test-e2e-debug` runs single-server with `--lf` and `-x` exactly as before

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

## Glossary

- **asyncio orchestrator**: A coordinator using Python's `asyncio` event loop to manage multiple concurrent subprocesses without threads.
- **branch test database**: The PostgreSQL database for the current git branch (e.g. `pg_test_95_annotation_tags`), used as the template from which worker databases are cloned.
- **CREATE DATABASE ... TEMPLATE**: PostgreSQL DDL that creates a new database as an exact copy of an existing one. Requires no active connections on the source during the clone.
- **exit code 5**: pytest's exit code meaning "no tests collected." Treated as pass so `-k` filters matching nothing in a file don't cause false failures.
- **fail-fast**: Stop all workers when any single worker reports a non-zero exit code.
- **junitparser**: Python library for merging per-file JUnit XML reports into one aggregate result.
- **process group / start_new_session**: Unix concept where `start_new_session=True` makes a subprocess a process group leader, enabling `os.killpg()` to signal the server and all its children at once.
- **worker database**: A PostgreSQL database created per test file during parallel mode (e.g. `pg_test_95_annotation_tags_w0`). Cloned from the branch test database, used by one server+pytest pair, dropped after tests.

## Architecture

An asyncio orchestrator in `src/promptgrimoire/cli.py` coordinates N worker pairs (server subprocess + pytest subprocess), one per E2E test file.

### Three-Phase Lifecycle

**Phase 1 — Setup (sequential, fast):**
Discover test files via `glob("tests/e2e/test_*.py")`. Allocate N ports simultaneously (hold all sockets open, release together). Run Alembic migrations and truncate the branch test database, then `CREATE DATABASE {branch_db}_w{i} TEMPLATE {branch_db}` for each worker (~50ms each, sequential). Start N server subprocesses via `asyncio.create_subprocess_exec` with `start_new_session=True`. Health-check all servers concurrently (HTTP poll, 15s timeout).

**Phase 2 — Run (concurrent):**
Launch N pytest subprocesses, one per test file. Each receives `E2E_BASE_URL=http://localhost:{port}` and `DATABASE__URL={worker_db_url}` in its environment. Each writes JUnit XML to a temp directory (`--junitxml={tmpdir}/{stem}.xml`). For `test-e2e --parallel`: `asyncio.gather()` all workers, wait for every process. For `test-e2e-debug`: `asyncio.as_completed()`, kill remaining workers on first failure.

**Phase 3 — Teardown (always runs, `try/finally`):**
Kill all server process groups (`SIGTERM`, 5s grace, `SIGKILL`). Merge JUnit XML with `junitparser`. Print summary. Drop worker databases (skip on failure for debugging). Exit with worst exit code (treating exit code 5 "no tests collected" as pass).

### Data Flow

```
cli.py test_e2e(--parallel)
  |
  +-- _pre_test_db_cleanup()        # Alembic + truncate on branch DB
  +-- clone_database() x N          # CREATE DATABASE ... TEMPLATE
  +-- allocate_ports() x N          # socket bind(0) simultaneously
  |
  +-- for each (port, db, file):
  |     +-- server = create_subprocess(python -c _E2E_SERVER_SCRIPT, port)
  |     |     env: DATABASE__URL={worker_db}
  |     +-- health_check(port)
  |     +-- pytest = create_subprocess(uv run pytest file)
  |     |     env: E2E_BASE_URL=http://localhost:{port}
  |     |          DATABASE__URL={worker_db}
  |     +-- await pytest.wait()
  |     +-- killpg(server.pid, SIGTERM)
  |
  +-- merge JUnit XML
  +-- print summary + exit
```

### CLI Integration

`test_e2e()`: `--parallel` replaces the current xdist codepath. Calls the async orchestrator via `asyncio.run()`. Without `--parallel`, unchanged (single server, serial, fail-fast). User args (e.g. `-k browser`, `-v`) forwarded to each pytest subprocess. The orchestrator strips `--junitxml` from forwarded user args to avoid conflicting with its own per-worker `--junitxml` injection.

`test_e2e_debug()`: Stays single-server. It is a debugging tool — serial execution, `--lf`, full tracebacks. Speed matters less than precision here.

### Output Strategy

Each pytest subprocess writes stdout/stderr to its own log file: `test-e2e-{stem}.log`. No subprocess output is mixed into the orchestrator's terminal.

**TTY mode:** Rich Live display tailing the last line from each worker's log file. Updates periodically. One line per worker showing file name + latest output.

**Non-TTY mode:** One line per worker completion (`PASS test_law_student.py (42s)` or `FAIL ...`). Final summary line with counts and wall-clock time.

Detection via `sys.stdout.isatty()`. Rich handles this natively.

## Existing Patterns

Investigation found the existing E2E infrastructure in `src/promptgrimoire/cli.py`:

- `_start_e2e_server(port)` / `_stop_e2e_server(process)` — server lifecycle management. Reused as-is per worker.
- `_E2E_SERVER_SCRIPT` — inline Python script for the server subprocess. Unchanged. Receives port via `sys.argv[1]`, database via `DATABASE__URL` env.
- `_pre_test_db_cleanup()` — Alembic migrations + table truncation. Runs once in the orchestrator for the template database.
- `_run_pytest()` — subprocess-based pytest invocation with Rich output. Cannot be reused directly (calls `sys.exit()`, streams to console). The orchestrator needs its own pytest subprocess management with per-file log capture.

Database patterns from `src/promptgrimoire/db/bootstrap.py`:

- `ensure_database_exists(url)` — create-if-not-exists with `^[a-zA-Z0-9_]+$` name validation. Pattern followed for `clone_database()` and `drop_database()`.
- `_suffix_db_url(url, suffix)` in `config.py` — pure string transform for branch-specific DB names. Worker URLs constructed similarly: `{branch_db}_w{N}`.

Test fixture patterns from `tests/e2e/conftest.py`:

- `_e2e_post_test_cleanup` reads `E2E_BASE_URL` from env — works per-worker with no changes.
- `_grant_workspace_access` reads `DATABASE__URL` from env — connects to the correct worker database automatically.
- `app_server` fixture checks `E2E_BASE_URL` — when set, yields directly. No changes needed.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Database Cloning Infrastructure
**Goal:** Add template-based database cloning and teardown to `bootstrap.py`.

**Components:**
- `clone_database(source_url, target_name)` in `src/promptgrimoire/db/bootstrap.py` — `CREATE DATABASE {target} TEMPLATE {source}` using sync psycopg, same connection pattern as `ensure_database_exists()`
- `drop_database(url)` in `src/promptgrimoire/db/bootstrap.py` — `DROP DATABASE IF EXISTS` with same validation guard

**Dependencies:** None

**Done when:** Can clone the branch test database into a worker database and drop it afterwards. Tests verify clone creates a database with the source's schema, and drop removes it.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Async Worker Coroutine
**Goal:** Single async function that manages one server+pytest pair lifecycle.

**Components:**
- `_run_e2e_worker(file, port, db_url, result_dir, user_args)` in `src/promptgrimoire/cli.py` — starts server subprocess (`start_new_session=True`), health-checks, launches pytest subprocess with per-file JUnit XML and log file, awaits pytest exit, kills server process group in `finally` block
- Port allocation utility — allocate N ports simultaneously, return list

**Dependencies:** Phase 1 (worker databases must exist before servers start, but the coroutine itself just receives a `db_url`)

**Done when:** A single worker can start a server, run pytest against one test file, capture output to a log file, produce JUnit XML, and clean up the server on completion or failure.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Parallel Orchestrator
**Goal:** Async function that coordinates N workers and collects results.

**Components:**
- `_run_parallel_e2e(test_files, user_args, fail_fast)` in `src/promptgrimoire/cli.py` — discovers test files, creates worker databases from template, allocates ports, launches N `_run_e2e_worker` coroutines via `asyncio.gather()` (or `asyncio.as_completed()` for fail-fast), collects exit codes, handles cleanup
- Result aggregation — merge JUnit XML files with `junitparser`, print summary table

**Dependencies:** Phase 1 (database cloning), Phase 2 (worker coroutine)

**Done when:** Running `_run_parallel_e2e()` with multiple test files launches concurrent workers, all workers complete (or are killed on first failure in fail-fast mode), JUnit XML is merged, and summary is printed.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: CLI Integration
**Goal:** Wire the parallel orchestrator into `test_e2e()` and clean up xdist removal.

**Components:**
- `test_e2e()` in `src/promptgrimoire/cli.py` — `--parallel` flag now calls `asyncio.run(_run_parallel_e2e(...))` instead of passing xdist args to `_run_pytest()`. Remove xdist codepath (`-n auto --dist=loadfile`).
- `test_e2e_debug()` — unchanged (single server, serial, fail-fast). Confirm `--lf` and `-x` still work.
- Output formatting — TTY: Rich Live tailing worker log files. Non-TTY: one line per completion.

**Dependencies:** Phase 3 (orchestrator)

**Done when:** `uv run test-e2e --parallel` runs all E2E test files in parallel with isolated servers and databases. `uv run test-e2e` (no flags) still runs serial. `uv run test-e2e-debug` still works as before. Output is readable in both TTY and non-TTY modes.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Cleanup and Documentation
**Goal:** Database teardown, error reporting, and documentation updates.

**Components:**
- Database cleanup in orchestrator teardown — drop worker databases after tests, skip on failure and log connection strings
- Error reporting — clear messages for server startup failures, include log file paths in failure output
- `docs/testing.md` updates — document `--parallel` behaviour, database isolation, log file locations
- `docs/e2e-debugging.md` updates — add parallel-mode debugging section

**Dependencies:** Phase 4 (CLI integration complete)

**Done when:** Worker databases are cleaned up on success, preserved on failure with logged connection strings. Documentation reflects the new parallel mode.
<!-- END_PHASE_5 -->

## Additional Considerations

**Process group cleanup:** `start_new_session=True` on server subprocesses makes each a process group leader. `os.killpg(pgid, SIGTERM)` kills the server and any children it spawned (e.g. NiceGUI's uvicorn workers). If SIGTERM does not terminate within 5 seconds, escalate to SIGKILL.

**Exit code semantics:** pytest exit code 5 ("no tests collected") is treated as success. This handles `-k` filters that match nothing in a given file. Any other non-zero exit code is a failure.

**Database naming:** Worker databases follow `{branch_db}_w{N}` pattern (e.g. `pg_test_95_annotation_tags_w0`). All underscores, passes `ensure_database_exists()` validation. The template database is the branch test database itself — no separate template management.

**Concurrent `CREATE DATABASE ... TEMPLATE` restriction:** PostgreSQL prohibits connections to the source database during template cloning. The orchestrator creates all worker databases sequentially before starting any servers. Since `_pre_test_db_cleanup()` disposes its engine after truncation, no connections remain to block cloning. As a safety measure, the orchestrator should terminate any lingering connections to the template database before cloning (via `pg_terminate_backend()`).

**Isolation boundary is the file:** The `app_server` fixture in `tests/conftest.py` is `scope="session"`. In parallel mode, each pytest subprocess constitutes one session containing one file's tests. This means each file gets exactly one server — the intended design. Do not change `app_server` to function scope; that would start a new server per test.

**PostgreSQL connection limits:** With N workers, each running a NiceGUI server with a connection pool (`pool_size=5, max_overflow=10`), the theoretical maximum is N * 15 connections against PostgreSQL's default `max_connections=100`. With 17 test files this is 255 theoretical max, though in practice each test uses 1-2 connections. If connection limits are hit, reduce pool size in `_E2E_SERVER_SCRIPT` or increase `max_connections` in PostgreSQL config.
