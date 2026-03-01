# Documentation Platform Implementation Plan — Phase 2

**Goal:** Replace rodney/showboat subprocess invocation in `make_docs()` with Playwright browser launch and Python guide function calls.

**Architecture:** Refactor `make_docs()` in `cli.py` to launch Playwright (sync API, 1280x800 viewport), import and call guide functions directly instead of invoking bash scripts via subprocess, and clean up rodney/showboat dependency checks. Retain existing server lifecycle (`_start_e2e_server`, `_stop_e2e_server`) and DB cleanup (`_pre_test_db_cleanup`).

**Tech Stack:** Python 3.14, Playwright sync API

**Scope:** 6 phases from original design (phase 2 of 6)

**Codebase verified:** 2026-02-28

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-platform-208.AC4: make_docs() orchestrates the full pipeline
- **docs-platform-208.AC4.1 Success:** `uv run make-docs` starts the NiceGUI server with mock auth, launches Playwright, runs guides, and stops both on completion
- **docs-platform-208.AC4.2 Success:** Instructor guide runs before student guide (student depends on data created by instructor)
- **docs-platform-208.AC4.3 Success:** Pipeline produces both markdown files and all screenshots in the expected output directories
- **docs-platform-208.AC4.4 Failure:** If a guide function raises an exception, `make_docs()` exits non-zero (integration test property)
- **docs-platform-208.AC4.5 Failure:** If pandoc is not on PATH, `make_docs()` exits with a clear error message before starting the server

### docs-platform-208.AC8: Old pipeline fully replaced (partial — production code only)
- **docs-platform-208.AC8.1 Success:** No references to `rodney` or `showboat` remain in production code or `pyproject.toml`

---

<!-- START_TASK_1 -->
### Task 1: Remove showboat from dev dependencies

**Files:**
- Modify: `pyproject.toml` (line 182)

**Step 1: Remove showboat dependency**

Delete the line `"showboat>=0.6",` from the `[dependency-groups] dev` list in `pyproject.toml`.

**Step 2: Verify operationally**

Run: `uv sync`
Expected: Dependencies install without errors. Showboat is no longer resolved.

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: remove showboat from dev dependencies"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Refactor make_docs() to use Playwright

**Verifies:** docs-platform-208.AC4.1, docs-platform-208.AC4.2, docs-platform-208.AC4.3, docs-platform-208.AC4.4, docs-platform-208.AC4.5, docs-platform-208.AC8.1

**Files:**
- Modify: `src/promptgrimoire/cli.py` (lines 2596–2694, the `make_docs()` function)
- Test: `tests/unit/test_make_docs.py` (unit — update existing tests)

**Implementation:**

Refactor `make_docs()` at `src/promptgrimoire/cli.py:2596` to:

1. **Dependency check:** Remove rodney and showboat checks. Keep only the pandoc check (AC4.5). If pandoc is missing, print a clear error message and `sys.exit(1)` before starting the server.

2. **DB cleanup and server start:** Keep existing `_pre_test_db_cleanup()` call and `_start_e2e_server(port)` pattern (already works correctly).

3. **Playwright launch:** After server is ready, launch Playwright sync API:
   ```python
   from playwright.sync_api import sync_playwright

   pw = sync_playwright().start()
   browser = pw.chromium.launch()
   page = browser.new_page(viewport={"width": 1280, "height": 800})
   ```

4. **Guide execution:** Import and call guide functions sequentially. For now (Phase 2), create stub guide functions that produce minimal output:
   ```python
   from promptgrimoire.docs.scripts.instructor_setup import run_instructor_guide
   from promptgrimoire.docs.scripts.student_workflow import run_student_guide

   run_instructor_guide(page, base_url)  # Runs first (AC4.2)
   run_student_guide(page, base_url)     # Runs second
   ```
   Create stub functions in `src/promptgrimoire/docs/scripts/instructor_setup.py` and `src/promptgrimoire/docs/scripts/student_workflow.py` that take `(page: Page, base_url: str)` and use the Guide DSL to produce a minimal markdown file with one step. These stubs will be replaced with real implementations in Phases 3 and 4.

   **Note on import path:** Guide scripts live in `src/promptgrimoire/docs/scripts/` (within the `promptgrimoire` package) rather than `docs/guides/scripts/` because `pyproject.toml` only includes `src/promptgrimoire` in `packages`. The `docs/` directory is not on the Python import path, so imports from `docs.guides.scripts` would fail at runtime. The design plan's `docs/guides/scripts/` path is the *output* directory for generated markdown and screenshots; the *source code* for guide scripts belongs in the package.

