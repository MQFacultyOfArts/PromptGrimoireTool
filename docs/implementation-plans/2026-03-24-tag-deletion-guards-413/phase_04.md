# Tag Deletion Guards & Import Hardening — Phase 4: UI Loading Guards

**Goal:** Prevent rapid-fire clicks on tag creation and import buttons by adding loading/disabled state during async operations.

**Architecture:** Follows the existing Done button pattern (tag_management.py:183-227): `btn.disable()` + `btn.props("loading")` in try/finally. "Add tag" buttons pass `e.sender` via lambda to give the callback access to the button element. `DuplicateNameError` caught in import path as defence-in-depth.

**Tech Stack:** Python 3.14, NiceGUI (ui.button props/disable)

**Scope:** Phase 4 of 4 from original design (independent of Phases 1-3)

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-deletion-guards-413.AC5: UI loading guards prevent rapid-fire clicks
- **tag-deletion-guards-413.AC5.1 Success:** Import button shows loading state and is disabled during async operation
- **tag-deletion-guards-413.AC5.2 Success:** "Add tag" button in management dialog shows loading state during creation
- **tag-deletion-guards-413.AC5.3 Success:** Quick Create save button shows loading state during creation
- **tag-deletion-guards-413.AC5.4 Success:** All three buttons re-enable after operation completes (success or failure)
- **tag-deletion-guards-413.AC5.5 Failure:** `DuplicateNameError` from import shows user notification (not Discord alert)

---

<!-- START_TASK_1 -->
### Task 1: Add loading guard to import button and catch DuplicateNameError

**Verifies:** tag-deletion-guards-413.AC5.1, tag-deletion-guards-413.AC5.4, tag-deletion-guards-413.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_import.py:99-136` (`_import_from_workspace` and import button creation)

**Implementation:**

The import button is created at line 134-136:
```python
ui.button("Import", on_click=_import_from_workspace).props(
    'flat dense data-testid="import-tags-btn"'
)
```

Change to capture button reference, add loading guard to `_import_from_workspace`:

```python
import_btn = ui.button("Import").props(
    'flat dense data-testid="import-tags-btn"'
)

async def _import_from_workspace() -> None:
    if not ws_select.value:
        ui.notify("Select a workspace first", type="warning")
        return

    import_btn.disable()
    import_btn.props("loading")
    try:
        # ... existing import logic (updated for ImportResult in Phase 3) ...
    except DuplicateNameError as exc:
        logger.warning(
            "tag_import_duplicate",
            operation="import_tags",
            reason=str(exc),
        )
        ui.notify(str(exc), type="warning")
        return
    finally:
        import_btn.props(remove="loading")
        import_btn.enable()

import_btn.on_click(_import_from_workspace)
```

Add `DuplicateNameError` to the existing imports from `promptgrimoire.db.exceptions` (alongside `SharePermissionError`, `TagCreationDeniedError` at line 114).

The `DuplicateNameError` catch goes after the existing `except (SharePermissionError, TagCreationDeniedError)` block. Note: After Phase 3's `ON CONFLICT DO NOTHING` rewrite, this should be unreachable from the import path — it's defence-in-depth.

**Testing:**

Tests must verify:
- tag-deletion-guards-413.AC5.1: Import button has `loading` prop and is disabled during import operation
- tag-deletion-guards-413.AC5.4: Import button re-enables after both successful and failed imports
- tag-deletion-guards-413.AC5.5: `DuplicateNameError` shows warning notification, not Discord alert

**Human UAT verification required for AC5.1 and AC5.4** — button loading state is visual and best verified manually. The `loading` prop and `disable()` calls are straightforward NiceGUI patterns; the code change is the test.

For AC5.5, an integration test can verify that `DuplicateNameError` is caught by checking log output level (warning, not error).

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat(ui): add loading guard to import button, catch DuplicateNameError (#413)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add loading guard to "Add tag" buttons

**Verifies:** tag-deletion-guards-413.AC5.2, tag-deletion-guards-413.AC5.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py:542-553` (`_add_tag_in_group`)
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py:580-584` (callback dict)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py:557-561` (grouped "Add tag" button lambda)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py:583-587` (ungrouped "Add tag" button lambda)

**Implementation:**

**Step A — Update `_add_tag_in_group` to accept sender button:**

```python
async def _add_tag_in_group(
    group_id: UUID | None, btn: ui.button | None = None
) -> None:
    if btn is not None:
        btn.disable()
        btn.props("loading")
    try:
        existing_names = (
            {t.name for t in state.tag_info_list} if state.tag_info_list else set()
        )
        name = _unique_tag_name(existing_names)
        tag = await _create_tag_or_notify(
            create_tag, state, name, _PRESET_PALETTE[0], group_id
        )
        if tag is None:
            return
        await render_tag_list()
        await _refresh_tag_state(state)
    finally:
        if btn is not None:
            btn.props(remove="loading")
            btn.enable()
