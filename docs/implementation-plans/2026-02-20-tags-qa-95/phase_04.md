# Annotation Tags QA Pass — Phase 4: Race Condition Fix

**Goal:** Eliminate duplicate `order_index` under concurrent tag/group creation by replacing `SELECT max(order_index)` with atomic counter columns on the workspace row.

**Architecture:** Add `next_tag_order` and `next_group_order` integer columns to the `workspace` table via Alembic migration. `create_tag()` and `create_tag_group()` claim order atomically via `UPDATE workspace SET next_tag_order = next_tag_order + 1 RETURNING next_tag_order - 1`. The explicit `order_index` parameter is removed from both functions — all ordering goes through the counter. `reorder_tags()` and `reorder_tag_groups()` update the counter after reordering. Data migration populates counters from existing tag/group counts.

**Tech Stack:** PostgreSQL, SQLModel, Alembic, SQLAlchemy (text/raw SQL for UPDATE RETURNING)

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-02-20

**Status:** NOT STARTED (audited 2026-02-21). No migration, no atomic counters, `create_tag()`/`create_tag_group()` still use `SELECT max(order_index)`.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC5: Race condition fixed
- **tags-qa-95.AC5.1 Success:** `workspace` table has `next_tag_order` and `next_group_order` columns
- **tags-qa-95.AC5.2 Success:** `create_tag` atomically claims order index via counter column UPDATE+RETURNING
- **tags-qa-95.AC5.3 Success:** `create_tag_group` atomically claims order index via counter column UPDATE+RETURNING
- **tags-qa-95.AC5.4 Success:** Two concurrent `create_tag` calls produce distinct `order_index` values
- **tags-qa-95.AC5.5 Success:** Counter correct after `reorder_tags` -- subsequent create uses next available index

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run alembic upgrade head` — migration applies cleanly, no errors
2. Check DB: `SELECT next_tag_order, next_group_order FROM workspace LIMIT 5` — counters populated correctly from existing data
3. Run `uv run test-all` — all unit + integration tests pass, including new concurrent creation tests
4. Run `uv run test-e2e` — all E2E tests pass (seeded workspaces have correct counter values)
5. Run `uv run seed-data` — seed data creates tags with correct counter updates

---

<!-- START_TASK_1 -->
### Task 1: Alembic migration — counter columns + model imports

**Verifies:** tags-qa-95.AC5.1

**Files:**
- Create: `alembic/versions/{hash}_add_workspace_tag_order_counters.py`
- Modify: `alembic/env.py` — add `TagGroup` and `Tag` imports
- Modify: `src/promptgrimoire/db/models.py` — add counter fields to Workspace model

**Implementation:**

**1. Update Workspace model** (`models.py`, after existing fields around line 315):

Add two fields:
```python
next_tag_order: int = Field(default=0)
next_group_order: int = Field(default=0)
```

**2. Add TagGroup and Tag to alembic/env.py imports** (line 21-32):

```python
from promptgrimoire.db.models import (  # noqa: F401
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    CourseRoleRef,
    Permission,
    Tag,         # ADD
    TagGroup,    # ADD
    User,
    Week,
    Workspace,
    WorkspaceDocument,
)
```

**3. Generate and customise Alembic migration:**

Run `uv run alembic revision -m "add workspace tag order counters"` and edit:

```python
def upgrade() -> None:
    # Add counter columns with default 0
    op.add_column("workspace", sa.Column("next_tag_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("workspace", sa.Column("next_group_order", sa.Integer(), nullable=False, server_default="0"))

    # Data migration: populate from existing tag/group counts
    op.execute("""
        UPDATE workspace SET next_tag_order = (
            SELECT count(*) FROM tag WHERE tag.workspace_id = workspace.id
        )
    """)
    op.execute("""
        UPDATE workspace SET next_group_order = (
            SELECT count(*) FROM tag_group WHERE tag_group.workspace_id = workspace.id
        )
    """)

def downgrade() -> None:
    op.drop_column("workspace", "next_group_order")
    op.drop_column("workspace", "next_tag_order")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly. Existing workspaces have correct counter values.

Run: `uv run test-all`
Expected: All tests still pass.

**Commit:** `feat: add next_tag_order/next_group_order counter columns to workspace`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Refactor create_tag and create_tag_group to use atomic counter

**Verifies:** tags-qa-95.AC5.2, tags-qa-95.AC5.3

**Files:**
- Modify: `src/promptgrimoire/db/tags.py` — `create_tag()` (line 168) and `create_tag_group()` (line 43)

**Implementation:**

**Remove `order_index` parameter** from both `create_tag()` and `create_tag_group()`.

**Replace the `SELECT max(order_index)` block** in both functions with an atomic `UPDATE ... RETURNING`:

```python
# In create_tag(), replace lines 209-218 with:
from sqlalchemy import text

result = await session.execute(
    text(
        "UPDATE workspace SET next_tag_order = next_tag_order + 1 "
        "WHERE id = :ws_id RETURNING next_tag_order - 1"
    ),
    {"ws_id": str(workspace_id)},
)
order_index = result.scalar_one()
```

Same pattern for `create_tag_group()` using `next_group_order`.

**Note:** Use `str(workspace_id)` when passing UUID values to `text()` queries — the asyncpg driver may not accept Python `UUID` objects in raw SQL parameter bindings. Alternatively, the implementor may use SQLAlchemy ORM update syntax (`sa.update(Workspace).where(Workspace.id == workspace_id).values(...)`) for consistency with the rest of the codebase, which handles type coercion automatically.

The `UPDATE` takes a row-level lock on the workspace row, serialising concurrent inserts. The `RETURNING next_tag_order - 1` gives the 0-based index to use.

**Also update `import_tags_from_activity()`** — this function does NOT call `create_tag_group()`/`create_tag()`. It uses direct `session.add(TagGroup(..., order_index=...))` and `session.add(Tag(..., order_index=...))` at lines 452-478, bypassing the CRUD functions and therefore bypassing the counter mechanism.

Since `import_tags_from_activity()` uses direct model construction, it must explicitly update the counter columns after all imports. Add at the end of the function, after all tags/groups are added and flushed:

```python
# Update counters to account for imported tags/groups
from sqlalchemy import text

imported_tag_count = len(imported_tags)
imported_group_count = len(group_id_map)
await session.execute(
    text(
        "UPDATE workspace SET "
        "next_tag_order = GREATEST(next_tag_order, :tag_count), "
        "next_group_order = GREATEST(next_group_order, :group_count) "
        "WHERE id = :ws_id"
    ),
    {
        "tag_count": imported_tag_count,
        "group_count": imported_group_count,
        "ws_id": str(target_workspace_id),
    },
)
```

Use `GREATEST(counter, count)` rather than assignment to handle the case where tags already exist on the target workspace before import.

**Also update `_seed_tags_for_activity()`** in `cli.py` — currently uses `session.add()` with explicit `order_index` values. Since seed functions bypass CRUD, they must update counters after bulk insert:

```python
# After all tags/groups are added and flushed:
workspace = await session.get(Workspace, activity.template_workspace_id)
workspace.next_tag_order = total_tag_count
workspace.next_group_order = total_group_count
session.add(workspace)
```

**Testing:**

- AC5.2: Integration test that calls `create_tag()` twice in sequence and verifies distinct `order_index` values
- AC5.3: Integration test that calls `create_tag_group()` twice and verifies distinct indices

**Verification:**

Run: `uv run test-all`
Expected: All existing tests pass with the refactored functions

**Commit:** `feat: use atomic counter for tag/group order_index assignment`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update reorder functions to sync counter

**Verifies:** tags-qa-95.AC5.5

**Files:**
- Modify: `src/promptgrimoire/db/tags.py` — `reorder_tags()` (line 345) and `reorder_tag_groups()` (line 368)

**Implementation:**

After the existing reorder logic (which sets `tag.order_index = idx` for each tag), add counter sync:

```python
# At the end of reorder_tags(), after the flush:
from sqlalchemy import text

await session.execute(
    text(
        "UPDATE workspace SET next_tag_order = :count "
        "WHERE id = :ws_id"
    ),
    {"count": len(tag_ids), "ws_id": str(tags[0].workspace_id)},
)
```

Same for `reorder_tag_groups()` with `next_group_order`.

Note: need to get `workspace_id` from the first tag/group in the list. If the list is empty, no reorder happens and no counter update is needed.

**Testing:**

- AC5.5: Integration test that reorders 3 tags (counter = 3), then creates a 4th, verifying `order_index = 3`

**Verification:**

Run: `uv run test-all`
Expected: All tests pass

**Commit:** `feat: sync counter after tag/group reorder`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Update Phase 1 E2E seed helper for counter columns

**Verifies:** None (infrastructure — ensures E2E tests work after counter columns added)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` (or wherever `_seed_tags_for_workspace()` was placed in Phase 1)

**Implementation:**

After the raw SQL inserts of tags and groups, add an UPDATE to set the counter columns:

```sql
UPDATE workspace
SET next_tag_order = 10, next_group_order = 3
WHERE id = :workspace_id
```

(10 tags, 3 groups in the Legal Case Brief seed set.)

Without this, the first `create_tag()` call on a seeded workspace would claim `order_index = 0`, colliding with seeded data.

**Verification:**

Run: `uv run test-e2e -k test_full_course_setup`
Expected: Instructor creates a tag via quick-create after clone — gets correct order_index (10, not 0)

**Commit:** `fix: update E2E seed helper for counter columns`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Concurrency integration tests

**Verifies:** tags-qa-95.AC5.4

**Files:**
- Modify: `tests/integration/test_tag_crud.py` — add `TestConcurrentTagCreation` class

**Implementation:**

Test that two concurrent `create_tag()` calls produce distinct `order_index` values.

```python
class TestConcurrentTagCreation:
    async def test_concurrent_create_tag_distinct_order(self):
        # Setup: create workspace via _make_course_week_activity()
        # Act: asyncio.gather(create_tag(..., name="A"), create_tag(..., name="B"))
        # Assert: tag_a.order_index != tag_b.order_index
        # Assert: {tag_a.order_index, tag_b.order_index} == {0, 1}

    async def test_concurrent_create_tag_group_distinct_order(self):
        # Same pattern for create_tag_group
```

Use `asyncio.gather()` to run two `create_tag()` calls concurrently. Under the old `SELECT max` pattern, both would get the same max and produce duplicate indices. Under the counter pattern, the `UPDATE` row-level lock serialises them and they get distinct indices.

Also add:

```python
    async def test_counter_correct_after_reorder_then_create(self):
        # Create 3 tags (indices 0, 1, 2)
        # Reorder to [2, 0, 1] (new indices 0, 1, 2)
        # Create a 4th tag
        # Assert 4th tag gets order_index == 3
```

**Testing:**

These tests ARE the verification for AC5.4 and AC5.5.

**Verification:**

Run: `uv run pytest tests/integration/test_tag_crud.py -k TestConcurrentTagCreation -v`
Expected: All concurrent tests pass with distinct order indices

**Commit:** `test: add concurrent tag creation integration tests`
<!-- END_TASK_5 -->
