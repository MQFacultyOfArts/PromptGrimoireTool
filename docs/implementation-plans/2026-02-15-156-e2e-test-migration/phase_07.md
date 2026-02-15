# E2E Test Migration Implementation Plan — Phase 7

**Goal:** Create persona-based E2E test for adversarial student behaviour — security edge cases, copy protection enforcement, and dead-end navigation.

**Architecture:** New `test_naughty_student.py` with multiple test methods using `pytest-subtests`. Covers three threat categories: dead-end navigation (bad workspace IDs), content injection (BLNS/XSS pasted as content), and copy protection bypass attempts (copy, cut, drag, print interception). Copy protection test requires a full instructor-creates-course-with-protection flow followed by student cloning and bypass attempts. BLNS strings are defined inline as representative samples — no cross-boundary import from unit test conftest.

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 7 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.5 Success:** `test_naughty_student.py` exists and passes, covering BLNS/XSS content injection, copy protection bypass attempts, and dead-end navigation with subtests
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

### 156-e2e-test-migration.AC7: Issues closable (DoD 8)
- **156-e2e-test-migration.AC7.3 Success:** #101 evidence exists (CJK, RTL content works in translation student test; BLNS edge cases handled in naughty student test)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create test_naughty_student.py — dead-end navigation

**Verifies:** 156-e2e-test-migration.AC3.5 (partial), 156-e2e-test-migration.AC5.1

**Files:**
- Create: `tests/e2e/test_naughty_student.py`

**Implementation:**

Create the test file with the first test method for dead-end navigation.

**`test_dead_end_navigation(self, browser, app_server, subtests)`:**

Narrative: Naughty student tries to access workspaces that don't exist or with invalid IDs.

