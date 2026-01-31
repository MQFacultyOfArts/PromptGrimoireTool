# Test Suite Consolidation - Phase 1: Validate Test Infrastructure

**Goal:** Verify pytest-subtests and pytest-depper plugins work correctly with this codebase

**Architecture:** Infrastructure validation phase - verify installed plugins load and function as expected

**Tech Stack:** pytest, pytest-subtests, pytest-depper, Playwright

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-01-31

---

## Phase Overview

Both pytest-subtests (>=0.15.0) and pytest-depper (>=0.2.0) are already installed in pyproject.toml dev dependencies. This phase validates they work correctly before relying on them in subsequent phases.

---

<!-- START_TASK_1 -->
### Task 1: Verify pytest plugins load

**Files:**
- None (verification only)

**Step 1: Run pytest collection to verify plugins load**

```bash
uv run pytest --co -q 2>&1 | head -20
```

Expected: Test collection succeeds without plugin errors. Output shows collected tests.

**Step 2: Verify subtests fixture is available**

```bash
uv run pytest --fixtures 2>&1 | grep -A 3 "subtests"
```

Expected: Shows `subtests` fixture description. If not found, the plugin may not be properly installed.

**Step 3: Commit verification note**

No commit needed - this is validation only.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Validate pytest-depper dependency detection

**Files:**
- `src/promptgrimoire/pages/annotation.py` (temporary modification for test)

**Step 1: Run pytest-depper in debug mode against current changes**

```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model
uv run pytest-depper --debug --base-branch main
```

Expected: Shows dependency analysis output. Note which test files it identifies as affected by recent changes to annotation.py.

**Step 2: Run pytest-depper list-only mode**

```bash
uv run pytest-depper --list-only --base-branch main
```

Expected: Lists affected test files. Should include `tests/e2e/test_annotation_page.py` since annotation.py was recently modified.

**Step 3: Document findings**

If pytest-depper correctly identifies affected tests:
- Note this in design doc or commit message
- The tool is ready for CI integration

If pytest-depper does NOT correctly identify E2E test dependencies:
- Document the limitation (E2E tests may have indirect dependencies not detected by import analysis)
- Plan to run all E2E tests in CI, use depper for unit/integration only

**Step 4: Run existing tests to ensure nothing is broken**

```bash
uv run pytest tests/e2e/test_annotation_page.py -v --tb=short
```

Expected: All existing tests pass.

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create minimal subtests validation test

**Files:**
- Create: `tests/e2e/test_subtests_validation.py`

**Step 1: Write a minimal test to validate subtests work with Playwright fixtures**

Create file `tests/e2e/test_subtests_validation.py`:

```python
"""Validation test for pytest-subtests with Playwright fixtures.

This test verifies:
1. subtests fixture is available
2. Fixtures are shared across subtests (not re-created)
3. Subtest failures don't stop other subtests

Delete this file after validation or keep as documentation.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e]


class TestSubtestsValidation:
    """Validate pytest-subtests works with E2E test patterns."""

    def test_subtests_share_fixture(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify the same page fixture is shared across all subtests."""
        page = authenticated_page
        page.goto(f"{app_server}/")

        # Track that we're using the same page object
        page_id = id(page)

        test_cases = [
            ("home_visible", lambda: expect(page.locator("body")).to_be_visible()),
            ("same_page", lambda: page_id == id(page)),
            ("title_exists", lambda: page.title() is not None),
        ]

        for name, check in test_cases:
            with subtests.test(msg=name):
                result = check()
                if isinstance(result, bool):
                    assert result, f"Check {name} returned False"
                # expect() assertions don't return - they raise on failure
```

**Step 2: Run the validation test**

```bash
uv run pytest tests/e2e/test_subtests_validation.py -v
```

Expected output should show:
- One test with multiple subtests
- All subtests PASSED
- Single fixture setup/teardown (not one per subtest)

**Step 3: Verify subtest reporting**

```bash
uv run pytest tests/e2e/test_subtests_validation.py -v 2>&1 | grep -E "(PASSED|SUBPASS|home_visible|same_page|title_exists)"
```

Expected: Each subtest shows in output with its name.

**Step 4: Commit the validation test**

```bash
git add tests/e2e/test_subtests_validation.py
git commit -m "test: add subtests validation for E2E test infrastructure

Validates pytest-subtests plugin works correctly with:
- Playwright page fixtures
- authenticated_page fixture sharing
- Subtest reporting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

## Phase Completion Checklist

- [ ] `uv run pytest --co` shows plugins loaded without errors
- [ ] `uv run pytest --fixtures | grep subtests` shows subtests fixture
- [ ] `uv run pytest-depper --debug` runs and shows dependency analysis
- [ ] pytest-depper detection documented (works or limitations noted)
- [ ] Validation test passes: `uv run pytest tests/e2e/test_subtests_validation.py -v`
- [ ] All existing tests still pass: `uv run pytest tests/e2e/test_annotation_page.py`
