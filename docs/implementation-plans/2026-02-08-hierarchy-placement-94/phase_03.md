# 94-hierarchy-placement Phase 3: Workspace Cloning (Documents)

**Goal:** Clone template workspace documents into a new student workspace. "Start" button on course page.

**Architecture:** `clone_workspace_from_activity()` creates a new Workspace within a single transaction, copies all template documents (preserving content, type, source_type, title, order_index), and builds a document ID mapping for Phase 4 CRDT remapping. A "Start" button on the course page triggers cloning and redirects to the new workspace.

**Tech Stack:** SQLModel, NiceGUI

**Scope:** Phase 3 of 4 from original design

**Codebase verified:** 2026-02-08

**Key files for executor context:**
- Testing patterns: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- CLAUDE.md: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- Document CRUD: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspace_documents.py`
- Workspace CRUD: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC4: Workspace cloning (documents)
- **94-hierarchy-placement.AC4.1 Success:** Clone creates new workspace with activity_id set and enable_save_as_draft copied
- **94-hierarchy-placement.AC4.2 Success:** Cloned documents preserve content, type, source_type, title, order_index
- **94-hierarchy-placement.AC4.3 Success:** Cloned documents have new UUIDs (independent of template)
- **94-hierarchy-placement.AC4.4 Success:** Original template documents and CRDT state unmodified after clone
- **94-hierarchy-placement.AC4.5 Edge:** Clone of empty template creates empty workspace with activity_id set

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: clone_workspace_from_activity function (document cloning)

**Verifies:** 94-hierarchy-placement.AC4.1, 94-hierarchy-placement.AC4.2, 94-hierarchy-placement.AC4.3, 94-hierarchy-placement.AC4.4, 94-hierarchy-placement.AC4.5

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add clone function)
- Modify: `src/promptgrimoire/db/__init__.py` (export)

**Implementation:**

Add `clone_workspace_from_activity()` to `workspaces.py`. This function uses a single session for atomicity, deviating from the one-session-per-function convention (necessary for ACID compliance as documented in design).

The function:
1. Fetches Activity and its template Workspace
2. Creates new Workspace with `activity_id` set and `enable_save_as_draft` copied
3. Fetches all template WorkspaceDocuments ordered by order_index
4. Creates cloned WorkspaceDocument for each, preserving: type, content, source_type, title, order_index
5. Builds `dict[UUID, UUID]` mapping `{template_doc_id: cloned_doc_id}`
6. Returns `tuple[Workspace, dict[UUID, UUID]]`

Does NOT call `add_document()` -- creates WorkspaceDocument instances directly within the same session, preserving explicit `order_index` from the template.

Does NOT clone CRDT state -- that is Phase 4's responsibility.

Raises `ValueError` if Activity or template workspace not found.

Add imports: `WorkspaceDocument` from models, `select` from sqlmodel.
Update `__init__.py` to export `clone_workspace_from_activity`.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add clone_workspace_from_activity for document cloning`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Document cloning integration tests

**Verifies:** 94-hierarchy-placement.AC4.1, 94-hierarchy-placement.AC4.2, 94-hierarchy-placement.AC4.3, 94-hierarchy-placement.AC4.4, 94-hierarchy-placement.AC4.5

**Files:**
- Create: `tests/integration/test_workspace_cloning.py`

**Implementation:**

Integration tests following existing patterns. Module-level skip guard for `TEST_DATABASE_URL`. Class-based organisation.

**Testing:**

- **AC4.1:** `TestCloneDocuments::test_clone_creates_workspace_with_activity_id_and_draft_flag` -- Create Activity, set `enable_save_as_draft=True` on template workspace (via session). Clone. Verify new workspace has `activity_id` matching the activity and `enable_save_as_draft=True`.
- **AC4.2:** `TestCloneDocuments::test_cloned_docs_preserve_fields` -- Add 2 documents to template with distinct content, type, source_type, title, order_index values. Clone. Verify each cloned document has matching field values.
- **AC4.3:** `TestCloneDocuments::test_cloned_docs_have_new_uuids` -- Clone template with documents. Verify each cloned document ID differs from its template counterpart. Verify doc_id_map has correct key-value pairs matching template-to-clone.
- **AC4.4:** `TestCloneDocuments::test_original_template_unmodified` -- Record template workspace and document state (content, crdt_state, document count, field values) before clone. Clone. Re-fetch template workspace and documents. Verify nothing changed.
- **AC4.5:** `TestCloneDocuments::test_empty_template_produces_empty_workspace` -- Create Activity (template has no documents). Clone. Verify new workspace exists with `activity_id` set, has zero documents, `doc_id_map` is empty dict.
- **Error:** `TestCloneDocuments::test_clone_nonexistent_activity_raises` -- Call with `uuid4()`. Assert raises `ValueError`.

Helper function using unique identifiers:
```python
async def _make_activity_with_docs(num_docs: int = 2) -> tuple[Course, Week, Activity]:
    code = f"C{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Clone Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Cloneable Activity")
    for i in range(num_docs):
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="source",
            content=f"<p>Document {i} content</p>",
            source_type="html",
            title=f"Document {i}",
        )
    return course, week, activity
```

**Verification:**
Run: `uv run pytest tests/integration/test_workspace_cloning.py -v`
Expected: All tests pass

**Commit:** `test: add document cloning integration tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3) -->
<!-- START_TASK_3 -->
### Task 3: "Start" button on course detail page

**Verifies:** 94-hierarchy-placement.AC4.1, 94-hierarchy-placement.AC4.12 (UAT path)

**Note:** The design document (AC4.12) uses "Instantiate button". We use "Start" as the label — deliberately more student-friendly language per user feedback.

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add Start button to Activity display in course_detail_page)

**Implementation:**

In the course detail page's `weeks_list()` function (added in Phase 1 Task 8), each Activity is displayed under its parent Week. Add a "Start" button alongside each Activity that:

1. Calls `clone_workspace_from_activity(activity.id)`
2. Redirects to `/annotation?workspace_id={clone.id}`

Add import:
```python
from promptgrimoire.db.workspaces import clone_workspace_from_activity
```

In the Activity list rendering, modify to show different controls for instructors vs students:
- **Instructors** (`can_manage`): see Activity title as link to template workspace (for editing), plus "Start" button
- **Students**: see Activity title as label, plus "Start" button

The "Start" button is visible to all enrolled users. Each click creates a new clone (a future enhancement outside this seam would check for existing clones).

The async click handler:
```python
async def start_activity(aid: UUID = act.id) -> None:
    clone, _doc_map = await clone_workspace_from_activity(aid)
    ui.navigate.to(f"/annotation?workspace_id={clone.id}")
```

Button style: `ui.button("Start", on_click=start_activity).props("flat dense size=sm color=primary")`

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add Start button for Activity cloning on course page`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

---

## UAT Steps

After all Phase 3 tasks are complete, verify manually:

### AC4.12: Start button clones template and redirects to new workspace
1. Navigate to a course detail page
2. Find an Activity that has documents in its template (add documents via the annotation page if needed)
3. Click the "Start" button next to the Activity
4. **Verify:** Redirected to `/annotation?workspace_id={new_clone_id}` (a different workspace_id than the template)
5. **Verify:** Cloned workspace contains the same documents as the template (same titles, content)
6. **Verify:** The cloned workspace is a new, independent workspace (changes to it should not affect the template)
7. **Evidence:** New workspace URL differs from template, document content matches
