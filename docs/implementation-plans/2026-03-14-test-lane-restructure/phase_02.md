# Test Lane Restructure Implementation Plan

**Goal:** Restructure the test suite around a formal lane model with a `smoke` marker for toolchain-dependent tests.

**Architecture:** Define `smoke` pytest marker, propagate through decorator factories, exclude from default test runs. Each new lane is a `_run_pytest()` call producing a `LaneResult`.

**Tech Stack:** pytest, pytest-xdist, typer CLI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-lane-restructure.AC5: Misclassified tests fixed
- **test-lane-restructure.AC5.2 Success:** `TestEnsureDatabaseExistsIntegration` lives in `tests/integration/test_settings_db.py`

---

## Phase 2: Move Misclassified Integration Test

<!-- START_TASK_1 -->
### Task 1: Create tests/integration/test_settings_db.py with extracted class

**Verifies:** test-lane-restructure.AC5.2

**Files:**
- Create: `tests/integration/test_settings_db.py`
- Modify: `tests/unit/test_settings.py` (remove lines 560-661: `_get_test_db_url`, `_skip_no_pg`, and `TestEnsureDatabaseExistsIntegration`)

**Implementation:**

Create `tests/integration/test_settings_db.py` containing:
1. Module docstring explaining these are real PostgreSQL integration tests for database bootstrap
2. `pytestmark` module-level skip using `get_settings().dev.test_database_url` (matching integration test conventions)
3. A `_get_test_db_url()` helper (moved from test_settings.py)
4. The `TestEnsureDatabaseExistsIntegration` class with both methods (`test_creates_missing_database` and `test_idempotent_no_error_on_existing`)

The class uses `psycopg` directly (sync driver) — no async fixtures needed. Each test creates a unique temporary database, runs the assertion, and drops the database in a `finally` block.

Remove from `tests/unit/test_settings.py`:
- The `_get_test_db_url()` function (lines 560-568)
- The `_skip_no_pg` marker (lines 571-574)
- The entire `TestEnsureDatabaseExistsIntegration` class (lines 578-661)

Adopt `pytestmark` convention instead of `@_skip_no_pg` class decorator.

**Testing:**
- test-lane-restructure.AC5.2: Run the new file and verify both tests appear (pass with PostgreSQL, skip without)

## UAT Steps
1. Run: `uv run pytest tests/integration/test_settings_db.py -v`
2. Verify: 2 tests shown (passed or skipped depending on PostgreSQL availability)
3. Run: `uv run pytest tests/unit/test_settings.py -k "EnsureDatabase" --co -q`
4. Verify: `no tests ran` (class no longer in unit tests)
5. Run: `uv run grimoire test all 2>&1 | tail -3`
6. Verify: Tests pass

## Evidence Required
- [ ] pytest output showing 2 tests in new location
- [ ] pytest output showing 0 tests in old location
- [ ] test all passing

**Commit:** `refactor: move TestEnsureDatabaseExistsIntegration to tests/integration/`
<!-- END_TASK_1 -->
