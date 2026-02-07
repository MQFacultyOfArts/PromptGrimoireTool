# Hierarchy & Placement Implementation Plan — Phase 4

**Goal:** Clone template CRDT state (highlights, comments) with document ID remapping via API replay into new student workspaces.

**Architecture:** Extends `clone_workspace_from_activity()` from Phase 3. Deserialises template CRDT into a temporary AnnotationDocument, creates a fresh AnnotationDocument for the clone, replays all highlights with remapped `document_id` values using the doc_id_map from Phase 3, replays comments, serialises, and saves. Client metadata is NOT cloned. All within the same database transaction.

**Tech Stack:** pycrdt (via AnnotationDocument wrapper), SQLModel

**Scope:** Phase 4 of 4 from original design

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC4 (continued): Workspace cloning — CRDT state
- **94-hierarchy-placement.AC4.6 Success:** Cloned CRDT highlights reference new document UUIDs (remapped)
- **94-hierarchy-placement.AC4.7 Success:** Highlight fields preserved (start_char, end_char, tag, text, author)
- **94-hierarchy-placement.AC4.8 Success:** Comments on highlights preserved in clone
- **94-hierarchy-placement.AC4.9 Success:** Client metadata NOT cloned (fresh client state)
- **94-hierarchy-placement.AC4.10 Edge:** Clone of template with no CRDT state produces workspace with null crdt_state
- **94-hierarchy-placement.AC4.11 Success:** Clone operation is atomic (all-or-nothing within single transaction)
- **94-hierarchy-placement.AC4.12 UAT:** Instantiate button clones template and redirects to new workspace with highlights visible

---

## Codebase Investigation Findings

- ✓ `AnnotationDocument` at `crdt/annotation_doc.py` wraps pycrdt Y.Doc
- ✓ Highlights stored in `doc["highlights"]` Y.Map, keyed by highlight UUID
- ✓ Highlight fields: `id`, `document_id`, `start_char`, `end_char`, `tag`, `text`, `author`, `para_ref`, `created_at`, `comments`
- ✓ Comments: list of `{id, author, text, created_at}` dicts nested in each highlight
- ✓ `get_all_highlights()` returns `list[dict]` sorted by start_char
- ✓ `add_highlight(start_char, end_char, tag, text, author, para_ref, origin_client_id, document_id) -> str` returns new highlight ID
- ✓ `add_comment(highlight_id, author, text, origin_client_id) -> str | None` returns comment ID
- ✓ `get_full_state() -> bytes` serialises; `apply_update(bytes)` deserialises
- ✓ `client_meta` Y.Map stores cursor colours/names — must NOT be cloned
- ✓ Persistence: `save_workspace_crdt_state(workspace_id, crdt_state: bytes)` in `db/workspaces.py`

