# E2E Test Suite Refactor: Phase 2 Implementation Plan

**Goal:** Implement the complex UI edge case testing using `nicegui_user`.

**Architecture:** We will create two new integration tests using NiceGUI's `user_simulation` to exhaustively test Quasar UI dialogs (Course creation and Tag management) without the overhead of a Playwright browser. We will refactor the simulation setup from `test_crud_management_ui.py` into a reusable fixture in `tests/integration/conftest.py`.

**Tech Stack:** NiceGUI `user_simulation`, pytest, PostgreSQL via SQLAlchemy

**Scope:** Phase 2 from original design.

**Codebase verified:** 2026-03-04

---

## Acceptance Criteria Coverage

This phase implements and tests:

### e2e-instructor-workflow-split.AC3: Exhaustive Setup Integration Tests
- **e2e-instructor-workflow-split.AC3.1 Success:** `test_instructor_setup_ui.py` can exhaustively create, rename, and change colors for tags.
- **e2e-instructor-workflow-split.AC3.2 Success:** The test successfully locks tags and reorders tag groups.
- **e2e-instructor-workflow-split.AC3.3 Success:** The test exhaustively verifies course and activity creation edge cases.
- **e2e-instructor-workflow-split.AC3.4 Performance:** The test executes via `nicegui_user` without invoking a Playwright browser instance.

---

<!-- START_TASK_1 -->
### Task 1: Create reusable `nicegui_user` fixture

**Verifies:** e2e-instructor-workflow-split.AC3.4

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_crud_management_ui.py`

**Implementation:**
Extract the `user_simulation` context manager pattern currently isolated in `test_crud_management_ui.py` into an `@pytest_asyncio.fixture` named `nicegui_user` in `tests/integration/conftest.py`.
Update `test_crud_management_ui.py` to use the new fixture instead of managing the context block manually, ensuring it continues to pass.

**Testing:**
Run the existing CRUD UI test to ensure the refactored fixture works correctly.

**Verification:**
Run: `uv run grimoire test all -k test_crud_management_ui`
Expected: The existing test passes cleanly using the new fixture.

**Commit:** `test: extract nicegui_user fixture for integration tests`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement Course Admin UI Integration Test

**Verifies:** e2e-instructor-workflow-split.AC3.3, e2e-instructor-workflow-split.AC3.4

**Files:**
- Create: `tests/integration/test_instructor_course_admin_ui.py`

**Implementation:**
Create tests that use the `nicegui_user` fixture to test the `/courses` route.
1. Authenticate using the `mock-token-instructor@uni.edu` magic link.
2. Verify the Create Course dialog (validation on empty code/name, success path).
3. Verify adding a Week and publishing it.
4. Verify adding an Activity.
5. Verify toggling Course-level default copy protection in the settings dialog.
6. Verify Enrolling a student via the roster tab.

Use the established UI simulation patterns from `test_crud_management_ui.py` (e.g. `await user.open()`, `await _click_test_id(user, "...")`).

**Testing:**
Run the new integration test directly.

**Verification:**
Run: `uv run grimoire test all -k test_instructor_course_admin_ui`
Expected: The test passes cleanly.

**Commit:** `test: add course admin nicegui integration tests`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement Template Configuration UI Integration Test

**Verifies:** e2e-instructor-workflow-split.AC3.1, e2e-instructor-workflow-split.AC3.2, e2e-instructor-workflow-split.AC3.4

**Files:**
- Create: `tests/integration/test_instructor_template_ui.py`

**Implementation:**
Create tests that use the `nicegui_user` fixture to test the Tag Management dialogs on the `/annotation` route.
1. Use a database helper (like `create_course` and `add_activity_to_week` from `promptgrimoire.db`) to bypass UI setup and directly instantiate a course and activity template in the DB.
2. Authenticate as the instructor and navigate directly to the template workspace via `await user.open(f"/annotation?workspace_id={ws_id}")`.
3. Open the Tag Management dialog.
4. Verify creating a new tag group and tags.
5. Verify changing a tag color.
6. Verify clicking the lock icon toggles the readonly state.
7. Verify clicking the up/down arrows reorders the groups.
8. Use `import_tags_from_activity` DB helper to stage a second activity, and verify the "Import Tags" UI dropdown successfully pulls them in.

**Testing:**
Run the new integration test directly.

**Verification:**
Run: `uv run grimoire test all -k test_instructor_template_ui`
Expected: The test passes cleanly.

**Commit:** `test: add template configuration nicegui integration tests`
<!-- END_TASK_3 -->
