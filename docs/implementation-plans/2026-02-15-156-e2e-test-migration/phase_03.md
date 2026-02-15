# E2E Test Migration Implementation Plan — Phase 3

**Goal:** Create persona-based E2E test for the instructor course setup workflow.

**Architecture:** New `test_instructor_workflow.py` with narrative subtests covering course creation through template editing and copy protection. New `course_helpers.py` module for course/activity setup helpers reusable by later phases. All interactions require authentication first. Locators use Playwright role/text-based selectors (no `data-testid` in courses.py).

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 3 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.1 Success:** `test_instructor_workflow.py` exists and passes, covering course creation through template editing and copy protection configuration
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add email parameter to _authenticate_page()

**Verifies:** None (infrastructure change enabling Task 3)

**Files:**
- Modify: `tests/e2e/conftest.py:113-121`

**Implementation:**

Add an optional `email` parameter to `_authenticate_page()` so callers can authenticate as a specific role (e.g. `instructor@uni.edu` for instructor role). When no email is provided, the existing UUID-based random email behaviour is preserved.

Current signature:
```python
def _authenticate_page(page: Page, app_server: str) -> None:
```

New signature:
```python
def _authenticate_page(page: Page, app_server: str, *, email: str | None = None) -> None:
```

When `email` is `None`, generate the UUID-based email as before. When `email` is provided, use it directly (skip UUID generation). The rest of the function remains identical.

Also update the `authenticated_page` fixture (lines 76-110) to pass `email` through if needed — but since the fixture is for general student auth, it continues using the default `None` (random email). The fixture itself doesn't change; only `_authenticate_page` does.

**Important:** Tests needing role-specific auth (e.g. instructor) must create their own browser context and call `_authenticate_page()` directly with the `email` parameter — they should NOT use the `authenticated_page` fixture, which always authenticates as a random student.

**Testing:**
- Existing tests using `authenticated_page` fixture continue to work (default behaviour unchanged)
- Manual verification: `_authenticate_page(page, app_server, email="instructor@uni.edu")` authenticates with instructor role

**Verification:**
Run: `uv run pytest tests/e2e/test_browser_gate.py -v -x --timeout=30 -m e2e` (quick smoke test using auth)
Expected: Existing auth-dependent tests still pass

**Commit:** `fix(e2e): add email parameter to _authenticate_page for role-specific auth`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create course_helpers.py

**Verifies:** None (helper module enabling Task 3 and Phases 4-5)

**Files:**
- Create: `tests/e2e/course_helpers.py`

**Implementation:**

Create a helper module with functions for course/activity CRUD via the UI. All functions expect an **already-authenticated** page. Key helpers:

**`create_course(page, app_server, *, code, name, semester)`** — Navigate to `/courses/new`, fill the code/name/semester fields, submit. Wait for the course page to load (URL should contain the course ID or redirect to course detail). Return after course detail page is visible.

**`add_week(page, *, week_number, title)`** — On the course detail page, click "Add Week" button, fill week_number and title in the dialog, submit. Wait for the week card to appear.

**`add_activity(page, *, title, description="")`** — On the course detail page within a week section, click "Add Activity" button, fill title and optional description in the dialog, submit. Wait for the activity to appear in the week.

**`configure_course_copy_protection(page, *, enabled)`** — Open course settings dialog, toggle the copy protection switch to match `enabled`, close the dialog.

**`publish_week(page, week_title)`** — Find the week card matching `week_title`, click the "Publish" button on it.

All helpers use `page.get_by_role()`, `page.get_by_placeholder()`, and `page.get_by_text()` locators — no `data-testid` attributes exist in `courses.py`. Each helper should include reasonable timeouts and wait for UI feedback (e.g. dialog close, element visibility).

The helper functions should follow the pattern in `annotation_helpers.py`: type-hinted, docstrings, `from __future__ import annotations`, `TYPE_CHECKING` guard for `Page`.

**Testing:**
- No standalone tests — helpers are verified by their consumers (Task 3 and Phases 4-5)

**Verification:**
Run: `uv run ruff check tests/e2e/course_helpers.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat(e2e): add course_helpers.py with course/activity setup functions`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create test_instructor_workflow.py

**Verifies:** 156-e2e-test-migration.AC3.1, 156-e2e-test-migration.AC3.6, 156-e2e-test-migration.AC4.1, 156-e2e-test-migration.AC4.2, 156-e2e-test-migration.AC5.1, 156-e2e-test-migration.AC5.2

**Files:**
- Create: `tests/e2e/test_instructor_workflow.py`

**Implementation:**

Create a single narrative test class with one test method using `pytest-subtests` for discrete checkpoints. The test authenticates as an instructor and walks through the complete course setup flow.

**Authentication:** Use `_authenticate_page(page, app_server, email="instructor@uni.edu")` from `conftest.py`. The mock auth grants `["stytch_member", "instructor"]` roles to this email.

**Narrative flow with subtests:**

1. **`subtest: authenticate_as_instructor`** — Authenticate with `instructor@uni.edu`, navigate to `/courses`, verify the page loads and shows course management UI.

2. **`subtest: create_course`** — Use `create_course()` helper. Create a course with a unique code (include UUID fragment for xdist isolation). Verify the course detail page shows the course name.

3. **`subtest: add_week`** — Use `add_week()` helper. Add "Week 1" to the course. Verify the week card appears.

4. **`subtest: create_activity`** — Use `add_activity()` helper. Add an activity (e.g. "Annotate Becky"). Verify the activity appears in the week.

5. **`subtest: configure_copy_protection`** — Use `configure_course_copy_protection()` helper. Toggle course-level copy protection on. Verify the setting is applied (dialog shows switch in expected state after reopening, or a visual indicator appears).

6. **`subtest: edit_template_workspace`** — Click on the activity to open its template workspace. The workspace should load in annotation view. Use `setup_workspace_with_content()` pattern: fill content in the text area, submit, confirm content type, wait for `_textNodes` readiness. Verify the document content is visible in `#doc-container`.

7. **`subtest: publish_week`** — Navigate back to the course page. Use `publish_week()` helper. Verify the week status changes (button text changes from "Publish" to "Unpublish" or similar visual indicator).

**Isolation:** The test creates a fresh course with a UUID-suffixed code. No shared database state. Each test run creates its own course/week/activity/workspace.

**Constraints from AC4:** No `CSS.highlights` assertions. No `page.evaluate()` for internal DOM state. All assertions use Playwright locators checking user-visible text, button labels, and element visibility.

**Testing:**
- 156-e2e-test-migration.AC3.1: `test_instructor_workflow.py` exists and passes all subtests
- 156-e2e-test-migration.AC3.6: Test uses `subtests.test(msg=...)` for each checkpoint
- 156-e2e-test-migration.AC4.1: `grep "CSS.highlights" tests/e2e/test_instructor_workflow.py` returns no matches
- 156-e2e-test-migration.AC4.2: `grep "page.evaluate" tests/e2e/test_instructor_workflow.py` returns no matches (or only for user-visible text content checks)
- 156-e2e-test-migration.AC5.1: Test creates its own course/workspace, no fixture sharing
- 156-e2e-test-migration.AC5.2: Course code includes UUID, no cross-test DB dependency

**Verification:**
Run: `uv run pytest tests/e2e/test_instructor_workflow.py -v -x --timeout=120 -m e2e`
Expected: All subtests pass; instructor can create course, add week/activity, configure copy protection, edit template, and publish

**Commit:** `feat(e2e): add test_instructor_workflow.py persona test (AC3.1)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
