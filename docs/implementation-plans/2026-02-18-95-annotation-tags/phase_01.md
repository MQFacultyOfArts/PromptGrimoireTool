# Annotation Tag Configuration — Phase 1: Data Model + Migration

**Goal:** Create TagGroup and Tag tables, add tag creation policy columns, extend PlacementContext, seed Legal Case Brief tag set.

**Architecture:** Two new SQLModel classes (TagGroup, Tag) following existing UUID PK + cascade FK patterns. Activity/Course gain allow_tag_creation tri-state columns following the copy_protection pattern. PlacementContext extended with allow_tag_creation resolution. Seed data goes in `seed-data` script (not migration) because tags require workspace_id FK.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC1: Data model and migration
- **95-annotation-tags.AC1.1 Success:** TagGroup table exists with workspace_id FK (CASCADE), name, order_index, created_at
- **95-annotation-tags.AC1.2 Success:** Tag table exists with workspace_id FK (CASCADE), group_id FK (SET NULL), name, description, color, locked, order_index, created_at
- **95-annotation-tags.AC1.3 Success:** Seed data: one "Legal Case Brief" TagGroup and 10 Tags with colorblind-accessible palette exist after migration
- **95-annotation-tags.AC1.4 Success:** Activity has `allow_tag_creation` nullable boolean; Course has `default_allow_tag_creation` boolean (default TRUE)
- **95-annotation-tags.AC1.5 Success:** PlacementContext resolves `allow_tag_creation` via tri-state inheritance (Activity explicit -> Course default)
- **95-annotation-tags.AC1.6 Failure:** Deleting a Workspace CASCADEs to its TagGroup and Tag rows
- **95-annotation-tags.AC1.7 Failure:** Deleting a TagGroup sets `group_id=NULL` on its Tags (SET NULL), does not delete Tags

---

**Note on AC1.3:** The design plan specified seed data in the migration. Since tags require a `workspace_id` FK and no workspaces exist at migration time, seed data goes in the `seed-data` script instead (which creates activities with template workspaces). The migration creates empty tables. AC1.3 is satisfied after running `uv run seed-data`.

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/db/models.py` — all SQLModel classes, FK helpers (`_cascade_fk_column`, `_set_null_fk_column`, `_timestamptz_column`)
- `src/promptgrimoire/db/workspaces.py:105-237` — PlacementContext dataclass and `_resolve_activity_placement()`
- `src/promptgrimoire/db/__init__.py` — model exports and `__all__`
- `alembic/versions/1184bd94f104_add_sharing_columns.py` — current migration head, column addition pattern
- `alembic/versions/7c50e4641d69_add_acl_reference_tables.py` — table creation + seed data pattern
- `src/promptgrimoire/cli.py:835-907` — `_seed_enrolment_and_weeks()` for seed data pattern
- `tests/unit/conftest.py:143-193` — factory fixtures (make_user, make_workspace, make_workspace_document)
- `tests/unit/test_db_schema.py:16-66` — schema registration and expected table count
- `tests/integration/test_activity_crud.py` — integration test pattern (pytestmark skip guard, class-based, async)
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Add TagGroup and Tag SQLModel classes to db/models.py

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

Add two new model classes between the `WorkspaceDocument` class and the `ACLEntry` class in `db/models.py`. Place them after `WorkspaceDocument` and before `ACLEntry`. Follow existing patterns exactly.

`TagGroup` — visual container for grouping tags within a workspace:
- `__tablename__ = "tag_group"`
- `id: UUID` — PK, `Field(default_factory=uuid4, primary_key=True)`
- `workspace_id: UUID` — CASCADE FK using `Field(sa_column=_cascade_fk_column("workspace.id"))`
- `name: str` — `Field(max_length=100)`
- `order_index: int` — `Field(default=0)`
- `created_at: datetime` — `Field(default_factory=_utcnow, sa_column=_timestamptz_column())`

`Tag` — per-workspace annotation tag:
- No custom `__tablename__` (defaults to `"tag"`)
- `id: UUID` — PK
- `workspace_id: UUID` — CASCADE FK to `"workspace.id"`
- `group_id: UUID | None` — SET NULL FK using `Field(default=None, sa_column=_set_null_fk_column("tag_group.id"))`
- `name: str` — `Field(max_length=100)`
- `description: str | None` — `Field(default=None, sa_column=Column(sa.Text(), nullable=True))` (same pattern as WorkspaceDocument.content but nullable)
- `color: str` — `Field(max_length=7)` (hex colour like `"#1f77b4"`)
- `locked: bool` — `Field(default=False)`
- `order_index: int` — `Field(default=0)`
- `created_at: datetime` — `Field(default_factory=_utcnow, sa_column=_timestamptz_column())`

**Verification:**
Run: `uvx ty check`
Expected: No type errors from new model classes

**Commit:** `feat: add TagGroup and Tag SQLModel classes`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add allow_tag_creation to Activity and Course models

**Files:**
- Modify: `src/promptgrimoire/db/models.py`

**Implementation:**

On the `Activity` class, add after the `allow_sharing` field:
- `allow_tag_creation: bool | None = Field(default=None)` with docstring: `"""Tri-state tag creation control. None=inherit from course, True=allowed, False=disallowed."""`

On the `Course` class, add after the `default_allow_sharing` field:
- `default_allow_tag_creation: bool = Field(default=True)` with docstring: `"""Course-level default for tag creation. Inherited by activities with allow_tag_creation=NULL."""`

Note: `default=True` — tag creation is permissive by default (unlike copy_protection and allow_sharing which default False).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add allow_tag_creation tri-state to Activity and Course`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`

**Implementation:**

Add `Tag` and `TagGroup` to the `from promptgrimoire.db.models import (...)` block (line 47-58). Add both to the `__all__` list (line 97-173) in alphabetical order.

**Verification:**
Run: `python -c "from promptgrimoire.db import Tag, TagGroup; print('OK')"`
Expected: `OK`

**Commit:** `chore: export Tag and TagGroup from db module`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create Alembic migration for tag tables and policy columns

**Files:**
- Create: `alembic/versions/XXXX_add_tag_tables_and_policy.py` (use `alembic revision --autogenerate -m "add tag tables and policy"` to generate, then verify and adjust)

**Implementation:**

The migration must:

1. Create `tag_group` table:
   - `id` UUID PK
   - `workspace_id` UUID NOT NULL FK -> workspace.id ON DELETE CASCADE
   - `name` VARCHAR(100) NOT NULL
   - `order_index` INTEGER NOT NULL DEFAULT 0
   - `created_at` TIMESTAMP WITH TIME ZONE NOT NULL

2. Create `tag` table:
   - `id` UUID PK
   - `workspace_id` UUID NOT NULL FK -> workspace.id ON DELETE CASCADE
   - `group_id` UUID FK -> tag_group.id ON DELETE SET NULL (nullable)
   - `name` VARCHAR(100) NOT NULL
   - `description` TEXT (nullable)
   - `color` VARCHAR(7) NOT NULL
   - `locked` BOOLEAN NOT NULL DEFAULT false
   - `order_index` INTEGER NOT NULL DEFAULT 0
   - `created_at` TIMESTAMP WITH TIME ZONE NOT NULL

3. Add `allow_tag_creation` BOOLEAN (nullable) to `activity` table
4. Add `default_allow_tag_creation` BOOLEAN NOT NULL DEFAULT true to `course` table

Down revision: `1184bd94f104`

Use `alembic revision --autogenerate` then review the generated migration. Adjust if autogenerate doesn't capture server_default or FK ondelete correctly. The ondelete CASCADE/SET NULL MUST be explicitly set.

**Verification:**
Run: `alembic upgrade head` (with `DEV__TEST_DATABASE_URL` or `DATABASE__URL` configured)
Expected: Migration applies without errors

Run: `alembic downgrade -1`
Expected: Clean rollback, all four changes removed

Run: `alembic upgrade head` (again, to leave schema at head)

**Commit:** `feat: add tag_group and tag tables with policy columns (migration)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Extend PlacementContext with allow_tag_creation resolution

