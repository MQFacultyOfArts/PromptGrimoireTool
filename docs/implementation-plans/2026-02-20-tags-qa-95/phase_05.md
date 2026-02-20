# Annotation Tags QA Pass — Phase 5: CHECK Constraint + Integration Test Gaps

**Goal:** Add `ck_tag_group_color_hex` CHECK constraint on `tag_group.color` and fill 7 integration test coverage gaps.

**Architecture:** One Alembic migration for the CHECK constraint with data assertion guard. New integration tests added to existing test classes in `test_tag_crud.py` and `test_tag_schema.py` following the project's class-per-function organisation pattern.

**Tech Stack:** PostgreSQL (CHECK constraint), Alembic, pytest, SQLModel

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC6: Integration test gaps filled
- **tags-qa-95.AC6.1 Success:** `tag_group.color` CHECK constraint rejects invalid hex
- **tags-qa-95.AC6.2 Success:** `tag_group.color` CHECK constraint allows NULL
- **tags-qa-95.AC6.3 Success:** `update_tag` with `bypass_lock=True` succeeds on locked tag
- **tags-qa-95.AC6.4 Success:** `delete_tag` with `bypass_lock=True` succeeds on locked tag
- **tags-qa-95.AC6.5 Success:** `delete_tag` with nonexistent UUID returns False
- **tags-qa-95.AC6.6 Failure:** `import_tags_from_activity` with nonexistent activity raises ValueError
- **tags-qa-95.AC6.7 Success:** `update_tag_group(color=None)` clears group colour
- **tags-qa-95.AC6.8 Success:** `update_tag_group` without `color` preserves existing colour
- **tags-qa-95.AC6.9 Failure:** `reorder_tags` with unknown tag UUID raises ValueError
- **tags-qa-95.AC6.10 Failure:** `reorder_tag_groups` with unknown group UUID raises ValueError

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run alembic upgrade head` — CHECK constraint migration applies cleanly
2. Run `uv run test-all` — all integration tests pass, including new bypass_lock, delete nonexistent, import ValueError, color sentinel, and reorder ValueError tests
3. Verify CHECK constraint at DB level: `INSERT INTO tag_group (id, workspace_id, name, color, order_index) VALUES (gen_random_uuid(), (SELECT id FROM workspace LIMIT 1), 'test', 'red', 99)` — should fail with CHECK violation
4. Verify NULL colour is accepted: `INSERT INTO tag_group (id, workspace_id, name, color, order_index) VALUES (gen_random_uuid(), (SELECT id FROM workspace LIMIT 1), 'test2', NULL, 99)` — should succeed

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Alembic migration — CHECK constraint on tag_group.color

**Verifies:** tags-qa-95.AC6.1, tags-qa-95.AC6.2

**Files:**
- Create: `alembic/versions/{hash}_add_tag_group_color_check.py`
- Modify: `src/promptgrimoire/db/models.py` — add `CheckConstraint` to `TagGroup.__table_args__`

**Implementation:**

**1. Update TagGroup model** (`models.py`, lines 391-393):

```python
__table_args__ = (
    UniqueConstraint("workspace_id", "name", name="uq_tag_group_workspace_name"),
    CheckConstraint(
        "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
        name="ck_tag_group_color_hex",
    ),
)
```

Note: TagGroup.color is nullable (unlike Tag.color), so the constraint includes `color IS NULL OR ...`.

**2. Generate Alembic migration:**

Run `uv run alembic revision -m "add tag group color check"` and edit:

```python
def upgrade() -> None:
    # Assert no existing invalid data
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT count(*) FROM tag_group "
        "WHERE color IS NOT NULL AND color !~ '^#[0-9a-fA-F]{6}$'"
    ))
    bad_count = result.scalar()
    if bad_count:
        raise RuntimeError(
            f"Cannot add CHECK constraint: {bad_count} tag_group rows "
            f"have invalid color values. Fix data first."
        )

    op.create_check_constraint(
        "ck_tag_group_color_hex",
        "tag_group",
        "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
    )

def downgrade() -> None:
    op.drop_constraint("ck_tag_group_color_hex", "tag_group", type_="check")
```

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly (no existing invalid data)

Run: `uv run test-all`
Expected: All tests pass

**Commit:** `feat: add ck_tag_group_color_hex CHECK constraint`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: CHECK constraint schema test

**Verifies:** tags-qa-95.AC6.1, tags-qa-95.AC6.2

**Files:**
- Modify: `tests/integration/test_tag_schema.py` — add `TestTagGroupColorConstraint` class

**Implementation:**

Add a new test class verifying the CHECK constraint at the DB level:

```python
class TestTagGroupColorConstraint:
    async def test_invalid_hex_rejected(self):
        # Create workspace, then attempt to create tag_group with color="red"
        # Assert IntegrityError (CHECK violation)

    async def test_null_color_allowed(self):
        # Create tag_group with color=None
        # Assert created successfully

    async def test_valid_hex_accepted(self):
        # Create tag_group with color="#FF0000"
        # Assert created successfully
