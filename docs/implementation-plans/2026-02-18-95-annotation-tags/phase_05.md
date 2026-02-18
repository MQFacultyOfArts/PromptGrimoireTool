# Annotation Tag Configuration — Phase 5: Tag Management UX

**Goal:** UI for creating, editing, and organising tags within the annotation page via quick-create and full management dialogs.

**Architecture:** New `pages/annotation/tag_management.py` module with two dialog functions: `open_quick_create()` (creates a tag and immediately applies it as a highlight) and `open_tag_management()` (full editing, reordering, import, lock management). Both dialogs call Phase 2 CRUD functions and refresh Phase 4's `state.tag_info_list` + CSS after mutations. The "+" and gear buttons are appended to Phase 4's tag toolbar via new optional callback parameters. Visibility gated by `PlacementContext.allow_tag_creation` for creation controls and `ctx.is_template and is_privileged_user(auth_user)` for instructor-only features.

**Tech Stack:** NiceGUI (dialogs, inputs, color_input, SortableJS element), SQLModel

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC6: Tag management UX — quick create
- **95-annotation-tags.AC6.1 Success:** "+" button on toolbar opens quick-create dialog with name, color picker, optional group
- **95-annotation-tags.AC6.2 Success:** Creating a tag via quick-create applies it to the current text selection
- **95-annotation-tags.AC6.3 Failure:** "+" button is hidden when `allow_tag_creation` resolves to False

