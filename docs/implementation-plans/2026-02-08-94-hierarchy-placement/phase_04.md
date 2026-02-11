# 94-hierarchy-placement Phase 4: Workspace Cloning (CRDT State)

**Goal:** Clone template CRDT state (highlights, comments, general notes) with document ID remapping via API replay.

**Architecture:** Extends `clone_workspace_from_activity()` from Phase 3 with CRDT replay logic. Creates a temporary `AnnotationDocument` from template state, a fresh `AnnotationDocument` for the clone, replays highlights with remapped `document_id` values using the doc_id_map from Phase 3, replays comments for each highlight, clones general notes, then serialises the fresh document's state and saves it to the cloned workspace — all within the existing single-transaction clone function.

**Tech Stack:** pycrdt (via AnnotationDocument wrapper), SQLModel

**Scope:** Phase 4 of 4 from original design

**Codebase verified:** 2026-02-08

**Key files for executor context:**
- Testing patterns: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- CLAUDE.md: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- AnnotationDocument: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/crdt/annotation_doc.py`
- CRDT Persistence: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/crdt/persistence.py`
- Workspace CRUD: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC4: Workspace cloning (CRDT state)
- **94-hierarchy-placement.AC4.6 Success:** Cloned CRDT highlights reference new document UUIDs (remapped)
- **94-hierarchy-placement.AC4.7 Success:** Highlight fields preserved (start_char, end_char, tag, text, author)
- **94-hierarchy-placement.AC4.8 Success:** Comments on highlights preserved in clone
- **94-hierarchy-placement.AC4.9 Success:** Client metadata NOT cloned (fresh client state)
- **94-hierarchy-placement.AC4.10 Edge:** Clone of template with no CRDT state produces workspace with null crdt_state
- **94-hierarchy-placement.AC4.11 Success:** Clone operation is atomic (all-or-nothing within single transaction)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: CRDT replay logic in clone_workspace_from_activity

**Verifies:** 94-hierarchy-placement.AC4.6, 94-hierarchy-placement.AC4.7, 94-hierarchy-placement.AC4.8, 94-hierarchy-placement.AC4.9, 94-hierarchy-placement.AC4.10, 94-hierarchy-placement.AC4.11

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (extend clone function with CRDT replay)

**Implementation:**

Extend `clone_workspace_from_activity()` (added in Phase 3) with CRDT state cloning. After document cloning and doc_id_map construction, add a CRDT replay block.

The CRDT replay logic:

1. Check if template workspace has `crdt_state` (bytes). If `None` or empty, skip CRDT cloning entirely — cloned workspace gets `crdt_state = None` (AC4.10).

2. If template has `crdt_state`:
   a. Create a temporary `AnnotationDocument("template-tmp")` and call `apply_update(template_workspace.crdt_state)` to load template state.
   b. Create a fresh `AnnotationDocument("clone-tmp")` for building the clone's state.
   c. Read all highlights from the template doc via `get_all_highlights()`.
   d. For each highlight, call `add_highlight()` on the clone doc with:
      - `document_id`: remap using `doc_id_map` — `str(doc_id_map[UUID(hl["document_id"])])` if `hl["document_id"]` is not None and exists in the map, else pass `hl["document_id"]` as-is (for backward compat with highlights that have no document_id).
      - All other fields passed through: `start_char`, `end_char`, `tag`, `text`, `author`, `para_ref`
   e. For each comment on the highlight (from `hl.get("comments", [])`), call `add_comment()` on the clone doc with `highlight_id` (the NEW highlight ID returned by `add_highlight()`), `author`, and `text`.
   f. Clone general notes: read via template doc's `get_general_notes()`, if non-empty call `set_general_notes()` on clone doc.
   g. Serialise clone doc state via `get_full_state()`.
   h. Set `cloned_workspace.crdt_state = clone_doc.get_full_state()` within the same session.
   i. Flush and refresh the cloned workspace.

3. The `client_meta` Y.Map is deliberately NOT replayed (AC4.9) — the fresh `AnnotationDocument` starts with empty client_meta.

Add imports at top of `workspaces.py`:
```python
from promptgrimoire.crdt.annotation_doc import AnnotationDocument
```