**Verifies:** 95-annotation-tags.AC1.5

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

1. Add two new fields to `PlacementContext` dataclass (after `allow_sharing`, line ~125):
   - `allow_tag_creation: bool = True` — Default `True` matches the Course default. Add docstring: `"""Resolved tag creation permission. True = students can create tags."""`
   - `course_id: UUID | None = None` — Add docstring: `"""Course UUID for activity-placed workspaces. None for loose/course-only placement."""` Import `UUID` from `uuid` if not already imported at module level.

2. In `_resolve_activity_placement()` (line ~201-222), add resolution block after the `allow_sharing` resolution:
```python
# Resolve tri-state allow_tag_creation: explicit wins, else course default
if activity.allow_tag_creation is not None:
    resolved_tag_creation = activity.allow_tag_creation
else:
    resolved_tag_creation = course.default_allow_tag_creation
```

3. Add `allow_tag_creation=resolved_tag_creation` and `course_id=course.id` to the `PlacementContext(...)` constructor call (line ~213-222).

**Testing:**
Tests must verify AC1.5:
- 95-annotation-tags.AC1.5: Integration test in `tests/integration/test_tag_schema.py`. Create a course with `default_allow_tag_creation=True`, an activity with `allow_tag_creation=None`, clone a workspace, call `get_placement_context()` and assert `allow_tag_creation is True`. Repeat with activity `allow_tag_creation=False` overriding course `True` — context should resolve to `False`. Repeat with course default `False`, activity `True` — should resolve to `True`.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat: resolve allow_tag_creation in PlacementContext`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Unit tests for new models and schema registration update

**Verifies:** 95-annotation-tags.AC1.1, 95-annotation-tags.AC1.2, 95-annotation-tags.AC1.4

**Files:**
- Modify: `tests/unit/conftest.py` — add `make_tag_group` and `make_tag` factory fixtures
- Create: `tests/unit/test_tag_models.py` — unit tests for TagGroup and Tag
- Modify: `tests/unit/test_db_schema.py` — update expected tables from 10 to 12

**Implementation:**

Add two factory fixtures to `tests/unit/conftest.py` following the `make_workspace_document` pattern:
- `make_tag_group(workspace_id=None, name="Test Group", order_index=0, **kwargs)` — creates `TagGroup` instance (not persisted)
- `make_tag(workspace_id=None, name="Test Tag", color="#1f77b4", order_index=0, **kwargs)` — creates `Tag` instance (not persisted)

Update `tests/unit/test_db_schema.py`:
- Add `"tag_group"` and `"tag"` to the `expected_tables` set (line 26-37)
- Update `test_get_expected_tables_returns_all_tables` assertion from `len(tables) == 10` to `len(tables) == 12`
- Add `assert "tag_group" in tables` and `assert "tag" in tables`

**Testing:**
Unit tests for new models (in `tests/unit/test_tag_models.py`):
- AC1.1: TagGroup has default UUID, name, order_index defaults to 0, has created_at
- AC1.2: Tag has default UUID, workspace_id, group_id nullable (defaults None), name, description nullable, color required, locked defaults False, order_index defaults 0, has created_at
- AC1.4: Activity.allow_tag_creation defaults to None; Course.default_allow_tag_creation defaults to True

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass including new model tests and updated schema test

**Commit:** `test: add unit tests for TagGroup, Tag models and schema registration`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 7-8) -->
<!-- START_TASK_7 -->
### Task 7: Integration tests for cascade, set-null, and PlacementContext

**Verifies:** 95-annotation-tags.AC1.5, 95-annotation-tags.AC1.6, 95-annotation-tags.AC1.7

**Files:**
- Create: `tests/integration/test_tag_schema.py`

**Implementation:**

Follow the pattern from `tests/integration/test_activity_crud.py`:
- Module-level `pytestmark = pytest.mark.skipif(not get_settings().dev.test_database_url, reason="DEV__TEST_DATABASE_URL not configured")`
- Class-based grouping, `@pytest.mark.asyncio async def` methods
- UUID isolation for all created entities
- Call service layer functions directly (e.g., `create_workspace()`)
- For low-level FK constraint tests, use `get_session()` directly to create/delete rows and verify cascades

**Testing:**

`TestTagCascadeOnWorkspaceDelete`:
- AC1.6: Create a workspace, add a TagGroup and Tag to it (via direct session insert). Delete the workspace. Verify TagGroup and Tag rows are gone.

`TestTagGroupSetNullOnDelete`:
- AC1.7: Create a workspace with a TagGroup and a Tag in that group. Delete the TagGroup. Verify the Tag still exists with `group_id=None`.

`TestPlacementContextTagCreation`:
- AC1.5 (inherit): Create course with `default_allow_tag_creation=True`, activity with `allow_tag_creation=None`. Create workspace placed in activity. `get_placement_context()` returns `allow_tag_creation=True`. Also assert `ctx.course_id == course.id`.
- AC1.5 (override False): Same course, activity with `allow_tag_creation=False`. Context returns `allow_tag_creation=False`. Also assert `ctx.course_id == course.id`.
- AC1.5 (override True): Course with `default_allow_tag_creation=False`, activity with `allow_tag_creation=True`. Context returns `allow_tag_creation=True`. Also assert `ctx.course_id == course.id`.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `test: add integration tests for tag cascade, set-null, and PlacementContext`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Update seed-data script to seed Legal Case Brief tags

**Verifies:** 95-annotation-tags.AC1.3

**Files:**
- Modify: `src/promptgrimoire/cli.py`

**Implementation:**

Add a `_seed_tags_for_activity(activity)` async helper function. Call it from `_seed_enrolment_and_weeks()` after the activity is created (after line 903).

The function:
1. Query existing TagGroups for the activity's template workspace. If any exist, print `[yellow]Tags exist:[/]` and return (idempotent).
2. Create one TagGroup: `name="Legal Case Brief"`, `workspace_id=activity.template_workspace_id`, `order_index=0`
3. Create 10 Tags with the colorblind-accessible palette (Matplotlib tab10), all in that group:

| order_index | name | color |
|---|---|---|
| 0 | Jurisdiction | #1f77b4 |
| 1 | Procedural History | #ff7f0e |
| 2 | Legally Relevant Facts | #2ca02c |
| 3 | Legal Issues | #d62728 |
| 4 | Reasons | #9467bd |
| 5 | Court's Reasoning | #8c564b |
| 6 | Decision | #e377c2 |
| 7 | Order | #7f7f7f |
| 8 | Domestic Sources | #bcbd22 |
| 9 | Reflection | #17becf |

All tags: `locked=True` (instructor-provided tags students shouldn't modify), `workspace_id=activity.template_workspace_id`, `group_id=<the new TagGroup's id>`.

Use `get_session()` to create all rows in one transaction. Import `TagGroup` and `Tag` from `promptgrimoire.db.models`.

**Verification:**
Run: `uv run seed-data`
Expected: Tags seeded message appears. Subsequent runs show "Tags exist" (idempotent).

**Commit:** `feat: seed Legal Case Brief tags in seed-data script`
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_C -->
