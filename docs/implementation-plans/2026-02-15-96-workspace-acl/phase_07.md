# Workspace ACL Implementation Plan — Phase 7

**Goal:** Implement workspace listing for students and instructors. Students see "my workspaces" (owned + shared). Instructors see all student workspaces in their course. Activity rows show "Resume" vs "Start Activity" based on existing workspace ownership.

**Architecture:** Three new query functions in `db/acl.py` join ACLEntry with Workspace to resolve accessible workspaces. `list_accessible_workspaces()` returns all workspaces a user has ACL entries for (student "my workspaces"). `list_course_workspaces()` returns all non-template workspaces in a course's activities plus loose workspaces (instructor view). `list_activity_workspaces()` returns all non-template workspaces for a specific activity (per-activity instructor view). The courses page gains "Resume" detection by querying `get_user_workspace_for_activity()` (added in Phase 5) for each activity.

**Tech Stack:** SQLModel, PostgreSQL

**Scope:** 8 phases from original design (this is phase 7 of 8)

**Codebase verified:** 2026-02-15

**Existing functions:** `list_workspaces_for_activity()` (workspaces.py:315) and `list_loose_workspaces_for_course()` (workspaces.py:335) exist but list ALL workspaces without ACL awareness. The new Phase 7 functions are ACL-aware and live in `db/acl.py`.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC9: Listing queries
- **96-workspace-acl.AC9.1 Success:** Student sees all workspaces they own (cloned)
- **96-workspace-acl.AC9.2 Success:** Student sees workspaces shared with them
- **96-workspace-acl.AC9.3 Success:** Instructor sees all student workspaces in their course via hierarchy
- **96-workspace-acl.AC9.4 Success:** Instructor sees loose workspaces placed in their course
- **96-workspace-acl.AC9.5 Success:** "Resume" shown for activity when user already has a workspace for it
- **96-workspace-acl.AC9.6 Success:** "Start Activity" shown when user has no workspace for the activity
- **96-workspace-acl.AC9.7 Edge:** Workspace whose activity was deleted (activity_id SET NULL) still appears in student's "my workspaces"

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Implement list_accessible_workspaces() in db/acl.py

**Verifies:** 96-workspace-acl.AC9.1, 96-workspace-acl.AC9.2, 96-workspace-acl.AC9.7

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `list_accessible_workspaces()` to `db/acl.py`:

```python
async def list_accessible_workspaces(
    user_id: UUID,
) -> list[tuple[Workspace, str]]:
    """List all workspaces a user can access, with their permission level.

    Returns workspaces where the user has an explicit ACL entry. This covers:
    - Owned workspaces (permission="owner")
    - Shared workspaces (permission="editor" or "viewer")
    - Workspaces whose activity was deleted (activity_id SET NULL) —
      still returned because the ACLEntry persists.

    Returns:
        List of (Workspace, permission_name) tuples, ordered by workspace.created_at.
    """
    from promptgrimoire.db.models import Workspace

    async with get_session() as session:
        result = await session.exec(
            select(Workspace, ACLEntry.permission)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)
            .where(ACLEntry.user_id == user_id)
            .order_by(Workspace.created_at)  # type: ignore[arg-type]
        )
        return list(result.all())
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import list_accessible_workspaces; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add list_accessible_workspaces() for student my-workspaces view`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement list_course_workspaces() in db/acl.py

**Verifies:** 96-workspace-acl.AC9.3, 96-workspace-acl.AC9.4

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `list_course_workspaces()` to `db/acl.py`. This returns all non-template student workspaces in a course (both activity-placed and loose):

