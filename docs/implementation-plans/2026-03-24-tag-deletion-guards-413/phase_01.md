# Tag Deletion Guards & Import Hardening — Phase 1: Exception Types and DB Guards

**Goal:** Add deletion guard checks to the DB layer so destructive operations raise before mutating state.

**Architecture:** Three new `BusinessLogicError` subclasses carry entity ID + count for UI messaging. Pre-delete checks are added inside existing `delete_*` functions, reading highlight/tag counts from DB-persisted CRDT state (not in-memory snapshots) to close TOCTOU gaps. `can_delete_document` gains an `annotation_count` parameter for UI-level defence-in-depth.

**Tech Stack:** Python 3.14, SQLModel, pycrdt, pytest (integration tests with real DB)

**Scope:** Phase 1 of 4 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-deletion-guards-413.AC1: Tag group deletion blocked when group has tags
- **tag-deletion-guards-413.AC1.1 Success:** Deleting an empty tag group succeeds and removes the group
- **tag-deletion-guards-413.AC1.2 Failure:** Deleting a tag group with 1+ tags raises `HasChildTagsError` with correct count
- **tag-deletion-guards-413.AC1.4 Edge:** Group deletion succeeds after all its tags are moved to another group or deleted

### tag-deletion-guards-413.AC2: Tag deletion blocked when tag has highlights
- **tag-deletion-guards-413.AC2.1 Success:** Deleting a tag with zero CRDT highlights succeeds
- **tag-deletion-guards-413.AC2.2 Failure:** Deleting a tag with 1+ CRDT highlights raises `HasHighlightsError` with correct count
- **tag-deletion-guards-413.AC2.4 Edge:** Tag deletion succeeds after all its highlights are removed

### tag-deletion-guards-413.AC3: Document deletion blocked when document has annotations
- **tag-deletion-guards-413.AC3.1 Success:** Deleting a user-uploaded document with zero annotations succeeds
- **tag-deletion-guards-413.AC3.2 Failure:** Deleting a document with 1+ CRDT highlights raises `HasAnnotationsError` with correct count
- **tag-deletion-guards-413.AC3.4 Success:** `can_delete_document` returns False when document has annotations (delete button hidden)
- **tag-deletion-guards-413.AC3.5 Edge:** Document deletion succeeds after all annotations on it are removed

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add three exception classes to db/exceptions.py

**Files:**
- Modify: `src/promptgrimoire/db/exceptions.py:141` (append after `StudentIdConflictError`)

**Implementation:**

Add three new `BusinessLogicError` subclasses following the existing `DeletionBlockedError` pattern (line 43-55). Each takes an entity UUID and an integer count, stores both as attributes, and calls `super().__init__()` with a formatted message.

```python
class HasChildTagsError(BusinessLogicError):
    """Tag group cannot be deleted because it contains tags.

    Attributes:
        group_id: The tag group that was attempted to be deleted.
        tag_count: Number of tags in the group.
    """

    def __init__(self, group_id: UUID, tag_count: int) -> None:
        self.group_id = group_id
        self.tag_count = tag_count
        super().__init__(
            f"Tag group {group_id} has {tag_count} "
            f"tag{'s' if tag_count != 1 else ''} and cannot be deleted"
        )


class HasHighlightsError(BusinessLogicError):
    """Tag cannot be deleted because highlights reference it.

    Attributes:
        tag_id: The tag that was attempted to be deleted.
        highlight_count: Number of CRDT highlights referencing this tag.
    """

    def __init__(self, tag_id: UUID, highlight_count: int) -> None:
        self.tag_id = tag_id
        self.highlight_count = highlight_count
        super().__init__(
            f"Tag {tag_id} has {highlight_count} "
            f"highlight{'s' if highlight_count != 1 else ''} and cannot be deleted"
        )


class HasAnnotationsError(BusinessLogicError):
    """Document cannot be deleted because it has annotations.

    Attributes:
        document_id: The document that was attempted to be deleted.
        highlight_count: Number of CRDT highlights on this document.
    """

    def __init__(self, document_id: UUID, highlight_count: int) -> None:
        self.document_id = document_id
        self.highlight_count = highlight_count
        super().__init__(
            f"Document {document_id} has {highlight_count} "
            f"annotation{'s' if highlight_count != 1 else ''} and cannot be deleted"
        )
```

Note: The `UUID` import is already in the `TYPE_CHECKING` block (line 12-13). No new imports needed.

**Testing:**

Tests must verify each exception:
- Instantiation stores attributes correctly (`group_id`/`tag_id`/`document_id`, count)
- Message string includes the count with correct pluralisation (1 = singular, 2+ = plural)
- All three are subclasses of `BusinessLogicError`
- Test file: `tests/unit/test_exceptions.py` (unit — no DB needed)