### 95-annotation-tags.AC7: Tag management UX — full dialog
- **95-annotation-tags.AC7.1 Success:** Gear button opens management dialog showing tags grouped by TagGroup
- **95-annotation-tags.AC7.2 Success:** Tags can be renamed, recolored, and given descriptions inline
- **95-annotation-tags.AC7.3 Success:** Tags can be moved between groups or ungrouped
- **95-annotation-tags.AC7.4 Success:** Tags and groups can be reordered via drag
- **95-annotation-tags.AC7.5 Success:** Tag deletion shows highlight count and requires confirmation
- **95-annotation-tags.AC7.6 Success:** Group deletion moves tags to ungrouped (no highlight loss)
- **95-annotation-tags.AC7.7 Success:** "Import tags from..." dropdown lists activities in course (instructor on template only)
- **95-annotation-tags.AC7.8 Success:** Lock toggle available for instructors on template workspaces
- **95-annotation-tags.AC7.9 Failure:** Locked tags show lock icon; edit/delete controls disabled for students

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/pages/annotation/tags.py` — `TagInfo` dataclass, `workspace_tags()` async query (Phase 4)
- `src/promptgrimoire/pages/annotation/__init__.py:165-214` — `PageState` dataclass
- `src/promptgrimoire/pages/annotation/workspace.py:630-719` — workspace rendering, `ctx` at line 645, `state` at line 649
- `src/promptgrimoire/pages/annotation/css.py:286-317` — `_build_tag_toolbar()` (Phase 4 version with `tag_info_list` and `on_tag_click` params)
- `src/promptgrimoire/pages/annotation/highlights.py:139-158` — `_update_highlight_css()` (Phase 4 version with colour dict)
- `src/promptgrimoire/pages/annotation/highlights.py:187-246` — `_add_highlight(state, tag: str)` (Phase 4 version)
- `src/promptgrimoire/pages/courses.py:125-199` — dialog patterns: `with ui.dialog() as dialog, ui.card().classes("w-96"):`
- `src/promptgrimoire/db/tags.py` — Phase 2 CRUD: `create_tag`, `create_tag_group`, `update_tag`, `delete_tag`, `reorder_tags`, `import_tags_from_activity`, etc.
- `src/promptgrimoire/db/workspaces.py:105-126` — `PlacementContext` (Phase 1 version with `allow_tag_creation` and `course_id`)
- `src/promptgrimoire/db/activities.py:153-165` — `list_activities_for_course(course_id)`
- `src/promptgrimoire/elements/sortable/sortable.py` — vendored SortableJS element with `on_end` callback
- `src/promptgrimoire/auth/__init__.py:39-52` — `is_privileged_user(auth_user)`
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

**Note on testing scope:** Phase 5 AC6/AC7 criteria describe UI dialog behavior. The underlying CRUD operations are fully tested in Phase 2 (`tests/integration/test_tag_crud.py`). The `workspace_tags()` query is tested in Phase 4. Phase 5 adds integration tests that verify the *combined workflow* — creating/importing tags and verifying they appear in the rendering pipeline — which is the integration point this phase wires together. Full UI interaction testing (dialog rendering, button visibility) requires E2E tests or manual UAT.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create tag_management.py with quick-create dialog

**Files:**
- Create: `src/promptgrimoire/pages/annotation/tag_management.py`

**Implementation:**

Create a new module in the annotation package with the quick-create dialog and shared utilities.

**Shared utilities:**

1. Define the preset colour palette constant — the 10 tab10 colors used in seed data:
   ```python
   _PRESET_PALETTE: list[str] = [
       "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
       "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
   ]
   ```

2. Create an async helper `_refresh_tag_state(state: PageState) -> None` that:
   - Imports `workspace_tags` from `promptgrimoire.pages.annotation.tags` (lazy import to avoid circular deps)
   - Reloads `state.tag_info_list = await workspace_tags(state.workspace_id)`
   - Imports `_update_highlight_css` from `promptgrimoire.pages.annotation.highlights` (lazy import)
   - Calls `_update_highlight_css(state)` to rebuild CSS with the new tag colours

**Quick-create dialog (`open_quick_create`):**

3. `async def open_quick_create(state: PageState) -> None:` — Opens a dialog for creating a new tag and applying it to the current text selection.

   The function:
   - Uses the standard dialog pattern: `with ui.dialog() as dialog, ui.card().classes("w-96"):`
   - Title: "Quick Create Tag"
   - Name input: `ui.input("Tag name").classes("w-full")` — required, validates non-empty
   - Colour picker section:
     - Label: "Colour"
     - Row of 10 preset swatch buttons — small coloured `ui.button("")` elements (e.g., `.classes("w-8 h-8 min-w-0 p-0 rounded-full")`) with `style=f"background-color: {color}"`. Clicking sets the selected colour and highlights the swatch (add a border/ring).
     - Below the preset row: a `ui.color_input(label="Custom", value=selected_color, preview=True, on_change=...)` for freeform selection
     - Default selection: first preset colour
   - Group dropdown: `ui.select(label="Group (optional)", options=..., value=None, clearable=True)` populated from `list_tag_groups_for_workspace(state.workspace_id)` (lazy import from `promptgrimoire.db.tags`)
   - Action buttons row:
     - Cancel button: `ui.button("Cancel", on_click=dialog.close).props("flat")`
     - Create button: calls the save handler

   Save handler logic:
   1. Validate name is not empty — `ui.notify("Name is required", type="warning")` if empty
   2. Import `create_tag` from `promptgrimoire.db.tags` (lazy import)
   3. Call `new_tag = await create_tag(workspace_id=state.workspace_id, name=name.value, color=selected_color, group_id=group_select.value)`
   4. Call `await _refresh_tag_state(state)` to reload tags and rebuild CSS
   5. Import `_add_highlight` from `promptgrimoire.pages.annotation.highlights` (lazy import)
   6. If `state.selection_start is not None and state.selection_end is not None`: call `await _add_highlight(state, str(new_tag.id))` — applies the new tag to the stored text selection
   7. Close dialog
   8. `ui.notify(f"Tag '{name.value}' created", type="positive")`

   The text selection coordinates (`state.selection_start`, `state.selection_end`) are set by JS events before the "+" button is clicked. They persist in Python state while the dialog is open — no special preservation mechanism needed. If no text was selected, the tag is created but no highlight is applied (tag appears in toolbar for future use).

   Wrap the `create_tag` call in try/except `PermissionError` — this shouldn't happen since the "+" button is hidden when creation is disallowed, but defense-in-depth: `ui.notify("Tag creation not allowed", type="negative")`.

4. Open the dialog with `dialog.open()`, then `await dialog` to suspend until the dialog closes. Both calls are required: `dialog.open()` makes the dialog visible; `await dialog` blocks the coroutine until `dialog.submit()` or `dialog.close()` is called. This ensures the caller (`_on_add_tag()` in Task 2) can rebuild the toolbar after the dialog returns.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add tag_management.py with quick-create dialog`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Extend toolbar with "+" and gear buttons, wire quick-create

