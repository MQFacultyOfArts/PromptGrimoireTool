# Per-Activity Copy Protection Implementation Plan — Phase 1

**Goal:** Add nullable `copy_protection` to Activity and `default_copy_protection` to Course with Alembic migration. Extend PlacementContext with resolved copy_protection boolean.

**Architecture:** Two new columns (one nullable boolean on Activity, one non-nullable boolean on Course) with an Alembic migration. PlacementContext gains a `copy_protection: bool` field resolved lazily in `_resolve_activity_placement()` — the function already loads the Course object, so reading one additional field is zero extra queries. Loose and course-placed workspaces always resolve to False.

**Tech Stack:** SQLModel, Alembic, PostgreSQL, Python 3.14

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 103-copy-protection.AC1: Activity copy_protection field
- **103-copy-protection.AC1.1 Success:** Activity with `copy_protection=True` stores and retrieves correctly
- **103-copy-protection.AC1.2 Success:** Activity with `copy_protection=False` (explicit override) stores and retrieves correctly
- **103-copy-protection.AC1.3 Success:** Activity with `copy_protection=NULL` (default, inherit from course) stores and retrieves correctly
- **103-copy-protection.AC1.4 Edge:** Existing activities (pre-migration) default to `copy_protection=NULL`

### 103-copy-protection.AC2: PlacementContext resolution
- **103-copy-protection.AC2.1 Success:** Workspace in activity with `copy_protection=True` -> PlacementContext has `copy_protection=True`
- **103-copy-protection.AC2.2 Success:** Workspace in activity with `copy_protection=False` -> PlacementContext has `copy_protection=False`
- **103-copy-protection.AC2.3 Success:** Loose workspace (no activity) -> PlacementContext has `copy_protection=False`
- **103-copy-protection.AC2.4 Success:** Course-placed workspace -> PlacementContext has `copy_protection=False`

### 103-copy-protection.AC3: Nullable fallback inheritance
- **103-copy-protection.AC3.1 Success:** Activity with `copy_protection=NULL` in course with `default_copy_protection=True` -> resolves to True
- **103-copy-protection.AC3.2 Success:** Activity with `copy_protection=NULL` in course with `default_copy_protection=False` -> resolves to False
- **103-copy-protection.AC3.3 Success:** Activity with explicit `copy_protection=True` overrides course default of False
- **103-copy-protection.AC3.4 Success:** Activity with explicit `copy_protection=False` overrides course default of True
- **103-copy-protection.AC3.5 Success:** Changing course default dynamically affects activities with `copy_protection=NULL`
- **103-copy-protection.AC3.6 Success:** Changing course default does NOT affect activities with explicit `copy_protection`
- **103-copy-protection.AC3.7 Edge:** New activities default to `copy_protection=NULL` (inherit from course)

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/docs/testing.md` — Testing methodology
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/integration/test_activity_crud.py` — Activity test patterns
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/integration/test_workspace_placement.py` — PlacementContext test patterns
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/conftest.py` — Fixture definitions (db_session, db_schema_guard)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add model fields and Alembic migration

**Verifies:** None (infrastructure — verified operationally)

**Files:**
- Modify: `src/promptgrimoire/db/models.py:164-200` (Activity class — add `copy_protection` field)
- Modify: `src/promptgrimoire/db/models.py:77-99` (Course class — add `default_copy_protection` field)
- Create: `alembic/versions/XXXX_add_copy_protection_fields.py` (migration)

**Step 1: Add fields to models**

In `src/promptgrimoire/db/models.py`, add to the `Activity` class (after existing fields, before `created_at`):

```python
copy_protection: bool | None = Field(default=None)
"""Tri-state copy protection: None=inherit from course, True=on, False=off."""
```

In `src/promptgrimoire/db/models.py`, add to the `Course` class (after existing fields, before `created_at`):

```python
default_copy_protection: bool = Field(default=False)
"""Course-level default for copy protection. Inherited by activities with copy_protection=NULL."""
```