1. **`subtest: invalid_workspace_id`** — Create browser context, authenticate via `_authenticate_page()`. Navigate to `/annotation?workspace_id=not-a-valid-uuid`. Verify page shows error state — look for "Invalid workspace ID" text or "No workspace selected" UI element. Verify no crash (page doesn't show 500 error). Verify a "Create Workspace" button is visible (fallback UI).

2. **`subtest: nonexistent_workspace_id`** — Navigate to `/annotation?workspace_id=00000000-0000-0000-0000-000000000000` (valid UUID format but doesn't exist). Verify page shows "Workspace not found" text (red text in annotation.py:2885-2888). Verify a "Create New Workspace" button is visible.

3. **`subtest: no_workspace_id`** — Navigate to `/annotation` (no query parameter). Verify the page loads and shows the workspace creation UI (not a crash).

**Commit:** `feat(e2e): add test_naughty_student.py with dead-end navigation tests`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add BLNS/XSS content injection tests

**Verifies:** 156-e2e-test-migration.AC3.5 (partial), 156-e2e-test-migration.AC7.3 (partial)

**Files:**
- Modify: `tests/e2e/test_naughty_student.py`

**Implementation:**

Add test methods for content injection and resilience.

**`test_xss_injection_sanitised(self, browser, app_server, subtests)`:**

Narrative: Naughty student attempts XSS injection via pasted content.

1. **`subtest: script_tag_stripped`** — Create browser context, authenticate. Use `setup_workspace_with_content(page, app_server, '<script>alert("xss")</script>Safe text here')`. Verify `#doc-container` contains "Safe text here". Verify `#doc-container` does NOT contain "alert" or "script" (script tags stripped by input pipeline's `_STRIP_TAGS` frozenset in `html_input.py:34`). No JavaScript alert should have fired.

2. **`subtest: html_injection_escaped`** — Create new workspace with content `'<img src=x onerror=alert(1)>Normal text'`. Verify `#doc-container` contains "Normal text". Verify no JavaScript errors occurred (Playwright can listen for `page.on("pageerror")`).

**`test_blns_content_resilience(self, browser, app_server, subtests)`:**

Narrative: Naughty student pastes BLNS strings as content — system doesn't crash.

Define representative BLNS strings inline in the test file — do NOT import from `tests.unit.conftest` (cross-boundary import between e2e and unit test packages). Use a module-level dict with category → list of strings:

```python
BLNS_SAMPLES = {
    "script_injection": [
        '<script>alert("XSS")</script>',
        '"><img src=x onerror=alert(1)>',
        "javascript:alert('XSS')",
    ],
    "sql_injection": [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
    ],
    "two_byte_characters": [
        "田中さんにあげて下さい",
        "パーティーへ行かないか",
        "사765765765765",
    ],
}
```

For each category and string:

1. **`subtest: blns_{category}_{index}`** — Create workspace with the BLNS string as content. If the content type dialog appears, confirm it. If `_textNodes` readiness times out (some strings may produce empty documents after sanitisation), that's acceptable — the test verifies no crash, not that all content renders. Verify the page is still responsive (no infinite loop, no 500 error) by checking that a known UI element (e.g. the workspace header) is still visible.

2. **`subtest: blns_highlight_resilience`** — For strings that successfully render with `_textNodes.length > 0`, attempt to highlight the first few characters with `select_chars(page, 0, 2)` and create a highlight. Verify the annotation card appears (proves the annotation pipeline handles the naughty content).

**Commit:** `feat(e2e): add BLNS/XSS content injection tests to test_naughty_student`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add copy protection bypass tests

**Verifies:** 156-e2e-test-migration.AC3.5 (partial), 156-e2e-test-migration.AC5.2

**Files:**
- Modify: `tests/e2e/test_naughty_student.py`

**Implementation:**

Add a test method for copy protection bypass attempts. This test requires a full instructor-creates-course → student-clones-workspace flow.

**`test_copy_protection_bypass(self, browser, app_server, subtests)`:**

Narrative: Instructor creates a copy-protected course/activity. Student clones the workspace and attempts to bypass copy protection.

**Setup (instructor side):**
1. Create browser context for instructor. Authenticate with `_authenticate_page(page_instructor, app_server, email="instructor@uni.edu")` (instructor role).
2. Use `create_course()` helper (from `course_helpers.py` created in Phase 3) to create a course with a UUID-suffixed code for isolation.
3. Use the course settings to enable `default_copy_protection` — open settings dialog, toggle the switch on, close dialog.
4. Use `add_week()` to add a week.
5. Use `add_activity()` to add an activity (inherits copy protection from course).
6. Navigate to the activity's template workspace (click "Edit Template" button or equivalent). Add content via `setup_workspace_with_content()` pattern or directly fill the workspace.
7. Use `publish_week()` to make the week visible to students.
8. Extract the activity ID or the course URL for the student to access.

**Student attempts (student side):**
1. Create a separate browser context for the student. Authenticate with default random email (student role).
2. Navigate to the course page. Find the activity. Click "Start Activity" button to clone the template workspace. Wait for redirect to `/annotation?workspace_id=...`.
3. Wait for `_textNodes` readiness.

Now attempt bypass:

4. **`subtest: copy_blocked`** — Select text in `#doc-container` (e.g. `select_chars(page_student, 0, 5)`). Press `Control+c`. Verify the toast notification appears: `expect(page_student.locator(".q-notification")).to_contain_text("Copying is disabled", timeout=5000)`.

5. **`subtest: cut_blocked`** — Press `Control+x`. Verify the toast notification appears.

6. **`subtest: context_menu_blocked`** — Right-click on `#doc-container`. Verify the default context menu does NOT appear (the event is prevented). The toast notification should appear.

7. **`subtest: print_blocked`** — Press `Control+p`. Verify the toast notification appears (the print dialog should NOT open because the keydown event is intercepted).

8. **`subtest: protected_indicator_visible`** — Verify the "Protected" lock icon chip is visible in the workspace header: look for text "Protected" or a lock icon indicator.

**Cleanup:** Close both browser contexts.

**Isolation:** Course code includes UUID fragment. Student uses random email. No shared state.

**Commit:** `feat(e2e): add copy protection bypass tests to test_naughty_student`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
