# Workspace ACL Implementation Plan — Phase 2

**Goal:** Replace the `CourseRole` StrEnum with a FK to the `course_role` reference table (string PK from Phase 1), updating all consumers.

**Architecture:** ALTER the existing `role` column from PG enum to VARCHAR with FK constraint (in-place, zero data loss). Replace all `CourseRole.member` enum accesses with string literals. Query the `course_role` table for UI dropdown values.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 2 of 8)

**Codebase verified:** 2026-02-15

**Design deviation:** The design plan specifies dropping the `role` column and adding a new `role_id` UUID FK. With string PKs, we ALTER the column type in-place instead — the string values are already correct. The `CourseRole` StrEnum is deleted entirely; all code uses string literals.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC3: CourseRole normalisation
- **96-workspace-acl.AC3.1 Success:** CourseEnrollment uses role_id FK to CourseRole table
- **96-workspace-acl.AC3.2 Success:** Week visibility logic works identically after normalisation (coordinators/instructors/tutors see all weeks, students see only published)
- **96-workspace-acl.AC3.3 Success:** Enrollment CRUD functions accept role by reference table lookup
- **96-workspace-acl.AC3.4 Failure:** Enrolling with an invalid role_id is rejected (FK constraint)

**Note:** AC3.1 references `role_id` per original design; with string PKs the equivalent is `role` as a VARCHAR FK to `course_role.name`. AC3.3 references "reference table lookup" — with string PKs, the role string IS the FK value directly.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Alembic migration — ALTER role column from PG enum to VARCHAR FK

**Verifies:** 96-workspace-acl.AC3.1, 96-workspace-acl.AC3.4

**Files:**
- Create: `alembic/versions/XXXX_normalise_course_role_to_fk.py` (auto-generated revision ID)

**Implementation:**