```python
async def list_course_workspaces(
    course_id: UUID,
) -> list[Workspace]:
    """List all non-template workspaces in a course (instructor view).

    Finds workspaces via two paths:
    1. Activity-placed: Workspace.activity_id → Activity.week_id → Week.course_id
    2. Loose: Workspace.course_id = course_id (directly placed in course)

    Excludes template workspaces (those referenced by Activity.template_workspace_id).

    Returns:
        List of Workspaces ordered by created_at.
    """
    from promptgrimoire.db.models import Activity, Week, Workspace

    async with get_session() as session:
        # Collect template workspace IDs to exclude
        template_result = await session.exec(
            select(Activity.template_workspace_id).join(
                Week, Activity.week_id == Week.id
            ).where(Week.course_id == course_id)
        )
        template_ids = set(template_result.all())

        # Activity-placed workspaces: via Activity → Week → Course
        activity_result = await session.exec(
            select(Workspace)
            .join(Activity, Workspace.activity_id == Activity.id)
            .join(Week, Activity.week_id == Week.id)
            .where(Week.course_id == course_id)
            .order_by(Workspace.created_at)  # type: ignore[arg-type]
        )
        activity_workspaces = list(activity_result.all())

        # Loose workspaces: directly placed in course
        loose_result = await session.exec(
            select(Workspace)
            .where(Workspace.course_id == course_id)
            .where(Workspace.activity_id == None)  # noqa: E711
            .order_by(Workspace.created_at)  # type: ignore[arg-type]
        )
        loose_workspaces = list(loose_result.all())

        # Combine and exclude templates
        all_workspaces = activity_workspaces + loose_workspaces
        return [ws for ws in all_workspaces if ws.id not in template_ids]
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import list_course_workspaces; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add list_course_workspaces() for instructor view`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement list_activity_workspaces() in db/acl.py

**Verifies:** 96-workspace-acl.AC9.3

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `list_activity_workspaces()` to `db/acl.py`. This returns all non-template workspaces for a specific activity:

```python
async def list_activity_workspaces(
    activity_id: UUID,
) -> list[tuple[Workspace, str, UUID]]:
    """List all non-template workspaces for an activity with owner info.

    Returns workspaces placed in this activity that have an ACL entry
    with "owner" permission. This is the per-activity instructor view
    showing who has cloned the activity.

    Returns:
        List of (Workspace, permission, user_id) tuples, ordered by workspace.created_at.
    """
    from promptgrimoire.db.models import Activity, Workspace

    async with get_session() as session:
        # Get template workspace ID to exclude
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return []
        template_id = activity.template_workspace_id

        result = await session.exec(
            select(Workspace, ACLEntry.permission, ACLEntry.user_id)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.permission == "owner",
            )
            .order_by(Workspace.created_at)  # type: ignore[arg-type]
        )
        rows = list(result.all())
        return [(ws, perm, uid) for ws, perm, uid in rows if ws.id != template_id]
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import list_activity_workspaces; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add list_activity_workspaces() for per-activity instructor view`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Update courses page with Resume vs Start Activity detection

**Verifies:** 96-workspace-acl.AC9.5, 96-workspace-acl.AC9.6

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

Update the activity rendering logic (around lines 390-423) to detect existing workspaces and show "Resume" instead of "Start Activity":

1. Before the activity rendering loop, batch-query for the user's existing workspaces across all activities:

```python
# Build map of activity_id → user's workspace for "Resume" detection
user_workspace_map: dict[UUID, Workspace] = {}
if user_id:
    for act in activities:
        existing = await get_user_workspace_for_activity(act.id, user_id)
        if existing is not None:
            user_workspace_map[act.id] = existing
```

2. In `_render_activity_row()`, replace the unconditional "Start Activity" button with conditional logic:

```python
if act.id in user_workspace_map:
    # User already has a workspace — show Resume
    ws = user_workspace_map[act.id]
    qs = urlencode({"workspace_id": str(ws.id)})

    ui.button(
        "Resume",
        icon="play_arrow",
        on_click=lambda q=qs: ui.navigate.to(f"/annotation?{q}"),
    ).props("flat dense size=sm color=primary")
else:
    # No workspace yet — show Start Activity
    async def start_activity(aid: UUID = act.id) -> None:
        user_id = _get_user_id()
        if user_id is None:
            ui.notify("Please log in to start an activity", type="warning")
            return

        existing = await get_user_workspace_for_activity(aid, user_id)
        if existing is not None:
            qs = urlencode({"workspace_id": str(existing.id)})
            ui.navigate.to(f"/annotation?{qs}")
            return

        error = await check_clone_eligibility(aid, user_id)
        if error is not None:
            ui.notify(error, type="negative")
            return

        clone, _doc_map = await clone_workspace_from_activity(aid, user_id)
        qs = urlencode({"workspace_id": str(clone.id)})
        ui.navigate.to(f"/annotation?{qs}")

    ui.button("Start Activity", on_click=start_activity).props(
        "flat dense size=sm color=primary"
    )
```

The `get_user_workspace_for_activity` import was already added in Phase 5.

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.courses import *; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: show Resume vs Start Activity based on existing workspace ownership`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

Add the new listing functions to the ACL imports:

```python
from promptgrimoire.db.acl import (
    can_access_workspace,
    grant_permission,
    grant_share,
    list_accessible_workspaces,
    list_activity_workspaces,
    list_course_workspaces,
    list_entries_for_resource,
    list_entries_for_user,
    resolve_permission,
    revoke_permission,
)
```

Add all to `__all__`.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import list_accessible_workspaces, list_course_workspaces, list_activity_workspaces; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: export listing query functions from db package`

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_6 -->
### Task 6: Integration tests for listing queries

**Verifies:** 96-workspace-acl.AC9.1, 96-workspace-acl.AC9.2, 96-workspace-acl.AC9.3, 96-workspace-acl.AC9.4, 96-workspace-acl.AC9.5, 96-workspace-acl.AC9.6, 96-workspace-acl.AC9.7

**Files:**
- Create: `tests/integration/test_listing_queries.py`

**Implementation:**

Integration tests using real PostgreSQL. Include skip guard. Shared async fixture creates test data:
- Two users (student_a, student_b) enrolled as students in a course
- An instructor_user enrolled as instructor
- A course, week, and activity with template workspace
- student_a clones the activity (creates workspace + ACLEntry(owner))
- student_a shares workspace with student_b as viewer (ACLEntry(viewer))
- A loose workspace placed in the course (course_id set, no activity_id) with ACLEntry for student_a

Tests:

- **AC9.1:** Call `list_accessible_workspaces(student_a.id)`. Verify the cloned workspace appears with `permission == "owner"`. Verify the loose workspace appears.

- **AC9.2:** Call `list_accessible_workspaces(student_b.id)`. Verify student_a's shared workspace appears with `permission == "viewer"`.

- **AC9.3:** Call `list_course_workspaces(course_id)`. Verify student_a's cloned workspace appears. Verify template workspace does NOT appear.

- **AC9.4:** Call `list_course_workspaces(course_id)`. Verify the loose workspace appears in the results.

- **AC9.5:** Call `get_user_workspace_for_activity(activity_id, student_a.id)`. Verify returns student_a's cloned workspace (not None).

- **AC9.6:** Call `get_user_workspace_for_activity(activity_id, student_b.id)`. Verify returns None (student_b has a shared workspace, but didn't clone this activity). Note: student_b's ACLEntry is on student_a's workspace, so `get_user_workspace_for_activity` should only match workspaces the user owns for this activity.

- **AC9.7:** Delete the activity (SET NULL on student workspaces' activity_id). Call `list_accessible_workspaces(student_a.id)`. Verify the workspace still appears (ACLEntry persists even when activity_id is SET NULL).

**Testing:**

Run: `uv run pytest tests/integration/test_listing_queries.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new listing query tests.

**Commit:** `test: add integration tests for workspace listing queries`

<!-- END_TASK_6 -->
