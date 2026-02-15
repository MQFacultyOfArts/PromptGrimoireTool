# Workspace ACL Implementation Plan — Phase 4

**Goal:** Implement the hybrid permission resolution function that checks explicit ACL entries, then derives access from course enrollment for instructors.

**Architecture:** `resolve_permission()` in `db/acl.py` performs a two-step sequential lookup: (1) explicit ACLEntry for (workspace_id, user_id), (2) enrollment-derived access by resolving Workspace → Activity → Course hierarchy and checking CourseEnrollment. If both apply, the higher Permission.level wins. Admin bypass is NOT in this function — it lives at the page level via `is_privileged_user()`. Course gains a `default_instructor_permission` field (str FK to `permission.name`, default `"editor"`).

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 4 of 8)

**Codebase verified:** 2026-02-15

**Design deviation:** The design plan specifies `Course.default_instructor_permission_id: UUID FK → Permission`. With string PKs (Phase 1 decision), this becomes `default_instructor_permission: str` — a VARCHAR FK to `permission.name`.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC6: Permission resolution
- **96-workspace-acl.AC6.1 Success:** User with explicit ACL entry gets that permission level
- **96-workspace-acl.AC6.2 Success:** Instructor enrolled in course gets Course.default_instructor_permission for workspaces in that course
- **96-workspace-acl.AC6.3 Success:** Coordinator enrolled in course gets access (same as instructor)
- **96-workspace-acl.AC6.4 Success:** Tutor enrolled in course gets access (same as instructor)
- **96-workspace-acl.AC6.5 Success:** When both explicit ACL and enrollment-derived access exist, the higher permission level wins
- **96-workspace-acl.AC6.6 Success:** Admin (via Stytch) gets owner-level access regardless of ACL/enrollment
- **96-workspace-acl.AC6.7 Failure:** Student enrolled in course but without explicit ACL entry gets None (no access to others' workspaces)
- **96-workspace-acl.AC6.8 Failure:** Unenrolled user with no ACL entry gets None
- **96-workspace-acl.AC6.9 Failure:** User with no auth session gets None
- **96-workspace-acl.AC6.10 Edge:** Workspace with no activity_id (loose) — only explicit ACL entries grant access, no enrollment derivation
- **96-workspace-acl.AC6.11 Edge:** Workspace placed in course (course_id set, no activity_id) — instructor access derived from course enrollment

**Note:** AC6.6 and AC6.9 are tested in Phase 8 (enforcement layer) where the admin check and auth session exist. This phase tests the DB-layer resolution (AC6.1-AC6.5, AC6.7-AC6.8, AC6.10-AC6.11). AC6.6 is verified at the DB layer by confirming resolve_permission does NOT check admin — that responsibility belongs to the enforcement layer.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add Course.default_instructor_permission and Alembic migration

**Files:**
- Modify: `src/promptgrimoire/db/models.py`
- Create: `alembic/versions/XXXX_add_course_default_instructor_permission.py`

**Implementation:**

1. Add `default_instructor_permission` field to the `Course` class (after `default_copy_protection`, line 99):

```python
default_instructor_permission: str = Field(
    default="editor",
    sa_column=Column(
        String(50),
        ForeignKey("permission.name", ondelete="RESTRICT"),
        nullable=False,
        server_default="editor",
    ),
)
"""Default permission level for instructors accessing student workspaces.

Instructors (coordinator/instructor/tutor roles) get this permission
when accessing workspaces in the course via enrollment-derived access.
"""
```

2. Generate a migration stub and hand-write the operation:

```bash
uv run alembic revision -m "add course default instructor permission"
```

The `upgrade()` function:

```python
def upgrade() -> None:
    op.add_column(
        "course",
        sa.Column(
            "default_instructor_permission",
            sa.String(50),
            sa.ForeignKey("permission.name", ondelete="RESTRICT"),
            nullable=False,
            server_default="editor",
        ),
    )
```

The `downgrade()` function:

```python
def downgrade() -> None:
    op.drop_column("course", "default_instructor_permission")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly. Existing courses get `default_instructor_permission = "editor"`.

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade succeed.

**Commit:** `feat: add Course.default_instructor_permission FK to permission table`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement resolve_permission() in db/acl.py

**Verifies:** 96-workspace-acl.AC6.1, 96-workspace-acl.AC6.2, 96-workspace-acl.AC6.3, 96-workspace-acl.AC6.4, 96-workspace-acl.AC6.5, 96-workspace-acl.AC6.7, 96-workspace-acl.AC6.8

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `resolve_permission()` to `db/acl.py`. This is the core resolution function — pure data, no admin check.

```python
async def resolve_permission(
    workspace_id: UUID, user_id: UUID
) -> str | None:
    """Resolve the effective permission for a user on a workspace.

    Two-step hybrid resolution:
    1. Explicit ACL lookup: query ACLEntry for (workspace_id, user_id).
    2. Enrollment-derived: resolve Workspace → Activity → Week → Course
       hierarchy, check CourseEnrollment for staff role.
    3. If both apply, the higher Permission.level wins.
    4. Default deny: return None.

    Admin bypass is NOT checked here — that belongs at the page level
    via is_privileged_user().

    Returns:
        Permission name string (e.g., "owner", "editor", "viewer") or None if denied.
    """
    async with get_session() as session:
        # Step 1: Explicit ACL lookup
        explicit_entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        explicit = explicit_entry.one_or_none()

        # Step 2: Enrollment-derived access
        derived_permission = await _derive_enrollment_permission(
            session, workspace_id, user_id
        )

        # Step 3: Highest wins
        if explicit and derived_permission:
            # Compare Permission.level values
            explicit_level = await session.exec(
                select(Permission.level).where(
                    Permission.name == explicit.permission
                )
            )
            derived_level = await session.exec(
                select(Permission.level).where(
                    Permission.name == derived_permission
                )
            )
            e_level = explicit_level.one()
            d_level = derived_level.one()
            return explicit.permission if e_level >= d_level else derived_permission

        if explicit:
            return explicit.permission
        if derived_permission:
            return derived_permission

        # Step 4: Default deny
        return None
```

Add the private helper for enrollment-derived access:

```python
async def _derive_enrollment_permission(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> str | None:
    """Derive permission from course enrollment for staff roles.

    Resolves Workspace → (Activity → Week →) Course hierarchy.
    Checks CourseEnrollment for instructor/coordinator/tutor role.
    Returns Course.default_instructor_permission if staff, None otherwise.
    """
    from promptgrimoire.db.models import (
        Activity,
        Course,
        CourseEnrollment,
        Week,
        Workspace,
    )

    # Find Workspace by workspace_id
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        return None

    # Resolve course_id from workspace placement
    course_id: UUID | None = None

    if workspace.activity_id is not None:
        # Activity-placed: Activity → Week → Course
        activity = await session.get(Activity, workspace.activity_id)
        if activity is not None:
            week = await session.get(Week, activity.week_id)
            if week is not None:
                course_id = week.course_id
    elif workspace.course_id is not None:
        # Course-placed: direct
        course_id = workspace.course_id

    # Loose workspaces (no activity_id, no course_id): no enrollment derivation
    if course_id is None:
        return None

    # Check enrollment with staff role
    enrollment_result = await session.exec(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.user_id == user_id,
        )
    )
    enrollment = enrollment_result.one_or_none()
    if enrollment is None:
        return None

    # Staff roles get derived access; students do not
    staff_roles = {"coordinator", "instructor", "tutor"}
    if enrollment.role not in staff_roles:
        return None

    # Return course's default instructor permission
    course = await session.get(Course, course_id)
    if course is None:
        return None
    return course.default_instructor_permission
```

Add the necessary imports at the top of `acl.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from promptgrimoire.db.models import ACLEntry, Permission
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import resolve_permission; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: implement hybrid permission resolution in db/acl.py`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Implement can_access_workspace() convenience function

**Verifies:** 96-workspace-acl.AC6.10, 96-workspace-acl.AC6.11

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Add `can_access_workspace()` to `db/acl.py`:

```python
async def can_access_workspace(
    workspace_id: UUID, user_id: UUID
) -> str | None:
    """Check if a user can access a workspace and return their permission level.

    Delegates directly to resolve_permission(workspace_id, user_id).
    ACLEntry links directly to Workspace via workspace_id, so no
    separate lookup is needed.

    Returns:
        Permission name string or None if denied.
    """
    return await resolve_permission(workspace_id, user_id)
```

To support session reuse from internal callers, refactor `resolve_permission()`
to delegate to an internal `_resolve_permission_with_session()` that accepts
an explicit session:

```python
async def _resolve_permission_with_session(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> str | None:
    """Internal: resolve permission using an existing session."""
    # Step 1: Explicit ACL lookup
    explicit_entry = await session.exec(
        select(ACLEntry).where(
            ACLEntry.workspace_id == workspace_id,
            ACLEntry.user_id == user_id,
        )
    )
    explicit = explicit_entry.one_or_none()

    # Step 2: Enrollment-derived access
    derived_permission = await _derive_enrollment_permission(
        session, workspace_id, user_id
    )

    # Step 3: Highest wins
    if explicit and derived_permission:
        explicit_level = await session.exec(
            select(Permission.level).where(
                Permission.name == explicit.permission
            )
        )
        derived_level = await session.exec(
            select(Permission.level).where(
                Permission.name == derived_permission
            )
        )
        e_level = explicit_level.one()
        d_level = derived_level.one()
        return explicit.permission if e_level >= d_level else derived_permission

    if explicit:
        return explicit.permission
    if derived_permission:
        return derived_permission

    # Step 4: Default deny
    return None


async def resolve_permission(
    workspace_id: UUID, user_id: UUID
) -> str | None:
    """Public wrapper that opens its own session."""
    async with get_session() as session:
        return await _resolve_permission_with_session(
            session, workspace_id, user_id
        )
```

Since ACLEntry links directly to Workspace via `workspace_id`,
`can_access_workspace()` is a thin alias for `resolve_permission()`.
The `_resolve_permission_with_session()` internal function exists for
callers that need to share a session (e.g. `grant_share()` in Phase 6).

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import can_access_workspace; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add can_access_workspace() convenience function`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

Add the new functions to the ACL imports:

```python
from promptgrimoire.db.acl import (
    can_access_workspace,
    grant_permission,
    list_entries_for_resource,
    list_entries_for_user,
    resolve_permission,
    revoke_permission,
)
```

Add all to `__all__`.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import resolve_permission, can_access_workspace; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: export permission resolution functions from db package`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Integration tests for permission resolution

**Verifies:** 96-workspace-acl.AC6.1, 96-workspace-acl.AC6.2, 96-workspace-acl.AC6.3, 96-workspace-acl.AC6.4, 96-workspace-acl.AC6.5, 96-workspace-acl.AC6.7, 96-workspace-acl.AC6.8, 96-workspace-acl.AC6.10, 96-workspace-acl.AC6.11

**Files:**
- Create: `tests/integration/test_permission_resolution.py`

**Implementation:**

Integration tests using real PostgreSQL. Include skip guard. Shared async fixture creates test data:
- Two users (staff_user, student_user)
- A course with `default_instructor_permission = "editor"`
- A week and an activity in that course
- A workspace cloned from the activity (via `create_workspace()`)
- CourseEnrollments (staff_user as instructor, student_user as student)

Tests:

- **AC6.1:** Grant "viewer" ACL to student_user on workspace. `resolve_permission()` returns "viewer".

- **AC6.2:** Enroll user as instructor. No explicit ACL. `resolve_permission()` returns "editor" (from `Course.default_instructor_permission`).

- **AC6.3:** Enroll user as coordinator. `resolve_permission()` returns "editor".

- **AC6.4:** Enroll user as tutor. `resolve_permission()` returns "editor".

- **AC6.5:** Grant explicit "viewer" ACL to instructor. `resolve_permission()` returns "editor" (enrollment-derived "editor" level 20 > explicit "viewer" level 10). Then grant explicit "owner" ACL. `resolve_permission()` returns "owner" (level 30 > 20).

- **AC6.7:** Student enrolled in course, no explicit ACL. `resolve_permission()` returns None.

- **AC6.8:** Unenrolled user, no ACL. `resolve_permission()` returns None.

- **AC6.10:** Loose workspace (no activity_id, no course_id), no explicit ACL. `resolve_permission()` returns None. Grant ACL. `resolve_permission()` returns the granted permission.

- **AC6.11:** Course-placed workspace (course_id set, no activity_id). Instructor enrolled in course. `resolve_permission()` returns "editor".

**Testing:**

Run: `uv run pytest tests/integration/test_permission_resolution.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new resolution tests.

**Commit:** `test: add integration tests for hybrid permission resolution`

<!-- END_TASK_5 -->
