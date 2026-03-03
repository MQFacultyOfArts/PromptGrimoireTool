# Word Count with Configurable Limits Implementation Plan

**Goal:** End-to-end verification of the full word count workflow.

**Architecture:** Three separate E2E test classes: settings UI, badge display/update, export enforcement. DB-driven workspace setup for speed and reliability. Uses existing E2E helpers for authentication, workspace creation, and PDF verification.

**Tech Stack:** Playwright, pytest-subtests, pymupdf

**Scope:** 6 phases from original design (phase 6 of 6)

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase verifies end-to-end:

### word-count-limits-47.AC3: Activity settings UI (E2E verification)
- **word-count-limits-47.AC3.1 Success:** Instructor can set word minimum via number input
- **word-count-limits-47.AC3.2 Success:** Instructor can set word limit via number input
- **word-count-limits-47.AC3.3 Success:** Word limit enforcement appears as tri-state select
- **word-count-limits-47.AC3.4 Success:** Course defaults page has toggle for default word limit enforcement
- **word-count-limits-47.AC3.5 Success:** Values persist across page reloads

### word-count-limits-47.AC4: Header badge display (E2E verification)
- **word-count-limits-47.AC4.1 Success:** Badge visible in header bar on all tabs when limits configured
- **word-count-limits-47.AC4.2 Success:** Badge hidden when no limits configured
- **word-count-limits-47.AC4.7 Success:** Badge updates live as student types

### word-count-limits-47.AC5: Export enforcement - soft mode (E2E verification)
- **word-count-limits-47.AC5.1 Success:** Export shows warning dialog
- **word-count-limits-47.AC5.2 Success:** User can confirm and proceed with export
- **word-count-limits-47.AC5.3 Success:** PDF shows snitch badge
- **word-count-limits-47.AC5.5 Edge:** Both min and max violated -- dialog shows both violations

### word-count-limits-47.AC6: Export enforcement - hard mode (E2E verification)
- **word-count-limits-47.AC6.1 Success:** Export blocked with dialog
- **word-count-limits-47.AC6.2 Success:** Dialog has no export button

---

<!-- START_TASK_1 -->
### Task 1: Create E2E helper for word count workspace setup

**Files:**
- Modify: `tests/e2e/annotation_helpers.py`

**Implementation:**

Add a helper function that creates a workspace with word count limits configured via DB:

```python
def _create_workspace_with_word_limits(
    user_email: str,
    html_content: str,
    *,
    word_minimum: int | None = None,
    word_limit: int | None = None,
    word_limit_enforcement: bool | None = None,
    default_word_limit_enforcement: bool = False,
) -> str:
    """Create workspace with word count limits configured on the activity."""
```

Follow the pattern from `_create_workspace_no_tag_permission()` (annotation_helpers.py:278-435):
- Create Course with `default_word_limit_enforcement`
- Create Week under Course
- Create Activity with `word_minimum`, `word_limit`, `word_limit_enforcement`
- Create Workspace placed in Activity
- Create WorkspaceDocument with html_content
- Grant ACL entry for user_email
- Return workspace_id

**Testing:**

Verified by E2E tests in subsequent tasks.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `test: add E2E helper for workspace with word count limits`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: E2E test for activity settings UI

**Verifies:** word-count-limits-47.AC3.1, word-count-limits-47.AC3.2, word-count-limits-47.AC3.3, word-count-limits-47.AC3.4, word-count-limits-47.AC3.5

**Files:**
- Create: `tests/e2e/test_word_count.py`

**Implementation:**

```python
@pytest.mark.e2e
class TestWordCountSettings:
    def test_activity_word_count_settings(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify word count settings can be configured via activity settings dialog."""
```

Test flow using subtests:
1. Create a course and activity via UI (using `course_helpers.create_course`, `add_week`, `add_activity`)
2. Open activity settings dialog: `page.get_by_test_id("activity-settings-btn").click()`
3. Set word minimum: `page.get_by_test_id("activity-word-minimum-input").fill("200")`
4. Set word limit: `page.get_by_test_id("activity-word-limit-input").fill("500")`
5. Set enforcement to Hard: click the select to open it, then click the option by testid:
   ```python
   page.get_by_test_id("activity-word_limit_enforcement-select").click()
   page.get_by_test_id("activity-word_limit_enforcement-opt-on").click()
   ```
6. Save: `page.get_by_test_id("save-activity-settings-btn").click()`
7. Reload page
8. Reopen activity settings and verify values persisted (AC3.5)
9. Navigate to course settings page (AC3.4):
   - Open course settings dialog
   - Verify `data-testid="course-default_word_limit_enforcement-switch"` is visible
   - Toggle it on, save, reload, verify it persisted

All interactions use `data-testid` locators per project convention.

**Verification:**

Run: `uv run grimoire e2e run -k TestWordCountSettings -x`
Expected: All subtests pass.

**Commit:** `test: add E2E tests for word count activity settings`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: E2E test for word count badge display and live update

**Verifies:** word-count-limits-47.AC4.1, word-count-limits-47.AC4.2, word-count-limits-47.AC4.7

**Files:**
- Modify: `tests/e2e/test_word_count.py`

**Implementation:**

```python
@pytest.mark.e2e
class TestWordCountBadge:
    def test_badge_visible_with_limits(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify word count badge appears and updates live."""
```