**Verifies:** 95-annotation-tags.AC6.1, 95-annotation-tags.AC6.2, 95-annotation-tags.AC6.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/css.py`
- Modify: `src/promptgrimoire/pages/annotation/workspace.py`

**Implementation:**

**In `css.py` — extend `_build_tag_toolbar()` (Phase 4 version):**

1. Add two optional callback parameters to the signature:
   ```python
   def _build_tag_toolbar(
       tag_info_list: list[TagInfo],
       on_tag_click: Any,
       *,
       on_add_click: Any | None = None,
       on_manage_click: Any | None = None,
   ) -> Any:  # Returns the toolbar ui.row() element (set by Phase 4 Task 4)
   ```

2. After the existing tag button loop, append the action buttons:
   ```python
   # "+" button — quick-create (hidden when tag creation not allowed)
   if on_add_click is not None:
       ui.button("+", on_click=on_add_click).classes(
           "text-xs compact-btn"
       ).props("round dense").tooltip("Create new tag")

   # Gear button — full management (always visible)
   if on_manage_click is not None:
       ui.button(icon="settings", on_click=on_manage_click).classes(
           "text-xs compact-btn"
       ).props("round dense flat").tooltip("Manage tags")
   ```

   AC6.3 is enforced by passing `on_add_click=None` when `allow_tag_creation` is False (see workspace.py wiring below). The "+" button simply doesn't render.

**In `workspace.py` — wire the callbacks:**

3. Add import at top of file: `from promptgrimoire.pages.annotation.tag_management import open_quick_create`

4. In the workspace rendering function, after `ctx` is loaded (line 645) and `state` is created (line 649), define the callbacks:
   ```python
   # Tag management callbacks
   async def _on_add_tag() -> None:
       await open_quick_create(state)
       # Rebuild toolbar buttons — a new tag may have been created
       if state.toolbar_container is not None:
           state.toolbar_container.clear()
           with state.toolbar_container:
               _build_tag_toolbar(
                   state.tag_info_list or [],
                   handle_tag_click,
                   on_add_click=_on_add_tag if ctx.allow_tag_creation else None,
                   on_manage_click=_on_manage_tags,
               )

   async def _on_manage_tags() -> None:
       pass  # Wired in Task 5 (management dialog)
   ```
   Note: `handle_tag_click`, `ctx`, and the `_build_tag_toolbar` import must be in scope. They are — `handle_tag_click` is defined in the same `_setup_document_events()` scope, `ctx` is from the enclosing workspace rendering function, and `_build_tag_toolbar` is already imported by `document.py`.

5. Pass the callbacks to the document/toolbar setup. Find where `_build_tag_toolbar` is called (via `_setup_document_events` or `handle_tag_click`). The `on_add_click` should be `_on_add_tag` if `ctx.allow_tag_creation` else `None`. The `on_manage_click` should be `_on_manage_tags`.

   Since the toolbar is built inside `_setup_document_events()` in `document.py`, the callbacks need to be passed through. Update `_setup_document_events()` to accept `on_add_click` and `on_manage_click` parameters and forward them to `_build_tag_toolbar()`.

6. In the `_setup_document_events()` call in workspace.py, pass:
   ```python
   _setup_document_events(
       state,
       on_add_click=_on_add_tag if ctx.allow_tag_creation else None,
       on_manage_click=_on_manage_tags,
   )
   ```

**In `document.py` — accept and forward the new params:**

7. Update `_setup_document_events()` signature to accept `on_add_click: Any | None = None` and `on_manage_click: Any | None = None`.

8. Forward to `_build_tag_toolbar()`:
   ```python
   _build_tag_toolbar(
       state.tag_info_list or [],
       handle_tag_click,
       on_add_click=on_add_click,
       on_manage_click=on_manage_click,
   )
   ```

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: wire quick-create "+" button into tag toolbar`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Full management dialog — tag list, inline editing, group management

