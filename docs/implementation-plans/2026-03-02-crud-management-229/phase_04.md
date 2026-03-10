# CRUD Management Implementation Plan - Phase 4: Week & Activity Edit Dialogs

**Goal:** Instructors can edit week and activity metadata via inline dialogs, with template clone warnings when students have cloned.

**Architecture:** Edit dialogs follow the existing settings dialog pattern (`ui.dialog()` + `ui.card()`, pre-filled inputs, async save handler) but additionally refresh the weeks list and broadcast to other clients. Template clone warning is an async pre-navigation check that shows an interstitial dialog only when student clones exist.

**Tech Stack:** NiceGUI, Quasar

**Scope:** Phase 4 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (data-testid convention)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC1: Edit week and activity metadata
- **crud-management-229.AC1.1 Success:** Instructor edits week title and week_number via dialog; changes persist after page refresh
- **crud-management-229.AC1.2 Success:** Instructor edits activity title and description via dialog; changes persist after page refresh
- **crud-management-229.AC1.3 Success:** Edit dialog pre-fills current values from the model
- **crud-management-229.AC1.4 Success:** Edit triggers broadcast refresh to other connected clients
- **crud-management-229.AC1.5 Edge:** Template clone warning shown when instructor clicks "Edit Template" on an activity with student clones
- **crud-management-229.AC1.6 Edge:** Template clone warning not shown when no students have cloned

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add open_edit_week() dialog

**Verifies:** crud-management-229.AC1.1, crud-management-229.AC1.3, crud-management-229.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add new function near existing dialog functions around lines 192-272)

**Implementation:**

Create `open_edit_week()` following the `open_course_settings()` dialog pattern at lines 192-224, with these differences:

Signature:
```python
async def open_edit_week(
    week: Week,
    weeks_list: ui.refreshable,
    course_id: UUID,
    client_id: str,
) -> None:
```

Dialog contents:
- Title: `f"Edit Week {week.week_number}"`
- `ui.number` input for week_number, pre-filled with `week.week_number`, min=1, max=52
- `ui.input` for title, pre-filled with `week.title`
- Cancel button (flat) and Save button (color=primary)
- Both with `data-testid` attributes: `"save-edit-week-btn"`, `"cancel-edit-week-btn"`

Save handler must:
1. Call `update_week(week.id, title=title_input.value, week_number=int(number_input.value))`
2. Update the in-memory `week` object via `setattr()` (matching settings pattern)
3. Close dialog
4. Notify: "Week updated"
5. Call `weeks_list.refresh()` (update originating client)
6. Call `_broadcast_weeks_refresh(course_id, client_id)` (update other clients)

Import `update_week` from `promptgrimoire.db.weeks` (may already be imported — check existing imports).

Add an "Edit" button to the week card header (in the `if can_manage:` block around lines 636-655, alongside publish/unpublish buttons):
```python
ui.button(
    icon="edit",
    on_click=lambda w=week: open_edit_week(w, weeks_list, cid, client_id),
).props('flat round dense data-testid="edit-week-btn"').tooltip("Edit Week")
```

**Scoping note:** The Edit button lambda references `weeks_list` which is the `@ui.refreshable` decorated function. This button MUST be placed inside the `@ui.refreshable weeks_list()` function body, not before it. Python closures allow referencing `weeks_list` in lambdas that execute after the function is defined, but the button rendering must occur within the refreshable scope for the `weeks_list.refresh()` call to work correctly.

**Testing:**

