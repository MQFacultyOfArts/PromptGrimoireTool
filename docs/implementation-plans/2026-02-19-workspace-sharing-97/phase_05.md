# Workspace Sharing & Visibility — Phase 5: Sharing UX

**Goal:** Instructor activity/course sharing settings, student "Share with class" toggle, and per-user sharing dialog.

**Architecture:** Activity/course settings follow existing tri-state UI pattern. "Share with class" toggle in workspace header for owner or privileged users. Per-user sharing dialog uses existing `grant_share()` with email-based user lookup — built as foundational infrastructure for all future user-user interaction.

**Tech Stack:** NiceGUI, SQLModel, PostgreSQL

**Scope:** 7 phases from original design (phase 5 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 1 (model fields: `shared_with_class`, `title`), Phase 4 (PageState `can_manage_acl`, `effective_permission`)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC7: Sharing UX
- **workspace-sharing-97.AC7.1 Success:** Instructor can toggle allow_sharing per activity (tri-state)
- **workspace-sharing-97.AC7.2 Success:** Instructor can toggle anonymous_sharing per activity (tri-state)
- **workspace-sharing-97.AC7.3 Success:** Instructor can set course defaults for both
- **workspace-sharing-97.AC7.4 Success:** Owner sees 'Share with class' toggle when activity allows sharing
- **workspace-sharing-97.AC7.5 Success:** Owner can toggle shared_with_class on and off
- **workspace-sharing-97.AC7.6 Success:** Owner can share loose workspace with specific user via grant_share
- **workspace-sharing-97.AC7.7 Failure:** 'Share with class' not shown when activity disallows sharing
- **workspace-sharing-97.AC7.8 Failure:** Non-owner cannot see sharing controls

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add anonymous_sharing to activity and course settings dialogs

**Verifies:** workspace-sharing-97.AC7.1, workspace-sharing-97.AC7.2, workspace-sharing-97.AC7.3

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py:80-84` (add `_ANONYMOUS_SHARING_OPTIONS` dict)
- Modify: `src/promptgrimoire/pages/courses.py:161-199` (activity settings dialog — add select)
- Modify: `src/promptgrimoire/pages/courses.py:125-158` (course settings dialog — add switch)

**Implementation:**

1. Add options dict near line 84 (after `_SHARING_OPTIONS`):
   ```python
   _ANONYMOUS_SHARING_OPTIONS: dict[str, str] = {
       "inherit": "Inherit from course",
       "on": "Anonymous",
       "off": "Named",
   }
   ```

2. In `open_activity_settings()` (line 161), add a tri-state select for `anonymous_sharing` after the `sharing_select` (line 180), following the exact same pattern as `cp_select` and `sharing_select`:
   - `ui.select(options=_ANONYMOUS_SHARING_OPTIONS, value=_model_to_ui(activity.anonymous_sharing), label="Anonymity")`
   - In the `save()` closure, add `anonymous_sharing=_ui_to_model(anon_select.value)` to the `update_activity()` call

3. In `open_course_settings()` (line 125), add a `ui.switch` for `default_anonymous_sharing` after `sharing_switch` (line 140):
   - `ui.switch("Anonymous sharing by default", value=course.default_anonymous_sharing)`
   - In the `save()` closure, add `default_anonymous_sharing=anon_switch.value` to the `update_course()` call

4. Update `_model_to_ui` and `_ui_to_model` docstrings to mention `anonymous_sharing`.

**Testing:**

The settings dialogs are interactive NiceGUI components. Verification is primarily UAT. Ensure `update_activity` and `update_course` DB functions accept the new kwargs (they should if Phase 1 added the model fields).

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(courses): add anonymous_sharing to activity and course settings`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `update_workspace_sharing()` DB function

**Verifies:** workspace-sharing-97.AC7.5 (persistence)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add new function at end of file)
- Create: `tests/integration/test_workspace_sharing.py`

**Implementation:**

Add function following the `place_workspace_in_activity` pattern:

```python
async def update_workspace_sharing(
    workspace_id: UUID,
    shared_with_class: bool,
) -> Workspace:
    """Update a workspace's class sharing status."""
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if not workspace:
            msg = f"Workspace {workspace_id} not found"
            raise ValueError(msg)
        workspace.shared_with_class = shared_with_class
        workspace.updated_at = datetime.now(UTC)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace
```

Also add a title update function (for workspace-sharing-97.AC5.2 in Phase 6):

```python
async def update_workspace_title(
    workspace_id: UUID,
    title: str | None,
) -> Workspace:
    """Update a workspace's display title."""
    ...
```

**Testing:**

