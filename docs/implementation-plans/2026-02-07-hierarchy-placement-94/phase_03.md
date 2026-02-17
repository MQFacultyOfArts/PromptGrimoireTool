# Hierarchy & Placement Implementation Plan — Phase 3

**Goal:** Clone template workspace documents into a new student workspace when instantiating from an Activity. Instantiate button on course page.

**Architecture:** `clone_workspace_from_activity()` in `db/workspaces.py` creates a new Workspace and copies all WorkspaceDocuments within a single database transaction (ACID). Returns a doc_id_mapping (`{old_doc_id: new_doc_id}`) for Phase 4's CRDT remapping. CRDT state is NOT copied in this phase.

**Tech Stack:** SQLModel, SQLAlchemy (transactions), NiceGUI

**Scope:** Phase 3 of 4 from original design

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC4 (partial): Workspace cloning — documents
- **94-hierarchy-placement.AC4.1 Success:** Clone creates new workspace with activity_id set and enable_save_as_draft copied
- **94-hierarchy-placement.AC4.2 Success:** Cloned documents preserve content, type, source_type, title, order_index
- **94-hierarchy-placement.AC4.3 Success:** Cloned documents have new UUIDs (independent of template)
- **94-hierarchy-placement.AC4.4 Success:** Original template documents and CRDT state unmodified after clone
- **94-hierarchy-placement.AC4.5 Edge:** Clone of empty template creates empty workspace with activity_id set

---

## Codebase Investigation Findings

- ✓ `workspace_documents.py` has `add_document()` with auto-assigned `order_index` — clone must preserve original order_index, so creates `WorkspaceDocument` directly rather than using `add_document()`
- ✓ `get_session()` auto-commits on success, rollback on error — single transaction guaranteed within one `async with get_session()` block
- ✓ `WorkspaceDocument` fields: `id` (UUID PK), `workspace_id` (FK CASCADE), `type`, `content` (Text), `source_type`, `order_index` (int), `title` (optional), `created_at`
- ✓ `list_documents()` queries by workspace_id ordered by order_index — usable for fetching template docs
- ✓ Workspace model has `enable_save_as_draft` (Phase 1) and `activity_id` (Phase 1) — both needed for clone

**Key files for implementor to read:**
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py` (add clone function here)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspace_documents.py` (document model reference)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/models.py` (WorkspaceDocument, Activity, Workspace fields)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/pages/courses.py` (Instantiate button location)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: clone_workspace_from_activity function (document cloning)

**Verifies:** 94-hierarchy-placement.AC4.1, AC4.2, AC4.3, AC4.4, AC4.5

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add `clone_workspace_from_activity` function)
- Test: `tests/integration/test_workspace_clone.py` (integration)

**Implementation:**

Add `clone_workspace_from_activity(activity_id: UUID) -> tuple[Workspace, dict[UUID, UUID]]` to `workspaces.py`.

The function operates within a single `get_session()` call for ACID atomicity. This is a deliberate divergence from the one-session-per-function CRUD pattern — cloning requires multiple operations to be atomic.

Steps within the single session:

1. `session.get(Activity, activity_id)` — raise `ValueError("Activity not found")` if None
2. `session.get(Workspace, activity.template_workspace_id)` — raise `ValueError("Template workspace not found")` if None
3. Create new `Workspace(activity_id=activity_id, enable_save_as_draft=template.enable_save_as_draft)`. `session.add()`, `flush()`, `refresh()` to get ID.
4. Query template's documents: `select(WorkspaceDocument).where(WorkspaceDocument.workspace_id == template.id).order_by("order_index")`
5. For each template doc, create new `WorkspaceDocument`:
   - `workspace_id=new_workspace.id`
   - Copy: `type`, `content`, `source_type`, `title`, `order_index`
   - Fresh UUID via `default_factory` (do NOT copy `id`)
   - Do NOT copy `created_at` (fresh timestamp)
   - Build mapping: `doc_id_map[old_doc.id] = new_doc.id`
6. `session.add_all(new_docs)`, `flush()` (to generate new doc IDs)
7. Refresh each new doc to populate generated IDs for the mapping
8. Return `(new_workspace, doc_id_map)`