- crud-management-229.AC1.1: Open edit week dialog, change title and week_number, save. Verify changes persist by re-querying the week from the database.
- crud-management-229.AC1.3: Open edit week dialog, verify inputs are pre-filled with current week values.
- crud-management-229.AC1.4: After save, verify `_broadcast_weeks_refresh()` is called (this is best tested via E2E with two clients, but the integration test can verify the DB update persists).

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add edit week dialog with broadcast`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add open_edit_activity() dialog

**Verifies:** crud-management-229.AC1.2, crud-management-229.AC1.3, crud-management-229.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add new function near edit week dialog)

**Implementation:**

Create `open_edit_activity()` following the same pattern:

Signature:
```python
async def open_edit_activity(
    activity: Activity,
    weeks_list: ui.refreshable,
    course_id: UUID,
    client_id: str,
) -> None:
```

Dialog contents:
- Title: `f"Edit Activity: {activity.title}"`
- `ui.input` for title, pre-filled with `activity.title`
- `ui.textarea` for description, pre-filled with `activity.description or ""`
- Cancel and Save buttons with `data-testid`: `"save-edit-activity-btn"`, `"cancel-edit-activity-btn"`

Save handler must:
1. Call `update_activity(activity.id, title=title_input.value, description=desc_input.value or None)` — pass only title and description, not the tri-state policy fields (those stay in the separate settings dialog)
2. Update in-memory model
3. Close, notify, refresh, broadcast (same as edit week)

Add an "Edit" button to the activity row (in the `if can_manage:` block at `_render_activity_row()`):
```python
ui.button(
    icon="edit",
    on_click=lambda a=act: open_edit_activity(a, weeks_list, course_id, client_id),
).props(
    f'flat round dense size=sm data-testid="edit-activity-btn-{act.id}"'
).tooltip("Edit Activity")
```

Note: `_render_activity_row()` will need additional parameters for `weeks_list`, `course_id`, and `client_id` to pass them through to the dialog.

**Testing:**

- crud-management-229.AC1.2: Edit activity title and description via dialog, verify changes persist.
- crud-management-229.AC1.3: Dialog pre-fills current title and description.
- crud-management-229.AC1.4: Broadcast fires after save.

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add edit activity dialog with broadcast`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add template clone warning to Edit Template button

**Verifies:** crud-management-229.AC1.5, crud-management-229.AC1.6

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (Edit Template button handler at lines 549-553)

**Implementation:**

Replace the current direct-navigation lambda with an async handler that checks for student clones:

```python
async def handle_edit_template(activity_id: UUID, template_workspace_id: UUID) -> None:
    count = await has_student_workspaces(activity_id)
    if count > 0:
        # Show interstitial confirmation dialog
        with ui.dialog() as warn_dialog, ui.card().classes("w-96"):
            ui.label("Template Already Cloned").classes("text-lg font-bold")
            plural = "student has" if count == 1 else "students have"
            ui.label(
                f"{count} {plural} cloned this template. "
                "Changes here won't propagate to existing copies."
            )
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=warn_dialog.close).props(
                    'flat data-testid="cancel-template-warning-btn"'
                )
                qs = urlencode({"workspace_id": str(template_workspace_id)})
                ui.button(
                    "Proceed",
                    on_click=lambda: ui.navigate.to(f"/annotation?{qs}"),
                ).props('color=primary data-testid="proceed-template-warning-btn"')
        warn_dialog.open()
    else:
        qs = urlencode({"workspace_id": str(template_workspace_id)})
        ui.navigate.to(f"/annotation?{qs}")
```

Update the Edit Template button to use this handler:
```python
ui.button(
    btn_label,
    icon=btn_icon,
    on_click=lambda a=act: handle_edit_template(a.id, a.template_workspace_id),
).props(f'flat dense size=sm color=secondary data-testid="template-btn-{act.id}"')
```

Import `has_student_workspaces` from `promptgrimoire.db.workspaces`.

**Testing:**

- crud-management-229.AC1.5: Create activity, clone for a student, click Edit Template as instructor — warning dialog appears with student count, Proceed navigates, Cancel stays
- crud-management-229.AC1.6: Create activity with no clones, click Edit Template — navigates immediately, no dialog

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add template clone warning to Edit Template button`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests for edit dialogs and template warning

**Verifies:** crud-management-229.AC1.1, crud-management-229.AC1.2, crud-management-229.AC1.3, crud-management-229.AC1.5, crud-management-229.AC1.6

**Files:**
- Create: `tests/integration/test_edit_dialogs.py`

**Testing:**

Follow project test patterns (skip guard, class-based, UUID isolation).

Note: the edit dialogs are UI components, so full dialog interaction testing requires E2E tests. Integration tests focus on the underlying DB operations and the `has_student_workspaces()` query that drives the template warning.

**`TestEditWeekPersistence`** — AC1.1:
- Create a week, call `update_week()` with new title and week_number
- Re-fetch the week and verify updated values persist
- Verify original values were different (confirms the update happened)

**`TestEditActivityPersistence`** — AC1.2:
- Create an activity, call `update_activity()` with new title and description
- Re-fetch and verify updated values persist

**`TestTemplateCloneWarningQuery`** — AC1.5, AC1.6:
- Create activity with no clones — `has_student_workspaces()` returns 0 (AC1.6 scenario)
- Clone for one user — returns 1 (AC1.5 scenario)
- Clone for second user — returns 2

These tests verify the data layer that the UI relies on. The dialog rendering and user interaction are verified via E2E tests (Phase 3 added `data-testid` attributes that E2E tests can target).

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

Run: `uv run test-all`
Expected: No regressions

**Commit:** `test: add integration tests for edit persistence and template warning query`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