Integration tests:
- Set `shared_with_class=True` then verify persisted
- Set `shared_with_class=False` then verify persisted
- Non-existent workspace_id raises ValueError
- Set title then verify persisted
- Set title to None then verify persisted

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(workspaces): add update_workspace_sharing and update_workspace_title`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add "Share with class" toggle to workspace header

**Verifies:** workspace-sharing-97.AC7.4, workspace-sharing-97.AC7.5, workspace-sharing-97.AC7.7, workspace-sharing-97.AC7.8

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:337-429` (`_render_workspace_header` — add toggle)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:682` (pass new params to header)

**Implementation:**

1. Add parameters to `_render_workspace_header`:
   - `allow_sharing: bool = False` — from PlacementContext
   - `shared_with_class: bool = False` — current workspace state
   - `can_manage_sharing: bool = False` — True if owner OR privileged user

2. After the copy protection chip (line 429), add a conditional "Share with class" section:
   ```python
   if allow_sharing and can_manage_sharing:
       share_toggle = ui.switch(
           "Share with class",
           value=shared_with_class,
           on_change=lambda e: handle_share_toggle(e.value),
       )
   ```

3. The `handle_share_toggle` async handler calls `update_workspace_sharing(workspace_id, value)`.

4. At the call site (line 682), compute and pass:
   - `allow_sharing=ctx.allow_sharing`
   - `shared_with_class=workspace.shared_with_class` (load workspace object)
   - `can_manage_sharing=(permission == "owner" or is_privileged_user(auth_user))`

5. AC7.7: When `allow_sharing=False`, the toggle is not rendered.
6. AC7.8: When `can_manage_sharing=False` (non-owner, non-privileged), the toggle is not rendered.

**Testing:**

Primarily UAT. The DB update is tested in Task 2. UI gating logic:
- Owner + allow_sharing=True: toggle visible
- Privileged (instructor) + allow_sharing=True: toggle visible
- Peer + allow_sharing=True: toggle NOT visible
- Owner + allow_sharing=False: toggle NOT visible

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(annotation): add Share with class toggle to workspace header`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add per-user sharing dialog

**Verifies:** workspace-sharing-97.AC7.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (add sharing dialog function and button)
- Modify: `src/promptgrimoire/db/users.py` (add user lookup by email if not exists)

**Implementation:**

1. Check if a `get_user_by_email()` function exists in `db/users.py`. If not, add one:
   ```python
   async def get_user_by_email(email: str) -> User | None:
       async with get_session() as session:
           result = await session.exec(
               select(User).where(User.email == email)
           )
           return result.one_or_none()
   ```

2. Add a sharing dialog function in `workspace.py`:
   ```python
   async def _open_sharing_dialog(
       workspace_id: UUID,
       grantor_id: UUID,
       sharing_allowed: bool,
       grantor_is_staff: bool,
   ) -> None:
   ```

   The dialog contains:
   - `ui.input(label="Recipient email")` — email of user to share with
   - `ui.select(options={"viewer": "Viewer", "editor": "Editor"}, value="viewer", label="Permission")` — permission level
   - "Share" button that:
     a. Looks up user by email via `get_user_by_email()`
     b. If not found: `ui.notify("User not found", type="negative")`
     c. If found: calls `grant_share(workspace_id, grantor_id, recipient.id, permission, sharing_allowed=sharing_allowed, grantor_is_staff=grantor_is_staff)`
     d. On success: `ui.notify(f"Shared with {email}", type="positive")`
     e. On PermissionError: displays error message
   - Current shares list: query `list_entries_for_workspace()` and display existing ACL entries with revoke buttons

3. Add a "Share" button in the workspace header, visible only when `can_manage_acl` is True (owner only) or user is privileged. For loose workspaces, this is the primary sharing mechanism since there's no class sharing.

4. Build this dialog as foundational infrastructure — clean error handling, input validation (email format), clear feedback. Future user-user interactions (invitations, transfers) will follow this pattern.

**Testing:**

Integration test for `get_user_by_email` if new. The `grant_share` flow is already tested in existing ACL tests. UI interaction is UAT.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(annotation): add per-user sharing dialog with email lookup`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

---

## UAT Protocol

### Activity/Course Settings (Tasks 1)

1. As an instructor, open activity settings — verify `anonymous_sharing` select appears with options: Inherit, On, Off
2. Change to "On", save, reopen — verify persisted
3. Open course settings — verify `default_anonymous_sharing` switch appears
4. Toggle course default, verify activity "Inherit" reflects the new default

### Share with Class Toggle (Tasks 3)

5. As the workspace owner on an activity with `allow_sharing=True` — verify "Share with class" toggle appears in workspace header
6. Toggle on, reload — verify persisted and toggle shows enabled state
7. Set `allow_sharing=False` on the activity, reload workspace — verify toggle disappears
8. As a non-owner viewer, verify sharing toggle is NOT visible

### Per-User Sharing Dialog (Task 4)

9. As workspace owner, click "Share" button — verify dialog opens with email input and permission select
10. Enter a valid email of an existing user, select "Viewer", click Share — verify success notification
11. Enter a non-existent email — verify "User not found" error
12. Verify the shared user can now access the workspace with viewer permission
