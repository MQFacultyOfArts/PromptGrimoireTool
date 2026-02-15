# Workspace ACL Implementation Plan — Phase 6

**Goal:** Enable student-to-student workspace sharing. Owners can share workspaces as editor or viewer when sharing is allowed. Sharing permission follows the same tri-state inheritance pattern as copy protection.

**Architecture:** `Activity.allow_sharing` (tri-state `bool | None`) and `Course.default_allow_sharing` (bool, default `False`) mirror the existing copy protection pattern. `PlacementContext` gains an `allow_sharing: bool` field resolved identically. `grant_share()` in `db/acl.py` validates the caller is the owner, sharing is enabled, and the granted permission is at most editor (never owner). UI follows the existing `_model_to_ui()`/`_ui_to_model()` mapping pattern.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 6 of 8)

**Codebase verified:** 2026-02-15

**Pattern precedent:** The sharing tri-state exactly mirrors `Activity.copy_protection` (models.py:204) / `Course.default_copy_protection` (models.py:99) and its resolution in `_resolve_activity_placement()` (workspaces.py:119-133). UI mapping functions follow `_model_to_ui()`/`_ui_to_model()` (courses.py:71-88).

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC8: Sharing controls
- **96-workspace-acl.AC8.1 Success:** Owner can share workspace as editor when allow_sharing is True
- **96-workspace-acl.AC8.2 Success:** Owner can share workspace as viewer when allow_sharing is True
- **96-workspace-acl.AC8.3 Success:** Activity.allow_sharing=None inherits Course.default_allow_sharing
- **96-workspace-acl.AC8.4 Success:** Activity.allow_sharing=True overrides Course.default_allow_sharing=False
- **96-workspace-acl.AC8.5 Success:** Activity.allow_sharing=False overrides Course.default_allow_sharing=True
- **96-workspace-acl.AC8.6 Success:** Instructor can share on behalf of students regardless of allow_sharing flag
- **96-workspace-acl.AC8.7 Failure:** Non-owner (editor/viewer) cannot share
- **96-workspace-acl.AC8.8 Failure:** Owner cannot share when allow_sharing resolves to False
- **96-workspace-acl.AC8.9 Failure:** Cannot grant permission higher than owner (owner cannot make someone else owner)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add sharing fields to Activity and Course models

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

1. Add `allow_sharing` to `Activity` class (after `copy_protection`, line 208):

```python
allow_sharing: bool | None = Field(default=None)
"""Tri-state sharing control.

None=inherit from course, True=allowed, False=disallowed.
"""
```

2. Add `default_allow_sharing` to `Course` class (after `default_copy_protection`, line 103):

```python
default_allow_sharing: bool = Field(default=False)
"""Course-level default for workspace sharing.

Inherited by activities with allow_sharing=NULL.
"""
```

These mirror `copy_protection`/`default_copy_protection` exactly.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.models import Activity, Course; print(Activity(title='t', week_id='00000000-0000-0000-0000-000000000000', template_workspace_id='00000000-0000-0000-0000-000000000001').allow_sharing)"`
Expected: `None`

**Commit:** `feat: add allow_sharing tri-state to Activity and Course models`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Alembic migration for sharing columns

**Files:**
- Create: `alembic/versions/XXXX_add_sharing_columns.py`

**Implementation:**

Generate a migration stub and hand-write the operations:

```bash
uv run alembic revision -m "add sharing columns"
```

The `upgrade()` function:

```python
def upgrade() -> None:
    op.add_column(
        "course",
        sa.Column(
            "default_allow_sharing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "activity",
        sa.Column("allow_sharing", sa.Boolean(), nullable=True),
    )
```

The `downgrade()` function:

```python
def downgrade() -> None:
    op.drop_column("activity", "allow_sharing")
    op.drop_column("course", "default_allow_sharing")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly.

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade succeed.

**Commit:** `feat: add migration for sharing columns on course and activity`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Add allow_sharing to PlacementContext and resolution

**Verifies:** 96-workspace-acl.AC8.3, 96-workspace-acl.AC8.4, 96-workspace-acl.AC8.5

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

1. Add `allow_sharing: bool = False` field to `PlacementContext` (after `copy_protection`, line 39):

```python
allow_sharing: bool = False
```

2. In `_resolve_activity_placement()` (around line 119-133), add sharing resolution alongside copy protection:

```python
# Resolve tri-state allow_sharing: explicit wins, else course default
if activity.allow_sharing is not None:
    resolved_sharing = activity.allow_sharing
else:
    resolved_sharing = course.default_allow_sharing

return PlacementContext(
    placement_type="activity",
    activity_title=activity.title,
    week_number=week.week_number,
    week_title=week.title,
    course_code=course.code,
    course_name=course.name,
    copy_protection=resolved_cp,
    allow_sharing=resolved_sharing,
)
```

3. Loose and course-placed workspaces resolve `allow_sharing` to `False` (same as `copy_protection`).

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.workspaces import PlacementContext; print(PlacementContext(placement_type='loose').allow_sharing)"`
Expected: `False`

