# Workspace Model Implementation Plan - Phase 4: Parallel Operation

**Goal:** Both old (`/demo/live-annotation`) and new (`/annotation`) routes work simultaneously. This is a verification phase, not an implementation phase.

**Architecture:** No new code. Verification that Phase 1-3 changes are backward compatible.

**Tech Stack:** pytest, Playwright

**Scope:** 5 phases from original design (this is phase 4 of 5)

**Codebase verified:** 2026-01-31

**Design document:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model/docs/design-plans/2026-01-30-workspace-model.md`

---

## UAT: Falsifiable Statement

> The full test suite passes. Both `/demo/live-annotation` (old route) and `/annotation` (new route) work correctly. No regressions in existing functionality.

**How to verify:**
1. Run full test suite: `uv run pytest`
2. Manually test `/demo/live-annotation` - create highlights, verify persistence
3. Manually test `/annotation` - full workflow from Phase 3

---

## Note: Design Document Acceptance Criterion

The design document (`docs/design-plans/2026-01-30-workspace-model.md`) states:

> "Using the new `/annotation` route: upload 183.rtf, annotate it, click export PDF, and get a PDF with all annotations included."

This acceptance criterion spans ALL phases:
- Phase 1: Schema exists
- Phase 2: CRDT persistence works
- Phase 3: `/annotation` route works with create/annotate flow
- Phase 4: Both systems work (THIS PHASE)
- Phase 5: Old system removed

**PDF export and RTF upload are NOT implemented in these phases** - they are existing functionality that should work with the new workspace model. Verifying PDF export with workspace annotations should be tested manually in Phase 4.

If PDF export is broken with the new system, it should be fixed before Phase 5.

---

## Why This Phase Exists

Phase 4 is the "safety net" before teardown. It ensures:

1. **No regressions** - Phase 1-3 changes didn't break existing functionality
2. **Clean transition** - Both systems coexist, allowing gradual migration
3. **Rollback option** - If Phase 5 causes issues, we can stay in Phase 4

---

<!-- START_TASK_1 -->
## Task 1: Verify full test suite passes

**Files:**
- None (verification only)

**Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests pass, including:
- `tests/unit/test_workspace*.py` (Phase 1)
- `tests/unit/test_highlight_document_id.py` (Phase 2)
- `tests/integration/test_workspace*.py` (Phase 1-2)
- `tests/e2e/test_annotation_page.py` (Phase 3)
- All existing tests (pre-workspace)

**Step 2: If tests fail**

Debug and fix. Do NOT proceed to Phase 5 until all tests pass.

**Step 3: Document results**

Record test count and any notable findings:

```
Total tests: ___
Passed: ___
Failed: ___
Skipped: ___
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Manual verification of /demo/live-annotation

**Files:**
- None (manual testing)

**Prerequisites:**
- Database running with TEST_DATABASE_URL set
- App running: `uv run python -m promptgrimoire`

**Step 1: Test highlight creation**

1. Navigate to `/demo/live-annotation`
2. Select some text
3. Create a highlight
4. Verify highlight appears with yellow background

**Step 2: Test persistence**

1. Create a highlight
2. Note the case_id in URL or page state
3. Reload the page
4. Verify highlight is still visible

**Step 3: Test comments**

1. Create a highlight
2. Add a comment to the highlight
3. Reload the page
4. Verify comment is still visible

**Step 4: Document results**

```
/demo/live-annotation Manual Test Results:
- [ ] Page loads without errors
- [ ] Text selection works
- [ ] Highlight creation works
- [ ] Highlights persist after reload
- [ ] Comments can be added
- [ ] Comments persist after reload
- [ ] PDF export works (if applicable)
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: Manual verification of /annotation (new route)

**Files:**
- None (manual testing)

**Prerequisites:**
- Database running with TEST_DATABASE_URL set
- App running: `uv run python -m promptgrimoire`

**Step 1: Test workspace creation**

1. Navigate to `/annotation`
2. Click "Create Workspace"
3. Verify URL updates with workspace_id

**Step 2: Test document creation**

1. In workspace view, paste text content
2. Click "Add Document"
3. Verify text appears with word spans

**Step 3: Test highlight creation**

1. Select text in document
2. Click "Highlight" in menu
3. Verify highlight appears

**Step 4: Test persistence**

1. Create workspace and document
2. Create a highlight
3. Wait 6 seconds (debounce)
4. Copy the URL
5. Open in new tab
6. Verify highlight is still visible

**Step 5: Document results**

```
/annotation Manual Test Results:
- [ ] Page loads without errors
- [ ] Workspace creation works
- [ ] Document creation works (paste content)
- [ ] Word spans are created
- [ ] Text selection shows highlight menu
- [ ] Highlight creation works
- [ ] Highlights persist after reload
- [ ] Workspace ID in URL allows direct access
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Verify no cross-contamination

**Files:**
- None (verification)

**Purpose:** Ensure old and new systems don't interfere with each other.

**Step 1: Create data in old system**

1. Go to `/demo/live-annotation`
2. Create highlights
3. Note the case_id

**Step 2: Create data in new system**

1. Go to `/annotation`
2. Create workspace and document
3. Create highlights
4. Note the workspace_id

**Step 3: Verify isolation**

1. Old system data (AnnotationDocumentState) doesn't appear in new system
2. New system data (Workspace) doesn't appear in old system
3. Each system's persistence works independently

**Step 4: Database verification**

```sql
-- Check old system
SELECT COUNT(*) FROM annotation_document_state;

-- Check new system
SELECT COUNT(*) FROM workspace;
SELECT COUNT(*) FROM workspace_document;

-- Verify tables are independent
SELECT * FROM annotation_document_state LIMIT 5;
SELECT w.id, w.crdt_state IS NOT NULL as has_crdt
FROM workspace w LIMIT 5;
```

**Step 5: Document results**

```
Cross-contamination Check:
- [ ] Old system highlights only in AnnotationDocumentState
- [ ] New system highlights only in Workspace.crdt_state
- [ ] No shared state between systems
- [ ] Both systems persist independently
```
<!-- END_TASK_4 -->

---

## Phase 4 Verification

**Automated:**
```bash
uv run pytest -v
```

**Manual:**
Complete the checklists in Tasks 2-4.

---

## UAT Checklist

- [ ] Full test suite passes (Task 1)
- [ ] `/demo/live-annotation` works manually (Task 2)
- [ ] `/annotation` works manually (Task 3)
- [ ] No cross-contamination between systems (Task 4)

**If all checks pass:** Phase 4 complete. Both systems work in parallel. Safe to proceed to Phase 5 (teardown).

**If any check fails:** Fix before proceeding. Phase 5 removes the old system - any issues must be resolved first.

---

## Decision Point

After Phase 4 verification, decide:

1. **Proceed to Phase 5** - Remove old system, migrate fully to workspace model
2. **Stay in Phase 4** - Keep both systems running (temporary or permanent)
3. **Rollback** - Revert Phase 1-3 changes if fundamental issues discovered

Phase 5 is DESTRUCTIVE (removes old tables and routes). Only proceed when confident.