**Verifies:** 95-annotation-tags.AC7.1, 95-annotation-tags.AC7.2, 95-annotation-tags.AC7.3, 95-annotation-tags.AC7.5, 95-annotation-tags.AC7.6, 95-annotation-tags.AC7.9

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py`

**Implementation:**

Add `open_tag_management()` to `tag_management.py`:

```python
async def open_tag_management(
    state: PageState,
    ctx: PlacementContext,
    auth_user: dict,
) -> None:
```

**Dialog structure:**

1. Use wider dialog: `with ui.dialog() as dialog, ui.card().classes("w-[600px]"):`
2. Title: "Manage Tags"
3. Close button in header: `ui.button(icon="close", on_click=dialog.close).props("flat round dense")`

**Tag list rendering:**

4. Create an async inner function `_render_tag_list()` that:
   - Clears and rebuilds the tag list content area (use a `ui.column()` container that gets `.clear()` and repopulated)
   - Queries `list_tag_groups_for_workspace(state.workspace_id)` and `list_tags_for_workspace(state.workspace_id)` (lazy imports from `promptgrimoire.db.tags`)
   - Groups tags by `group_id` — tags with `group_id=None` go into an "Ungrouped" section at the bottom
   - For each group: renders a group header with name, then renders tags within the group
   - For "Ungrouped": renders tags without a group header

**Group header rendering:**

5. Each group header row contains:
   - Group name as `ui.input(value=group.name)` — editable inline
   - Save button (appears on change): calls `update_tag_group(group.id, name=new_name)` then re-renders
   - Delete group button (with confirmation): shows `ui.dialog` confirming "Delete group? Tags will become ungrouped." On confirm: calls `delete_tag_group(group.id)` then re-renders (AC7.6)

**Tag row rendering:**

6. Each tag row contains:
   - Colour swatch: small coloured div or button showing the tag's colour
   - Name: `ui.input(value=tag.name).classes("w-40")` — editable inline
   - Colour: `ui.color_input(value=tag.color, preview=True).classes("w-24")` — editable inline
   - Description: `ui.input(value=tag.description or "", label="Description").classes("flex-1")` — editable inline
   - Group assignment: `ui.select(options=group_options, value=tag.group_id, clearable=True, label="Group").classes("w-32")` — moving between groups (AC7.3)
   - Save button: calls `update_tag(tag.id, name=..., color=..., description=..., group_id=...)` then re-renders
   - Delete button: see below (AC7.5)

7. **Lock icon for locked tags (AC7.9):** If `tag.locked` is True:
   - Show a lock icon (`ui.icon("lock").classes("text-gray-400")`) next to the tag name
   - Determine if edit controls should be disabled: `is_instructor = ctx.is_template and is_privileged_user(auth_user)`. If the user is NOT an instructor, disable the name input, colour input, description input, group select, and delete button (`.props("disable")` or `.props("readonly")`).
   - If the user IS an instructor, locked tags are still editable (instructors can modify their own locked tags — the lock only prevents student modification). Wait — re-read AC7.8/7.9: "Lock toggle available for instructors on template workspaces" and "Locked tags show lock icon; edit/delete controls disabled for students." So: instructors see editable controls + lock toggle. Students see disabled controls + lock icon.

   Implementation:
   ```python
   is_instructor = ctx.is_template and is_privileged_user(auth_user)
   can_edit = not tag.locked or is_instructor
   ```
   If `not can_edit`: set `.props("readonly")` on inputs and `.props("disable")` on buttons.

8. **Delete with highlight count (AC7.5):** The delete button opens a confirmation dialog showing the count of highlights referencing this tag. To get the count without expensive CRDT parsing:
   - Load the workspace's CRDT state, create a temporary `AnnotationDocument`, iterate `get_all_highlights()`, count where `tag == str(tag.id)`
   - OR: for simplicity in the UI layer, just show "Delete tag '{name}'? This will remove all highlights using this tag." without the exact count. The CRDT cleanup happens in `delete_tag()` (Phase 2).
   - Preferred: show the count for user confidence. Import `AnnotationDocument` lazily, load workspace CRDT state, count matching highlights.
   - On confirm: call `delete_tag(tag.id)` (which handles CRDT cleanup internally), then call `_refresh_tag_state(state)`, re-render the dialog tag list.
   - Wrap in try/except `ValueError` (locked tag) — `ui.notify("Tag is locked", type="warning")`.

**Add tag button:**

9. At the bottom of each group section (and the ungrouped section), add an "Add tag" button that creates a new tag with default colour (first preset) in that group:
   ```python
   async def _add_tag_in_group(group_id: UUID | None) -> None:
       await create_tag(
           workspace_id=state.workspace_id,
           name="New tag",
           color=_PRESET_PALETTE[0],
           group_id=group_id,
       )
       await _render_tag_list()
       await _refresh_tag_state(state)
   ```

**Add group button:**

10. At the top or bottom of the dialog, add an "Add group" button:
    ```python
    async def _add_group() -> None:
        await create_tag_group(
            workspace_id=state.workspace_id,
            name="New group",
        )
        await _render_tag_list()
    ```

11. `dialog.open()` then `await dialog` — both calls required. `dialog.open()` makes the dialog visible; `await dialog` blocks until `dialog.submit()` or `dialog.close()` is called, so the caller (`_on_manage_tags()` in Task 5) can rebuild the toolbar after the dialog returns.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add full tag management dialog with inline editing and group CRUD`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Management dialog — drag reorder, import, and lock toggle