**Commit:** `feat: resolve allow_sharing tri-state in PlacementContext`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add grant_share() to db/acl.py

**Verifies:** 96-workspace-acl.AC8.1, 96-workspace-acl.AC8.2, 96-workspace-acl.AC8.6, 96-workspace-acl.AC8.7, 96-workspace-acl.AC8.8, 96-workspace-acl.AC8.9

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `grant_share()` which validates sharing rules and creates/updates the ACLEntry in a single session:

```python
async def grant_share(
    workspace_id: UUID,
    grantor_id: UUID,
    recipient_id: UUID,
    permission: str,
    *,
    sharing_allowed: bool,
    grantor_is_staff: bool = False,
) -> ACLEntry:
    """Share a workspace with another user.

    Validates sharing rules before creating the ACLEntry:
    1. Grantor must be the workspace owner (ACLEntry with "owner" permission)
       OR grantor_is_staff must be True.
    2. If not staff, sharing must be allowed (sharing_allowed=True).
    3. Permission must be "editor" or "viewer" (never "owner").

    TOCTOU fix (DBA I5): the ownership check and grant happen in a SINGLE
    session to prevent race conditions. Does NOT delegate to the public
    grant_permission() which opens its own session.

    Args:
        workspace_id: The Workspace UUID.
        grantor_id: The user UUID granting the share.
        recipient_id: The user UUID receiving the share.
        permission: Permission level to grant ("editor" or "viewer").
        sharing_allowed: Whether sharing is enabled for this workspace's context.
        grantor_is_staff: Whether the grantor is an instructor/coordinator/tutor.

    Returns:
        The created or updated ACLEntry.

    Raises:
        PermissionError: If sharing rules are violated.
    """
    # Rule 3: Cannot grant owner permission
    if permission == "owner":
        raise PermissionError("Cannot grant owner permission via sharing")

    async with get_session() as session:
        # Rule 1: Grantor must be owner or staff
        if not grantor_is_staff:
            entry = await session.exec(
                select(ACLEntry).where(
                    ACLEntry.workspace_id == workspace_id,
                    ACLEntry.user_id == grantor_id,
                )
            )
            grantor_entry = entry.one_or_none()
            if grantor_entry is None or grantor_entry.permission != "owner":
                raise PermissionError("Only workspace owners can share")

            # Rule 2: Sharing must be allowed (non-staff only)
            if not sharing_allowed:
                raise PermissionError("Sharing is not allowed for this workspace")

        # Grant within the same session (no separate grant_permission() call)
        existing = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == recipient_id,
            )
        )
        acl_entry = existing.one_or_none()
        if acl_entry is not None:
            acl_entry.permission = permission
        else:
            acl_entry = ACLEntry(
                workspace_id=workspace_id,
                user_id=recipient_id,
                permission=permission,
            )
            session.add(acl_entry)
        await session.flush()
        await session.refresh(acl_entry)
        return acl_entry
```

The `sharing_allowed` and `grantor_is_staff` parameters are resolved by the caller (page layer) from `PlacementContext.allow_sharing` and enrollment role. This keeps the function pure with respect to its inputs -- no additional DB queries for context resolution. The ownership check and the grant happen in a single session to prevent TOCTOU races.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import grant_share; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add grant_share() with ownership and sharing validation`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update update_activity() and update_course() for sharing fields

**Files:**
- Modify: `src/promptgrimoire/db/activities.py`
- Modify: `src/promptgrimoire/db/courses.py`

**Implementation:**

1. **update_activity()** (activities.py:79-107) — add `allow_sharing` parameter following the same Ellipsis sentinel pattern as `copy_protection`:

```python
async def update_activity(
    activity_id: UUID,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]  # Ellipsis sentinel: distinguishes "not provided" from explicit None
    copy_protection: bool | None = ...,  # type: ignore[assignment]  # Ellipsis sentinel
    allow_sharing: bool | None = ...,  # type: ignore[assignment]  # Ellipsis sentinel
) -> Activity | None:
```

Add in the body:
```python
if allow_sharing is not ...:
    activity.allow_sharing = allow_sharing