The `doc_id_map` built in Phase 3 has type `dict[UUID, UUID]`. When remapping, highlight `document_id` is stored as a string in the CRDT map, so convert: `str(doc_id_map.get(UUID(hl["document_id"]), UUID(hl["document_id"])))` — if the template doc ID isn't in the map (shouldn't happen), fall back to the original.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add CRDT state cloning with document ID remapping`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: CRDT cloning integration tests

**Verifies:** 94-hierarchy-placement.AC4.6, 94-hierarchy-placement.AC4.7, 94-hierarchy-placement.AC4.8, 94-hierarchy-placement.AC4.9, 94-hierarchy-placement.AC4.10, 94-hierarchy-placement.AC4.11

**Files:**
- Modify: `tests/integration/test_workspace_cloning.py` (add CRDT clone tests alongside Phase 3's document clone tests)

**Implementation:**

Add a new test class `TestCloneCRDT` to the existing `test_workspace_cloning.py` file. These tests build on the `_make_activity_with_docs()` helper from Phase 3.

To set up CRDT state on a template workspace, tests will:
1. Create an `AnnotationDocument` instance
2. Call `add_highlight()` with a `document_id` matching a template document's UUID
3. Call `add_comment()` on that highlight
4. Optionally call `set_general_notes()`
5. Serialise via `get_full_state()` and save to the template workspace's `crdt_state` column using `save_workspace_crdt_state()`

After cloning, tests load the cloned workspace's `crdt_state` into a fresh `AnnotationDocument` via `apply_update()` and inspect the replayed highlights.

**Testing:**

- **AC4.6:** `TestCloneCRDT::test_cloned_highlights_reference_new_document_uuids` -- Create Activity with 2 docs. Add highlight to template with `document_id=str(template_doc_1.id)`. Save CRDT state. Clone. Load clone's CRDT state into AnnotationDocument. Get all highlights. Verify the highlight's `document_id` matches the CLONED doc UUID (from `doc_id_map`), NOT the template doc UUID.

- **AC4.7:** `TestCloneCRDT::test_highlight_fields_preserved` -- Add highlight with specific `start_char=10`, `end_char=50`, `tag="jurisdiction"`, `text="sample text"`, `author="instructor"`, `para_ref="[3]"`. Clone. Load clone CRDT. Verify cloned highlight has matching `start_char`, `end_char`, `tag`, `text`, `author`, `para_ref` values.

- **AC4.8:** `TestCloneCRDT::test_comments_preserved_in_clone` -- Add highlight to template, then add 2 comments with distinct author/text. Save CRDT state. Clone. Load clone CRDT. Get highlight's comments. Verify 2 comments exist with matching `author` and `text` fields.

- **AC4.9:** `TestCloneCRDT::test_client_metadata_not_cloned` -- Register a client on template AnnotationDocument (which writes to `client_meta` map). Save CRDT state. Clone. Load clone CRDT. Verify `client_meta` map is empty (no keys).

- **AC4.10:** `TestCloneCRDT::test_null_crdt_state_produces_null_clone` -- Create Activity with docs but do NOT set any CRDT state (template `crdt_state` is None). Clone. Verify cloned workspace's `crdt_state` is None.

- **AC4.11:** `TestCloneCRDT::test_clone_atomicity_with_crdt` -- This is validated implicitly by the single-session design. Test that a clone with CRDT state either fully succeeds (workspace + docs + CRDT all present) or fully fails. Create Activity with docs and CRDT state. Clone. Verify cloned workspace has non-null `crdt_state`, correct document count, and highlight count matches template.

- **General notes:** `TestCloneCRDT::test_general_notes_cloned` -- Set general notes on template: "Instructor notes for this activity". Save CRDT state. Clone. Load clone CRDT. Verify `get_general_notes()` returns "Instructor notes for this activity".

- **Multiple highlights across documents:** `TestCloneCRDT::test_multiple_highlights_across_documents_remapped` -- Create Activity with 2 docs. Add 1 highlight referencing doc 1, 1 highlight referencing doc 2. Clone. Verify each cloned highlight's `document_id` correctly maps to its respective cloned document UUID.

**Verification:**
Run: `uv run pytest tests/integration/test_workspace_cloning.py -v -k TestCloneCRDT`
Expected: All tests pass

**Commit:** `test: add CRDT cloning integration tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

After all Phase 4 tasks are complete, verify manually (extends Phase 3 UAT):

### AC4.12 (extended): Start button clones template with highlights visible
1. Navigate to a template workspace via its Activity link on the course page
2. Add a document, then add highlights and comments to it using the annotation UI
3. Return to the course detail page
4. Click "Start" on that Activity
5. **Verify:** Cloned workspace opens with the same documents
6. **Verify:** Highlights are visible on the correct documents in the cloned workspace
7. **Verify:** Comments on highlights are preserved and visible
8. **Verify:** Highlight positions (character ranges) match the template's highlights
9. **Evidence:** Highlights and comments appear in the clone, on the correct documents
