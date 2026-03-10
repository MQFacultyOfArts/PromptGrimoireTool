# CRUD Management Implementation Plan - Phase 6: Workspace Deletion

**Goal:** Workspace owners can delete their own workspaces from both the course detail page and the navigator, enabling "start over" workflows.

**Architecture:** On the course page, a delete icon appears next to the Resume button for owned workspaces. After deletion, `weeks_list.refresh()` re-renders the activity row which transitions from "Resume" to "Start Activity" (since `get_user_workspace_for_activity()` returns None). On the navigator, a delete icon appears on owned workspace cards. After deletion, the card element is removed from the DOM via NiceGUI's `.delete()` method, preserving scroll position.

**Tech Stack:** NiceGUI, Quasar

**Scope:** Phase 6 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (data-testid convention)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC3: Workspace owners delete their own workspaces
- **crud-management-229.AC3.1 Success:** Owner deletes workspace from course detail page; "Start Activity" reappears
- **crud-management-229.AC3.2 Success:** Owner deletes workspace from navigator; card is removed
- **crud-management-229.AC3.3 Success:** Confirmation dialog shown before workspace deletion
- **crud-management-229.AC3.4 Failure:** Non-owner cannot see or trigger workspace delete

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add workspace delete to course detail page

**Verifies:** crud-management-229.AC3.1, crud-management-229.AC3.3, crud-management-229.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (activity row rendering, Resume button area at lines 561-569)

**Implementation:**

Add import for `delete_workspace`:
```python
from promptgrimoire.db.workspaces import ..., delete_workspace
```

In `_render_activity_row()`, in the branch where `act.id in user_workspace_map` (Resume button, lines 561-569), add a delete icon next to the Resume button:

```python
if act.id in user_workspace_map:
    ws = user_workspace_map[act.id]
    qs = urlencode({"workspace_id": str(ws.id)})
    ui.button(
        "Resume",
        icon="play_arrow",
        on_click=lambda q=qs: ui.navigate.to(f"/annotation?{q}"),
    ).props(
        f'flat dense size=sm color=primary data-testid="resume-btn-{act.id}"'
    )

    async def handle_delete_workspace(ws_id: UUID = ws.id) -> None:
        confirmed = await _confirm_delete(
            "Delete Your Workspace?",
            "Delete your workspace and all annotations? "
            "You can start fresh by cloning again.",
        )
        if not confirmed:
            return
        uid = _get_user_id()
        await delete_workspace(ws_id, user_id=uid)
        weeks_list.refresh()
        ui.notify("Workspace deleted", type="positive")

    ui.button(
        icon="delete_outline",
        on_click=handle_delete_workspace,
    ).props(
        f'flat round dense size=sm color=negative '
        f'data-testid="delete-workspace-btn-{act.id}"'
    ).tooltip("Delete workspace")
```

The `_confirm_delete()` helper was created in Phase 5 Task 1.

After `delete_workspace()` succeeds with the user's ID (ownership verified by Phase 2's guard), `weeks_list.refresh()` rebuilds the activity rows. `_build_user_workspace_map()` runs again and won't find the deleted workspace, so the activity row renders "Start Activity" instead of "Resume".

The delete icon is only visible when the user has a workspace (the `if act.id in user_workspace_map:` branch), so non-owners never see it (AC3.4 — they see "Start Activity" or nothing).

`_render_activity_row()` will need `weeks_list` passed as a parameter (added in Phase 4).

**Testing:**

- crud-management-229.AC3.1: Delete workspace from course page — Resume button disappears, "Start Activity" appears
- crud-management-229.AC3.3: Confirmation dialog shows before deletion
- crud-management-229.AC3.4: Non-owner sees "Start Activity" not delete icon (implicit from branch structure)

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add workspace delete to course detail page`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add workspace delete to navigator cards

**Verifies:** crud-management-229.AC3.2, crud-management-229.AC3.3, crud-management-229.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/navigator/_cards.py` (workspace card rendering at lines 199-261)

**Implementation:**

Add import for `delete_workspace`:
```python
from promptgrimoire.db.workspaces import delete_workspace
```

In `render_workspace_entry()`, add a delete icon in the actions column (the `ui.column().classes("items-end gap-1")` section) for owned workspaces only:

```python
with ui.column().classes("items-end gap-1"):
    date_str = format_updated_at(row)
    if date_str:
        ui.label(date_str).classes("text-xs text-gray-400")

    if row.workspace_id is not None:
        with ui.row().classes("items-center gap-1"):
            action = ACTION_LABELS.get(row.permission, "Open")
            url = workspace_url(row.workspace_id)
            ui.button(
                action,
                on_click=lambda u=url: ui.navigate.to(u),
            ).props("flat dense size=sm color=primary").classes(
                "navigator-action-btn"
            )

            # Delete button — only for owners
            if row.permission == "owner":
                # ... delete handler and button here
```

The delete handler must capture a reference to the enclosing card element so it can be removed from the DOM after deletion:

```python
# Capture card reference from the outer `with ui.card() as card:` context
if row.permission == "owner":
    async def handle_delete_ws(
        ws_id: UUID = row.workspace_id,
        card_ref: ui.card = card,
    ) -> None:
        # Use _confirm_delete pattern or inline dialog
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            ui.label("Delete Workspace?").classes("text-lg font-bold")
            ui.label(
                "Delete this workspace and all annotations? "
                "You can start fresh from the course page."
            ).classes("text-sm my-2")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(
                    "Cancel", on_click=lambda: dlg.submit(False)
                ).props('flat data-testid="cancel-delete-ws-btn"')
                ui.button(
                    "Delete", on_click=lambda: dlg.submit(True)
                ).props(
                    'outline color=negative '
                    'data-testid="confirm-delete-ws-btn"'
                )
        dlg.open()
        confirmed = await dlg
        if not confirmed:
            return

        user_id = page_state["user_id"] if page_state else None
        await delete_workspace(ws_id, user_id=user_id)
        card_ref.delete()  # Remove card from DOM
        ui.notify("Workspace deleted", type="positive")

    ui.button(
        icon="delete_outline",
        on_click=handle_delete_ws,
    ).props(
        'flat round dense size=sm color=negative '
        f'data-testid="delete-ws-nav-btn-{row.workspace_id}"'
    ).tooltip("Delete workspace")
```

**Implementation notes:**
- The `card` variable must be captured from the outer `with ui.card() as card:` context. The current code uses `ui.card()` without capturing it — the implementor will need to add `as card` to the card context manager at line 207. Verify that deleting the `card` element also removes the enclosing row — inspect the actual DOM structure (the `with ui.card()` and `with ui.row()` nesting) and capture the correct outermost container.
- `page_state["user_id"]` is typed as `UUID` in the navigator's `PageState` TypedDict — the implementor should verify this against the actual `PageState` definition in `navigator/_page.py` and cast if needed.

Non-owners (`row.permission != "owner"`) never see the delete button (AC3.4).

**E2E test gap:** AC3.2 (card removal from navigator), AC3.3 (confirmation dialog) require E2E (Playwright) tests for full UI verification. These will be tracked in `test-requirements.md`.

**Testing:**

- crud-management-229.AC3.2: Delete workspace from navigator — card disappears without page reload
- crud-management-229.AC3.3: Confirmation dialog shown
- crud-management-229.AC3.4: Non-owner cards have no delete button (permission check)

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add workspace delete to navigator cards`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for workspace deletion UI flows

**Verifies:** crud-management-229.AC3.1, crud-management-229.AC3.2, crud-management-229.AC3.4

**Files:**
- Create: `tests/integration/test_workspace_deletion.py`

**Testing:**

Follow project test patterns (skip guard, class-based, UUID isolation).

**`TestWorkspaceDeletionFromCourse`** — AC3.1:
- Create activity, clone for user, verify workspace exists via `get_user_workspace_for_activity()`
- Call `delete_workspace(ws_id, user_id=owner_uid)`
- Re-query `get_user_workspace_for_activity()` — should return None
- This proves the Resume → Start Activity transition (UI depends on this query)

**`TestWorkspaceDeletionOwnership`** — AC3.4:
- Create workspace, attempt `delete_workspace(ws_id, user_id=non_owner_uid)` — should raise `PermissionError` (Phase 2 guard)
- Create workspace, `delete_workspace(ws_id, user_id=owner_uid)` — succeeds
- This is a regression test confirming Phase 2's ownership guard works in context

**`TestWorkspaceDeletionCascade`** — AC3.2:
- Create workspace with documents, tags, tag groups
- Delete workspace
- Verify all child entities are cascade-deleted (documents, tags, tag groups, ACL entries)
- This confirms the navigator card removal is safe — no orphaned data

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

Run: `uv run test-all`
Expected: No regressions

**Commit:** `test: add integration tests for workspace deletion flows`
<!-- END_TASK_3 -->