**Verification:**
Run: `uv run grimoire test run tests/unit/test_exceptions.py`
Expected: All tests pass

**Commit:** `feat(db): add HasChildTagsError, HasHighlightsError, HasAnnotationsError exceptions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add HasChildTagsError guard to delete_tag_group

**Verifies:** tag-deletion-guards-413.AC1.1, tag-deletion-guards-413.AC1.2, tag-deletion-guards-413.AC1.4

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:245-266` (`delete_tag_group` function)
- Test: `tests/integration/test_tag_crud.py` (integration — needs real DB)

**Implementation:**

Inside `delete_tag_group` (line 245), after loading the group from the session (line 257), add a count query for child tags before the `await session.delete(group)` call (line 261).

The guard queries `Tag` rows where `Tag.group_id == group_id` using `select(func.count()).where(Tag.group_id == group_id)`. If count > 0, raise `HasChildTagsError(group_id, count)`. The query runs inside the existing `get_session()` context manager, so it shares the transaction with the delete.

```python
from sqlmodel import func, select

# Inside the existing get_session() block, after loading group:
tag_count_result = await session.exec(
    select(func.count()).select_from(Tag).where(Tag.group_id == group_id)
)
tag_count = tag_count_result.one()
if tag_count > 0:
    raise HasChildTagsError(group_id, tag_count)
```

Import `HasChildTagsError` from `promptgrimoire.db.exceptions`. The `Tag` model import is already at the top of tags.py (it's defined in the same module's model imports).

**Testing:**

Tests in `tests/integration/test_tag_crud.py`, add to or extend the existing `TestDeleteTagGroup` class. Follow the existing pattern: each test creates its own DB state inline using `_make_course_week_activity()` helper (line 30) and direct `create_tag_group`/`create_tag` calls.

