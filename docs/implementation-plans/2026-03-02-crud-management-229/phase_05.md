# CRUD Management Implementation Plan - Phase 5: Week, Activity & Unit Delete UI

**Goal:** Instructors can delete weeks, activities, and units from the course management UI with appropriate guards, confirmation dialogs, and admin force-delete override.

**Architecture:** Delete buttons appear for authorised users (can_manage for weeks/activities, coordinator/admin for units). All deletes show confirmation dialogs. DeletionBlockedError is caught and shown as a notification for non-admins, or as a force-delete dialog for org-level admins. After deletion, the UI refreshes and broadcasts to other clients.

**Tech Stack:** NiceGUI, Quasar

**Scope:** Phase 5 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (data-testid convention)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC2: Delete weeks and activities (guarded)
- **crud-management-229.AC2.1 Success:** Instructor deletes a week with no student workspaces; week and its activities are removed
- **crud-management-229.AC2.2 Success:** Instructor deletes an activity with no student workspaces; activity and template workspace are removed
- **crud-management-229.AC2.3 Failure:** Delete blocked with notification showing student count when student workspaces exist (force=False)
- **crud-management-229.AC2.4 Success:** Admin force-deletes a week with student workspaces; cascade removes all child entities
- **crud-management-229.AC2.5 Success:** Confirmation dialog shown before all destructive deletes
- **crud-management-229.AC2.6 Success:** UI refreshes and broadcasts after deletion

### crud-management-229.AC6: Unit deletion
- **crud-management-229.AC6.1 Success:** Admin deletes a unit with no student workspaces
- **crud-management-229.AC6.2 Success:** Convenor (coordinator) deletes their own unit with no student workspaces
- **crud-management-229.AC6.3 Failure:** Delete blocked when student workspaces exist (same guard as weeks/activities)
- **crud-management-229.AC6.4 Success:** Admin force-deletes unit with student workspaces
- **crud-management-229.AC6.5 Failure:** Non-admin, non-convenor cannot see Delete Unit button

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add delete confirmation dialog helper

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add helper function near existing dialog functions)

**Implementation:**

Create a reusable async confirmation dialog for destructive operations. Follow the awaitable pattern from `dialogs.py:44-85` using `dialog.submit()`:

```python
async def _confirm_delete(title: str, message: str) -> bool:
    """Show a confirmation dialog for destructive operations.

    Returns True if user confirmed, False if cancelled.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(title).classes("text-lg font-bold")
        ui.label(message).classes("text-sm my-2")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                'flat data-testid="cancel-delete-btn"'
            )
            ui.button("Delete", on_click=lambda: dialog.submit(True)).props(
                'outline color=negative data-testid="confirm-delete-btn"'
            )
    dialog.open()
    return await dialog
```

Also create a force-delete dialog for admins when DeletionBlockedError is caught:

```python
async def _confirm_force_delete(count: int, entity_type: str) -> bool:
    """Show force-delete dialog for admins when student workspaces block deletion.

    Args:
        count: Number of student workspaces that will be destroyed.
        entity_type: "week", "activity", or "unit" for the message.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Force Delete {entity_type.title()}?").classes(
            "text-lg font-bold"
        )
        plural = "workspace" if count == 1 else "workspaces"
        ui.label(
            f"{count} student {plural} will be permanently destroyed. "
            "This cannot be undone."
        ).classes("text-sm text-red-600 my-2")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                'flat data-testid="cancel-force-delete-btn"'
            )
            ui.button(
                "Force Delete", on_click=lambda: dialog.submit(True)
            ).props(
                'outline color=negative data-testid="confirm-force-delete-btn"'
            )
    dialog.open()
    return await dialog
```

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add delete confirmation dialog helpers`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add delete buttons for weeks and activities

**Verifies:** crud-management-229.AC2.1, crud-management-229.AC2.2, crud-management-229.AC2.3, crud-management-229.AC2.4, crud-management-229.AC2.5, crud-management-229.AC2.6

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (week card rendering around lines 636-655, activity row in `_render_activity_row()`)

**Implementation:**

Add imports for `delete_week`, `delete_activity`, `DeletionBlockedError`:
```python
from promptgrimoire.db.weeks import create_week, delete_week, ...
from promptgrimoire.db.activities import create_activity, delete_activity, ...
from promptgrimoire.db.exceptions import DeletionBlockedError
```

**Delete Week button** — add to the week card's `if can_manage:` button row (alongside edit and publish buttons):

```python
ui.button(
    icon="delete",
    on_click=lambda w=week: handle_delete_week(w),
).props(
    'flat round dense color=negative data-testid="delete-week-btn"'
).tooltip("Delete Week")
```

The async handler:
```python
async def handle_delete_week(week: Week) -> None:
    confirmed = await _confirm_delete(
        f"Delete Week {week.week_number}?",
        f'Delete "{week.title}" and all its activities? This cannot be undone.',
    )
    if not confirmed:
        return
    try:
        await delete_week(week.id)
        weeks_list.refresh()
        _broadcast_weeks_refresh(cid, client_id)
        ui.notify(f"Week {week.week_number} deleted", type="positive")
    except DeletionBlockedError as e:
        auth_user = _get_current_user()
        is_admin = auth_user and auth_user.get("is_admin") is True
        if is_admin:
            force = await _confirm_force_delete(
                e.student_workspace_count, "week"
            )
            if force:
                await delete_week(week.id, force=True)
                weeks_list.refresh()
                _broadcast_weeks_refresh(cid, client_id)
                ui.notify(f"Week {week.week_number} force-deleted", type="positive")
        else:
            plural = "workspace" if e.student_workspace_count == 1 else "workspaces"
            ui.notify(
                f"Cannot delete: {e.student_workspace_count} student {plural} exist. "
                "Contact an administrator.",
                type="negative",
            )
