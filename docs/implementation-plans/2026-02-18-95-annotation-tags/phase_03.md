# Annotation Tag Configuration — Phase 3: Workspace Cloning

**Goal:** Propagate tags through workspace cloning with CRDT highlight remapping.

**Architecture:** Extend `clone_workspace_from_activity()` to clone TagGroup and Tag rows (bypassing CRUD permission checks — cloning is a system operation). Extend `_replay_crdt_state()` with an optional `tag_id_map` parameter to remap highlight tag references and tag_order keys.

**Tech Stack:** SQLModel, pycrdt, PostgreSQL

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC4: Workspace cloning propagates tags
- **95-annotation-tags.AC4.1 Success:** Cloning creates independent copies of all TagGroups in the student workspace
- **95-annotation-tags.AC4.2 Success:** Cloning creates independent copies of all Tags with group_id remapped to new TagGroup UUIDs
- **95-annotation-tags.AC4.3 Success:** CRDT highlights in cloned workspace reference the new Tag UUIDs (not template UUIDs)
- **95-annotation-tags.AC4.4 Success:** CRDT tag_order in cloned workspace uses new Tag UUIDs as keys
- **95-annotation-tags.AC4.5 Success:** Locked flag is preserved on cloned tags
- **95-annotation-tags.AC4.6 Edge:** Template with no tags clones cleanly (empty tag set)

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/db/workspaces.py:519-599` — `clone_workspace_from_activity()`, the function to extend
- `src/promptgrimoire/db/workspaces.py:450-516` — `_replay_crdt_state()`, the function to extend with tag remapping
- `src/promptgrimoire/db/workspaces.py:580-592` — document ID remapping pattern (same approach for tag IDs)
- `src/promptgrimoire/db/models.py` — TagGroup and Tag models (from Phase 1)
- `src/promptgrimoire/crdt/annotation_doc.py:230-270` — `add_highlight()` signature (tag parameter)
- `src/promptgrimoire/crdt/annotation_doc.py:344-375` — `tag_order` Map structure
- `tests/integration/test_workspace_cloning.py` — existing clone tests (pattern and helpers)
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Extend clone_workspace_from_activity() to clone tags

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

In `clone_workspace_from_activity()` (line 519-599), add tag cloning between the document cloning loop (line 592) and the CRDT replay call (line 595).

1. Add `TagGroup` and `Tag` to the imports from `promptgrimoire.db.models` at the top of the file (line 7-11 area).

2. After document cloning and before CRDT replay, add tag cloning:
   - Query all TagGroups for the template workspace, ordered by `order_index`
   - For each template TagGroup, create a new TagGroup in the clone workspace with the same `name` and `order_index`. Build `group_id_map: dict[UUID, UUID]` mapping old → new group IDs.
   - Query all Tags for the template workspace, ordered by `order_index`
   - For each template Tag, create a new Tag in the clone workspace with: same `name`, `color`, `description`, `locked`, `order_index`, and `group_id=group_id_map.get(template_tag.group_id)` (remapped, or None if ungrouped). Build `tag_id_map: dict[UUID, UUID]` mapping old → new tag IDs.

3. Pass `tag_id_map` to `_replay_crdt_state()`:
   - Change the call from `_replay_crdt_state(template, clone, doc_id_map)` to `_replay_crdt_state(template, clone, doc_id_map, tag_id_map)`

4. Update the docstring of `clone_workspace_from_activity()` to mention tag cloning.

5. Update the return type if needed — the function currently returns `tuple[Workspace, dict[UUID, UUID]]` (workspace + doc_id_map). Consider whether callers need `tag_id_map` too. If not, keep the return type unchanged.

**Note:** Tags are created directly via `session.add()`, NOT via the `create_tag()`/`create_tag_group()` CRUD functions. The CRUD functions enforce `allow_tag_creation` permission, but cloning is a system operation that should always copy the instructor's tag set regardless of the permission flag.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: clone TagGroup and Tag rows during workspace cloning`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Extend _replay_crdt_state() with tag_id_map remapping

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

Update `_replay_crdt_state()` (line 450-516) to accept and use a tag remapping:

1. Add `tag_id_map: dict[UUID, UUID] | None = None` parameter to the function signature (after `doc_id_map`).

2. In the highlight replay loop (lines 492-500), remap the tag field:
   ```python
   # Remap tag UUID if tag_id_map provided
   raw_tag = hl["tag"]
   if tag_id_map is not None:
       try:
           template_tag_uuid = UUID(raw_tag)
           remapped_tag = str(tag_id_map.get(template_tag_uuid, template_tag_uuid))
       except ValueError:
           # Not a UUID (legacy BriefTag string) — pass through
           remapped_tag = raw_tag
   else:
       remapped_tag = raw_tag
   ```
   Then pass `tag=remapped_tag` to `clone_doc.add_highlight()`.