Tests must verify:
- tag-deletion-guards-413.AC1.1: Create a group with zero tags → `delete_tag_group(group_id)` returns True, group is gone
- tag-deletion-guards-413.AC1.2: Create a group, add 2 tags → `delete_tag_group(group_id)` raises `HasChildTagsError` with `tag_count=2`
- tag-deletion-guards-413.AC1.4: Create group A with 1 tag, create group B. Move the tag to group B (update `group_id` to B's ID). Verify `delete_tag_group(group_A_id)` now succeeds. Also test: create group with 1 tag, delete the tag, verify `delete_tag_group` succeeds.

Existing `TestDeleteTagGroup` tests at ~line 600+ already test basic deletion. New tests should be added alongside them.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_tag_crud.py::TestDeleteTagGroup`
Expected: All tests pass (existing + new)

**Commit:** `feat(db): guard delete_tag_group against non-empty groups (#413)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add HasHighlightsError guard to delete_tag (inline CRDT count)

**Verifies:** tag-deletion-guards-413.AC2.1, tag-deletion-guards-413.AC2.2, tag-deletion-guards-413.AC2.4

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:509-553` (`delete_tag` function)
- Test: `tests/integration/test_tag_crud.py` (integration — needs real DB + CRDT state)

**Implementation:**

Restructure `delete_tag` to check the highlight count inside the same transaction as the deletion, closing the TOCTOU gap. The design requires reading from DB-persisted CRDT state "inside the same transaction as the delete."

The current three-session pattern (read → CRDT cleanup → delete) changes to: read+guard → CRDT cleanup → delete. The guard and the read share the first session. If the guard passes (count == 0), the CRDT cleanup is a no-op (nothing to clean up), so the separate cleanup session is still safe.

The CRDT count is inlined inside the first `get_session()` block, after loading the tag and checking `tag.locked`, but before the session closes. This reads the workspace's persisted CRDT blob in the same transaction that confirmed the tag exists.

```python
async def delete_tag(
    tag_id: UUID,
    *,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
) -> bool:
    # ... docstring unchanged ...
    async with get_session() as session:
        tag = await session.get(Tag, tag_id)
        if not tag:
            return False

        if tag.locked and not bypass_lock:
            msg = "Tag is locked"
            raise TagLockedError(msg)

        workspace_id = tag.workspace_id
        tag_id_for_cleanup = tag.id

        # Guard: count highlights from DB-persisted CRDT state (same session)
        workspace = await session.get(Workspace, workspace_id)
        if workspace and workspace.crdt_state:
            from promptgrimoire.crdt.annotation_doc import (
                AnnotationDocument as AnnotationDocumentCls,
            )
            guard_doc = AnnotationDocumentCls("guard-tmp")
            guard_doc.apply_update(workspace.crdt_state)
            tag_str = str(tag_id_for_cleanup)
            highlight_count = sum(
                1 for hl in guard_doc.get_all_highlights()
                if hl.get("tag") == tag_str
            )
            if highlight_count > 0:
                raise HasHighlightsError(tag_id_for_cleanup, highlight_count)

    # CRDT cleanup before row deletion (separate session — see docstring)
    await _cleanup_crdt_highlights_for_tag(
        workspace_id, tag_id_for_cleanup, crdt_doc=crdt_doc
    )

    # Delete the tag row (separate session)
    async with get_session() as session:
        tag_row = await session.get(Tag, tag_id_for_cleanup)
        if tag_row:
            await session.delete(tag_row)
            return True
    return False
```

Import `HasHighlightsError` from `promptgrimoire.db.exceptions` and `Workspace` from `promptgrimoire.db.models`.

No separate `_count_highlights_for_tag_from_db` helper is needed — the count is inlined in the same session that reads the tag. This matches the pattern used in Task 4 for `delete_document`.

**Testing:**

Tests in `tests/integration/test_tag_crud.py`, add to or extend the existing `TestDeleteTag` / `TestDeleteTagCrdtCleanup` classes. Follow existing CRDT setup pattern: create `AnnotationDocument`, add highlights via `doc.add_highlight(...)`, persist via `save_workspace_crdt_state(ws.id, doc.get_full_state())`.

Tests must verify:
- tag-deletion-guards-413.AC2.1: Tag with zero CRDT highlights → `delete_tag(tag_id)` returns True, tag is gone
- tag-deletion-guards-413.AC2.2: Tag with 3 CRDT highlights → `delete_tag(tag_id)` raises `HasHighlightsError` with `highlight_count=3`
- tag-deletion-guards-413.AC2.4: Tag with highlights → remove all highlights from CRDT → persist state → `delete_tag(tag_id)` now succeeds

See existing `TestDeleteTagCrdtCleanup` tests (around line 700+) for the CRDT setup pattern:
```python
doc = AnnotationDocument("test")
doc.add_highlight(start_char=0, end_char=5, tag=str(tag.id), text="hello", author="test")
await save_workspace_crdt_state(ws.id, doc.get_full_state())
```

**Verification:**
Run: `uv run grimoire test run tests/integration/test_tag_crud.py::TestDeleteTag`
Expected: All tests pass (existing + new)

**Commit:** `feat(db): guard delete_tag against tags with active highlights (#413)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add annotation count helper and HasAnnotationsError guard to delete_document

**Verifies:** tag-deletion-guards-413.AC3.1, tag-deletion-guards-413.AC3.2, tag-deletion-guards-413.AC3.5

**Files:**
- Modify: `src/promptgrimoire/db/workspace_documents.py:206-262` (`delete_document` function)
- Test: `tests/integration/test_delete_guards.py` (integration — extends existing document deletion tests)

**Implementation:**

Inline the CRDT annotation count inside `delete_document`'s existing `get_session()` block, matching the pattern used in Task 3 for `delete_tag`. The count and the delete share the same transaction, closing the TOCTOU gap.

After the `ProtectedDocumentError` check (line 243-247) and before the ownership check (line 250), load the workspace's CRDT state and count highlights for this document:

```python
# Inside the existing get_session() block, after ProtectedDocumentError check:
workspace = await session.get(Workspace, doc.workspace_id)
if workspace and workspace.crdt_state:
    from promptgrimoire.crdt.annotation_doc import (
        AnnotationDocument as AnnotationDocumentCls,
    )
    count_doc = AnnotationDocumentCls("count-doc-tmp")
    count_doc.apply_update(workspace.crdt_state)
    annotation_count = len(
        count_doc.get_highlights_for_document(str(document_id))
    )
    if annotation_count > 0:
        raise HasAnnotationsError(document_id, annotation_count)
```

Import `HasAnnotationsError` from `promptgrimoire.db.exceptions` and `Workspace` from `promptgrimoire.db.models`.

No separate `_count_annotations_for_document_from_db` helper is needed — the count is inlined in the same session that loads the document, matching Task 3's pattern.

**Testing:**

Tests in `tests/integration/test_delete_guards.py`, extending the existing `TestDeleteDocument` class. CRDT state must be set up with highlights referencing specific documents.

Tests must verify:
- tag-deletion-guards-413.AC3.1: User-uploaded document with zero annotations → `delete_document(doc_id, user_id=owner_id)` returns True
- tag-deletion-guards-413.AC3.2: Document with 2 CRDT highlights → `delete_document` raises `HasAnnotationsError` with `highlight_count=2`
- tag-deletion-guards-413.AC3.5: Document with annotations → remove all annotations from CRDT → persist → `delete_document` now succeeds

CRDT setup pattern for document highlights — highlights carry a `document_id` field:
```python
doc = AnnotationDocument("test")
doc.add_highlight(
    start_char=0, end_char=5, tag=str(tag_id),
    text="hello", author="test",
    document_id=str(workspace_doc.id),  # Link to specific document
)
await save_workspace_crdt_state(ws.id, doc.get_full_state())
```

Verify that `add_highlight` accepts `document_id` kwarg by checking the `AnnotationDocument` API. The `get_highlights_for_document` method (line 367) filters by `h.get("document_id")`, confirming highlights store this field.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_delete_guards.py::TestDeleteDocument`
Expected: All tests pass (existing + new)

**Commit:** `feat(db): guard delete_document against documents with annotations (#413)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Update can_delete_document to check annotation count

**Verifies:** tag-deletion-guards-413.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document_management.py:76-86` (`can_delete_document` function)
- Modify: `src/promptgrimoire/pages/annotation/document_management.py:133-138` (delete button rendering in `_render_document_row`)
- Test: `tests/unit/test_document_management.py` (unit — pure function, no DB)

**Implementation:**

**Step A — Update `can_delete_document` signature:**

Add `annotation_count: int` as a required keyword argument, matching `can_edit_document`'s signature (line 62):

```python
def can_delete_document(
    doc: WorkspaceDocument, *, is_owner: bool, annotation_count: int
) -> bool:
    """Whether a document is eligible for deletion in the UI.

    A document can be deleted when:
    1. The viewer is the workspace owner, AND
    2. The document is user-uploaded (source_document_id IS NULL), AND
    3. The document has zero annotations (highlights).

    Template-cloned documents (source_document_id IS NOT NULL) never show
    a delete button. Documents with annotations must have annotations
    removed before deletion (defence-in-depth — DB guard also blocks).
    """
    return is_owner and doc.source_document_id is None and annotation_count == 0
```

**Step B — Update caller in `_render_document_row`:**

At line 133, the delete button is rendered unconditionally inside the `elif state.is_owner:` branch. Wrap it with `can_delete_document`:

```python
# Replace lines 133-138 with:
if can_delete_document(
    doc, is_owner=state.is_owner, annotation_count=annotation_count
):
    ui.button(
        icon="delete",
        on_click=lambda d=doc: _handle_delete_document(d, state, dialog),
    ).props(
        "flat round dense size=sm color=negative"
        f' data-testid="delete-doc-btn-{doc.id}"'
    )
```

Note: `annotation_count` is already computed at line 116 via `_get_annotation_count(state, doc.id)`.

**Testing:**

Unit tests for `can_delete_document` — it's a pure function, no DB needed.

Tests must verify:
- tag-deletion-guards-413.AC3.4: `can_delete_document(user_uploaded_doc, is_owner=True, annotation_count=3)` returns False
- Positive case: `can_delete_document(user_uploaded_doc, is_owner=True, annotation_count=0)` returns True
- Template doc: `can_delete_document(template_doc, is_owner=True, annotation_count=0)` returns False (existing behaviour preserved)
- Non-owner: `can_delete_document(user_uploaded_doc, is_owner=False, annotation_count=0)` returns False (existing behaviour preserved)

Create mock `WorkspaceDocument` objects with appropriate `source_document_id` values. Test file: `tests/unit/test_document_management.py` if it exists, otherwise create it.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass. Any existing callers of `can_delete_document` that don't pass `annotation_count` will fail with `TypeError` — find and update them.

**Commit:** `feat(ui): hide delete button for documents with annotations (#413)`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify all Phase 1 tests pass together

**Files:**
- No new files

**Verification:**
Run: `uv run grimoire test all`
Expected: All 3571+ tests pass (baseline was 3571).

If any tests fail due to the `can_delete_document` signature change, update those callers to pass `annotation_count=0` (or the appropriate value).

Run: `uvx ty check`
Expected: No type errors

**Commit:** No commit (verification only). If fixes needed, commit as `fix: update can_delete_document callers for new annotation_count parameter (#413)`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Correct memory record about FK cascade behaviour

**Files:**
- Modify: `/home/brian/.claude/projects/-home-brian-people-Brian-PromptGrimoireTool/memory/project_incident_20260322_tag_deletion.md`

**Implementation:**

The design document notes (§ Additional Considerations): "The project memory incorrectly states 'The DB cascade deleted the tags from the `tag` table.' The FK is actually SET NULL — tags survive as ungrouped when their group is deleted."

Update the memory file to correct this statement. The `Tag.group_id` FK has `ON DELETE SET NULL` (see models.py:729-731 `_set_null_fk_column("tag_group.id")`), not `ON DELETE CASCADE`. When a tag group is deleted, its tags remain in the workspace with `group_id = NULL` (ungrouped).

**Verification:**
Read the updated memory file and confirm the correction is accurate.

**Commit:** No commit (memory file is outside the repository).
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->
