# Workspace ACL Implementation Plan — Phase 5

**Goal:** Wire ACL ownership into the workspace cloning flow. Cloning creates an owner ACLEntry, is gated by enrollment and week visibility checks, and detects duplicate clones.

**Architecture:** `clone_workspace_from_activity()` gains a `user_id` parameter. Within its existing atomic session, it creates a Workspace and an ACLEntry with `workspace_id` pointing directly at the clone. `start_activity()` in `pages/courses.py` passes `user_id`, checks enrollment, and checks for existing workspaces. A new `get_user_workspace_for_activity()` query in `db/workspaces.py` handles duplicate detection.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 5 of 8)

**Codebase verified:** 2026-02-15

**Design note:** The clone function creates Workspace + ACLEntry in a single session (not via `create_workspace()` or `grant_permission()`, which each open their own sessions). This preserves atomicity — both rows commit or neither does.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC7: Ownership at clone
- **96-workspace-acl.AC7.1 Success:** Cloning a workspace from an activity creates ACLEntry with owner permission for the cloning user
- **96-workspace-acl.AC7.2 Success:** Clone is gated by enrollment check — user must be enrolled in the activity's course
- **96-workspace-acl.AC7.3 Success:** Clone is gated by week visibility — activity's week must be visible to the user
- **96-workspace-acl.AC7.4 Success:** If user already has a workspace for this activity, return existing workspace instead of creating duplicate
- **96-workspace-acl.AC7.5 Failure:** Unauthenticated user cannot clone
- **96-workspace-acl.AC7.6 Failure:** User not enrolled in the course cannot clone

**Note:** AC7.5 is tested at the page level (`start_activity()`) where auth session exists. The DB-layer function (`clone_workspace_from_activity()`) receives `user_id` as a required parameter — it cannot be called without one. AC7.2, AC7.3, and AC7.6 are enforced at the DB layer via a pre-clone gate function.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add get_user_workspace_for_activity() to db/workspaces.py

**Verifies:** 96-workspace-acl.AC7.4

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

Add `get_user_workspace_for_activity()` to `db/workspaces.py`. This queries for an existing non-template workspace **owned** by the user for a given activity:

```python
async def get_user_workspace_for_activity(
    activity_id: UUID, user_id: UUID
) -> Workspace | None:
    """Find an existing workspace owned by the user in an activity.

    Looks for a non-template workspace placed in this activity where the user
    has an owner ACL entry. Returns the first match, or None if the user has
    no owned workspace for this activity.

    Filters by permission == "owner" to exclude shared workspaces — a viewer
    of someone else's workspace should not be treated as having their own
    workspace for this activity (which would suppress the "Start Activity"
    button and show "Resume" instead).
    """
    from promptgrimoire.db.models import ACLEntry

    async with get_session() as session:
        result = await session.exec(
            select(Workspace)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        return result.first()
```

This excludes template workspaces implicitly — template workspaces have no ACLEntry rows (they are owned by the Activity, not by a user). The `permission == "owner"` filter ensures that a student who was shared someone else's workspace still sees "Start Activity" (not "Resume") for their own clone.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.workspaces import get_user_workspace_for_activity; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add get_user_workspace_for_activity() for duplicate clone detection`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update clone_workspace_from_activity() with user_id and owner ACLEntry

**Verifies:** 96-workspace-acl.AC7.1

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

1. Add imports at the top of the file (some may already be present from Phase 3):
   ```python
   from promptgrimoire.db.models import ACLEntry
   ```

2. Update the function signature and body. The key changes:
   - Add `user_id: UUID` parameter
   - Create ACLEntry with `workspace_id` pointing at the clone and `"owner"` permission within the same session