```

**Delete Activity button** — add to the activity row's `if can_manage:` section:

```python
ui.button(
    icon="delete",
    on_click=lambda a=act: handle_delete_activity(a),
).props(
    f'flat round dense size=sm color=negative '
    f'data-testid="delete-activity-btn-{act.id}"'
).tooltip("Delete Activity")
```

The handler follows the same pattern as delete week, calling `delete_activity()` instead. `_render_activity_row()` will need additional parameters (`weeks_list`, `course_id`, `client_id`, `auth_user` or `is_admin`) to support the delete handler.

**Testing:**

- crud-management-229.AC2.1: Delete week with no student workspaces via UI — week disappears from list
- crud-management-229.AC2.2: Delete activity with no student workspaces — activity disappears
- crud-management-229.AC2.3: Delete blocked — notification shows student count
- crud-management-229.AC2.4: Admin force-delete — second dialog appears, force proceeds
- crud-management-229.AC2.5: Confirmation dialog appears before all deletes
- crud-management-229.AC2.6: After deletion, `weeks_list.refresh()` and `_broadcast_weeks_refresh()` called

Integration tests verify the DB operations (Phase 2). E2E tests verify the full dialog flow using `data-testid` attributes added here.

**Verification:**

Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-all`
Expected: No regressions

**Commit:** `feat: add delete buttons for weeks and activities with guards`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add Delete Unit button to action bar

**Verifies:** crud-management-229.AC6.1, crud-management-229.AC6.2, crud-management-229.AC6.3, crud-management-229.AC6.4, crud-management-229.AC6.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (action bar section, currently around lines 498-506)

**Implementation:**

Add import for `delete_course`:
```python
from promptgrimoire.db.courses import ..., delete_course
```

Add "Delete Unit" button to the action bar, visible only to coordinators and org admins:

```python
auth_user = _get_current_user()
is_admin = auth_user and auth_user.get("is_admin") is True
can_delete_unit = enrollment.role == "coordinator" or is_admin

if can_manage:
    with ui.row().classes("gap-2 mb-4"):
        # ... existing Add Week, Manage Enrollments, Unit Settings buttons ...

        if can_delete_unit:
            ui.button(
                "Delete Unit",
                icon="delete_forever",
                on_click=lambda: handle_delete_course(),
            ).props(
                'outline color=negative data-testid="delete-unit-btn"'
            )
```

The handler:
```python
async def handle_delete_course() -> None:
    confirmed = await _confirm_delete(
        f"Delete Unit: {course.code}?",
        f'Permanently delete "{course.name}" and all its weeks, activities, '
        "and template workspaces? This cannot be undone.",
    )
    if not confirmed:
        return
    try:
        await delete_course(course.id)
        ui.notify(f"Unit {course.code} deleted", type="positive")
        ui.navigate.to("/courses")
    except DeletionBlockedError as e:
        if is_admin:
            force = await _confirm_force_delete(
                e.student_workspace_count, "unit"
            )
            if force:
                await delete_course(course.id, force=True)
                ui.notify(f"Unit {course.code} force-deleted", type="positive")
                ui.navigate.to("/courses")
        else:
            plural = "workspace" if e.student_workspace_count == 1 else "workspaces"
            ui.notify(
                f"Cannot delete: {e.student_workspace_count} student {plural} exist. "
                "Contact an administrator.",
                type="negative",
            )
```

After successful deletion, navigate to `/courses` (course list) since the current course page no longer exists.

**Testing:**

- crud-management-229.AC6.1: Admin deletes unit with no student workspaces — navigates to course list
- crud-management-229.AC6.2: Coordinator deletes own unit — succeeds
- crud-management-229.AC6.3: Delete blocked — notification with student count
- crud-management-229.AC6.4: Admin force-delete — second dialog, force succeeds
- crud-management-229.AC6.5: Instructor (not coordinator) does not see "Delete Unit" button

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add Delete Unit button with coordinator/admin visibility`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests for delete UI flows

**Verifies:** crud-management-229.AC2.5, crud-management-229.AC6.5

**Files:**
- Create: `tests/integration/test_delete_ui_guards.py`

**Testing:**

The delete guard logic was tested in Phase 2 (test_delete_guards.py). This phase adds tests for UI-layer concerns:

**`TestDeleteUnitVisibility`** — AC6.5:
- Verify the role-based visibility logic:
  - `enrollment.role == "coordinator"` or `is_admin` → can_delete_unit is True
  - `enrollment.role == "instructor"` and not admin → can_delete_unit is False
  - `enrollment.role == "student"` → can_delete_unit is False
- These are unit-testable logic checks, not requiring NiceGUI rendering

**`TestAdminForceDeleteDetection`**:
- Verify the admin detection pattern: `auth_user.get("is_admin") is True` returns True for admin, False for regular instructor
- Verify `is_privileged_user()` is NOT used for force-delete (it includes instructors)

**E2E test gap:** The following ACs require E2E (Playwright) tests for full verification and are NOT covered by integration tests alone: AC2.5 (confirmation dialog shown), AC2.6 (UI refreshes and broadcasts), AC6.2 (coordinator deletes own unit end-to-end). These will be tracked in `test-requirements.md` as requiring E2E coverage. Integration tests here verify only the data layer and permission logic.

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

Run: `uv run test-all`
Expected: No regressions

**Commit:** `test: add integration tests for delete UI permission logic`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
