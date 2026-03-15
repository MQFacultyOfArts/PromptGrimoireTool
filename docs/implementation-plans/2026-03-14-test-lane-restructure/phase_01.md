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
- **test-lane-restructure.AC5.1 Success:** All `@requires_pandoc` and `@requires_latexmk` decorated tests carry `smoke` marker

---

## Phase 1: Add Smoke Marker and Tag Tests

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Register smoke marker and update addopts exclusion

**Files:**
- Modify: `pyproject.toml` (lines 207-225)

**Implementation:**

Add `smoke` to the markers list in `[tool.pytest.ini_options]`:

```toml
markers = [
    "slow: marks tests as slow",
    "e2e: marks end-to-end tests",
    "nicegui_ui: marks NiceGUI UI tests",
    "blns: marks Big List of Naughty Strings tests",
    "perf: marks performance tests",
    "latex: marks tests requiring LaTeX",
    "latexmk_full: marks full LaTeX compilation tests",
    "cards: marks card-specific E2E tests",
    "browser_gate: marks browser gate tests",
    "skip_browserstack: marks tests to skip on BrowserStack",
    "smoke: marks tests requiring external toolchains (pandoc, lualatex, tlmgr)",
]
```

Update `addopts` to exclude `smoke`:

```toml
addopts = "-ra -q -m 'not blns and not slow and not perf and not smoke'"
```

## UAT Steps
1. Run: `uv run pytest --co -q -m smoke 2>&1 | tail -5`
2. Verify: `no tests ran` (marker registered but no tests tagged yet)
3. Run: `uv run pytest --co -q 2>&1 | tail -3`
4. Verify: Same count as before (~3891 tests)

## Evidence Required
- [ ] pytest --co output showing smoke marker registered
- [ ] Test count unchanged after marker registration

**Commit:** `chore: register smoke pytest marker and exclude from default addopts`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Centralise requires_pandoc and add smoke propagation to decorators

**Verifies:** test-lane-restructure.AC5.1

**Files:**
- Modify: `tests/conftest.py` (lines 99-166 area)
- Modify: `tests/unit/export/test_css_fidelity.py` (remove local requires_pandoc definition)
- Modify: `tests/unit/export/test_markdown_to_latex.py` (remove local requires_pandoc if present)
- Modify: any other files with local `requires_pandoc` definitions

**Implementation:**

In `tests/conftest.py`, add a `requires_pandoc()` decorator factory matching the existing `requires_latexmk()` pattern. It should:
1. Check if pandoc is installed (use `shutil.which("pandoc")`)
2. Apply `pytest.mark.skipif` if not found
3. Apply `pytest.mark.smoke` automatically

Also modify the existing `requires_latexmk()` to apply `pytest.mark.smoke` in addition to `pytest.mark.latex`.

And modify `requires_full_latexmk()` to also apply `pytest.mark.smoke`.

Then update all test files that define a local `requires_pandoc` marker to import from conftest instead. Pytest conftest fixtures and markers are auto-discovered, so the decorator will be available without explicit imports if defined at the right conftest level.

**Testing:**
- test-lane-restructure.AC5.1: Run `uv run pytest -m smoke --co -q` and verify all requires_pandoc and requires_latexmk decorated tests appear in the collection

## UAT Steps
1. Run: `uv run pytest -m smoke --co -q 2>&1 | tail -5`
2. Verify: ~30 tests collected (record exact count)
3. Run: `grep -rn "requires_pandoc = pytest.mark.skipif" tests/`
4. Verify: No results (all local definitions removed)
5. Run: `uv run grimoire test all 2>&1 | tail -3`
6. Verify: Count is reduced by smoke test count compared to pre-change baseline

## Evidence Required
- [ ] Smoke test collection count
- [ ] Grep confirming no local requires_pandoc definitions remain
- [ ] test all output showing reduced count

**Commit:** `feat: centralise requires_pandoc and propagate smoke marker through decorators`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Apply smoke marker to tests with custom toolchain checks

**Verifies:** test-lane-restructure.AC5.1

**Files:**
- Modify: `tests/unit/test_latex_environment.py` (line 30 area — `TestLaTeXEnvironment` class)
- Modify: `tests/unit/test_latex_packages.py` (line 73 area — `TestLaTeXPackages` class)
- Modify: `tests/unit/export/test_empty_content_guard.py` (line 125 area — `TestEmptyContentValueError` class)
- Modify: `tests/unit/input_pipeline/test_converters.py` (line 60 area — `TestConvertPdfToHtml` class)
- Modify: `tests/unit/input_pipeline/test_process_input.py` (line 130 area — `TestProcessInputPdf` class)

**Baseline (record before making changes):**
Run: `uv run pytest tests/unit/test_latex_environment.py tests/unit/test_latex_packages.py tests/unit/export/test_empty_content_guard.py tests/unit/input_pipeline/test_converters.py tests/unit/input_pipeline/test_process_input.py --co -q 2>&1 | tail -3`
Record the count — this is the number of tests that should gain the smoke marker.

**Implementation:**

These test classes use custom toolchain checks (e.g. `requires_tinytex` skipif) that are NOT covered by the centralised `requires_pandoc` or `requires_latexmk` decorators. Apply `@pytest.mark.smoke` directly at the class level.

For `test_latex_environment.py`: The class uses `@requires_tinytex` on individual methods. Add `@pytest.mark.smoke` at the class level to capture all methods.

For `test_latex_packages.py`: Already has `@pytest.mark.latex`. Add `@pytest.mark.smoke` alongside.

For the remaining three classes: Add `@pytest.mark.smoke` at class level.

**Testing:**
- test-lane-restructure.AC5.1: Verify all toolchain-dependent tests carry smoke marker

## UAT Steps
1. Run: `uv run pytest -m smoke --co -q 2>&1 | tail -5`
2. Verify: Total smoke count equals Task 2 count + baseline count recorded above
3. Run: `uv run grimoire test all 2>&1 | tail -3`
4. Verify: test all count + total smoke count = original 3,891 (minus integration tests moving in Phase 2)

## Evidence Required
- [ ] Baseline count from pre-change step
- [ ] Final smoke test collection count
- [ ] Arithmetic: test all + smoke = original total

**Commit:** `feat: apply smoke marker to custom-toolchain test classes`
<!-- END_TASK_3 -->