Test flow:
1. Create workspace with word_limit=100 via DB helper
2. Navigate to workspace
3. Verify badge visible in header: `page.get_by_test_id("word-count-badge")`
4. Switch to Respond tab: `page.get_by_test_id("tab-respond").click()`
5. Type text in editor using the existing `data-testid="milkdown-editor-container"` as scope: `page.get_by_test_id("milkdown-editor-container").locator("[contenteditable]").first.click(); page.keyboard.type("word " * 10)`
6. Wait for Yjs sync (brief timeout)
7. Verify badge text updated to show word count (AC4.7)
8. Switch to Annotate tab — verify badge still visible (AC4.1)

```python
    def test_badge_hidden_without_limits(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify badge hidden when no limits configured."""
```

Test flow:
1. Create workspace with no word limits
2. Navigate to workspace
3. Verify badge not present: `expect(page.get_by_test_id("word-count-badge")).not_to_be_visible()` (AC4.2)

**Verification:**

Run: `uv run grimoire e2e run -k TestWordCountBadge -x`
Expected: All tests pass.

**Commit:** `test: add E2E tests for word count badge display`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Badge visibility edge cases

**Verifies:** word-count-limits-47.AC4.1

**Files:**
- Modify: `tests/e2e/test_word_count.py`

**Testing:**

Additional badge tests:
- Workspace with word_minimum only (no word_limit) → badge visible
- Workspace with word_limit only (no word_minimum) → badge visible
- Badge text format verification: contains "Words:" and the limit number

**Verification:**

Run: `uv run grimoire e2e run -k TestWordCountBadge -x`
Expected: All tests pass.

**Commit:** `test: add badge edge case E2E tests`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: E2E test for soft export enforcement

**Verifies:** word-count-limits-47.AC5.1, word-count-limits-47.AC5.2, word-count-limits-47.AC5.3, word-count-limits-47.AC5.5

**Files:**
- Modify: `tests/e2e/test_word_count.py`

**Implementation:**

```python
@pytest.mark.e2e
class TestWordCountExport:
    def test_soft_enforcement_warning(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify soft enforcement shows warning and allows export."""
```

Test flow:
1. Create workspace with word_limit=10, word_limit_enforcement=False (soft)
2. Navigate and type 20+ words in Respond tab
3. Click Export PDF button
4. Verify warning dialog appears (AC5.1): `page.get_by_test_id("wc-export-anyway-btn")`
5. Click "Export Anyway" (AC5.2)
6. Download completes
7. If PDF mode: extract text, verify snitch badge text present (AC5.3)

Additional test for AC5.5 (both min and max violated):

```python
    def test_soft_enforcement_both_violations(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify dialog shows both violations when under minimum AND over limit."""
```

Test flow:
1. Create workspace with word_minimum=200, word_limit=500, word_limit_enforcement=False (soft)
2. Navigate and type only 5 words in Respond tab (under minimum, triggers under_minimum violation)
3. Click Export PDF button
4. Verify warning dialog appears mentioning "under the minimum"

**Note on AC5.5 "both violated":** When `word_minimum < word_limit` (enforced by AC2.5 validation), both violations cannot be True simultaneously — they are mutually exclusive. The "both violated" message formatting path is tested in Phase 5 Task 2 by constructing a `WordCountViolation` directly. This E2E test covers the under-minimum path; the over-limit path is covered by `test_soft_enforcement_warning` above.

**Verification:**

Run: `uv run grimoire e2e run -k test_soft_enforcement -x`
Expected: Test passes.

**Commit:** `test: add E2E test for soft export enforcement`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: E2E test for hard export enforcement

**Verifies:** word-count-limits-47.AC6.1, word-count-limits-47.AC6.2

**Files:**
- Modify: `tests/e2e/test_word_count.py`

**Implementation:**

```python
    def test_hard_enforcement_blocks(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify hard enforcement blocks export entirely."""
```

Test flow:
1. Create workspace with word_limit=10, word_limit_enforcement=True (hard)
2. Navigate and type 20+ words in Respond tab
3. Click Export PDF button
4. Verify blocking dialog appears (AC6.1): dialog with violation text
5. Verify NO export button in dialog (AC6.2): `expect(page.get_by_test_id("wc-export-anyway-btn")).not_to_be_visible()`
6. Verify dismiss button exists: `page.get_by_test_id("wc-dismiss-btn")`
7. Click dismiss — dialog closes, no download triggered

**Verification:**

Run: `uv run grimoire e2e run -k test_hard_enforcement -x`
Expected: Test passes.

**Commit:** `test: add E2E test for hard export enforcement`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_7 -->
### Task 7: Final E2E verification

**Files:**
- All E2E test files from this phase

**Step 1: Run all word count E2E tests**

Run: `uv run grimoire e2e run -k "WordCount or word_count" -x`
Expected: All tests pass.

**Step 2: Run full E2E suite to check for regressions**

Run: `uv run grimoire e2e run`
Expected: No regressions in existing E2E tests.

**Step 3: Verify no unit/integration regressions**

Run: `uv run grimoire test all`
Expected: All tests pass.

**Step 4: Verify commit history**

Run: `git log --oneline -8`
Expected: Clean commit history with conventional prefixes.
<!-- END_TASK_7 -->
