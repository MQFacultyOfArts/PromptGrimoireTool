# E2E Test Suite Refactor: Phase 1 Implementation Plan

**Goal:** Implement the stripped-down, continuous workflow test to guard against state bleed.

**Architecture:** A new Playwright E2E test file that performs a complete happy-path run-through of the application without database seeding. An instructor creates a course, activity, and one tag, then a student clones it and applies the tag.

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 1 from original design.

**Codebase verified:** 2026-03-04

---

## Acceptance Criteria Coverage

This phase implements and tests:

### e2e-instructor-workflow-split.AC2: The "Glue" Happy Path E2E
- **e2e-instructor-workflow-split.AC2.1 Success:** `test_happy_path_workflow.py` successfully creates a course, activity, and single tag without database seeding.
- **e2e-instructor-workflow-split.AC2.2 Success:** The test successfully enrolls a student who clicks "Start Activity" and applies the tag.
- **e2e-instructor-workflow-split.AC2.3 Prevention:** The test proves that browser state correctly transitions between administrative setup and canvas interaction without state bleed.

---

<!-- START_TASK_1 -->
### Task 1: Create Happy Path E2E Test

**Verifies:** e2e-instructor-workflow-split.AC2.1, e2e-instructor-workflow-split.AC2.2, e2e-instructor-workflow-split.AC2.3

**Files:**
- Create: `tests/e2e/test_happy_path_workflow.py`

**Implementation:**
Implement a new Playwright test class `TestHappyPathWorkflow`.
Use the `browser` and `app_server` fixtures. Use `pytest_subtests` for checkpointing.
Do not use `_create_workspace_via_db`.
The workflow should be:
1. Authenticate as Instructor.
2. Create course, add week, add activity ("Happy Path Activity").
3. Click "Create Template", fill some placeholder text, save.
4. Using the Quick Create tag dialog, create a single tag "Mammals".
5. Go back, publish week, enrol student.
6. Authenticate as Student in a new browser context.
7. Navigate to course, click "Start Activity"
8. Highlight a word and apply the "Mammals" tag.
9. Verify the annotation card is created.

**Testing:**
Run the new file directly. Because this is the test file itself, the execution is the test.

**Verification:**
Run: `uv run grimoire e2e run -k test_happy_path_workflow`
Expected: The test passes cleanly.

**Commit:** `test: add happy path glue workflow test`
<!-- END_TASK_1 -->
