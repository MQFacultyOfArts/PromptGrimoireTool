# Unified Test Suite Design

## Summary

This design unifies PromptGrimoire's test suite by integrating end-to-end (E2E) Playwright tests into the same pytest execution as unit and integration tests. Currently, E2E tests are excluded from the main test runners (`test-all`, `test-debug`) because of concerns about event loop contamination when Playwright's sync API runs in the same pytest-xdist worker as async tests. The unified approach moves server lifecycle management from individual test fixtures into the CLI layer: the `test-all` and `test-debug` commands will start a single NiceGUI application server before spawning pytest workers, then tear it down after all tests complete. All xdist workers share this server via an environment variable.

The implementation begins with an empirical falsification test to verify whether event loop coexistence is actually a problem under current pytest configuration (it may have been resolved by the `asyncio_default_fixture_loop_scope = "function"` setting). If contamination persists, E2E tests will be isolated to a dedicated xdist worker using pytest's `xdist_group` marker. Additionally, LaTeX compilation tests (slow ~8-11s each) will be prioritized via a custom collection hook so they start immediately on available workers, overlapping with faster tests rather than blocking the end of the test run. The design also addresses coverage gaps identified in a deprecated test audit by adding four new E2E tests, then cleans up the deprecated test directory.

## Definition of Done

`test-all` and `test-debug` run unit, integration, and E2E tests together under pytest-xdist parallel execution. A single NiceGUI server (variable port) is started once by the CLI before workers spawn and torn down after. All xdist workers share this server. LaTeX tests are scheduled first via a custom collection hook. The event loop contamination concern from #121 is empirically verified to be resolved (or mitigated if still present). Deprecated E2E test logic is audited to confirm coverage exists in current tests.

## Acceptance Criteria

### unified-test-suite.AC1: Unified test execution
- **unified-test-suite.AC1.1 Success:** `uv run test-all` runs unit, integration, and E2E tests in a single pytest invocation under xdist parallel execution
- **unified-test-suite.AC1.2 Success:** `uv run test-debug` includes E2E tests when pytest-depper determines they are affected by code changes
- **unified-test-suite.AC1.3 Success:** `uv run test-all-fixtures` runs all tests including BLNS, slow, and E2E
- **unified-test-suite.AC1.4 Success:** Running `pytest tests/unit/ -n auto` directly (without CLI) skips E2E tests cleanly via `pytest.skip()`
- **unified-test-suite.AC1.5 Failure:** `app_server` fixture raises clear skip message when `E2E_SERVER_URL` is not set

### unified-test-suite.AC2: CLI-managed server lifecycle
- **unified-test-suite.AC2.1 Success:** CLI starts a NiceGUI server on a free port before spawning pytest, with `AUTH_MOCK=true` and `STORAGE_SECRET` set
- **unified-test-suite.AC2.2 Success:** Server URL is passed to pytest workers via `E2E_SERVER_URL` environment variable
- **unified-test-suite.AC2.3 Success:** Server is terminated (SIGTERM then SIGKILL) after pytest exits, regardless of exit code
- **unified-test-suite.AC2.4 Success:** `DATABASE_URL` is set from `TEST_DATABASE_URL` for the server subprocess when a test database is configured
- **unified-test-suite.AC2.5 Failure:** CLI exits with clear error if server fails to start within timeout (15s)
- **unified-test-suite.AC2.6 Edge:** CLI works correctly when `TEST_DATABASE_URL` is not set (server starts without DB, DB-dependent E2E tests fail individually)

### unified-test-suite.AC3: LaTeX test prioritisation
- **unified-test-suite.AC3.1 Success:** `@pytest.mark.latex` tests appear at the front of the xdist collection, starting on workers before non-latex tests
- **unified-test-suite.AC3.2 Success:** `--durations` output confirms latex tests are among the first to complete (they start early despite being slow)
- **unified-test-suite.AC3.3 Edge:** Prioritisation does not break when no latex-marked tests exist in the collection (e.g., running `pytest tests/e2e/` only)

### unified-test-suite.AC4: Event loop coexistence
- **unified-test-suite.AC4.1 Success:** A Playwright sync API test and a pytest-asyncio async test can run in the same xdist worker without `Runner.run() cannot be called from a running event loop` errors — OR xdist_group mitigation is applied and verified
- **unified-test-suite.AC4.2 Success:** The empirical falsification test documents the result (coexistence works or mitigation needed)

