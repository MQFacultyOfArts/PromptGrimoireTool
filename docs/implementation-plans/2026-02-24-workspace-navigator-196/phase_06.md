# Workspace Navigator Implementation Plan — Phase 6: Inline Title Rename

**Goal:** Add inline workspace title editing from the navigator — pencil icon activates edit mode on a readonly input, save on blur/Enter, cancel on Escape. New workspaces default to the activity name.

**Architecture:** Each workspace title is a single `ui.input` that toggles between readonly (looks like plain text via Quasar `borderless` prop) and editable (outlined input) on pencil click. Save calls `update_workspace_title()`. The clone function is modified to default title to the activity name.

**Tech Stack:** NiceGUI (`ui.input` with Quasar props `readonly`/`borderless`/`outlined`), existing `update_workspace_title()` in `db/workspaces.py`.

**Scope:** Phase 6 of 8

**Codebase verified:** 2026-02-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC4: Inline title rename
- **workspace-navigator-196.AC4.1 Success:** Pencil icon next to workspace title activates inline edit
- **workspace-navigator-196.AC4.2 Success:** Enter or blur saves the new title
- **workspace-navigator-196.AC4.3 Success:** Escape cancels edit without saving
- **workspace-navigator-196.AC4.4 Success:** New workspaces created via [Start] default title to activity name
- **workspace-navigator-196.AC4.5 Failure:** Clicking pencil does not navigate to workspace (only title click navigates)

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/pages/navigator.py` — Navigator page from Phase 4. Workspace entries render title as a clickable link + pencil icon + action button. Only owners see the pencil.
- `src/promptgrimoire/db/workspaces.py:784-800` — `update_workspace_title(workspace_id: UUID, title: str | None) -> Workspace`. Uses shared `_update_workspace_fields()` helper which auto-updates `updated_at`.
- `src/promptgrimoire/db/workspaces.py:591-727` — `clone_workspace_from_activity(activity_id, user_id)`. Currently sets `title=None` on the clone (line 632-635). The Activity object is loaded at line 618: `activity = await session.get(Activity, activity_id)`.
- `src/promptgrimoire/db/models.py:344` — `Workspace.title: str | None = Field(default=None, sa_column=Column(sa.Text(), nullable=True))`
- `src/promptgrimoire/db/models.py:280` — `Activity.title: str = Field(max_length=200)`
- `src/promptgrimoire/pages/annotation/tag_management_rows.py:125-133` — Existing blur-save pattern: `.on("blur", async_callback)`.
- `docs/nicegui/ui-patterns.md` — NiceGUI patterns for `ui.input`, events, `ui.run_javascript`.

**Quasar QInput props for inline edit:**
- `readonly` — Input is read-only (no typing)
- `borderless` — No visible border/underline (looks like plain text)
- `outlined` — Visible border around input (edit mode appearance)
- `dense` — Compact height
- `.props(add='outlined', remove='readonly borderless')` — Switch to edit mode
- `.props(add='readonly borderless', remove='outlined')` — Switch to view mode

**Event handlers on ui.input:**
- `.on('keydown.enter', handler)` — Enter key pressed
- `.on('blur', handler)` — Input loses focus
- `.on('keydown.escape', handler)` — Escape key pressed

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Set default title on workspace clone

**Verifies:** workspace-navigator-196.AC4.4

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (around line 632-635)
- Modify: existing clone integration tests (if they assert on title)

**Implementation:**

In `clone_workspace_from_activity()`, after loading the activity (line 618), set the cloned workspace's title to the activity title:

```python
clone = Workspace(
    activity_id=activity_id,
    enable_save_as_draft=template.enable_save_as_draft,
    title=activity.title,  # Default title to activity name
)
```

This ensures every cloned workspace gets a sensible default title regardless of which page triggers the clone.

Update any existing tests that assert the cloned workspace has `title=None` — they should now expect `title=activity.title`.

**Verification:**
Run: `uv run test-changed`
Expected: All tests pass (updated assertions for title default).

**Commit:** `feat: default cloned workspace title to activity name`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Inline title edit with readonly toggle

**Verifies:** workspace-navigator-196.AC4.1, workspace-navigator-196.AC4.2, workspace-navigator-196.AC4.3, workspace-navigator-196.AC4.5

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

Replace the workspace title rendering for owned workspaces with an inline-editable pattern:

1. **Title element:** Use `ui.input` with value set to `row.title or "Untitled Workspace"`. Apply `.props('readonly borderless dense')` — looks like plain text.

2. **Pencil icon:** `ui.icon('edit', size='xs')` next to the title input. Only rendered when `row.permission == "owner"`. On click:
   - Store the current value as `original_title` (for Escape revert).
   - Switch props: `.props(remove='readonly borderless', add='outlined')`.
   - Focus the input: `title_input.run_method('focus')` or `title_input.run_method('select')`.

3. **Save on Enter/blur (with guard against double-fire):**
   Enter causes both `keydown.enter` and `blur` to fire. Use a `_saving` guard to prevent duplicate DB calls:
   ```python
   _saving = False

   async def save_title(e):
       nonlocal _saving
       if _saving:
           return
       _saving = True
       try:
           new_title = title_input.value.strip() or None
           await update_workspace_title(row.workspace_id, new_title)
           title_input.props(remove='outlined', add='readonly borderless')
       finally:
           _saving = False

   title_input.on('keydown.enter', save_title)
   title_input.on('blur', save_title)
   ```

5. **Cancel on Escape:**
   ```python
   async def cancel_edit(e):
       title_input.value = original_title
       title_input.props(remove='outlined', add='readonly borderless')
   title_input.on('keydown.escape', cancel_edit)
   ```

6. **Prevent navigation on pencil click (AC4.5):** The pencil icon's click handler only triggers edit mode — it does NOT call `ui.navigate.to()`. The title text itself (for non-owners, or when not in edit mode) remains a clickable link that navigates. For owners, the title input is readonly but clicking it should also navigate (not edit) — only the pencil icon activates edit mode. Consider wrapping the readonly input in a click handler that navigates.

**Verification:**
Manual: Click pencil → input becomes editable with border. Type new title, press Enter → saves, returns to readonly. Press Escape → reverts. Blur → saves. Refresh → title persists.
Run: `uv run test-changed`

**Commit:** `feat: add inline title rename with pencil icon on navigator`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: E2E test — inline title rename

**Verifies:** workspace-navigator-196.AC4.1, workspace-navigator-196.AC4.2, workspace-navigator-196.AC4.3, workspace-navigator-196.AC4.5

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E tests for inline title editing using Playwright:

- AC4.1: Click pencil icon on an owned workspace. Verify the input becomes editable (check for `outlined` class or absence of `readonly` attribute).
- AC4.2 (Enter): Type a new title, press Enter. Verify the title updates in the UI. Refresh the page — verify title persists.
- AC4.2 (blur): Click pencil, type a title, click elsewhere (blur). Verify title saves.
- AC4.3: Click pencil, type a different title, press Escape. Verify title reverts to original.
- AC4.5: Click the pencil icon. Verify the URL does NOT change (still on `/`). Then click the workspace title text (not in edit mode) — verify navigation to `/annotation?workspace_id=...`.

Use `page.locator('[data-testid="edit-title-btn"]')` or similar for the pencil icon.

**Verification:**
Run: `uv run test-e2e -k test_navigator`
Expected: All rename E2E tests pass.

**Commit:** `test: add E2E tests for inline title rename on navigator`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E test — default title on Start

**Verifies:** workspace-navigator-196.AC4.4

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E test verifying default title on workspace clone:
- Create a course with a published activity titled "Annotate Becky Bennett Interview".
- As enrolled student, navigate to `/` and click "Start" on the activity.
- After navigation to the new workspace, navigate back to `/`.
- Verify the workspace appears in "My Work" with title "Annotate Becky Bennett Interview" (not "Untitled Workspace").

**Verification:**
Run: `uv run test-e2e -k test_navigator`
Expected: All tests pass.

**Commit:** `test: add E2E test for default title on workspace clone`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

---

## Next Phase

Phase 7 adds cursor pagination UI ("Load more" button, DOM append into sections).