```python
async def clone_workspace_from_activity(
    activity_id: UUID,
    user_id: UUID,
) -> tuple[Workspace, dict[UUID, UUID]]:
    """Clone an Activity's template workspace into a new student workspace.

    Creates a new Workspace within a single transaction, copies all template
    documents (preserving content, type, source_type, title, order_index),
    builds a document ID mapping, and replays CRDT state (highlights,
    comments, general notes) with remapped document IDs. Client metadata
    is NOT cloned -- the fresh workspace starts with empty client state.

    Also creates an ACLEntry granting owner permission to the cloning user.

    Args:
        activity_id: The Activity UUID whose template workspace to clone.
        user_id: The user UUID who will own the cloned workspace.

    Returns:
        Tuple of (new Workspace, mapping of {template_doc_id: cloned_doc_id}).

    Raises:
        ValueError: If Activity or its template workspace is not found.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            msg = f"Activity {activity_id} not found"
            raise ValueError(msg)

        template = await session.get(Workspace, activity.template_workspace_id)
        if not template:
            msg = f"Template workspace {activity.template_workspace_id} not found"
            raise ValueError(msg)

        # Create new workspace with activity_id and enable_save_as_draft copied
        clone = Workspace(
            activity_id=activity_id,
            enable_save_as_draft=template.enable_save_as_draft,
        )
        session.add(clone)
        await session.flush()

        # Grant owner permission to cloning user
        acl_entry = ACLEntry(
            workspace_id=clone.id,
            user_id=user_id,
            permission="owner",
        )
        session.add(acl_entry)
        await session.flush()

        # Fetch all template documents ordered by order_index
        result = await session.exec(
            select(WorkspaceDocument)
            .where(WorkspaceDocument.workspace_id == template.id)
            .order_by(WorkspaceDocument.order_index)  # type: ignore[arg-type]  # TODO(2026-Q2): Revisit when SQLModel updates type stubs
        )
        template_docs = list(result.all())

        # Clone each document, preserving field values
        doc_id_map: dict[UUID, UUID] = {}
        for tmpl_doc in template_docs:
            cloned_doc = WorkspaceDocument(
                workspace_id=clone.id,
                type=tmpl_doc.type,
                content=tmpl_doc.content,
                source_type=tmpl_doc.source_type,
                title=tmpl_doc.title,
                order_index=tmpl_doc.order_index,
            )
            session.add(cloned_doc)
            await session.flush()
            doc_id_map[tmpl_doc.id] = cloned_doc.id

        # --- CRDT state cloning via API replay ---
        _replay_crdt_state(template, clone, doc_id_map)

        await session.flush()
        await session.refresh(clone)
        return clone, doc_id_map
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.workspaces import clone_workspace_from_activity; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: clone_workspace_from_activity() creates owner ACLEntry`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add pre-clone gate function to db/workspaces.py

**Verifies:** 96-workspace-acl.AC7.2, 96-workspace-acl.AC7.3, 96-workspace-acl.AC7.6

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

Add `check_clone_eligibility()` that validates enrollment and week visibility before cloning:

```python
async def check_clone_eligibility(
    activity_id: UUID, user_id: UUID
) -> str | None:
    """Check if a user is eligible to clone a workspace from an activity.

    Validates:
    1. Activity exists
    2. User is enrolled in the activity's course
    3. Activity's week is visible to the user

    Returns:
        None if eligible, or an error message string explaining why not.
    """
    from promptgrimoire.db.models import CourseEnrollment, Week

    async with get_session() as session:
        # 1. Activity must exist
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return "Activity not found"

        # 2. Resolve course via Week
        week = await session.get(Week, activity.week_id)
        if week is None:
            return "Week not found"

        # 3. User must be enrolled in the course
        enrollment_result = await session.exec(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == week.course_id,
                CourseEnrollment.user_id == user_id,
            )
        )
        enrollment = enrollment_result.one_or_none()
        if enrollment is None:
            return "User is not enrolled in this course"

        # 4. Week must be visible to the user
        # Instructors always have access
        staff_roles = {"coordinator", "instructor", "tutor"}
        if enrollment.role in staff_roles:
            return None

        # Students need published + visible week
        if not week.is_published:
            return "Week is not published"

        if week.visible_from and week.visible_from > datetime.now(UTC):
            return "Week is not yet visible"

        return None
```

