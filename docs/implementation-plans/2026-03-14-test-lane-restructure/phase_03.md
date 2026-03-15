# Test Lane Restructure Implementation Plan

**Goal:** Restructure the test suite around a formal lane model with a `smoke` marker for toolchain-dependent tests.

**Architecture:** Define `smoke` pytest marker, propagate through decorator factories, exclude from default test runs. Each new lane is a `_run_pytest()` call producing a `LaneResult`.

**Tech Stack:** pytest, pytest-xdist, typer CLI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-lane-restructure.AC1: `test all` runs unit-only
- **test-lane-restructure.AC1.1 Success:** `test all` collects tests only from `tests/unit/`
- **test-lane-restructure.AC1.2 Success:** `test all` excludes smoke-marked tests
- **test-lane-restructure.AC1.3 Verify:** `test all` wall-clock time is measurably faster than current 13.5s

---

## Phase 3: Narrow `test all` to Unit-Only

<!-- START_TASK_1 -->
### Task 1: Restrict test all to tests/unit and exclude smoke

**Verifies:** test-lane-restructure.AC1.1, test-lane-restructure.AC1.2, test-lane-restructure.AC1.3

**Files:**
- Modify: `src/promptgrimoire/cli/testing.py` (lines 48-49 for marker expression, lines 522-558 for `all_tests()`)

**Implementation:**

1. Update `_TEST_ALL_MARKER_EXPRESSION` (line 49) to add `and not smoke`:
   ```python
   _TEST_ALL_MARKER_EXPRESSION = f"{_NON_UI_MARKER_EXPRESSION} and not latexmk_full and not smoke"
   ```

2. In `all_tests()`, add `"tests/unit"` as a positional arg in `default_args` to restrict testpath. This overrides `pyproject.toml`'s `testpaths` for this invocation only.

3. Update the `title` to reflect the new scope (unit-only, not unit+integration).

4. The `log_path` stays as `test-all.log` (renaming happens in Phase 5 when `e2e all` takes over).

**Testing:**
- test-lane-restructure.AC1.1: Verify `test all --co` only shows tests from `tests/unit/`
- test-lane-restructure.AC1.2: Verify smoke-marked tests are excluded from collection
- test-lane-restructure.AC1.3: Measure wall-clock time and compare to baseline 13.5s

## UAT Steps
1. Run: `uv run grimoire test all -- --co -q 2>&1 | head -10`
2. Verify: All paths start with `tests/unit/`
3. Run: `uv run grimoire test all -- --co -q 2>&1 | grep -c "tests/integration/"`
4. Verify: 0 integration tests collected
5. Run: `uv run grimoire test all 2>&1 | tail -3`
6. Verify: Fewer tests than 3,891, wall-clock time < 13.5s

## Evidence Required
- [ ] Collection output showing only tests/unit/ paths
- [ ] Zero integration tests in collection
- [ ] test all output showing reduced count and faster time

**Commit:** `feat: narrow test all to unit-only, exclude smoke tests`
<!-- END_TASK_1 -->
