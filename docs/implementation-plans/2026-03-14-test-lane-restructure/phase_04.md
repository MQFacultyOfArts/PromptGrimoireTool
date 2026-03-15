# Test Lane Restructure Implementation Plan

**Goal:** Restructure the test suite around a formal lane model with a `smoke` marker for toolchain-dependent tests.

**Architecture:** Define `smoke` pytest marker, propagate through decorator factories, exclude from default test runs. Each new lane is a `_run_pytest()` call producing a `LaneResult`.

**Tech Stack:** pytest, pytest-xdist, typer CLI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-lane-restructure.AC2: `test smoke` exists and works
- **test-lane-restructure.AC2.1 Success:** `test smoke` collects and runs all smoke-marked tests
- **test-lane-restructure.AC2.2 Success:** `test smoke` runs serial (no xdist)

### test-lane-restructure.AC4: No regressions
- **test-lane-restructure.AC4.2 Success:** `test all-fixtures` produces command-not-found error

---

## Phase 4: Add `test smoke` Command and Remove `all-fixtures`

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add test smoke command

**Verifies:** test-lane-restructure.AC2.1, test-lane-restructure.AC2.2

**Files:**
- Modify: `src/promptgrimoire/cli/testing.py` (add `smoke_tests()` after `all_tests()`, before `all_fixtures_tests()`)
- Modify: `tests/unit/test_cli_testing.py` (add tests for the new `smoke` subcommand)

**Implementation:**

First, add tests for the smoke command to `tests/unit/test_cli_testing.py` (TDD — tests before implementation):
- Test that `smoke` is a registered subcommand (help text includes it)
- Test that the smoke command collects smoke-marked tests
- Test that no `-n` flag appears in the default args (serial execution)

Follow the existing test patterns in `test_cli_testing.py` for how other subcommands are tested.

Then implement:

Add a new typer command `smoke` on `test_app`. Follow the same pattern as `all_fixtures_tests()` (serial, no xdist):

1. Decorator: `@test_app.command("smoke", context_settings={...})`
2. Parameters: same `filter_expr`, `exit_first`, `failed_first` options as other commands
3. Docstring: `"""Run toolchain smoke tests (pandoc, lualatex, tlmgr) serially."""`
4. `default_args`: `["-m", "smoke", "-v", "--tb=short", "-o", "addopts="]`
   - The `-o addopts=` override is critical: it clears the default `addopts` which excludes `smoke` via `-m 'not blns and not slow and not perf and not smoke'`. Without this, pytest would AND the two marker expressions and collect 0 tests.
5. `log_path`: `Path("test-smoke.log")`
6. No `extra_env` needed

**Testing:**
- test-lane-restructure.AC2.1: `test smoke --co` collects all smoke-marked tests (~30)
- test-lane-restructure.AC2.2: No `-n` flag in default_args means serial execution

## UAT Steps
1. Run: `uv run pytest tests/unit/test_cli_testing.py -k "smoke" -v 2>&1 | tail -10`
2. Verify: New smoke command tests pass
3. Run: `uv run grimoire test smoke -- --co -q 2>&1 | tail -5`
4. Verify: ~30 tests collected
5. Run: `uv run grimoire test smoke 2>&1 | tail -5`
6. Verify: Tests run serially (no xdist worker output), all pass or skip

## Evidence Required
- [ ] CLI test output showing smoke command tests pass
- [ ] Smoke test collection count
- [ ] Serial execution confirmed (no xdist output)

**Commit:** `feat: add test smoke command for toolchain-dependent tests`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove all-fixtures command and its tests

**Verifies:** test-lane-restructure.AC4.2

**Files:**
- Modify: `src/promptgrimoire/cli/testing.py` (delete `all_fixtures_tests()` function, lines 561-590)
- Modify: `tests/unit/test_cli_testing.py` (remove test functions for `all-fixtures`, approximately lines 495-550)
- Modify: `.gitignore` (remove `test-all-fixtures.log` entry, line 44)

**Implementation:**

1. Delete the entire `all_fixtures_tests()` function from `testing.py`
2. In `test_cli_testing.py`, remove all test functions that reference `all-fixtures` or `all_fixtures` (approximately 4 test functions)
3. Remove `test-all-fixtures.log` from `.gitignore`
4. Do NOT update `docs/testing.md` here — that happens in Phase 6

**Testing:**
- test-lane-restructure.AC4.2: `test all-fixtures` should produce a command-not-found error

## UAT Steps
1. Run: `uv run grimoire test all-fixtures 2>&1`
2. Verify: Error message (no such command / usage error)
3. Run: `uv run grimoire test all 2>&1 | tail -3`
4. Verify: Tests still pass (regression check)
5. Run: `uv run pytest tests/unit/test_cli_testing.py -v 2>&1 | tail -10`
6. Verify: All remaining CLI tests pass, no references to all-fixtures

## Evidence Required
- [ ] Error output from test all-fixtures
- [ ] test all passing
- [ ] CLI tests passing without all-fixtures references

**Commit:** `chore: remove obsolete test all-fixtures command`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
