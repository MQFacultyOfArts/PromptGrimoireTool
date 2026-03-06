# Tag Lifecycle Refactor — Phase 4: Tag Management Dialog Refactor

**Goal:** Replace save-on-blur event handlers with NiceGUI data bindings, route all mutations through dual write.

**Architecture:** Replace `.on("blur")` / `.on("change")` handlers in tag_management_rows.py with `bind_value()` to model dicts. Save all modified rows on dialog close via "Done" button, with immediate debounced save for colour changes. Pass `crdt_doc=state.crdt_doc` to all db/tags.py mutation calls. After each mutation, `_refresh_tag_state()` reads from CRDT (Phase 3), then `state.broadcast_update()` propagates to other clients.

**Tech Stack:** NiceGUI bind_value(), ui.timer() for debounce, existing dual-write from Phase 2

**Scope:** 8 phases from original design (phase 4 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC2: Tag lifecycle sync
- **tag-lifecycle-235-291.AC2.1 Success:** Creating a tag via quick create immediately appears on all connected clients' tag bars (no refresh)
- **tag-lifecycle-235-291.AC2.2 Success:** Creating a tag via management dialog immediately appears on all connected clients
- **tag-lifecycle-235-291.AC2.3 Success:** Editing a tag's name updates on all connected clients' toolbars
- **tag-lifecycle-235-291.AC2.4 Success:** Editing a tag's colour updates highlight CSS on all connected clients
- **tag-lifecycle-235-291.AC2.5 Success:** Deleting a tag removes it from all connected clients' toolbars and organise tabs
- **tag-lifecycle-235-291.AC2.6 Success:** Every newly created tag has a group assignment (never "uncategorised" unless explicitly ungrouped)
- **tag-lifecycle-235-291.AC2.7 Failure:** Creating a tag with a duplicate name within the same workspace is rejected

### tag-lifecycle-235-291.AC4: Tag colour persistence
- **tag-lifecycle-235-291.AC4.1 Success:** Changing a tag's colour in the management dialog persists across page refresh
- **tag-lifecycle-235-291.AC4.2 Success:** Colour change propagates to all connected clients' highlight rendering

---

## Pre-existing Complexity Violations

The following functions in files touched by this phase exceed the complexipy threshold (15). When modifying these functions, extract helpers to bring them below threshold:

| Function | File | Complexity | Action |
|----------|------|-----------|--------|
| `_render_tag_row` | tag_management_rows.py | **38** | Phase 4 replaces event handlers — extract element creation, model binding, and colour debounce into separate helpers |
| `_build_management_callbacks` | tag_management.py | **27** | Phase 4 updates callbacks — extract callback groups (tag CRUD, group CRUD, reorder) into sub-functions |
| `open_quick_create` | tag_quick_create.py | **16** | Phase 4 adds crdt_doc — extract save handler and validation into named function |

**These must be below 15 after Phase 4 changes or commits will be rejected by pre-commit hook.**

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Replace save-on-blur with bind_value() in tag rows

**Verifies:** tag-lifecycle-235-291.AC4.1, tag-lifecycle-235-291.AC4.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py:25-186` (`_render_tag_row`)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py:71-122` (`_save_single_tag`)

**Implementation:**

In `_render_tag_row()`, replace the event-handler pattern with bind_value():

1. Create a model dict per tag row to track current values:
   ```python
   model = {
       "name": tag.name,
       "color": tag.color,
       "description": tag.description or "",
       "group_id": str(tag.group_id) if tag.group_id else None,
   }
   ```

2. Replace element creation + `.on("blur")` with `bind_value()`:
   ```python
   name_input = ui.input(value=model["name"]).bind_value(model, "name")
   desc_input = ui.input(value=model["description"]).bind_value(model, "description")
   color_input = ui.color_input(value=model["color"]).bind_value(model, "color")
   group_sel = ui.select(..., value=model["group_id"]).bind_value(model, "group_id")
   ```

3. Remove the `.on("blur", _blur_save)`, `.on("change", _blur_save)`, and `.on("update:model-value", _blur_save)` calls (lines 131-133).

4. Store the model dict in `tag_row_inputs[tag_id]` instead of raw element refs. Update `_save_single_tag()` to read from the model dict instead of element `.value` properties.

5. For colour changes that need immediate feedback (AC4.2), add a debounced save callback:
   ```python
   pending_timer = None
   def _on_color_change():
       nonlocal pending_timer
       if pending_timer:
           pending_timer.active = False
       pending_timer = ui.timer(
           0.3,
           lambda: asyncio.create_task(_save_and_broadcast(tag_id)),
           once=True,
       )
   color_input.on("change", _on_color_change)
   ```

**Testing:**

- The save logic is tested via integration tests in Task 3
- Colour persistence is tested via E2E in Task 5

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `refactor: replace save-on-blur with bind_value in tag management rows`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace save-on-blur with bind_value() in group rows

**Verifies:** tag-lifecycle-235-291.AC2.3 (group edits propagate)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py:191-272` (`_render_group_header`)

**Implementation:**

Same pattern as Task 1, but for group headers:

1. Create model dict per group:
   ```python
   model = {"name": group.name, "color": group.color or ""}
   ```

2. Bind elements:
   ```python
   group_name_input = ui.input(value=model["name"]).bind_value(model, "name")
   group_color_input = ui.color_input(value=model["color"]).bind_value(model, "color")
   ```

3. Remove `.on("blur", _blur_save)` and `.on("change", _blur_save)` (lines 261-262).

4. Store model in `group_row_inputs[group_id]`.

5. Add debounced colour save callback (same pattern as tag colour).

**Testing:**

- Covered by integration tests in Task 3

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `refactor: replace save-on-blur with bind_value in group management rows`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Update save logic to use dual-write and broadcast

**Verifies:** tag-lifecycle-235-291.AC2.3, tag-lifecycle-235-291.AC2.4, tag-lifecycle-235-291.AC2.5, tag-lifecycle-235-291.AC4.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py:71-149` (`_save_single_tag`, `_save_single_group`)
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py` (all db/tags.py call sites — lines 213, 220, 257, 284, 355, 371, 410, 449)

**Implementation:**

1. Update `_save_single_tag()` to:
   - Read values from model dict (not element refs)
   - Pass `crdt_doc=state.crdt_doc` to `update_tag()`
   - After successful save, call `_refresh_tag_state(state)` then `await state.broadcast_update()` if available

2. Update `_save_single_group()` similarly with `crdt_doc=state.crdt_doc` on `update_tag_group()`.

3. Update all mutation call sites in `tag_management.py`:
   - `create_tag()` → add `crdt_doc=state.crdt_doc`
   - `create_tag_group()` → add `crdt_doc=state.crdt_doc`
   - `delete_tag()` → add `crdt_doc=state.crdt_doc` (replaces `reload_crdt=True` path)
   - `delete_tag_group()` → add `crdt_doc=state.crdt_doc`
   - `reorder_tags()` → add `crdt_doc=state.crdt_doc`
   - `reorder_tag_groups()` → add `crdt_doc=state.crdt_doc`

4. After each mutation, ensure pattern is: DB+CRDT write → `_refresh_tag_state(state)` → `await state.broadcast_update()`.

5. The "Done" button handler should save all modified rows before closing. Iterate `tag_row_inputs` and `group_row_inputs`, call save for any that have changes.

**Testing:**

Integration tests:
- tag-lifecycle-235-291.AC4.1: Create tag with crdt_doc, update colour with crdt_doc, verify DB and CRDT both have new colour
- tag-lifecycle-235-291.AC2.5: Delete tag with crdt_doc, verify removed from both DB and CRDT

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v`
Expected: All tests pass

**Commit:** `feat: route tag management mutations through dual write with broadcast`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update quick create to use dual-write

**Verifies:** tag-lifecycle-235-291.AC2.1, tag-lifecycle-235-291.AC2.6, tag-lifecycle-235-291.AC2.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_quick_create.py:134-189` (save handler)

**Implementation:**

In the quick create save handler:
1. Pass `crdt_doc=state.crdt_doc` to `create_tag()` call
2. After successful creation, call `_refresh_tag_state(state)` then `await state.broadcast_update()`
3. Ensure group_id is always set (AC2.6) — the UI group selector must default to the first existing group. If no groups exist, the quick create button is disabled until a group is created via the management dialog. Do not auto-create groups.
4. Duplicate name handling (AC2.7): The existing IntegrityError handling in create_tag() already rejects duplicates. Verify the error message is surfaced to the user.

**Testing:**

Integration tests:
- tag-lifecycle-235-291.AC2.7: Call `create_tag()` twice with same name and workspace_id — verify IntegrityError or graceful rejection
- tag-lifecycle-235-291.AC2.6: Create tag via quick create with no group explicitly selected — verify the created tag has a non-None `group_id` (the UI must assign a default group)

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `feat: update quick create to use dual write with broadcast`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: E2E test — colour change persists across refresh

**Verifies:** tag-lifecycle-235-291.AC4.1, tag-lifecycle-235-291.AC4.2

**Files:**
- Test: `tests/e2e/test_tag_sync.py` (extend from Phase 3)

**Implementation:**

E2E test for the core bug fix (colour persistence):

1. Open workspace, open tag management dialog
2. Change a tag's colour via the colour picker
3. Close the dialog (Done button saves all modified rows)
4. Refresh the page
5. Reopen management dialog — verify the colour persisted (not reverted)
6. Verify the tag's highlight CSS on the annotation page uses the new colour

For AC4.2 (propagation): open a second browser context on the same workspace before step 2. After step 3, verify the second client's highlight CSS updates to the new colour without refresh.

**Testing:**

Two tests:
- `test_tag_colour_persists_across_refresh` (AC4.1)
- `test_tag_colour_propagates_to_second_client` (AC4.2)

**Verification:**
Run: `uv run grimoire e2e run -k "tag_colour"`
Expected: Both tests pass

**Commit:** `test: E2E verify tag colour persistence and propagation`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Full regression verification

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass. No save-on-blur handlers remain in tag_management_rows.py.

Run: `grep -n "on(\"blur\"" src/promptgrimoire/pages/annotation/tag_management_rows.py`
Expected: No matches (all blur handlers removed)

**Commit:** No commit needed — verification only

<!-- END_TASK_6 -->