The `doc_id_map` will be used by Phase 4 to remap document references in CRDT highlights. In this phase, `new_workspace.crdt_state` remains None.

**Concurrent clones are expected:** Multiple students clicking "Instantiate" simultaneously for the same Activity will each produce an independent workspace with its own UUID. No deduplication or locking is needed — this is the intended behaviour.

Import `WorkspaceDocument`, `Activity` from models. Import `select` from sqlmodel.

**Testing:**

Integration tests in `tests/integration/test_workspace_clone.py`. Requires `TEST_DATABASE_URL`.

Setup helper: Create Course → Week → Activity (which creates template workspace automatically). Then add documents to the template workspace directly using the session.

Tests must verify each AC:
- AC4.1: Clone Activity → new workspace has `activity_id == activity.id`, `enable_save_as_draft` matches template's value (test both True and False)
- AC4.2: Add 2 docs to template (with specific content, type, source_type, title, order_index values) → clone → fetch cloned docs → verify all fields match originals
- AC4.3: Clone → verify every cloned doc ID differs from every template doc ID (use set intersection, must be empty)
- AC4.4: Record template's document content and crdt_state before clone → clone → re-fetch template → verify content identical and crdt_state unchanged
- AC4.5: Create Activity with empty template (0 documents) → clone → verify new workspace exists with activity_id set, `list_documents(new_workspace.id)` returns empty list

**Verification:**

Run: `uv run pytest tests/integration/test_workspace_clone.py -v`
Expected: All tests pass

**Commit:** `feat: add workspace document cloning from Activity template`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Instantiate button on course page

**Verifies:** 94-hierarchy-placement.AC4.1 (UI trigger), AC4.5 (empty template via UI)

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (Activity display section within weeks_list)

**Implementation:**

In the Activity display section added in Phase 1 Task 8 (within the `weeks_list` refreshable, inside the Activity loop), add an "Instantiate" button next to each Activity listing.

The button:
1. Is visible to all enrolled users (students, tutors, instructors, coordinators)
2. On click: calls `clone_workspace_from_activity(activity.id)`
3. On success: navigates to `/annotation?workspace_id={new_workspace.id}`
4. On error: shows notification with error message

Import `clone_workspace_from_activity` from `promptgrimoire.db.workspaces`.

The async click handler:

```python
async def instantiate(aid: UUID = activity.id) -> None:
    try:
        new_ws, _doc_map = await clone_workspace_from_activity(aid)
        ui.navigate.to(f"/annotation?workspace_id={new_ws.id}")
    except ValueError as e:
        ui.notify(str(e), type="negative")
```

Place the button alongside the Activity link (e.g., in a `ui.row()` with the Activity title link and the Instantiate button).

**Testing:** UAT (manual verification).

**Verification:**

Start app, navigate to course detail, click "Instantiate" on an Activity with documents, verify redirect to new workspace with cloned documents.

**Commit:** `feat: add Instantiate button for Activity workspace cloning`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Start app with seeded test data
2. [ ] Login as `admin@example.com`, navigate to course detail for LAWS1100
3. [ ] Create Activity under Week 1 (or use existing from Phase 1 UAT)
4. [ ] Click the Activity to open its template workspace in annotation page
5. [ ] Add a document to the template: paste some text content (e.g., "This is a contract between Party A and Party B...")
6. [ ] Navigate back to course detail page (click back or navigate to `/courses/{id}`)
7. [ ] Click "Instantiate" on the Activity
8. [ ] Verify: Redirected to annotation page with a NEW workspace UUID (different from template)
9. [ ] Verify: The cloned workspace shows the same document content as the template
10. [ ] Navigate back to the Activity's template workspace (click Activity link on course page)
11. [ ] Verify: Template workspace and its document are unchanged (content identical to step 5)
12. [ ] Test empty template: Create a new Activity, do NOT add documents, click "Instantiate"
13. [ ] Verify: Redirected to annotation page with empty workspace (no documents, but workspace exists)
14. [ ] Run all tests: `uv run test-all`
15. [ ] Verify: All tests pass

## Evidence Required
- [ ] Screenshot of cloned workspace showing same content as template
- [ ] Screenshot of template workspace unchanged after cloning
- [ ] Test output showing green for all tests
