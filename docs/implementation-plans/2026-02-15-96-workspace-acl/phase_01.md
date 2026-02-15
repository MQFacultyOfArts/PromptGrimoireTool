# Workspace ACL Implementation Plan

**Goal:** Create the foundational reference tables (Permission, CourseRole) that all subsequent ACL phases depend on.

**Architecture:** Two new SQLModel tables in `db/models.py`. Both use string PKs (name is the identity) with level columns for ordering. Level columns are UNIQUE (prevents ambiguous resolution) and CHECK-constrained (BETWEEN 1 AND 100). One Alembic migration creates both tables and seeds the reference data.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 1 of 8)

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC1: Reference tables exist with correct seed data
- **96-workspace-acl.AC1.1 Success:** Permission table contains owner (level 30), editor (level 20), viewer (level 10) with string PKs
- **96-workspace-acl.AC1.2 Success:** CourseRole table contains coordinator (40), instructor (30), tutor (20), student (10) with string PKs
- **96-workspace-acl.AC1.3 Success:** Reference table rows are created by the migration, not seed-data script
- **96-workspace-acl.AC1.4 Failure:** Duplicate name INSERT into Permission or CourseRole is rejected (PK constraint)
- **96-workspace-acl.AC1.5 Success:** Level columns have CHECK constraints (BETWEEN 1 AND 100) and are UNIQUE within each table

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create Permission and CourseRoleRef models

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

Add two new SQLModel table classes after the existing `CourseRole` StrEnum (which remains until Phase 2):

```python
class Permission(SQLModel, table=True):
    """Reference table for access permission levels.

    String PK — the name is the identity. Rows seeded by migration.
    Level is UNIQUE to prevent ambiguous "highest wins" resolution.
    """

    name: str = Field(
        primary_key=True,
        max_length=50,
        sa_column=Column(String(50), nullable=False),
    )
    level: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            unique=True,
        ),
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 100", name="ck_permission_level_range"),
    )


class CourseRoleRef(SQLModel, table=True):
    """Reference table for course roles (will replace CourseRole StrEnum in Phase 2).

    String PK — the name is the identity. Rows seeded by migration.
    Named CourseRoleRef to avoid collision with existing CourseRole StrEnum.
    """

    __tablename__ = "course_role"

    name: str = Field(
        primary_key=True,
        max_length=50,
        sa_column=Column(String(50), nullable=False),
    )
    level: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            unique=True,
        ),
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 100", name="ck_course_role_level_range"),
    )
```

Add `String, Integer, CheckConstraint` to the existing `sqlalchemy` imports at the top of the file.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.models import Permission, CourseRoleRef; print('OK')"`
Expected: `OK` — models importable without errors.

**Commit:** `feat: add Permission and CourseRoleRef SQLModel tables`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Alembic migration with seed data

**Verifies:** 96-workspace-acl.AC1.1, 96-workspace-acl.AC1.2, 96-workspace-acl.AC1.3, 96-workspace-acl.AC1.5

**Files:**
- Create: `alembic/versions/XXXX_add_acl_reference_tables.py` (auto-generated revision ID)

**Implementation:**

Generate the migration:
```bash
cd /path/to/worktree
uv run alembic revision --autogenerate -m "add acl reference tables"
```

Review and adjust the generated migration. The `upgrade()` function should:

1. Create `permission` table with `name` (String PK), `level` (Integer, UNIQUE), CHECK constraint
2. Create `course_role` table with `name` (String PK), `level` (Integer, UNIQUE), CHECK constraint
3. INSERT seed data for Permission: `("owner", 30)`, `("editor", 20)`, `("viewer", 10)`
4. INSERT seed data for CourseRole: `("coordinator", 40)`, `("instructor", 30)`, `("tutor", 20)`, `("student", 10)`

Seed INSERTs use `op.execute()` with raw SQL:
```python
op.execute("INSERT INTO permission (name, level) VALUES ('owner', 30)")
op.execute("INSERT INTO permission (name, level) VALUES ('editor', 20)")
op.execute("INSERT INTO permission (name, level) VALUES ('viewer', 10)")

op.execute("INSERT INTO course_role (name, level) VALUES ('coordinator', 40)")
op.execute("INSERT INTO course_role (name, level) VALUES ('instructor', 30)")
op.execute("INSERT INTO course_role (name, level) VALUES ('tutor', 20)")
op.execute("INSERT INTO course_role (name, level) VALUES ('student', 10)")
```

The `downgrade()` function should drop both tables in reverse order (no other tables reference them yet):
```python
op.drop_table("course_role")
op.drop_table("permission")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly.

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade succeed (idempotent).

**Commit:** `feat: add migration for ACL reference tables with seed data`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for reference table seed data and constraints

**Verifies:** 96-workspace-acl.AC1.1, 96-workspace-acl.AC1.2, 96-workspace-acl.AC1.3, 96-workspace-acl.AC1.4, 96-workspace-acl.AC1.5

**Files:**
- Create: `tests/integration/test_acl_reference_tables.py`

**Implementation:**

Integration tests using the `db_session` fixture (real PostgreSQL, NullPool). Must include the skip guard:

```python
pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)
```

Tests must verify each AC listed above:
- **96-workspace-acl.AC1.1:** Query Permission table, verify exactly 3 rows with correct names and levels: owner/30, editor/20, viewer/10
- **96-workspace-acl.AC1.2:** Query CourseRoleRef table (`course_role`), verify exactly 4 rows with correct names and levels: coordinator/40, instructor/30, tutor/20, student/10
- **96-workspace-acl.AC1.3:** Seed data exists without running `seed-data` script — inherent from migration, but test confirms rows are present after migration-only setup
- **96-workspace-acl.AC1.4:** Attempt INSERT of a duplicate name into Permission (e.g., a second "owner"), verify IntegrityError is raised. Same for CourseRoleRef.
- **96-workspace-acl.AC1.5:** Attempt INSERT with level outside 1-100 range, verify IntegrityError. Attempt INSERT with duplicate level, verify IntegrityError.

Follow project testing patterns from `docs/testing.md`. Use `@pytest_asyncio.fixture` for any async fixtures. Tests are parallel-safe via UUID isolation.

**Verification:**

Run: `uv run pytest tests/integration/test_acl_reference_tables.py -v`
Expected: All tests pass.

**Commit:** `test: add integration tests for ACL reference table seed data and constraints`

<!-- END_TASK_3 -->