Generate a migration stub and hand-write the operations (autogenerate won't handle enum-to-varchar correctly):

```bash
uv run alembic revision -m "normalise course role to fk"
```

The `upgrade()` function:

```python
def upgrade() -> None:
    # 1. Convert column type from PG enum to varchar
    op.alter_column(
        "course_enrollment",
        "role",
        type_=sa.String(50),
        existing_type=sa.Enum(
            "coordinator", "instructor", "tutor", "student", name="courserole"
        ),
        postgresql_using="role::text",
    )

    # 2. Add FK constraint to course_role reference table
    op.create_foreign_key(
        "fk_course_enrollment_role",
        "course_enrollment",
        "course_role",
        ["role"],
        ["name"],
    )

    # 3. Drop the PG enum type (no longer needed)
    op.execute("DROP TYPE courserole")
```

The `downgrade()` function:

```python
def downgrade() -> None:
    # 1. Drop the FK constraint
    op.drop_constraint("fk_course_enrollment_role", "course_enrollment", type_="foreignkey")

    # 2. Recreate the PG enum type
    courserole = sa.Enum("coordinator", "instructor", "tutor", "student", name="courserole")
    courserole.create(op.get_bind())

    # 3. Convert column type back to PG enum
    op.alter_column(
        "course_enrollment",
        "role",
        type_=courserole,
        existing_type=sa.String(50),
        postgresql_using="role::courserole",
    )
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly. Existing enrollment rows preserved with same role values.

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade succeed.

**Commit:** `feat: migrate CourseEnrollment.role from PG enum to FK on course_role`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update CourseEnrollment model and delete StrEnum

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

1. Delete the `CourseRole` StrEnum class (lines 19-28).

2. Update `CourseEnrollment.role` field (line 132) from:
   ```python
   role: CourseRole = Field(default=CourseRole.student)
   ```
   to:
   ```python
   role: str = Field(
       default="student",
       sa_column=Column(String(50), ForeignKey("course_role.name"), nullable=False),
   )
   ```

3. Add `String` to the `sqlalchemy` imports if not already there (may have been added in Phase 1).

4. Remove `CourseRole` from the `StrEnum` import if it becomes unused.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.models import CourseEnrollment; print(CourseEnrollment(role='student'))"`
Expected: Creates instance without errors.

**Commit:** `refactor: replace CourseRole StrEnum with string FK on CourseEnrollment`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Update db/courses.py — enrollment CRUD

**Verifies:** 96-workspace-acl.AC3.3

**Files:**
- Modify: `src/promptgrimoire/db/courses.py`

**Implementation:**

1. Remove `CourseRole` from the import on line 14.

2. Update `enroll_user()` (line 148-190):
   - Change parameter type from `role: CourseRole = CourseRole.student` to `role: str = "student"`

3. Update `update_user_role()` (line 277-305):
   - Change parameter type from `role: CourseRole` to `role: str`

No other logic changes needed — the functions just pass the role value through to the model.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.courses import enroll_user, update_user_role; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: update enrollment CRUD to use string roles`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update db/weeks.py — visibility checks

**Verifies:** 96-workspace-acl.AC3.2

**Files:**
- Modify: `src/promptgrimoire/db/weeks.py`

**Implementation:**

1. Remove `CourseRole` from the import on line 18.

2. In `get_visible_weeks()` (lines 232-241), replace:
   ```python
   if enrollment.role in (
       CourseRole.coordinator,
       CourseRole.instructor,
       CourseRole.tutor,
   ):
   ```
   with:
   ```python
   if enrollment.role in ("coordinator", "instructor", "tutor"):
   ```

3. Same change in `can_access_week()` (lines 289-293).

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.weeks import get_visible_weeks, can_access_week; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: update week visibility to use string role comparisons`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update pages/courses.py — UI and permission checks

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py`

**Implementation:**

1. Remove `CourseRole` from the import on line 40.

2. Replace all `CourseRole.coordinator` → `"coordinator"`, `CourseRole.instructor` → `"instructor"`, etc. throughout the file (10+ locations identified by codebase investigation).

3. The instructor check pattern `enrollment.role in (CourseRole.coordinator, CourseRole.instructor)` becomes `enrollment.role in ("coordinator", "instructor")`.

4. Auto-enroll creator (line 297): `role=CourseRole.coordinator` → `role="coordinator"`.

5. **UI role dropdown** (line 754): Replace `options=[r.value for r in CourseRole]` with a query to the `course_role` table. The dropdown should fetch role names from the DB:
   ```python
   from sqlmodel import select
   from promptgrimoire.db.engine import get_session
   from promptgrimoire.db.models import CourseRoleRef

   async with get_session() as session:
       roles = await session.exec(select(CourseRoleRef.name))
       role_names = roles.all()
   ```
   Use `role_names` as the dropdown options.

6. **Role assignment** (line 774): Replace `role=CourseRole(new_role.value)` with `role=new_role.value` (the string IS the value).

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.courses import *; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: update courses page to use string roles and DB-backed dropdown`

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Update cli.py and db/__init__.py

**Files:**
- Modify: `src/promptgrimoire/cli.py`
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

1. **cli.py** — In `seed_data()` function (line 518), remove the `CourseRole` import and replace enum references:
   ```python
   # Before
   ("instructor@uni.edu", "Test Instructor", CourseRole.coordinator),
   # After
   ("instructor@uni.edu", "Test Instructor", "coordinator"),
   ```
   Same for all four seed users.

2. **db/__init__.py** — Remove `CourseRole` from the import (line 40) and from `__all__` (line 85). Add `CourseRoleRef` and `Permission` to the imports and `__all__` list instead.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import CourseRoleRef, Permission; print('OK')"`
Expected: New models importable from db package.

Run: `uv run python -c "from promptgrimoire.db import CourseRole"`
Expected: ImportError (CourseRole StrEnum no longer exported).

**Commit:** `refactor: update cli seed data and db exports for reference tables`

<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update tests and verify all existing tests pass

**Verifies:** 96-workspace-acl.AC3.1, 96-workspace-acl.AC3.2, 96-workspace-acl.AC3.3, 96-workspace-acl.AC3.4

**Files:**
- Modify: `tests/integration/test_course_service.py`
- Create: `tests/integration/test_course_role_normalisation.py`

**Implementation:**

1. **Update test_course_service.py** — Remove `CourseRole` import (line 15). Replace all `CourseRole.student` → `"student"`, `CourseRole.tutor` → `"tutor"`, etc.

2. **Create test_course_role_normalisation.py** — New integration tests verifying:
   - **AC3.1:** CourseEnrollment.role is a FK to course_role table (create enrollment, verify role value matches a course_role row)
   - **AC3.2:** Week visibility identical after normalisation — enroll as instructor, verify all weeks visible; enroll as student, verify only published weeks visible
   - **AC3.3:** `enroll_user()` accepts role as string, enrollment stored correctly
   - **AC3.4:** Enrolling with an invalid role string (e.g., `"nonexistent"`) raises IntegrityError

**Testing:**

Follow project patterns from `docs/testing.md`. Include skip guard. Use `db_session` fixture. Use `@pytest_asyncio.fixture` for async fixtures.

**Verification:**

Run: `uv run test-all`
Expected: All existing tests pass. New normalisation tests pass.

**Commit:** `test: update and add tests for CourseRole normalisation`

<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->