Note: This uses string role comparisons (not `CourseRole` enum) because Phase 2 normalises the role column to a VARCHAR FK.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.workspaces import check_clone_eligibility; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add check_clone_eligibility() pre-clone gate`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update start_activity() in pages/courses.py

**Verifies:** 96-workspace-acl.AC7.4, 96-workspace-acl.AC7.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

Update `start_activity()` (lines 415-423) to:
1. Check authentication (AC7.5)
2. Check for existing workspace (AC7.4)
3. Check clone eligibility (AC7.2, AC7.3, AC7.6)
4. Pass `user_id` to `clone_workspace_from_activity()`

```python
async def start_activity(aid: UUID = act.id) -> None:
    user_id = _get_user_id()
    if user_id is None:
        ui.notify("Please log in to start an activity", type="warning")
        return

    # Check for existing workspace (duplicate detection)
    existing = await get_user_workspace_for_activity(aid, user_id)
    if existing is not None:
        qs = urlencode({"workspace_id": str(existing.id)})
        ui.navigate.to(f"/annotation?{qs}")
        return

    # Check enrollment and week visibility
    error = await check_clone_eligibility(aid, user_id)
    if error is not None:
        ui.notify(error, type="negative")
        return

    clone, _doc_map = await clone_workspace_from_activity(aid, user_id)
    qs = urlencode({"workspace_id": str(clone.id)})
    ui.navigate.to(f"/annotation?{qs}")
```

Add imports at the top of the file:
```python
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    get_user_workspace_for_activity,
)
```

This resolves the `# TODO(Seam-D): Add workspace-level auth check here` comment at line 416.

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.courses import *; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: start_activity() gates clone by auth, enrollment, and duplicate detection`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

Add the new functions to the workspace imports:

```python
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
    create_workspace,
    get_placement_context,
    get_user_workspace_for_activity,
    # ... other existing imports
)
```

Add all to `__all__`.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import check_clone_eligibility, get_user_workspace_for_activity; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: export clone eligibility and duplicate detection from db package`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration tests for ownership at clone

**Verifies:** 96-workspace-acl.AC7.1, 96-workspace-acl.AC7.2, 96-workspace-acl.AC7.3, 96-workspace-acl.AC7.4, 96-workspace-acl.AC7.5, 96-workspace-acl.AC7.6

**Files:**
- Create: `tests/integration/test_clone_ownership.py`

**Implementation:**

Integration tests using real PostgreSQL. Include skip guard. Shared async fixture creates test data:
- A user (student_user) enrolled as student in a course
- A second user (unenrolled_user) not enrolled
- A course, week (published), and activity with template workspace
- CourseEnrollment for student_user as "student"

Tests:

- **AC7.1:** Clone workspace via `clone_workspace_from_activity(activity_id, student_user.id)`. Query ACLEntry for `(workspace_id=clone.id, user_id=student_user.id)` -- verify `permission == "owner"`.

- **AC7.2:** Call `check_clone_eligibility(activity_id, student_user.id)` — returns None (eligible). Call `check_clone_eligibility(activity_id, unenrolled_user.id)` — returns error string.

- **AC7.3:** Set week to unpublished (`is_published=False`). Call `check_clone_eligibility(activity_id, student_user.id)` — returns error string about week. Set week to future visibility (`visible_from` in the future). Call again — returns error about visibility. Staff user should still pass.

- **AC7.4:** Clone once for student_user. Call `get_user_workspace_for_activity(activity_id, student_user.id)` — returns the cloned workspace. Verify the returned workspace matches the first clone.

- **AC7.5:** (Tested implicitly — `clone_workspace_from_activity()` requires `user_id` parameter. Page-level `start_activity()` checks `_get_user_id()`. No DB-layer test needed; this is a type-system guarantee.)

- **AC7.6:** Call `check_clone_eligibility(activity_id, unenrolled_user.id)` — returns error about enrollment. Attempt to clone without checking eligibility — the clone succeeds at the DB level (it doesn't re-check enrollment itself), but the page layer prevents this. Test the gate function returns the correct error.

**Testing:**

Run: `uv run pytest tests/integration/test_clone_ownership.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new clone ownership tests.

**Commit:** `test: add integration tests for clone ownership and eligibility gates`

<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->
