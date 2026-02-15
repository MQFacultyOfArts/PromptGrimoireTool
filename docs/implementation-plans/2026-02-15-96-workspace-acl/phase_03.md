# Workspace ACL Implementation Plan — Phase 3

**Goal:** Create ACLEntry table linking users to workspaces with permissions, and implement ACL CRUD operations.

**Architecture:** ACLEntry uses surrogate UUID PK + unique constraint on (workspace_id, user_id), following the CourseEnrollment pattern. ACLEntry links directly to Workspace (CASCADE), User (CASCADE), and Permission (RESTRICT). New `db/acl.py` module provides grant/revoke/list operations with PostgreSQL upsert for grant.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 8 phases from original design (this is phase 3 of 8)

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC4: ACLEntry model
- **96-workspace-acl.AC4.1 Success:** ACLEntry can be created with valid workspace_id, user_id, permission (string FK)
- **96-workspace-acl.AC4.2 Success:** Deleting a Workspace CASCADEs to its ACLEntry rows
- **96-workspace-acl.AC4.3 Success:** Deleting a User CASCADEs to their ACLEntry rows
- **96-workspace-acl.AC4.4 Failure:** Duplicate (workspace_id, user_id) pair is rejected (UNIQUE constraint)
- **96-workspace-acl.AC4.5 Edge:** Granting a new permission to an existing (workspace_id, user_id) pair upserts the permission

### 96-workspace-acl.AC5: ACL CRUD operations
- **96-workspace-acl.AC5.1 Success:** Grant permission to a user on a workspace
- **96-workspace-acl.AC5.2 Success:** Revoke permission (delete ACLEntry)
- **96-workspace-acl.AC5.3 Success:** List all ACL entries for a workspace
- **96-workspace-acl.AC5.4 Success:** List all ACL entries for a user

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add ACLEntry model to models.py

**Verifies:** 96-workspace-acl.AC4.1, 96-workspace-acl.AC4.2, 96-workspace-acl.AC4.3, 96-workspace-acl.AC4.4

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

Add `ACLEntry` class after the Permission model (added in Phase 1):

```python
class ACLEntry(SQLModel, table=True):
    """Per-user, per-workspace permission grant.

    One entry per (workspace, user) pair. Permission level can be updated
    via upsert. Cascade-deletes when the Workspace or User is deleted.
    """

    __tablename__ = "acl_entry"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_acl_entry_workspace_user"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    user_id: UUID = Field(sa_column=_cascade_fk_column("user.id"))
    permission: str = Field(
        sa_column=Column(
            String(50),
            ForeignKey("permission.name", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
```

**Note:** The `permission` FK uses explicit `ondelete="RESTRICT"` to communicate intent — permission reference rows must never be deleted while ACLEntries reference them. PostgreSQL default is `NO ACTION` (which behaves like RESTRICT within a transaction), but explicit is better.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.models import ACLEntry; print(ACLEntry.__table__.columns.keys())"`
Expected: `['id', 'workspace_id', 'user_id', 'permission', 'created_at']`

**Commit:** `feat: add ACLEntry model with workspace/user/permission FKs`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Alembic migration — create acl_entry table

**Verifies:** 96-workspace-acl.AC4.1, 96-workspace-acl.AC4.4

**Files:**
- Create: `alembic/versions/XXXX_add_acl_entry_table.py` (auto-generated revision ID)

**Implementation:**

Generate the migration:
```bash
uv run alembic revision --autogenerate -m "add acl entry table"
```

Review and adjust the generated migration. The `upgrade()` function should:

```python
def upgrade() -> None:
    op.create_table(
        "acl_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission"], ["permission.name"], ondelete="RESTRICT"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_acl_entry_workspace_user"),
    )
    # Index on user_id for "list entries for user" queries
    op.create_index("ix_acl_entry_user_id", "acl_entry", ["user_id"])
```

The `downgrade()` function:

```python
def downgrade() -> None:
    op.drop_index("ix_acl_entry_user_id", table_name="acl_entry")
    op.drop_table("acl_entry")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly.

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade succeed.

**Commit:** `feat: add migration for acl_entry table`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create db/acl.py with ACL CRUD functions

**Verifies:** 96-workspace-acl.AC4.5, 96-workspace-acl.AC5.1, 96-workspace-acl.AC5.2, 96-workspace-acl.AC5.3, 96-workspace-acl.AC5.4

**Files:**
- Create: `src/promptgrimoire/db/acl.py`

**Implementation:**

```python
"""ACL (Access Control List) operations for workspace permissions.

Provides grant, revoke, and query operations for per-user, per-workspace
permission entries.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import ACLEntry


async def grant_permission(
    workspace_id: UUID, user_id: UUID, permission: str
) -> ACLEntry:
    """Grant a permission to a user on a workspace.

    If the user already has a permission on this workspace, it is updated
    (upsert). Returns the created or updated ACLEntry.
    """
    async with get_session() as session:
        stmt = pg_insert(ACLEntry).values(
            workspace_id=workspace_id,
            user_id=user_id,
            permission=permission,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_acl_entry_workspace_user",
            set_={"permission": stmt.excluded.permission},
        )
        await session.execute(stmt)
        await session.flush()

        # Fetch the upserted row
        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        return entry.one()


async def revoke_permission(workspace_id: UUID, user_id: UUID) -> bool:
    """Revoke a user's permission on a workspace.

    Returns True if an entry was deleted, False if no entry existed.
    """
    async with get_session() as session:
        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        row = entry.one_or_none()
        if row is None:
            return False
        await session.delete(row)
        await session.flush()
        return True


async def list_entries_for_workspace(workspace_id: UUID) -> list[ACLEntry]:
    """List all ACL entries for a workspace."""
    async with get_session() as session:
        result = await session.exec(
            select(ACLEntry).where(ACLEntry.workspace_id == workspace_id)
        )
        return list(result.all())


async def list_entries_for_user(user_id: UUID) -> list[ACLEntry]:
    """List all ACL entries for a user."""
    async with get_session() as session:
        result = await session.exec(
            select(ACLEntry).where(ACLEntry.user_id == user_id)
        )
        return list(result.all())
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import grant_permission, revoke_permission, list_entries_for_workspace, list_entries_for_user; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add ACL CRUD operations (grant, revoke, list)`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

1. Add `ACLEntry` to the model imports (alongside Permission, CourseRoleRef added in Phase 1):
   ```python
   from promptgrimoire.db.models import (
       ACLEntry,
       # ... existing imports ...
   )
   ```

2. Add ACL CRUD function imports:
   ```python
   from promptgrimoire.db.acl import (
       grant_permission,
       list_entries_for_user,
       list_entries_for_workspace,
       revoke_permission,
   )
   ```

3. Add all new names to `__all__`.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db import ACLEntry, grant_permission, revoke_permission; print('OK')"`
Expected: Imports succeed.

**Commit:** `refactor: export ACLEntry and ACL CRUD from db package`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5) -->
<!-- START_TASK_5 -->
### Task 5: Integration tests for ACLEntry model and ACL CRUD

**Verifies:** 96-workspace-acl.AC4.1, 96-workspace-acl.AC4.2, 96-workspace-acl.AC4.3, 96-workspace-acl.AC4.4, 96-workspace-acl.AC4.5, 96-workspace-acl.AC5.1, 96-workspace-acl.AC5.2, 96-workspace-acl.AC5.3, 96-workspace-acl.AC5.4

**Files:**
- Create: `tests/integration/test_acl_crud.py`

**Implementation:**

Integration tests using the `db_session` fixture (real PostgreSQL, NullPool). Include skip guard:

```python
pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)
```

Tests must verify each AC:

- **AC4.1:** Create an ACLEntry with valid workspace_id, user_id, permission. Verify it persists and fields match.
  - Setup: create a User, create a Workspace, call `grant_permission()`.

- **AC4.2:** Delete a Workspace, verify its ACLEntry rows are cascade-deleted.
  - Setup: create User + Workspace + grant_permission. Delete the Workspace via session. Verify ACLEntry is gone.

- **AC4.3:** Delete a User, verify their ACLEntry rows are cascade-deleted.
  - Setup: create User + Workspace + grant_permission. Delete the User via session. Verify ACLEntry is gone.

- **AC4.4:** Attempt to create two ACLEntry rows with same (workspace_id, user_id). Verify IntegrityError.
  - Setup: create User + Workspace + insert ACLEntry directly via session (not upsert). Insert duplicate. Verify IntegrityError.

- **AC4.5:** Call `grant_permission()` twice with different permissions for the same (workspace_id, user_id). Verify the second call updates the permission (upsert).

- **AC5.1:** `grant_permission()` creates an entry. Verify returned ACLEntry has correct fields.

- **AC5.2:** `revoke_permission()` deletes an entry. Verify returns True. Call again, verify returns False.

- **AC5.3:** Create multiple ACLEntry rows for one workspace (different users). Call `list_entries_for_workspace()`. Verify all returned.

- **AC5.4:** Create multiple ACLEntry rows for one user (different workspaces). Call `list_entries_for_user()`. Verify all returned.

Follow project patterns from `docs/testing.md`. Use `@pytest_asyncio.fixture` for async fixtures. Use unique identifiers (`uuid4().hex[:8]`) for test isolation.

**Testing:**

Run: `uv run pytest tests/integration/test_acl_crud.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new ACL tests.

**Commit:** `test: add integration tests for ACLEntry model and ACL CRUD operations`

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->
