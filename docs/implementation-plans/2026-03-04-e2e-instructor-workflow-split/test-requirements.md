# Test Requirements: E2E Instructor Workflow Split

This document maps the acceptance criteria from the design plan to specific test implementations.

## e2e-instructor-workflow-split.AC1: Component Refactoring
- **AC1.1 Success:** `tests/e2e/test_instructor_workflow.py` is entirely deleted from the codebase.
  - **Type:** Operational
  - **Location:** File deleted in Phase 4.
- **AC1.2 Success:** The test suite passes in CI/CD without the monolithic file.
  - **Type:** Operational
  - **Location:** Run `uv run grimoire test all` and `uv run grimoire e2e run` in Phase 4.

## e2e-instructor-workflow-split.AC2: The "Glue" Happy Path E2E
- **AC2.1 Success:** `test_happy_path_workflow.py` successfully creates a course, activity, and single tag without database seeding.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_happy_path_workflow.py::TestHappyPathWorkflow::test_happy_path_workflow`
- **AC2.2 Success:** The test successfully enrolls a student who clicks "Start Activity" and applies the tag.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_happy_path_workflow.py::TestHappyPathWorkflow::test_happy_path_workflow`
- **AC2.3 Prevention:** The test proves that browser state correctly transitions between administrative setup and canvas interaction without state bleed.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_happy_path_workflow.py::TestHappyPathWorkflow::test_happy_path_workflow`

## e2e-instructor-workflow-split.AC3: Exhaustive Setup Integration Tests
- **AC3.1 Success:** `test_instructor_setup_ui.py` can exhaustively create, rename, and change colors for tags.
  - **Type:** Integration (`nicegui_user`)
  - **Location:** `tests/integration/test_instructor_template_ui.py`
- **AC3.2 Success:** The test successfully locks tags and reorders tag groups.
  - **Type:** Integration (`nicegui_user`)
  - **Location:** `tests/integration/test_instructor_template_ui.py`
- **AC3.3 Success:** The test exhaustively verifies course and activity creation edge cases.
  - **Type:** Integration (`nicegui_user`)
  - **Location:** `tests/integration/test_instructor_course_admin_ui.py`
- **AC3.4 Performance:** The test executes via `nicegui_user` without invoking a Playwright browser instance.
  - **Type:** Integration (`nicegui_user`)
  - **Location:** `tests/integration/conftest.py` (fixture creation)

## e2e-instructor-workflow-split.AC4: Exhaustive Canvas E2E
- **AC4.1 Success:** `test_annotation_canvas.py` successfully navigates to a pre-seeded workspace and applies a tag to text via the Playwright DOM.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_annotation_canvas.py::test_student_canvas_interactions`
- **AC4.2 Restriction:** The student persona is prevented from renaming a pre-seeded locked tag (input is readonly).
  - **Type:** E2E
  - **Location:** `tests/e2e/test_annotation_canvas.py::test_student_canvas_interactions`
- **AC4.3 Success:** The student persona successfully uses keyboard shortcuts to apply tags based on the instructor's custom sort order.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_annotation_canvas.py::test_student_canvas_interactions`
- **AC4.4 Success:** The instructor persona successfully threads a comment on a highlight and organises cards.
  - **Type:** E2E
  - **Location:** `tests/e2e/test_annotation_canvas.py::test_instructor_marking_interactions`
