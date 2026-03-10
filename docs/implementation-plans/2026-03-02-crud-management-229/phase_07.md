# CRUD Management Implementation Plan - Phase 7: Document Deletion

**Goal:** Workspace owners can delete user-uploaded documents from the annotation page. Template-cloned documents are protected from deletion. Template source documents show a clone-count warning before deletion.

**Architecture:** Delete button appears in the document header area for owners when `source_document_id IS NULL`. Deletion follows CRDT-first ordering: clean up highlights from CRDT state, persist, then delete the DB row. Template source documents trigger a warning showing how many student clones will lose protection. After deletion, redirect to workspace (shows upload form if no documents remain).

**Tech Stack:** NiceGUI, pycrdt, SQLModel

**Scope:** Phase 7 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (data-testid convention)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC4: Document deletion with provenance protection
- **crud-management-229.AC4.1 Success:** Owner deletes a user-uploaded document (source_document_id IS NULL); document and annotations removed, tags preserved
- **crud-management-229.AC4.2 Success:** After deletion, owner can upload a replacement document
- **crud-management-229.AC4.3 Failure:** Template-cloned document (source_document_id IS NOT NULL) has no delete button in UI

### crud-management-229.AC5: Document provenance tracking (partial — cascade effects)
- **crud-management-229.AC5.4 Edge:** Deleting a template source document sets clones' source_document_id to NULL (ON DELETE SET NULL)
- **crud-management-229.AC5.5 Edge:** Warning shown when deleting a template document that has clones: "X students have copies. Deleting makes their copies deletable."

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add count_clones_of_document() query

**Verifies:** (supports AC5.5 — building block for clone warning)

**Files:**
- Modify: `src/promptgrimoire/db/workspace_documents.py` (add after `reorder_documents()` or after the Phase 2 `delete_document()` function)

**Implementation:**

Add a query function that counts documents referencing a given source document ID:

```python
async def count_clones_of_document(source_document_id: UUID) -> int:
    """Count workspace documents cloned from the given source document.

    Used to warn instructors before deleting a template document that
    has been cloned by students. Returns 0 if no clones reference this
    document.
    """
    async with get_session() as session:
        result = await session.exec(
            select(func.count())
            .select_from(WorkspaceDocument)
            .where(
                WorkspaceDocument.source_document_id == source_document_id,
            )
        )
        return result.one()
```

Import `func` from `sqlalchemy` if not already imported.

**Testing:**

- Create a template document, clone workspace for a user — `count_clones_of_document(template_doc.id)` returns 1
- Clone for second user — returns 2
- Document with no clones — returns 0

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add count_clones_of_document() query`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add CRDT highlight cleanup for document deletion

**Verifies:** (supports AC4.1 — annotations removed on deletion)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add method to AnnotationDocument class)

**Implementation:**

Add a method to `AnnotationDocument` that removes all highlights and comments for a given document ID.

**IMPORTANT: pycrdt mutation rules.** The implementor MUST:
1. Read existing methods `remove_highlight()` (line ~281) and `add_comment()` in `annotation_doc.py` to understand the pycrdt transaction pattern
2. Use `self.highlights.pop(hid)` (NOT `del self.highlights[hid]`) — this is the pycrdt Map mutation API used throughout the codebase
3. Wrap all mutations in the CRDT transaction/context pattern used by other methods
4. Clean up `tag_order` arrays to remove references to deleted highlight IDs

The exact implementation depends on how `tag_order` is structured in the CRDT document. The implementor should examine `annotation_doc.py` for the actual map structure and adapt accordingly. The key requirement: all CRDT references to the deleted document's highlights must be removed, using the same mutation patterns as existing code.

**Verification:**

Run: `uv run test-changed`
Expected: Any existing CRDT tests pass

**Commit:** `feat: add CRDT highlight cleanup for document deletion`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add document delete button to annotation page

**Verifies:** crud-management-229.AC4.1, crud-management-229.AC4.2, crud-management-229.AC4.3, crud-management-229.AC5.4, crud-management-229.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/header.py` or `workspace.py` (document header area — implementor to determine best location based on current header rendering)

**Implementation:**

Add a delete button that appears in the document header area when:
- `state.is_owner` is True
- The current document has `source_document_id is None` (user-uploaded or template source, not a clone)

For template-cloned documents (`source_document_id is not None`), no button renders (AC4.3).

The delete handler:

```python
async def handle_delete_document(state: PageState) -> None:
    if state.document_id is None:
        return

    # Get the document to check source_document_id
    doc = await get_document(state.document_id)
    if doc is None or doc.source_document_id is not None:
        return  # Defence in depth: don't delete cloned docs

    # Check for clones (AC5.5 warning)
    clone_count = await count_clones_of_document(doc.id)
    if clone_count > 0:
        # Show warning dialog
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            ui.label("Document Has Student Copies").classes("text-lg font-bold")
            plural = "student has" if clone_count == 1 else "students have"
            ui.label(
                f"{clone_count} {plural} copies of this document. "
                "Deleting it will make their copies deletable."
            ).classes("text-sm my-2")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=lambda: dlg.submit(False)).props(
                    'flat data-testid="cancel-delete-doc-btn"'
                )
                ui.button("Delete Anyway", on_click=lambda: dlg.submit(True)).props(
                    'outline color=negative data-testid="confirm-delete-doc-btn"'
                )
        dlg.open()
        confirmed = await dlg
        if not confirmed:
            return
    else:
        # Standard confirmation
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            title = doc.title or "this document"
            ui.label(f"Delete {title}?").classes("text-lg font-bold")
            ui.label(
                "Annotations will be removed. Tags will be preserved."
            ).classes("text-sm my-2")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=lambda: dlg.submit(False)).props(
                    'flat data-testid="cancel-delete-doc-btn"'
                )
                ui.button("Delete", on_click=lambda: dlg.submit(True)).props(
                    'outline color=negative data-testid="confirm-delete-doc-btn"'
                )
        dlg.open()
        confirmed = await dlg
        if not confirmed:
            return

    # 1. Clean up CRDT highlights for this document
    if state.crdt_doc is not None:
        state.crdt_doc.delete_highlights_for_document(str(doc.id))
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor="system",
        )
        await pm.force_persist_workspace(state.workspace_id)

    # 2. Delete the DB row
    await delete_document(doc.id)

    # 3. Redirect to workspace (shows upload form if no docs remain)
    qs = urlencode({"workspace_id": str(state.workspace_id)})
    ui.navigate.to(f"/annotation?{qs}")
```

Import `delete_document` and `count_clones_of_document` from `promptgrimoire.db.workspace_documents`, and `get_persistence_manager` from `promptgrimoire.crdt`.

The delete button:
```python
if state.is_owner and doc and doc.source_document_id is None:
    ui.button(
        "Delete Document",
        icon="delete_outline",
        on_click=lambda: handle_delete_document(state),
    ).props(
        'outline color=negative dense size=sm '
        'data-testid="delete-document-btn"'
    )
```

**Testing:**

- crud-management-229.AC4.1: Delete user-uploaded doc — document and annotations removed, verify tags remain
- crud-management-229.AC4.2: After deletion, workspace shows upload form — user can add replacement
- crud-management-229.AC4.3: Template-cloned doc — no delete button visible
- crud-management-229.AC5.4: Delete template source doc — verify student clones' source_document_id becomes NULL (ON DELETE SET NULL)
- crud-management-229.AC5.5: Delete template source doc with clones — warning dialog shows student count

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add document deletion to annotation page with provenance protection`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests for document deletion

**Verifies:** crud-management-229.AC4.1, crud-management-229.AC4.2, crud-management-229.AC4.3, crud-management-229.AC5.4, crud-management-229.AC5.5

**Files:**
- Create: `tests/integration/test_document_deletion.py`

**Testing:**

Follow project test patterns (skip guard, class-based, UUID isolation).

**`TestDeleteUserUploadedDocument`** — AC4.1, AC4.2:
- Create workspace, add user-uploaded document (`source_document_id IS NULL`)
- Add tags to workspace
- Call `delete_document(doc.id)` — succeeds, returns True
- Verify: document no longer exists via `get_document()`
- Verify: workspace tags still exist (query tags by workspace_id)
- Verify: workspace still exists (can add replacement document)

**`TestDeleteProtectedDocument`** — AC4.3 (DB defence-in-depth):
- Clone workspace from activity (creates doc with `source_document_id` set)
- Call `delete_document(cloned_doc.id)` — raises `ProtectedDocumentError`
- Verify: document still exists
- (This overlaps with Phase 2's test_delete_guards.py but is a specific regression test in document context)

**`TestDeleteTemplateSourceCascade`** — AC5.4:
- Create template document, clone workspace for user
- Verify clone's `source_document_id` points to template doc
- Delete template document (via direct session delete to bypass CRDT — testing FK behaviour)
- Re-fetch clone document — `source_document_id` should be `NULL` (ON DELETE SET NULL)

**`TestCountClonesOfDocument`** — AC5.5:
- Create template document — `count_clones_of_document()` returns 0
- Clone workspace for user — returns 1
- Clone for second user — returns 2
- Delete template document — clone count query returns 0 (no more references)

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

Run: `uv run test-all`
Expected: No regressions

**Commit:** `test: add integration tests for document deletion and provenance`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