3. After replaying all highlights and general notes, rebuild `tag_order` from the template doc with remapped keys and the new highlight IDs:
   - Read `template_doc.tag_order` — iterate its keys
   - For each key in the template's `tag_order`:
     - Remap the key through `tag_id_map` (if provided and key is a valid UUID)
     - The highlight IDs in the array need to map from template highlight IDs to clone highlight IDs. Build a `highlight_id_map` during the highlight replay loop (map old → new highlight IDs from the `add_highlight()` return values).
     - Set `clone_doc.set_tag_order(remapped_key, [highlight_id_map.get(old_id, old_id) for old_id in template_order])`

4. To build the `highlight_id_map`: during the highlight replay loop, capture the mapping:
   ```python
   highlight_id_map: dict[str, str] = {}
   for hl in template_doc.get_all_highlights():
       old_id = hl["id"]
       new_id = clone_doc.add_highlight(...)
       highlight_id_map[old_id] = new_id
   ```
   This is a small change to the existing loop — currently `new_hl_id` is only used for comment replay. Now it also feeds the highlight_id_map.

5. Update the docstring to document the new parameter and tag_order rebuilding.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-debug`
Expected: Existing workspace cloning tests still pass (backward compatible — `tag_id_map` defaults to None)

**Commit:** `feat: remap tag UUIDs and tag_order during CRDT state replay`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Integration tests for tag cloning

**Verifies:** 95-annotation-tags.AC4.1, 95-annotation-tags.AC4.2, 95-annotation-tags.AC4.5, 95-annotation-tags.AC4.6

**Files:**
- Create: `tests/integration/test_tag_cloning.py`

**Implementation:**

Follow the pattern from `tests/integration/test_workspace_cloning.py`:
- Module-level `pytestmark` skip guard
- Reuse or adapt the `_make_clone_user()` and `_make_activity_with_docs()` helpers
- Add a helper `_make_activity_with_tags()` that creates a Course → Week → Activity, then adds TagGroups and Tags to the template workspace via direct `session.add()` (or via Phase 2 CRUD — either works since the template workspace will have `allow_tag_creation=True` by default)

**Testing:**

`TestTagGroupCloning`:
- AC4.1: Create activity with 2 TagGroups. Clone workspace. Verify clone has 2 TagGroups with same names and order_index but different UUIDs and the clone's workspace_id.

`TestTagCloning`:
- AC4.2: Create activity with 1 TagGroup and 3 Tags (2 in the group, 1 ungrouped). Clone workspace. Verify clone has 3 Tags with correct names, colors, descriptions. Verify grouped tags point to the clone's TagGroup UUID (not the template's). Verify ungrouped tag has `group_id=None`.
- AC4.5: Create activity with a tag where `locked=True`. Clone. Verify cloned tag has `locked=True`.

`TestEmptyTagClone`:
- AC4.6: Create activity with no tags. Clone workspace. Verify clone has 0 TagGroups and 0 Tags. Verify clone completed successfully.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag row cloning`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests for CRDT tag remapping during clone

**Verifies:** 95-annotation-tags.AC4.3, 95-annotation-tags.AC4.4

**Files:**
- Modify: `tests/integration/test_tag_cloning.py`

**Implementation:**

Add test classes that verify CRDT state is correctly remapped during cloning.

These tests need to set up template workspace CRDT state with highlights referencing Tag UUIDs before cloning. Pattern:
1. Create activity with tags
2. Build CRDT state on the template workspace — create an `AnnotationDocument`, add highlights with `tag=str(template_tag.id)`, set `tag_order`, serialise via `get_full_state()`, save to template workspace's `crdt_state` column
3. Clone the workspace
4. Load the clone's CRDT state into a new `AnnotationDocument`
5. Verify highlights and tag_order use the cloned Tag UUIDs

**Testing:**

`TestCrdtTagRemapping`:
- AC4.3: Create activity with 2 tags. Add 3 highlights to template CRDT: 2 for tag A, 1 for tag B. Clone workspace. Load clone CRDT. Verify all highlights have tags remapped to the clone's Tag UUIDs (not the template's).
- AC4.4: Set `tag_order` on template with `{str(tag_a.id): [hl1, hl2], str(tag_b.id): [hl3]}`. Clone workspace. Load clone CRDT. Verify `tag_order` keys are the clone's Tag UUIDs. Verify highlight IDs in tag_order arrays are the clone's highlight IDs (new UUIDs, not template's).

`TestLegacyBriefTagPassthrough`:
- AC4.3 (backward compat): Create activity with 1 tag. Add 2 highlights to template CRDT: one with `tag=str(tag.id)` (UUID), one with `tag="jurisdiction"` (legacy BriefTag string — not a valid UUID). Clone workspace. Load clone CRDT. Verify the UUID-tagged highlight has its tag remapped to the clone's Tag UUID. Verify the legacy string-tagged highlight retains `tag="jurisdiction"` unchanged (passthrough via the `except ValueError` path in `_replay_crdt_state()`).

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for CRDT tag remapping during clone`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
