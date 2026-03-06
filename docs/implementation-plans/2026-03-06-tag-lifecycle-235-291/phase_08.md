# Tag Lifecycle Refactor — Phase 8: Legacy Cleanup

**Goal:** Remove dead code paths from the old tag system, fully eliminating the `tag_order` Map.

**Architecture:** Redirect all `tag_order` reads to the `tags` Map `highlights` field (populated by Phase 5 dual-write). Remove `tag_order` Map initialization, property, and methods from AnnotationDocument. Update `clone_workspace_from_activity()` to remap highlight IDs in the `tags` Map. Simplify `_refresh_tag_state()` to CRDT-only. Delete `import_tags_from_activity()` and remaining save-on-blur handlers.

**Tech Stack:** pycrdt (existing Map operations), SQLModel (existing)

**Scope:** 8 phases from original design (phase 8 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC6: Existing contracts preserved
- **tag-lifecycle-235-291.AC6.1 Success:** PDF export produces correct tag colours and names from DB data
- **tag-lifecycle-235-291.AC6.2 Success:** FTS search worker resolves tag UUIDs to names from DB

---

## Pre-existing Complexity Violations

The following functions in files touched by this phase exceed or approach the complexipy threshold (15). When modifying these functions, extract helpers to bring them below threshold:

| Function | File | Complexity | Action |
|----------|------|-----------|--------|
| `update_tag` | db/tags.py | **18** | Phase 2 should have already addressed this. If not, extract lock-check and partial-update logic into helpers when Phase 8 modifies this file. |
| `clone_workspace_from_activity` | db/workspaces.py | **13** | At threshold risk. Phase 8 modifies highlight remapping logic — extract the tag/highlight remapping into a helper function to prevent exceeding 15. |

**These must be below 15 after Phase 8 changes or commits will be rejected by pre-commit hook.**

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Redirect organise.py and workspace.py reads from `tag_order` to `tags` Map

**Verifies:** tag-lifecycle-235-291.AC6.1 (existing contracts preserved — organise tab still works)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py:329,343` (calls to `get_tag_order`)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:176,189-195` (drag handler)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add `get_tag_highlights` convenience method)

**Implementation:**

1. Add a convenience method to `AnnotationDocument` that reads highlights from the `tags` Map:

```python
def get_tag_highlights(self, tag_id: str) -> list[str]:
    """Get ordered highlight IDs for a tag from the tags Map."""
    tag_data = self.get_tag(tag_id)
    if tag_data is None:
        return []
    return list(tag_data.get("highlights", []))
```

2. In `organise.py`, replace `crdt_doc.get_tag_order(tag_id)` calls (lines 329, 343) with `crdt_doc.get_tag_highlights(tag_id)`.

3. In `workspace.py` drag handler, replace `crdt_doc.get_tag_order(tag_id)` and `crdt_doc.set_tag_order(tag_id, highlight_ids)` with reads/writes via the `tags` Map. For writes, update the `highlights` field using `set_tag()` with the existing tag metadata preserved.

**Testing:**

- Existing organise tab tests should continue to pass
- Unit test: `get_tag_highlights()` returns correct highlight list from `tags` Map

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `refactor: redirect tag_order reads to tags Map highlights field`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Rewrite `move_highlight_to_tag()` to operate on `tags` Map only

**Verifies:** tag-lifecycle-235-291.AC6.1 (organise drag still works)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:407-458` (`move_highlight_to_tag`)

**Implementation:**

Rewrite `move_highlight_to_tag()` to read/write `tags` Map `highlights` field instead of `tag_order`:

1. Read source highlights: `from_tag_data = self.get_tag(from_tag)` → `from_highlights = list(from_tag_data["highlights"])`
2. Remove highlight from source: `from_highlights.remove(highlight_id)`
3. Write back source: `self.set_tag(from_tag, ..., highlights=from_highlights)`
4. Read target highlights: `to_tag_data = self.get_tag(to_tag)` → `to_highlights = list(to_tag_data["highlights"])`
5. Insert highlight at position: `to_highlights.insert(position, highlight_id)`
6. Write back target: `self.set_tag(to_tag, ..., highlights=to_highlights)`
7. Update the highlight's tag field (existing logic at line 453 stays)
8. Remove all `tag_order` reads/writes from this method

**Testing:**

Existing `move_highlight_to_tag` tests must pass with the rewritten implementation. The tests from Phase 5 (Task 1) that verify both `tag_order` and `tags` Map should be updated to verify only `tags` Map.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "move_highlight"`
Expected: All tests pass