### unified-test-suite.AC5: Coverage gaps filled
- **unified-test-suite.AC5.1 Success:** E2E test verifies workspace isolation — highlights in workspace A are not visible in workspace B
- **unified-test-suite.AC5.2 Success:** E2E test verifies tag colors persist across page reload
- **unified-test-suite.AC5.3 Success:** E2E test verifies Ctrl+H creates a highlight on selected text
- **unified-test-suite.AC5.4 Success:** E2E test verifies Escape deselects current text selection

### unified-test-suite.AC6: Deprecated test audit
- **unified-test-suite.AC6.1 Success:** Each deprecated test is either confirmed covered by existing tests, migrated to current test files, or removed with documented justification
- **unified-test-suite.AC6.2 Success:** Tests blocked on #106 (file upload) are marked with `pytest.mark.skip` with clear reason
- **unified-test-suite.AC6.3 Success:** `tests/e2e/deprecated/` directory is cleaned up (removed or contains only skip-marked tests with explanations)

## Glossary

- **pytest-xdist**: pytest plugin that distributes tests across multiple CPU cores. Workers run tests in parallel using a work-stealing scheduler (`--dist=worksteal`).
- **xdist worker**: An individual subprocess spawned by pytest-xdist to execute tests in parallel.
- **event loop contamination**: When two different async/event-loop mechanisms (Playwright's greenlet-based sync API and pytest-asyncio's event loops) conflict in the same Python process, causing "cannot be called from a running event loop" errors.
- **Playwright sync API**: Playwright's synchronous Python API that uses greenlet internally to manage browser automation without async/await syntax.
- **pytest-asyncio**: pytest plugin that provides async test fixtures and enables `async def` test functions.
- **asyncio_default_fixture_loop_scope**: pytest-asyncio configuration option controlling when event loops are created/destroyed. `"function"` scope creates a fresh loop per test.
- **xdist_group**: pytest-xdist marker that routes all marked tests to the same worker, ensuring they don't run concurrently with other groups.
- **NiceGUI**: Web UI framework used by PromptGrimoire for the annotation interface. Tests need a running NiceGUI server to interact with.
- **pytest-depper**: Tool that analyzes code changes and selects only affected tests (used by `test-debug` command for fast feedback).
- **collection hook**: pytest hook (`pytest_collection_modifyitems`) that runs after test discovery to reorder or modify the test list before execution.
- **Alembic**: Database migration tool for SQLAlchemy/SQLModel. Runs migrations before tests to ensure test database schema is current.
- **LaTeX compilation tests**: Tests that invoke LaTeX (via TinyTeX) to verify PDF export functionality. Slow due to subprocess overhead and compilation time.
- **work-stealing scheduler**: xdist's default distribution strategy where idle workers take tests from other workers' queues, balancing load dynamically.
- **greenlet**: Python library for lightweight coroutines (cooperative multitasking) used by Playwright's sync API to manage browser operations without async/await.
- **empirical falsification test**: A test designed to prove whether a hypothesis is wrong by creating conditions where the hypothesized problem would manifest if it exists.

## Architecture

### Server Lifecycle: CLI-Managed

The CLI commands (`test-all`, `test-debug`, `test-all-fixtures`) manage a single NiceGUI server process. The current `_pre_test_db_cleanup()` in `src/promptgrimoire/cli.py` becomes `_pre_test_setup()` with server management added. The server lifecycle wraps the pytest subprocess in `_run_pytest()`:

1. **Before pytest:** `_pre_test_setup()` runs Alembic migrations, truncates tables, then starts a NiceGUI server subprocess on a free port with `AUTH_MOCK=true`, `STORAGE_SECRET`, and `DATABASE_URL` (from `TEST_DATABASE_URL`). Polls until the port accepts connections (max 15s).
2. **Set env var:** Sets `E2E_SERVER_URL=http://localhost:{port}` in the environment inherited by the pytest subprocess.
3. **Run pytest:** Spawns pytest as before.
4. **After pytest:** Terminates the server subprocess (SIGTERM, then SIGKILL after 5s timeout).

The server subprocess reuses the existing `_SERVER_SCRIPT` pattern from `tests/conftest.py` (lines 530-554), which clears `PYTEST`/`NICEGUI` env vars and sets mock auth. This script moves from `conftest.py` to `cli.py`.

### Fixture Adaptation