**Step 2: Generate Alembic migration**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection
uv run alembic revision --autogenerate -m "add copy protection fields"
```

Verify the generated migration contains:
- `op.add_column('activity', sa.Column('copy_protection', sa.Boolean(), nullable=True))`
- `op.add_column('course', sa.Column('default_copy_protection', sa.Boolean(), server_default=sa.text('false'), nullable=False))`

The downgrade should reverse both additions.

**Step 3: Verify migration runs**

Run:
```bash
uv run alembic upgrade head
```

Expected: Migration applies cleanly. Existing activities get `copy_protection=NULL`, existing courses get `default_copy_protection=false`.

**Step 4: Verify tests still pass**

Run:
```bash
uv run test-all
```

Expected: All existing tests pass (new nullable field with default doesn't break anything).

**Step 5: Commit**

```bash
git add src/promptgrimoire/db/models.py alembic/versions/*_add_copy_protection_fields.py
git commit -m "feat: add copy_protection to Activity and default_copy_protection to Course"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Extend PlacementContext with resolved copy_protection

**Verifies:** 103-copy-protection.AC1.1, AC1.2, AC1.3, AC1.4, AC2.1, AC2.2, AC2.3, AC2.4, AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC3.6, AC3.7

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py:28-54` (PlacementContext — add `copy_protection` field)
- Modify: `src/promptgrimoire/db/workspaces.py:95-120` (`_resolve_activity_placement()` — add resolution logic)
- Test: `tests/integration/test_workspace_placement.py` (integration — add copy protection resolution tests)

**Implementation:**

Add to the `PlacementContext` frozen dataclass in `workspaces.py`:

```python
copy_protection: bool = False
"""Resolved copy protection for this workspace. True = protection active."""
```

In `_resolve_activity_placement()`, after fetching the Activity and Course objects, resolve the tri-state:

```python
# Resolve nullable copy_protection: explicit value wins, else fall back to course default
if activity.copy_protection is not None:
    resolved_copy_protection = activity.copy_protection
else:
    resolved_copy_protection = course.default_copy_protection
```

Pass `copy_protection=resolved_copy_protection` when constructing the PlacementContext return value.

No changes needed to `_resolve_course_placement()` or the loose workspace path — both default to `copy_protection=False` via the dataclass default.

**Testing:**

Tests must verify each AC listed above. Follow the patterns in `tests/integration/test_workspace_placement.py`. All tests are integration tests requiring `TEST_DATABASE_URL`. Use the existing skip guard pattern and `db_session` fixture.

Test class: `TestCopyProtectionResolution` in `test_workspace_placement.py`

Tests should verify:
- **AC1.1-AC1.3:** Create activities with `copy_protection=True`, `False`, `None` — verify field round-trips through DB
- **AC1.4:** Activity created without specifying `copy_protection` defaults to `None`
- **AC2.1-AC2.2:** Workspace placed in activity with explicit `copy_protection` — PlacementContext reflects the value
- **AC2.3:** Loose workspace — PlacementContext has `copy_protection=False`
- **AC2.4:** Course-placed workspace — PlacementContext has `copy_protection=False`
- **AC3.1-AC3.2:** Activity with `copy_protection=None` inherits from `Course.default_copy_protection`
- **AC3.3-AC3.4:** Explicit `copy_protection` on activity overrides course default
- **AC3.5:** Update `Course.default_copy_protection`, re-fetch PlacementContext for NULL activity — reflects new value
- **AC3.6:** Update `Course.default_copy_protection`, re-fetch PlacementContext for explicit activity — unchanged
- **AC3.7:** New activity defaults to `copy_protection=None`

**Verification:**

Run:
```bash
uv run pytest tests/integration/test_workspace_placement.py -v
```

Expected: All existing and new tests pass.

**Commit:**

```bash
git add src/promptgrimoire/db/workspaces.py tests/integration/test_workspace_placement.py
git commit -m "feat: resolve copy_protection through Activity -> Course fallback in PlacementContext"
```

**UAT Steps (end of Phase 1):**

1. [ ] Verify migration applied: `uv run alembic current` shows the new migration as head
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Seed data: `uv run seed-data` — completes without error (existing seed path doesn't set copy_protection, so it defaults to NULL)
4. [ ] Verify tests: `uv run test-all` — all pass, including the new `TestCopyProtectionResolution` tests

**Evidence Required:**
- [ ] Test output showing all `TestCopyProtectionResolution` tests green
- [ ] `uv run alembic current` shows latest migration
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