**Commit:** `refactor: rewrite move_highlight_to_tag to use tags Map only`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Remove `tag_order` Map from AnnotationDocument

**Verifies:** None (cleanup — verified by regression)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (remove tag_order init, property, get_tag_order, set_tag_order)
- Modify: `tests/unit/test_annotation_doc.py` (remove/update TestTagOrder tests that reference tag_order directly)

**Implementation:**

1. Remove from `__init__` (line 65): `self.doc["tag_order"] = Map()`
2. Remove `tag_order` property (lines 96-98)
3. Remove `get_tag_order()` method (lines 374-386)
4. Remove `set_tag_order()` method (lines 388-405)
5. Update or remove any tests in `TestTagOrder` that directly test the `tag_order` Map. Tests that verify highlight ordering should be updated to read from `tags` Map `highlights` field.

**Note:** Existing CRDT state blobs in the database will still contain a `tag_order` key. pycrdt preserves unknown top-level keys without errors during `apply_update()`. No migration needed.

**Testing:**

- All unit tests must pass after removal
- Verify no imports or references to `tag_order` remain in annotation_doc.py
- **Backward-compat test:** Create an `AnnotationDocument`, inject a `tag_order` key into its underlying pycrdt doc via raw Map write, serialise via `get_full_state()`, create a fresh `AnnotationDocument` (without `tag_order` initialisation), call `apply_update()` — verify no exception is raised and the `tags` Map is still accessible. This confirms legacy state blobs won't break after removal.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v`
Expected: All tests pass

Run: `grep -n "tag_order" src/promptgrimoire/crdt/annotation_doc.py`
Expected: No matches

**Commit:** `refactor: remove tag_order Map from AnnotationDocument`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->
<!-- START_TASK_4 -->
### Task 4: Update `clone_workspace_from_activity()` to remap highlights in `tags` Map

**Verifies:** tag-lifecycle-235-291.AC6.1 (cloned workspaces have correct tag/highlight mapping)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py:588-662` (`clone_workspace_from_activity` — tag_order remapping section)

**Implementation:**

The clone function currently rebuilds `tag_order` with remapped tag keys and highlight IDs (lines 656-662). Replace this with remapping in the `tags` Map `highlights` field:

1. After cloning CRDT state and remapping highlights (existing logic), iterate the `tags` Map entries
2. For each tag entry, remap the `highlights` list: replace old highlight IDs with new ones using the same `highlight_id_map` already computed by the clone
3. Also remap tag IDs (keys) if tags are assigned new UUIDs during clone
4. Remove the old `tag_order` remapping code (lines 656-662)

**Complexity budget:** `clone_workspace_from_activity` is at 13. Extract the tag/highlight remapping into a helper function `_remap_cloned_tag_highlights(doc, tag_id_map, highlight_id_map)` to keep the parent function well under 15.

**Testing:**

Integration test: clone a workspace that has tags with highlights assigned. Verify the cloned workspace's CRDT `tags` Map has correct highlight IDs (new UUIDs, not old ones). Verify highlights are in the correct tag columns.

**Verification:**
Run: `uv run pytest tests/integration/ -v -k "clone"`
Expected: All clone tests pass

**Commit:** `refactor: update clone_workspace to remap highlights in tags Map`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Simplify `_refresh_tag_state()` and remove dead code

**Verifies:** None (cleanup — verified by regression)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py:23-68` (`_refresh_tag_state`)
- Modify: `src/promptgrimoire/db/tags.py` (remove `import_tags_from_activity`)
- Modify: `src/promptgrimoire/db/__init__.py` (remove export)
- Modify: `src/promptgrimoire/pages/annotation/tag_import.py` (remove old import)
- Modify: `src/promptgrimoire/db/tags.py:540-595` (remove `_cleanup_crdt_highlights_for_tag` load-from-DB fallback path)