```

**Step B — Update callback dict type hint** (line 580-584):

The callback dict key `"add_tag"` changes signature. Update the return type annotation if one exists. The dict is used by `tag_management_rows.py` to wire up buttons.

**Step C — Update button lambdas in `tag_management_rows.py`:**

At line 557-561 (grouped):
```python
ui.button(
    "+ Add tag",
    on_click=lambda e, gid=group.id: on_add_tag(gid, e.sender),
).props(f"flat dense data-testid=group-add-tag-btn-{group.id}").classes(
    "text-xs ml-8 mt-1"
)
```

At line 583-587 (ungrouped):
```python
ui.button(
    "+ Add tag",
    on_click=lambda e: on_add_tag(None, e.sender),
).props('flat dense data-testid="add-ungrouped-tag-btn"').classes(
    "text-xs ml-8 mt-1"
)
```

Check how `on_add_tag` is passed into the rendering function — verify the parameter name and that the type annotation accepts the new signature. Search for where the callback dict is destructured in `tag_management_rows.py`.

**Testing:**

Tests must verify:
- tag-deletion-guards-413.AC5.2: "Add tag" button shows loading state during tag creation
- tag-deletion-guards-413.AC5.4: Button re-enables after creation completes (success or failure)

E2E test: click "Add tag", verify button has loading prop, wait for tag to appear, verify button is re-enabled.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat(ui): add loading guard to add-tag buttons (#413)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add loading guard to Quick Create save button

**Verifies:** tag-deletion-guards-413.AC5.3, tag-deletion-guards-413.AC5.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_quick_create.py:196-217` (`_save` closure and button creation)

**Implementation:**

The `create_btn` is defined at line 214 and is in the same closure scope as `_save` (line 196). Add loading guard inside `_save`:

```python
async def _save(text: str) -> None:
    create_btn.disable()
    create_btn.props("loading")
    try:
        ok = await _quick_create_save(
            state,
            text,
            selected_color,
            group_select,
            saved_start,
            saved_end,
        )
        if not ok:
            return

        dialog.close()
        ui.notify(
            f"Tag '{text}' created",
            type="positive",
        )
    finally:
        create_btn.props(remove="loading")
        create_btn.enable()
```

Note: `create_btn` is defined after `_save` in the source (line 214 vs 196), but this works because `_save` is a closure — it captures `create_btn` by name, not by value. By the time `_save` is called (user clicks the button), `create_btn` is already assigned.

Verify this works by checking that `on_submit_with_value` calls `_save` asynchronously (not at definition time).

**Testing:**

Tests must verify:
- tag-deletion-guards-413.AC5.3: Quick Create "Create" button shows loading state during creation
- tag-deletion-guards-413.AC5.4: Button re-enables after creation completes (success or failure)

E2E test: open quick create dialog, fill name, click Create, verify button has loading prop, verify tag appears.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat(ui): add loading guard to quick-create save button (#413)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E tests for loading guards

**Verifies:** tag-deletion-guards-413.AC5.1, tag-deletion-guards-413.AC5.2, tag-deletion-guards-413.AC5.3, tag-deletion-guards-413.AC5.4

**Files:**
- Create: `tests/e2e/test_tag_loading_guards.py`

**Implementation:**

Create E2E tests that verify buttons show loading state during async operations and re-enable afterwards. Use `data-testid` locators exclusively.

The key challenge: loading state is transient (appears during async operation, disappears on completion). Tests need to either:
1. Assert the button has `disabled` attribute and the `loading` prop *during* the operation (requires intercepting network or slowing the operation)
2. Assert the *result* of the guard: rapid double-click produces only one entity

Option 2 is more reliable for E2E — it tests the observable outcome rather than transient CSS state.

Tests:

**test_import_button_prevents_double_import (AC5.1, AC5.4):**
1. Set up two workspaces — source with tags, target empty
2. Open tag import section
3. Select source workspace
4. Verify import button has `data-testid="import-tags-btn"`
5. Click import button
6. Assert button becomes disabled during operation (check `disabled` attribute)
7. After import completes, assert button is re-enabled
8. Assert imported tags appear

**test_add_tag_button_prevents_rapid_creation (AC5.2, AC5.4):**
1. Set up workspace, open tag management dialog
2. Click "Add tag" button
3. Wait for tag to appear
4. Count tags — should be exactly 1 new tag (not 2+ from rapid clicks)

**test_quick_create_button_prevents_double_create (AC5.3, AC5.4):**
1. Set up workspace with content, open quick create dialog
2. Fill tag name
3. Click Create button
4. Assert button has `disabled` attribute during creation
5. After creation, assert tag appears in toolbar

All tests use `@pytest.mark.e2e` marker.

**Verification:**
Run: `uv run grimoire e2e run tests/e2e/test_tag_loading_guards.py`
Expected: All tests pass

**Commit:** `test(e2e): verify loading guards on tag buttons (#413)`
<!-- END_TASK_4 -->