```

2. **update_course()** (courses.py:88-118) — add `default_allow_sharing` parameter:

```python
async def update_course(
    course_id: UUID,
    name: str | None = None,
    default_copy_protection: bool = ...,  # type: ignore[assignment]  # Ellipsis sentinel: distinguishes "not provided" from False
    default_allow_sharing: bool = ...,  # type: ignore[assignment]  # Ellipsis sentinel
) -> Course | None:
```

Add in the body:
```python
if default_allow_sharing is not ...:
    course.default_allow_sharing = default_allow_sharing
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.activities import update_activity; from promptgrimoire.db.courses import update_course; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: extend update_activity() and update_course() with sharing parameters`

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-8) -->
<!-- START_TASK_6 -->
### Task 6: Add sharing UI controls to pages/courses.py

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

1. Add sharing options dict (after `_COPY_PROTECTION_OPTIONS`, line 68):

```python
_SHARING_OPTIONS: dict[str, str] = {
    "inherit": "Inherit from course",
    "on": "Allowed",
    "off": "Not allowed",
}
```

2. In `open_course_settings()` (lines 107-131), add a sharing toggle alongside the copy protection switch:

```python
sharing_switch = ui.switch(
    "Default allow sharing",
    value=course.default_allow_sharing,
)
```

Update the `save()` function to include:
```python
await update_course(
    course.id,
    default_copy_protection=switch.value,
    default_allow_sharing=sharing_switch.value,
)
course.default_allow_sharing = sharing_switch.value
```

3. In the activity settings dialog (around line 134-161), add a sharing tri-state select following the copy protection select pattern:

```python
sharing_select = ui.select(
    _SHARING_OPTIONS,
    label="Allow Sharing",
    value=_model_to_ui(activity.allow_sharing),
)
```

Update the save handler to include:
```python
await update_activity(
    activity.id,
    allow_sharing=_ui_to_model(sharing_select.value),
)
```

The existing `_model_to_ui()` and `_ui_to_model()` functions work unchanged for the sharing tri-state — they convert between `bool | None` and UI string keys generically.

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.courses import *; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add sharing controls to course and activity settings UI`

<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

Add `grant_share` to the ACL imports:

```python
from promptgrimoire.db.acl import (
    can_access_workspace,
    grant_permission,
    grant_share,
    list_entries_for_workspace,
    list_entries_for_user,
    resolve_permission,
    revoke_permission,
)
```

Add to `__all__`.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import grant_share; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: export grant_share from db package`

<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Integration tests for sharing controls

**Verifies:** 96-workspace-acl.AC8.1, 96-workspace-acl.AC8.2, 96-workspace-acl.AC8.3, 96-workspace-acl.AC8.4, 96-workspace-acl.AC8.5, 96-workspace-acl.AC8.6, 96-workspace-acl.AC8.7, 96-workspace-acl.AC8.8, 96-workspace-acl.AC8.9

**Files:**
- Create: `tests/integration/test_sharing_controls.py`

**Implementation:**

Integration tests using real PostgreSQL. Include skip guard. Shared async fixture creates test data:
- An owner_user, a recipient_user, a staff_user (enrolled as instructor)
- A course with `default_allow_sharing = True`
- An activity with `allow_sharing = None` (inherits from course)
- A workspace cloned for owner_user with ACLEntry(owner)
- The workspace_id for the tests

Tests:

- **AC8.1:** Call `grant_share(workspace_id, owner_user.id, recipient_user.id, "editor", sharing_allowed=True)`. Verify ACLEntry created with `permission == "editor"`.

- **AC8.2:** Call `grant_share(workspace_id, owner_user.id, recipient_user.id, "viewer", sharing_allowed=True)`. Verify ACLEntry with `permission == "viewer"`.

- **AC8.3:** Create activity with `allow_sharing=None`, course with `default_allow_sharing=True`. Query `PlacementContext`. Verify `allow_sharing == True`. Repeat with `default_allow_sharing=False`. Verify `allow_sharing == False`.

- **AC8.4:** Activity `allow_sharing=True`, course `default_allow_sharing=False`. Verify PlacementContext `allow_sharing == True`.

- **AC8.5:** Activity `allow_sharing=False`, course `default_allow_sharing=True`. Verify PlacementContext `allow_sharing == False`.

- **AC8.6:** Call `grant_share(workspace_id, staff_user.id, recipient_user.id, "editor", sharing_allowed=False, grantor_is_staff=True)`. Verify succeeds (staff bypasses sharing_allowed check).

- **AC8.7:** Grant recipient_user "editor" ACL on workspace. Call `grant_share(workspace_id, recipient_user.id, another_user.id, "viewer", sharing_allowed=True)`. Verify `PermissionError("Only workspace owners can share")`.

- **AC8.8:** Call `grant_share(workspace_id, owner_user.id, recipient_user.id, "editor", sharing_allowed=False)`. Verify `PermissionError("Sharing is not allowed")`.

- **AC8.9:** Call `grant_share(workspace_id, owner_user.id, recipient_user.id, "owner", sharing_allowed=True)`. Verify `PermissionError("Cannot grant owner permission")`.

**Testing:**

Run: `uv run pytest tests/integration/test_sharing_controls.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new sharing tests.

**Commit:** `test: add integration tests for sharing controls`

<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_C -->
