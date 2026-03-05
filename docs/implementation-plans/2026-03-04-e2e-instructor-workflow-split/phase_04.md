# E2E Test Suite Refactor: Phase 4 Implementation Plan

**Goal:** Remove the old monolithic test to realize the speed and maintenance gains.

**Architecture:** Deleting `tests/e2e/test_instructor_workflow.py`.

**Tech Stack:** N/A

**Scope:** Phase 4 from original design.

**Codebase verified:** 2026-03-04

---

## Acceptance Criteria Coverage

This phase implements and tests:

### e2e-instructor-workflow-split.AC1: Component Refactoring
- **e2e-instructor-workflow-split.AC1.1 Success:** `tests/e2e/test_instructor_workflow.py` is entirely deleted from the codebase.
- **e2e-instructor-workflow-split.AC1.2 Success:** The test suite passes in CI/CD without the monolithic file.

---

<!-- START_TASK_1 -->
### Task 1: Delete monolithic test

**Verifies:** e2e-instructor-workflow-split.AC1.1, e2e-instructor-workflow-split.AC1.2

**Files:**
- Delete: `tests/e2e/test_instructor_workflow.py`

**Implementation:**
Delete the file.

**Testing:**
Run the entire E2E test suite to ensure no other files depended on imports from `test_instructor_workflow.py` and that the suite still passes.

**Verification:**
Run: `uv run grimoire e2e run`
Expected: The test suite passes cleanly.

**Commit:** `test: remove monolithic instructor workflow e2e test`
<!-- END_TASK_1 -->