**Implementation:**

1. **Simplify `_refresh_tag_state()`:** Remove the DB query path. The function becomes:
   - Read `state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)`
   - Rebuild CSS (`_update_highlight_css(state)`)
   - Rebuild highlight menu
   - Remove the `reload_crdt` parameter (no longer needed — CRDT doc is always in-memory)

2. **Delete `import_tags_from_activity()`** from `db/tags.py` (lines 428-534). Remove its export from `db/__init__.py`. Remove the import from `tag_import.py`.

3. **Simplify `_cleanup_crdt_highlights_for_tag()`:** Remove the load-from-DB fallback path (the branch when `crdt_doc is None` that loads workspace.crdt_state from DB, modifies, saves back). After Phase 2, all callers pass `crdt_doc`. The function should require `crdt_doc` (no longer optional) and operate on it directly.

4. **Remove remaining `tag_order` references** in other files:
   - `organise.py`: remove comment references to `tag_order` (lines 8, 164, 210)
   - `db/tags.py`: remove `tag_order` cleanup in `_cleanup_crdt_highlights_for_tag` (lines 587-588)

**Testing:**

- All existing tests must pass
- Verify no references to removed functions remain

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Run: `grep -rn "import_tags_from_activity\|tag_order\|reload_crdt" src/promptgrimoire/`
Expected: No matches (except DB `next_tag_order` counter field, which is a different concept)

**Commit:** `refactor: simplify _refresh_tag_state, remove import_tags_from_activity and tag_order remnants`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify export pipeline and FTS contracts

**Verifies:** tag-lifecycle-235-291.AC6.1, tag-lifecycle-235-291.AC6.2

**Files:**
- No modifications — verification and testing only
- Test: `tests/integration/test_tag_crud.py` (add AC6 verification tests)

**Implementation:**

Integration tests verifying existing contracts are preserved:

1. **tag-lifecycle-235-291.AC6.1:** Create a workspace with tags and highlights. Build `tag_colours` dict from `state.tag_info_list` (which now comes from CRDT). Verify the dict contains correct tag UUID → colour mappings. Pass to `generate_tag_colour_definitions(tag_colours)` — assert the returned LaTeX string contains a `\definecolor` command for each tag UUID with the correct colour value.

2. **tag-lifecycle-235-291.AC6.2:** Create a workspace with tags and highlights. Call `extract_searchable_text(crdt_state, tag_names)` where `tag_names` is built from DB query (existing pattern). Verify tag names appear in the extracted text.

These tests verify the seams between CRDT-rendered tags and the export/FTS pipelines that read from DB.

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "export or fts"`
Expected: All tests pass

**Commit:** `test: verify export pipeline and FTS contracts preserved after refactor`

<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_7 -->
### Task 7: Full regression verification and dead code audit

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run grimoire e2e run`
Expected: All E2E tests pass (including new tests from Phases 3-6)

Run: `grep -rn "tag_order" src/promptgrimoire/ | grep -v "next_tag_order" | grep -v "next_group_order"`
Expected: No matches — all `tag_order` Map references removed

Run: `grep -rn "import_tags_from_activity" src/promptgrimoire/`
Expected: No matches

Run: `grep -rn 'on("blur"' src/promptgrimoire/pages/annotation/tag_management_rows.py`
Expected: No matches

Run: `grep -rn "_cleanup_crdt_highlights_for_tag" src/promptgrimoire/`
Expected: All call sites pass `crdt_doc` as a required argument (no `None`, no omission)

Run: `uv run complexipy src/promptgrimoire/crdt/annotation_doc.py src/promptgrimoire/db/workspaces.py src/promptgrimoire/db/tags.py src/promptgrimoire/pages/annotation/tag_management_save.py --max-complexity-allowed 15`
Expected: No violations

**Commit:** No commit needed — verification only

<!-- END_TASK_7 -->