```

Follow existing test patterns: use `_make_course_week_activity()` helper for workspace setup. Use `create_tag_group()` CRUD function. For the invalid hex test, catch `IntegrityError` from SQLAlchemy.

**Testing:**

The tests themselves ARE the verification for AC6.1 and AC6.2.

**Verification:**

Run: `uv run pytest tests/integration/test_tag_schema.py -k TestTagGroupColorConstraint -v`
Expected: All 3 tests pass

**Commit:** `test: add tag_group color CHECK constraint tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: bypass_lock integration tests

**Verifies:** tags-qa-95.AC6.3, tags-qa-95.AC6.4

**Files:**
- Modify: `tests/integration/test_tag_crud.py` — add tests to `TestLockEnforcement`

**Implementation:**

Add to `TestLockEnforcement` class:

```python
async def test_update_locked_tag_with_bypass_lock(self):
    # Create locked tag
    # Call update_tag(tag.id, name="New Name", bypass_lock=True)
    # Assert returns updated tag with new name (not None, not error)

async def test_delete_locked_tag_with_bypass_lock(self):
    # Create locked tag
    # Call delete_tag(tag.id, bypass_lock=True)
    # Assert returns True (deleted successfully)
    # Verify tag no longer exists via get_tag()
```

**Testing:**

The tests themselves verify AC6.3 and AC6.4.

**Verification:**

Run: `uv run pytest tests/integration/test_tag_crud.py -k TestLockEnforcement -v`
Expected: All 6 tests pass (4 existing + 2 new)

**Commit:** `test: add bypass_lock integration tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: delete_tag nonexistent, import ValueError, color sentinel tests

**Verifies:** tags-qa-95.AC6.5, tags-qa-95.AC6.6, tags-qa-95.AC6.7, tags-qa-95.AC6.8

**Files:**
- Modify: `tests/integration/test_tag_crud.py` — add tests to existing classes

**Implementation:**

**delete_tag nonexistent** — add to new `TestDeleteTag` class (or existing class if suitable):

```python
class TestDeleteTag:
    async def test_delete_nonexistent_returns_false(self):
        # Call delete_tag(uuid4()) with a UUID that doesn't exist
        # Assert returns False
```

**import ValueError** — add to `TestImportTagsFromActivity`:

```python
async def test_import_nonexistent_activity_raises_value_error(self):
    # Create workspace (target)
    # Call import_tags_from_activity(uuid4(), workspace_id)
    # Assert raises ValueError with "not found" in message
```

**color sentinel** — add to `TestUpdateTagGroup`:

```python
async def test_update_color_to_none_clears(self):
    # Create tag_group with color="#FF0000"
    # Call update_tag_group(group.id, color=None)
    # Reload from DB, assert color is None

async def test_update_without_color_preserves(self):
    # Create tag_group with color="#FF0000"
    # Call update_tag_group(group.id, name="New Name")  # color not passed
    # Reload from DB, assert color is still "#FF0000"
```

**Testing:**

The tests themselves verify AC6.5-AC6.8.

**Verification:**

Run: `uv run pytest tests/integration/test_tag_crud.py -k "TestDeleteTag or TestImportTagsFromActivity or TestUpdateTagGroup" -v`
Expected: All new + existing tests pass

**Commit:** `test: fill integration test gaps (delete, import, color sentinel)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: reorder ValueError tests

**Verifies:** tags-qa-95.AC6.9, tags-qa-95.AC6.10

**Files:**
- Modify: `tests/integration/test_tag_crud.py` — add tests to `TestReorderTags` and `TestReorderTagGroups`

**Implementation:**

**reorder_tags ValueError** — add to `TestReorderTags`:

```python
async def test_reorder_with_unknown_tag_raises_value_error(self):
    # Create 2 tags
    # Call reorder_tags([tag1.id, uuid4()])  # second ID doesn't exist
    # Assert raises ValueError with "Tag" and "not found" in message
```

**reorder_tag_groups ValueError** — add to `TestReorderTagGroups`:

```python
async def test_reorder_with_unknown_group_raises_value_error(self):
    # Create 2 groups
    # Call reorder_tag_groups([group1.id, uuid4()])
    # Assert raises ValueError with "TagGroup" and "not found" in message
```

**Testing:**

The tests themselves verify AC6.9 and AC6.10.

**Verification:**

Run: `uv run pytest tests/integration/test_tag_crud.py -k "TestReorderTags or TestReorderTagGroups" -v`
Expected: All 4 tests pass (2 existing + 2 new)

**Commit:** `test: add reorder ValueError integration tests`
<!-- END_TASK_5 -->