The `app_server` fixture in `tests/conftest.py` (currently lines 557-612) changes from spawning a subprocess to reading `E2E_SERVER_URL` from the environment. If the env var is not set, the fixture calls `pytest.skip()` — this allows running `pytest tests/unit/` directly without a server (unit tests don't depend on `app_server`).

The `_find_free_port()` function and `_SERVER_SCRIPT` constant move from `tests/conftest.py` to `src/promptgrimoire/cli.py`. The `TEST_STORAGE_SECRET` constant stays in conftest (still needed by E2E fixtures).

### Test Collection and Ordering

A `pytest_collection_modifyitems` hook in `tests/conftest.py` reorders the test collection to place `@pytest.mark.latex`-marked tests at the front. Combined with `--dist=worksteal`, xdist workers pick up slow LaTeX compilation tests (~8-11s each) first while remaining workers handle fast tests.

The `latex` marker already exists (registered in `pyproject.toml` line 126, applied by `requires_latexmk` decorator in `tests/conftest.py` line 192). The hook adds ~10 lines to `tests/conftest.py`.

### Event Loop Coexistence

Issue #121 documented that Playwright's sync API (which uses greenlet internally) created an event loop that contaminated pytest-asyncio's loops in the same xdist worker.

**Primary hypothesis:** The current `asyncio_default_fixture_loop_scope = "function"` setting (each test gets a fresh event loop) resolves the contamination. An empirical falsification test verifies this.

**Fallback mitigation:** If contamination persists, all E2E tests get `@pytest.mark.xdist_group("e2e")`. This routes E2E tests to a single xdist worker while other workers handle unit/integration tests. Parallelism is preserved — E2E tests run concurrently with non-E2E.

### CLI Integration

- `test_all()`: Remove `-m "not e2e"` from default args.
- `test_debug()`: No changes needed — pytest-depper already includes E2E tests in its dependency analysis. When changes touch E2E-relevant code paths, depper selects those E2E tests automatically.
- `test_all_fixtures()`: Add server management (same as `test_all`).

## Existing Patterns

### Server Subprocess Pattern
The `_SERVER_SCRIPT` in `tests/conftest.py` (line 530) and the `app_server` fixture (line 557) establish the pattern for running NiceGUI in a subprocess with clean environment. This design moves that pattern to the CLI layer but preserves the same mechanism: inline Python script, env var clearing, port polling.

### Collection Hook Pattern
`tests/e2e/conftest.py` line 43 already uses `pytest_collection_modifyitems` to auto-apply the `e2e` marker. The LaTeX ordering hook follows the same pattern in `tests/conftest.py`.

### DB Cleanup in CLI Pattern
`_pre_test_db_cleanup()` in `cli.py` (line 23) runs setup once before pytest spawns. Server management extends this existing pattern.

### Marker-Based Test Filtering
`pyproject.toml` registers `e2e`, `latex`, `blns`, `slow` markers. The design uses these existing markers — no new markers needed (unless `xdist_group` fallback is triggered).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Event Loop Falsification

**Goal:** Empirically verify that Playwright sync API and pytest-asyncio coexist in the same xdist worker without event loop contamination.

**Components:**
- Falsification test in `tests/integration/test_event_loop_coexistence.py` — one Playwright sync test and one async test, run under `pytest -n 1` to force same worker
- If contamination detected: add `@pytest.mark.xdist_group("e2e")` to `tests/e2e/conftest.py`'s `pytest_collection_modifyitems` hook

**Dependencies:** None (first phase)

**Done when:** Either (a) falsification test passes — Playwright and async coexist, or (b) contamination confirmed and xdist_group mitigation applied, with the falsification test passing under that configuration.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CLI Server Lifecycle

**Goal:** `test-all`, `test-debug`, and `test-all-fixtures` start a NiceGUI server before pytest and tear it down after.

**Components:**
- `_pre_test_setup()` in `src/promptgrimoire/cli.py` — replaces `_pre_test_db_cleanup()`, adds server start after DB setup
- `_find_free_port()` moved from `tests/conftest.py` to `src/promptgrimoire/cli.py`
- `_SERVER_SCRIPT` moved from `tests/conftest.py` to `src/promptgrimoire/cli.py`
- `_run_pytest()` modified to set `E2E_SERVER_URL` env var and kill server after pytest exits
- `_start_test_server()` and `_stop_test_server()` helper functions in `cli.py`

**Dependencies:** Phase 1 (event loop result determines if xdist_group needed)

**Done when:** `uv run test-all` starts a NiceGUI server, runs all tests (including E2E), and tears down the server. Server URL visible in Rich header panel.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Fixture Adaptation

**Goal:** `app_server` fixture reads server URL from environment instead of starting a subprocess.

**Components:**
- `app_server` fixture in `tests/conftest.py` — rewritten to read `E2E_SERVER_URL`, `pytest.skip()` if missing
- Remove `_SERVER_SCRIPT`, `_find_free_port()` from `tests/conftest.py` (moved to cli.py in Phase 2)
- `tests/e2e/conftest.py` — no changes needed (fixtures already depend on `app_server`)

**Dependencies:** Phase 2 (server must be managed by CLI)

**Done when:** E2E tests receive server URL from env var. Running `pytest tests/unit/` directly (without CLI) skips E2E tests cleanly.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Unified Test Execution

**Goal:** `test-all` and `test-debug` run E2E tests alongside unit and integration tests.

**Components:**
- `test_all()` in `src/promptgrimoire/cli.py` — remove `-m "not e2e"` from default args
- `test_all_fixtures()` in `src/promptgrimoire/cli.py` — ensure server lifecycle applies
- Docstring updates for all three CLI commands to reflect unified execution

**Dependencies:** Phase 3 (fixtures must be adapted first)

**Done when:** `uv run test-all` runs the full suite (unit + integration + E2E) and passes. `uv run test-debug` includes E2E tests when depper selects them.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: LaTeX Test Prioritisation

**Goal:** LaTeX compilation tests are scheduled first so they start on xdist workers immediately, overlapping with fast tests on other workers.

**Components:**
- `pytest_collection_modifyitems` hook addition in `tests/conftest.py` — partitions `items` into latex-marked and non-latex, concatenates latex-first
- Verification that all LaTeX tests already carry `@pytest.mark.latex` (applied by `requires_latexmk` decorator)

**Dependencies:** Phase 4 (unified execution must work first)

**Done when:** `--durations=10` output shows LaTeX tests starting early in the run. Total wall-clock time for `test-all` is reduced compared to pre-prioritisation baseline.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Coverage Gap Tests

**Goal:** Add E2E tests for three gaps identified in the deprecated test audit: workspace isolation, tag color persistence, and keyboard shortcuts.

**Components:**
- Workspace isolation test in `tests/e2e/test_annotation_collab.py` — verify one user's highlights don't appear in a different workspace
- Tag color persistence test in `tests/e2e/test_annotation_highlights.py` — verify tag colors survive page reload
- Keyboard shortcut tests in `tests/e2e/test_annotation_basics.py` — Ctrl+H for highlight, Escape to deselect

**Dependencies:** Phase 4 (E2E tests must run in unified suite)

**Done when:** Three new E2E tests pass in `uv run test-all`, covering the identified gaps from the deprecated test audit.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Deprecated Test Cleanup

**Goal:** Audit deprecated tests against current coverage and clean up the deprecated directory.

**Components:**
- `tests/e2e/deprecated/` directory — review each file against current test coverage
- Remove tests whose logic is fully covered by current tests (23 confirmed covered + 9 partially covered from audit)
- Remove tests for dead demo pages (26 items testing raw-text CRDT pages that no longer exist)
- Skip tests blocked on #106 (file upload not yet implemented) — mark with `pytest.mark.skip(reason="Pending #106 file upload")`
- Remove `tests/e2e/deprecated/` directory if empty after cleanup

**Dependencies:** Phase 6 (coverage gaps must be filled first)

**Done when:** All deprecated tests are either migrated to current test files, confirmed covered by existing tests, or removed with justification. The deprecated directory is removed or contains only a README explaining any remaining items.
<!-- END_PHASE_7 -->

## Additional Considerations

**Server startup cost:** NiceGUI server startup is ~3-5s without DB, ~5-8s with DB. This is a fixed cost per test run, not per test. Acceptable given the current `test-all` baseline of 3+ minutes.

**Direct pytest usage:** Developers can still run `pytest tests/unit/ -n auto` directly without the CLI. E2E tests skip cleanly when `E2E_SERVER_URL` is absent. This preserves the existing fast-feedback loop for unit-only work.

**xdist_group fallback:** If Phase 1 reveals event loop contamination, the `xdist_group("e2e")` mitigation constrains E2E tests to one worker. With ~143 E2E test functions, this worker may become the bottleneck. Future optimisation could split E2E tests into multiple groups (e.g., `e2e-annotation`, `e2e-pdf`) to distribute across workers — but this is out of scope for this design.