5. **Cleanup:** In a `finally` block:
   - Close browser: `browser.close()`
   - Stop Playwright: `pw.stop()`
   - Stop server: `_stop_e2e_server(process)`
   - Clear env vars

6. **Error handling:** If a guide function raises an exception, let it propagate (the `finally` block handles cleanup). The non-zero exit is automatic from the unhandled exception (AC4.4).

Remove all rodney-related code: the `rodney start --local` subprocess call, rodney stop, `ROD_TIMEOUT` environment setup, and the rodney dependency check. Remove showboat references.

**Testing:**

Tests must verify each AC:
- docs-platform-208.AC4.1: Mock Playwright (`sync_playwright`) and verify the function calls `chromium.launch()`, `new_page(viewport=...)`, guide functions, and cleanup in order
- docs-platform-208.AC4.2: Verify instructor guide is called before student guide (use `unittest.mock.call_args_list` ordering)
- docs-platform-208.AC4.3: With mocked guides that create output files, verify markdown and screenshot directories exist after `make_docs()` completes
- docs-platform-208.AC4.4: Mock a guide function to raise an exception. Verify `make_docs()` exits non-zero (or raises)
- docs-platform-208.AC4.5: Mock `shutil.which("pandoc")` to return `None`. Verify `make_docs()` exits with error before starting server

Update existing test classes in `tests/unit/test_make_docs.py`:
- Remove `TestMakeDocsRodneyLifecycle` — rodney is gone
- Remove rodney/showboat from `TestMakeDocsDependencyChecks` — only pandoc check remains
- Update `TestMakeDocsServerLifecycle` to verify Playwright launch instead of rodney
- Update `TestMakeDocsErrorReporting` to verify guide function exception handling

**Verification:**

Run: `uv run pytest tests/unit/test_make_docs.py -v`
Expected: All tests pass

**Commit:** `feat: refactor make_docs() to use Playwright instead of rodney/showboat`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create stub guide functions

**Files:**
- Create: `src/promptgrimoire/docs/scripts/__init__.py`
- Create: `src/promptgrimoire/docs/scripts/instructor_setup.py`
- Create: `src/promptgrimoire/docs/scripts/student_workflow.py`

**Implementation:**

Create `src/promptgrimoire/docs/scripts/__init__.py` as an empty package init.

Create `src/promptgrimoire/docs/scripts/instructor_setup.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide

GUIDE_OUTPUT_DIR = Path("docs/guides")


def run_instructor_guide(page: Page, base_url: str) -> None:
    """Instructor setup guide — stub for Phase 2, replaced in Phase 3."""
    with Guide("Instructor Setup", GUIDE_OUTPUT_DIR, page) as guide:
        with guide.step("Placeholder") as g:
            g.note("This is a stub guide. Full content will be added in Phase 3.")
```

Create `src/promptgrimoire/docs/scripts/student_workflow.py` with the same pattern, referencing Phase 4.

**Step 2: Verify operationally**

Run: `uv run python -c "from promptgrimoire.docs.scripts.instructor_setup import run_instructor_guide; print('Import OK')"`
Expected: Prints "Import OK"

**Step 3: Commit**

```bash
git add src/promptgrimoire/docs/scripts/__init__.py src/promptgrimoire/docs/scripts/instructor_setup.py src/promptgrimoire/docs/scripts/student_workflow.py
git commit -m "feat: add stub guide functions for Playwright-based make_docs()"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite to verify no regressions

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `uv run test-all`
Expected: All tests pass, no regressions from make_docs() refactoring

**Step 2: Run linting and type checking**

Run: `uv run ruff check .`
Expected: No errors

Run: `uvx ty check`
Expected: No errors

**Step 3: Commit (if any formatting changes occurred)**

Only if hooks modified files:
```bash
git add -u
git commit -m "chore: formatting fixes from Phase 2"
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
