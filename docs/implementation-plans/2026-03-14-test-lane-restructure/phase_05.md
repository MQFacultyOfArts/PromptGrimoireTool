# Test Lane Restructure Implementation Plan

**Goal:** Restructure the test suite around a formal lane model with a `smoke` marker for toolchain-dependent tests.

**Architecture:** Define `smoke` pytest marker, propagate through decorator factories, exclude from default test runs. Each new lane is a `_run_pytest()` call producing a `LaneResult`.

**Tech Stack:** pytest, pytest-xdist, typer CLI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-lane-restructure.AC3: `e2e all` runs 6 lanes
- **test-lane-restructure.AC3.1 Success:** `e2e all` summary shows 6 named lanes (unit, integration, playwright, nicegui, smoke, blns+slow)
- **test-lane-restructure.AC3.2 Verify:** Total test count across all 6 lanes equals current 3,891

### test-lane-restructure.AC4: No regressions
- **test-lane-restructure.AC4.1 Success:** `e2e run`, `e2e slow`, `test changed`, `test run` behaviour unchanged

---

## Phase 5: Expand `e2e all` to 6 Lanes

<!-- START_TASK_1 -->
### Task 1: Narrow unit lane and add integration, smoke, blns+slow lanes

**Verifies:** test-lane-restructure.AC3.1, test-lane-restructure.AC3.2, test-lane-restructure.AC4.1

**Files:**
- Modify: `src/promptgrimoire/cli/e2e/__init__.py` (lines 135-183, `run_all_lanes()`)
- Modify: `.gitignore` (add new log file entries)

**Implementation:**

Modify `run_all_lanes()` to run 6 lanes sequentially, each producing a `LaneResult`:

**Lane 1 — Unit (narrowed):**
- Restrict to `tests/unit/` testpath
- Add `and not smoke` to marker expression
- Rename log to `test-unit.log`
- Keep xdist parallelisation

**Lane 2 — Integration (new):**
- Restrict to `tests/integration/` testpath
- Use `_NON_UI_MARKER_EXPRESSION` (same as current)
- Log to `test-integration.log`
- Use xdist parallelisation
- Keep `extra_env={"GRIMOIRE_TEST_SKIP_LATEXMK": "1"}`

**Lane 3 — Playwright (unchanged):**
- `run_playwright_lane(user_args, parallel=True, fail_fast=False, py_spy=False)`

**Lane 4 — NiceGUI (unchanged):**
- `run_nicegui_lane(user_args)`

**Lane 5 — Smoke (new):**
- No testpath restriction (smoke tests can be anywhere)
- Marker expression: `"smoke"`
- Override addopts: `"-o", "addopts="` to clear default exclusions
- Serial (no `-n` flag)
- Log to `test-smoke.log`

**Lane 6 — BLNS+Slow (new):**
- No testpath restriction
- Marker expression: `"(blns or slow) and not smoke"`
- Override addopts: `"-o", "addopts="` to clear default exclusions
- Serial (no `-n` flag)
- Log to `test-slow.log`

Update `.gitignore` to include new log files:
- `test-unit.log`
- `test-integration.log`
- `test-smoke.log`
- `test-slow.log`

Keep `test-all.log` in `.gitignore` for backwards compatibility (old log files may exist in working trees).

**Testing:**
- test-lane-restructure.AC3.1: `e2e all` summary shows all 6 named lanes
- test-lane-restructure.AC3.2: Total tests across all lanes equals 3,891
- test-lane-restructure.AC4.1: `e2e run`, `e2e slow`, `test changed`, `test run` behave unchanged

## UAT Steps

Before modifying run_all_lanes(), audit consumers of `test-all.log`:
1. Run: `grep -rn "test-all.log" .github/ Makefile 2>/dev/null || echo "No consumers found"`
2. Verify: No consumers, or document any found

After implementation:
3. Run: `uv run grimoire e2e all 2>&1 | grep -E "(unit|integration|playwright|nicegui|smoke|blns)"`
4. Verify: 6 lane names in summary output
5. Run: `uv run grimoire e2e all 2>&1 | tail -20`
6. Verify: Summary table with 6 lanes, all PASS

Regression check (AC4.1):
7. Run: `uv run grimoire e2e run -- --co -q 2>&1 | tail -3`
8. Verify: Collects E2E tests as before (unchanged)
9. Run: `uv run grimoire test changed 2>&1 | tail -3`
10. Verify: Runs or reports no changes (unchanged behaviour)
11. Run: `uv run grimoire test run tests/unit/test_settings.py -k "test_database_url_not_set" 2>&1 | tail -5`
12. Verify: Runs targeted test successfully (unchanged)
13. Run: `uv run grimoire e2e slow -- --co -q 2>&1 | tail -3`
14. Verify: Collects latexmk_full-marked tests as before (unchanged)
15. Run: `git status`
16. Verify: No new log files appear as untracked

## Evidence Required
- [ ] e2e all summary showing 6 lanes
- [ ] e2e run, e2e slow, test changed, test run regression checks passing
- [ ] git status clean of log files

**Commit:** `feat: expand e2e all to 6 lanes (unit, integration, playwright, nicegui, smoke, blns+slow)`
<!-- END_TASK_1 -->