**Verifies:** 95-annotation-tags.AC7.4, 95-annotation-tags.AC7.7, 95-annotation-tags.AC7.8

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py`

**Implementation:**

Extend the management dialog from Task 3 with advanced features.

**Drag reorder (AC7.4):**

1. Wrap the tag rows within each group in a `Sortable` element (from `promptgrimoire.elements.sortable.sortable import Sortable`):
   ```python
   with Sortable(
       on_end=lambda e: _on_tag_reorder(e, group_id),
       options={"handle": ".drag-handle", "animation": 150},
   ):
       for tag in group_tags:
           with ui.row().classes("items-center w-full"):
               ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
               # ... tag row content from Task 3
   ```

2. The `_on_tag_reorder` handler reads the new order from the Sortable event and calls `reorder_tags(new_order)`:
   ```python
   async def _on_tag_reorder(e: Any, group_id: UUID | None) -> None:
       # e contains the new element order — extract tag IDs from data attributes
       # Sortable's on_end gives old_index and new_index
       # Recompute the full tag order for this group and call reorder_tags()
       ...
       await _refresh_tag_state(state)
   ```

   To track tag IDs in Sortable: each tag row element needs a `data-tag-id` attribute. Use `ui.element("div").props(f'data-tag-id="{tag.id}"')` as the wrapper, or store tag IDs in a list and reorder by index.

3. Similarly, wrap group sections in a top-level `Sortable` for group reordering:
   ```python
   async def _on_group_reorder(e: Any) -> None:
       # Extract new group order, call reorder_tag_groups()
       ...
       await _render_tag_list()
   ```

**Import tags from activity (AC7.7):**

4. Show the import section only when `ctx.is_template and is_privileged_user(auth_user)`:
   ```python
   if ctx.is_template and is_privileged_user(auth_user):
       # Import section
   ```

5. Create a dropdown populated with activities from the same course:
   ```python
   from promptgrimoire.db.activities import list_activities_for_course

   if ctx.course_id is not None:
       activities = await list_activities_for_course(ctx.course_id)
       activity_options = {
           str(a.id): a.title for a in activities
           if a.template_workspace_id != state.workspace_id  # Exclude self
       }
   ```
   Note: `ctx.course_id` is available from Phase 1's PlacementContext extension.

6. "Import" button next to the dropdown:
   ```python
   async def _import_from_activity() -> None:
       if activity_select.value:
           from promptgrimoire.db.tags import import_tags_from_activity
           await import_tags_from_activity(
               source_activity_id=UUID(activity_select.value),
               target_workspace_id=state.workspace_id,
           )
           await _render_tag_list()
           await _refresh_tag_state(state)
           ui.notify("Tags imported", type="positive")
   ```

**Lock toggle (AC7.8):**

7. Show lock toggle only when `ctx.is_template and is_privileged_user(auth_user)`:
   ```python
   if is_instructor:  # is_instructor = ctx.is_template and is_privileged_user(auth_user)
       lock_switch = ui.switch(value=tag.locked).tooltip(
           "Lock tag (prevents student modification)"
       )
       lock_switch.on_value_change(lambda e, tid=tag.id: _toggle_lock(tid, e.value))
   ```

8. The `_toggle_lock` handler:
   ```python
   async def _toggle_lock(tag_id: UUID, locked: bool) -> None:
       from promptgrimoire.db.tags import update_tag
       await update_tag(tag_id, locked=locked)
       await _render_tag_list()
   ```

   Phase 2's `update_tag()` uses a refined lock guard that always permits changes to the `locked` field itself, while blocking other field changes on locked tags. No special handling needed here.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add drag reorder, import, and lock toggle to management dialog`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Wire gear button to management dialog

