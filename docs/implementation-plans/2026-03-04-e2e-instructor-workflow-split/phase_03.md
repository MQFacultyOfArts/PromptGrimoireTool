# E2E Test Suite Refactor: Phase 3 Implementation Plan

**Goal:** Consolidate all complex JS/DOM interactions into a focused Playwright test.

**Architecture:** A comprehensive Playwright E2E test file focused solely on the Annotation Canvas. It uses database seeding to bypass all UI-based setup, immediately placing either an instructor or student into a fully populated workspace. It tests DOM-heavy interactions like the Custom Highlight API, TreeWalker boundaries, and keyboard shortcuts.

**Tech Stack:** Playwright, pytest, Python, PostgreSQL via SQLAlchemy

**Scope:** Phase 3 from original design.

**Codebase verified:** 2026-03-04

---

## Acceptance Criteria Coverage

This phase implements and tests:

### e2e-instructor-workflow-split.AC4: Exhaustive Canvas E2E
- **e2e-instructor-workflow-split.AC4.1 Success:** `test_annotation_canvas.py` successfully navigates to a pre-seeded workspace and applies a tag to text via the Playwright DOM.
- **e2e-instructor-workflow-split.AC4.2 Restriction:** The student persona is prevented from renaming a pre-seeded locked tag (input is readonly).
- **e2e-instructor-workflow-split.AC4.3 Success:** The student persona successfully uses keyboard shortcuts to apply tags based on the instructor's custom sort order.
- **e2e-instructor-workflow-split.AC4.4 Success:** The instructor persona successfully threads a comment on a highlight and organises cards.

---

<!-- START_TASK_1 -->
### Task 1: Implement Canvas E2E Test (Student View)

**Verifies:** e2e-instructor-workflow-split.AC4.1, e2e-instructor-workflow-split.AC4.2, e2e-instructor-workflow-split.AC4.3

**Files:**
- Create: `tests/e2e/test_annotation_canvas.py`

**Implementation:**
Create a test class `TestAnnotationCanvas`.
Implement `test_student_canvas_interactions(authenticated_page, app_server)`:
1. Use `_create_workspace_via_db` to inject a workspace with `seed_tags=True`.
2. Navigate to `/annotation?workspace_id=...`
3. Verify the "Jurisdiction" tag (which is seeded as locked) shows a lock icon in the Tag Management dialog, and the input has the `readonly` attribute.
4. Verify keyboard shortcuts: select text using `select_chars` and press "2" or "3". Verify the correct seeded tag is applied.

**Testing:**
Run the new E2E test.

**Verification:**
Run: `uv run grimoire e2e run -k test_student_canvas_interactions`
Expected: The test passes cleanly.

**Commit:** `test: add student canvas interaction e2e tests`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement Canvas E2E Test (Instructor View)

**Verifies:** e2e-instructor-workflow-split.AC4.4

**Files:**
- Modify: `tests/e2e/test_annotation_canvas.py`

**Implementation:**
Add `test_instructor_marking_interactions(authenticated_page, app_server)` to the `TestAnnotationCanvas` class.
1. Use `_create_workspace_via_db` to inject a workspace with a highlight and comment already seeded. (Or inject the workspace and apply the highlight via UI, then comment).
2. Instructor navigates to the workspace.
3. Instructor threads a reply onto the existing comment.
4. Instructor switches to the Organise tab.
5. Verify the annotation card appears in the correct tag column.

**Testing:**
Run the new E2E test.

**Verification:**
Run: `uv run grimoire e2e run -k test_instructor_marking_interactions`
Expected: The test passes cleanly.

**Commit:** `test: add instructor marking interaction e2e tests`
<!-- END_TASK_2 -->