**Key files for implementor to read:**
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/crdt/annotation_doc.py` (AnnotationDocument API — read fully)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/crdt/persistence.py` (serialisation patterns)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py` (clone function to extend)

---

<!-- START_TASK_1 -->
### Task 1: Extend clone_workspace_from_activity with CRDT replay

**Verifies:** 94-hierarchy-placement.AC4.6, AC4.7, AC4.8, AC4.9, AC4.10, AC4.11

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (extend `clone_workspace_from_activity` function)
- Test: `tests/integration/test_workspace_clone_crdt.py` (integration)

**Implementation:**

Extend the existing `clone_workspace_from_activity()` function (from Phase 3). After the document cloning steps (workspace creation + document copying + doc_id_map building), add CRDT replay:

**After the existing document cloning steps, add:**

1. **Check for CRDT state:** If `template.crdt_state is None`, skip CRDT cloning entirely. Leave `new_workspace.crdt_state` as None (AC4.10).

2. **Deserialise template CRDT:** Create a temporary `AnnotationDocument("template-reader")`. Call `template_doc.apply_update(template.crdt_state)` to load the template's annotation state.

3. **Create fresh clone target:** Create `clone_doc = AnnotationDocument("clone-target")`. This starts with empty state — no client metadata, no highlights.

4. **Replay highlights with remapped document_id:** Iterate `template_doc.get_all_highlights()`. For each highlight:
   - Extract `document_id = highlight.get("document_id")`
   - If `document_id` is not None and `UUID(document_id)` is in `doc_id_map`: remap to `str(doc_id_map[UUID(document_id)])`
   - If `document_id` is None: keep as None
   - Call `new_hl_id = clone_doc.add_highlight(start_char=highlight["start_char"], end_char=highlight["end_char"], tag=highlight["tag"], text=highlight["text"], author=highlight["author"], para_ref=highlight.get("para_ref", ""), document_id=remapped_doc_id)`
   - For each comment in `highlight.get("comments", [])`: call `clone_doc.add_comment(highlight_id=new_hl_id, author=comment["author"], text=comment["text"])`
   - **Note:** `origin_client_id` is intentionally omitted from both `add_highlight()` and `add_comment()` calls (defaults to `None`). The clone is a server-side operation with no connected clients, so echo prevention is not applicable.

5. **Client metadata is NOT copied** (AC4.9). The fresh `clone_doc` has empty `client_meta` by construction — no action needed.

6. **Serialise and save:** `new_crdt_bytes = clone_doc.get_full_state()`. Set `new_workspace.crdt_state = new_crdt_bytes`. `session.add(new_workspace)`.

7. **Still within single `get_session()` transaction** (AC4.11). The entire clone — workspace creation, document cloning, CRDT replay — is atomic.

Import `AnnotationDocument` from `promptgrimoire.crdt` at the top of `workspaces.py`.

**Testing:**

Integration tests in `tests/integration/test_workspace_clone_crdt.py`. Requires `TEST_DATABASE_URL`.

**Setup helper for tests:** Create Activity with template workspace. Add 2 documents to template. Build CRDT state programmatically:
```python
template_doc = AnnotationDocument("test-template")
hl1_id = template_doc.add_highlight(
    start_char=0, end_char=10, tag="jurisdiction", text="Some text",
    author="Instructor", document_id=str(template_doc1_id)
)
template_doc.add_comment(hl1_id, author="Instructor", text="Note this")
hl2_id = template_doc.add_highlight(
    start_char=20, end_char=30, tag="legal_issues", text="Other text",
    author="Instructor", document_id=str(template_doc2_id)
)
# Save CRDT state to template workspace
crdt_bytes = template_doc.get_full_state()
await save_workspace_crdt_state(template_workspace_id, crdt_bytes)
```

**Tests must verify:**
- AC4.6: Clone → deserialise cloned CRDT into new AnnotationDocument → `get_all_highlights()` → for each highlight, verify `document_id` matches the NEW doc UUID from `doc_id_map`, NOT the template doc UUID
- AC4.7: Verify cloned highlight fields match originals: `start_char`, `end_char`, `tag`, `text`, `author`, `para_ref`
- AC4.8: Verify cloned highlights have comments with matching `author` and `text` fields
- AC4.9: First, add client metadata to the template AnnotationDocument (e.g., `template_doc.set_client_name(999, "Instructor")` or directly set a key in `template_doc.client_meta`). Save and clone. Deserialise cloned CRDT → verify `dict(clone_doc.client_meta)` is empty (the Y.Map has no entries). **Note:** Do NOT use `get_client_ids()` for this — that method checks the in-memory `_clients` dict, not the CRDT `client_meta` Y.Map, and would always return empty for a freshly constructed AnnotationDocument regardless of CRDT state.
- AC4.10: Create template with no CRDT state (`crdt_state=None`) → clone → verify `new_workspace.crdt_state is None`
- AC4.11: Verify that after a successful clone, both documents AND CRDT state are present (transaction committed atomically). Also verify failed clone (e.g., non-existent activity_id) raises ValueError without creating partial state.

**Verification:**

Run: `uv run pytest tests/integration/test_workspace_clone_crdt.py -v`
Expected: All tests pass

Run: `uv run pytest tests/integration/ -v`
Expected: All integration tests pass (including Phase 3 clone tests)

**Commit:** `feat: add CRDT state cloning with document ID remapping`
<!-- END_TASK_1 -->

---

## UAT Steps

1. [ ] Start app with seeded test data
2. [ ] Login as `admin@example.com`, navigate to course detail for LAWS1100
3. [ ] Create Activity under Week 1 (or use existing)
4. [ ] Click Activity to open template workspace in annotation page
5. [ ] Add a document: paste text content (e.g., "The plaintiff, Ms Bennett, was employed by Acme Corp from 2018 to 2023...")
6. [ ] Highlight a passage (select text, apply a tag like "jurisdiction")
7. [ ] Add a comment to the highlight (e.g., "Note: this establishes employment relationship")
8. [ ] Navigate back to course detail page
9. [ ] Click "Instantiate" on the Activity
10. [ ] Verify: Redirected to new workspace with same document content
11. [ ] Verify: Highlights visible on the document at the same character positions
12. [ ] Verify: Comment visible when clicking the highlight
13. [ ] Verify: No other user cursors or colour badges visible (fresh client state)
14. [ ] Navigate back to template workspace (click Activity on course page)
15. [ ] Verify: Template highlights, comments, and document are unchanged
16. [ ] Run all tests: `uv run test-all`
17. [ ] Verify: All tests pass

## Evidence Required
- [ ] Screenshot of cloned workspace showing highlights at correct positions
- [ ] Screenshot showing comment preserved on cloned highlight
- [ ] Screenshot of template workspace unchanged after cloning
- [ ] Test output showing green for all tests