**Verifies:** 95-annotation-tags.AC7.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py`

**Implementation:**

1. Add import: `from promptgrimoire.pages.annotation.tag_management import open_tag_management`

2. Replace the placeholder `_on_manage_tags` callback (from Task 2) with the real implementation:
   ```python
   async def _on_manage_tags() -> None:
       await open_tag_management(state, ctx, auth_user)
   ```

   `ctx` and `auth_user` are both available in the workspace rendering function scope (ctx at line 645, auth_user from the page route decorator).

3. After the management dialog closes (returns), the toolbar should reflect any tag changes. The `_refresh_tag_state()` inside the dialog already updates `state.tag_info_list` and CSS. But the toolbar buttons need rebuilding.

   Use `state.toolbar_container` (added to PageState in Phase 4) to clear and rebuild:
   ```python
   async def _on_manage_tags() -> None:
       await open_tag_management(state, ctx, auth_user)
       # Rebuild toolbar buttons — tags may have been added/removed/reordered
       if state.toolbar_container is not None:
           state.toolbar_container.clear()
           with state.toolbar_container:
               from promptgrimoire.pages.annotation.css import _build_tag_toolbar
               _build_tag_toolbar(
                   state.tag_info_list or [],
                   handle_tag_click,
                   on_add_click=_on_add_tag if ctx.allow_tag_creation else None,
                   on_manage_click=_on_manage_tags,
               )
   ```
   Note: `handle_tag_click` must be accessible — it's defined in the same scope (either passed as a parameter or captured in the closure from `_setup_document_events`). The implementer should verify the exact scope and adjust.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: wire gear button to full tag management dialog`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration tests for tag management workflow

**Verifies:** 95-annotation-tags.AC6.2 (workflow), 95-annotation-tags.AC6.3 (gating), 95-annotation-tags.AC7.5 (delete cascade), 95-annotation-tags.AC7.7 (import workflow)

**Files:**
- Create: `tests/integration/test_tag_management.py`

**Implementation:**

Follow the pattern from `tests/integration/test_tag_crud.py`:
- Module-level `pytestmark` skip guard
- Class-based grouping, `@pytest.mark.asyncio async def` methods
- Reuse the `_make_course_week_activity()` helper pattern

These tests verify the *combined workflow* that Phase 5 wires together — creating/importing tags and verifying they appear in the rendering pipeline. The dialog UI itself requires E2E testing; these tests exercise the underlying service-layer integration.

**Testing:**

`TestQuickCreateWorkflow`:
- AC6.2 (workflow): Create an activity with template workspace. Call `create_tag(workspace_id, name="Test", color="#1f77b4")`. Import `workspace_tags` from `promptgrimoire.pages.annotation.tags` and call `await workspace_tags(workspace_id)`. Verify the new tag appears in the returned list with correct name, colour, and a UUID `raw_key`. Then set up CRDT state on the workspace, call `AnnotationDocument.add_highlight(tag=raw_key)`, verify the highlight is stored with the correct tag UUID.

`TestCreationGating`:
- AC6.3 (gating): Create a Course with `default_allow_tag_creation=False`, an Activity with `allow_tag_creation=None` (inherits False). Get the template workspace ID. Call `create_tag(workspace_id, ...)` — should raise `PermissionError`. Then set `default_allow_tag_creation=True` on the course. Call `create_tag(workspace_id, ...)` — should succeed. (This re-verifies Phase 2 permission enforcement from the perspective of the rendering workflow.)

`TestDeleteWithCrdtCleanup`:
- AC7.5 (delete cascade): Create a workspace with a tag. Build CRDT state with 2 highlights referencing the tag UUID. Call `delete_tag(tag_id)`. Verify `workspace_tags(workspace_id)` no longer includes the deleted tag. Load CRDT state and verify the highlights are removed.

`TestImportWorkflow`:
- AC7.7 (import workflow): Create Activity A with template workspace containing 2 tags. Create Activity B with its own template workspace (no tags). Call `import_tags_from_activity(source_activity_id=A.id, target_workspace_id=B.template_workspace_id)`. Call `workspace_tags(B.template_workspace_id)`. Verify 2 tags appear with correct names and colours but different UUIDs from the source.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag management workflow`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->
