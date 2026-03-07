# Wargame Schema Implementation Plan

**Goal:** Extend `ACLEntry` so it can target either workspaces or wargame teams while preserving workspace ACL behavior and preventing NULL-related query regressions.

**Architecture:** `ACLEntry` remains a single polymorphic grant table with two nullable target FKs, guarded by an exactly-one-target `CHECK` constraint. Uniqueness is preserved with two partial unique indexes: one for workspace targets and one for team targets. Workspace-oriented query paths must explicitly exclude team-target rows where required.

**Tech Stack:** Python 3.14, SQLModel, SQLAlchemy, Alembic, PostgreSQL, pytest via `uv run grimoire` harness

**Scope:** 5 phases from original design (phase 5 of 5)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### wargame-schema-294.AC5: ACLEntry extension
- **wargame-schema-294.AC5.1 Success:** ACL grant with workspace_id set and team_id NULL (existing behaviour)
- **wargame-schema-294.AC5.2 Success:** ACL grant with team_id set and workspace_id NULL (new team grant)
- **wargame-schema-294.AC5.3 Failure:** ACL grant with both workspace_id and team_id set rejected by CHECK
- **wargame-schema-294.AC5.4 Failure:** ACL grant with both NULL rejected by CHECK
- **wargame-schema-294.AC5.5 Success:** Existing workspace ACL grants remain valid after migration

### wargame-schema-294.AC6: Migration integrity
- **wargame-schema-294.AC6.2 Success:** Migration downgrades cleanly

Additional operational contract for this branch:
- workspace-oriented ACL queries must not be contaminated by team-target rows with `workspace_id NULL`

---

<!-- START_TASK_1 -->
### Task 1: Keep the polymorphic ACL table shape and partial unique indexes

**Verifies:** wargame-schema-294.AC5.1 through wargame-schema-294.AC5.5

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:129-180`
- Modify: `src/promptgrimoire/db/models.py:641-692`

**Implementation:**

Preserve the Phase 5 table shape in both Alembic and SQLModel:

1. `workspace_id` becomes nullable.
2. `team_id` is added as a nullable FK to `wargame_team.id`.
3. Add the exactly-one-target constraint:

```sql
CONSTRAINT ck_acl_entry_exactly_one_target
  CHECK (num_nonnulls(workspace_id, team_id) = 1)
```

4. Replace the old single unique constraint with two partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_acl_entry_workspace_user
  ON acl_entry (workspace_id, user_id)
  WHERE workspace_id IS NOT NULL;

CREATE UNIQUE INDEX uq_acl_entry_team_user
  ON acl_entry (team_id, user_id)
  WHERE team_id IS NOT NULL;
```

In `src/promptgrimoire/db/models.py`:

1. Keep `workspace_id: UUID | None`.
2. Keep `team_id: UUID | None`.
3. Keep the model validator requiring exactly one target.

Do not collapse this back into one composite unique index and do not rely on application code alone to enforce target exclusivity.

**Why this is correct:**

- PostgreSQL unique constraints do not treat NULLs the way we need for a two-target polymorphic table.
- Partial unique indexes preserve the original workspace uniqueness rule and add the new team uniqueness rule without allowing duplicates through NULL combinations.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- both uniqueness paths and exactly-one-target failures pass

Run:
```bash
uv run ruff check src/promptgrimoire/db/models.py alembic/versions/1b59ab790954_add_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Audit workspace-oriented ACL queries for NULL-safe behavior

**Verifies:** wargame-schema-294.AC5.5 and branch-specific query correctness

**Files:**
- Modify: `src/promptgrimoire/db/acl.py:37-143`, `src/promptgrimoire/db/acl.py:196-447`, `src/promptgrimoire/db/acl.py:499-605`
- Review: any callers of workspace ACL helpers if signatures change

**Implementation:**

Treat query audit as a first-class deliverable of Phase 5. Once `workspace_id` becomes nullable, any ACL query that semantically means “workspace ACL rows” must be checked.

Audit each function in `src/promptgrimoire/db/acl.py` and ensure one of these is true:

1. It joins `ACLEntry.workspace_id == Workspace.id`, which naturally excludes team-target rows.
2. It explicitly filters `ACLEntry.workspace_id IS NOT NULL`.
3. It intentionally returns mixed resource targets and documents that behavior.

At minimum review and preserve correct behavior for:

- `grant_permission()`
- `grant_share()`
- `revoke_permission()`
- `list_entries_for_workspace()`
- `list_entries_for_user()`
- `list_accessible_workspaces()`
- `list_activity_workspaces()`
- `resolve_permission()`
- `list_peer_workspaces()`
- `list_peer_workspaces_with_owners()`

Specific expectations:

1. Workspace upsert logic must keep:

```python
index_where=sa.text("workspace_id IS NOT NULL")
```

2. Subqueries selecting owned workspaces must filter out team-target rows:

```python
ACLEntry.workspace_id != None
```

or the SQLAlchemy equivalent.

3. Workspace-target ACL creation paths must stay explicit about target type:

```python
team_id=None
```

Keep that explicit in both `grant_permission()` and `grant_share()` when they construct workspace-target ACL rows or insert values.

4. Add short comments where NULL-safety is non-obvious, especially around:
   - `workspace_id IS NOT NULL` partial-index upserts
   - `workspace_id != None` subqueries used with `NOT IN`

The comment should explain that `num_nonnulls(workspace_id, team_id) = 1` allows team-target rows with `workspace_id NULL`, so workspace-only queries must guard against NULL poisoning explicitly.

5. Functions intentionally returning mixed targets, such as `list_entries_for_user()`, should continue to do so and have tests proving the mixed result shape.

**Why this matters:**

- The main realistic regression in Phase 5 is not the table DDL; it is a workspace query accidentally seeing team-target rows with `workspace_id NULL`.
- The `NOT IN (subquery)` pattern is especially sensitive to NULL contamination.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- peer-listing and mixed-target ACL tests pass
- no NULL-poisoning regression
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Keep focused ACL extension tests and add any missing regressions

**Verifies:** wargame-schema-294.AC5.1 through wargame-schema-294.AC5.5

**Files:**
- Modify: `tests/integration/test_wargame_schema.py:335-646`
- Review or modify: `tests/integration/test_sharing_controls.py:79-220`
- Optionally modify: `tests/unit/test_wargame_models.py:112-163`

**Implementation:**

Keep the dedicated ACL extension coverage in `tests/integration/test_wargame_schema.py` rather than scattering it across unrelated workspace test files.

Ensure the suite covers:

1. Workspace-target ACL row still valid.
2. Team-target ACL row valid.
3. Both targets set fails.
4. Neither target set fails.
5. Workspace-target uniqueness preserved.
6. Team-target uniqueness enforced.
7. Team delete cascades to team-target ACL rows.
8. `list_entries_for_user()` returns both workspace-target and team-target rows.
9. Workspace peer-listing subqueries ignore team-target rows with `workspace_id NULL`.
10. Existing workspace sharing via `grant_share()` still creates workspace-target ACL rows with `team_id is None` and still upserts correctly.

If any of those are already present, keep them and avoid duplication. Add only what is missing.

Optional unit coverage:

- If the model validator is changed, keep one small unit test proving exactly-one-target validation at the model layer.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- all ACL extension tests pass

Run:
```bash
uv run ruff check tests/integration/test_wargame_schema.py tests/unit/test_wargame_models.py
```

Expected: clean pass.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Preserve honest downgrade semantics

**Verifies:** wargame-schema-294.AC6.2

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:161-180`

**Implementation:**

Keep the downgrade explicit about destructive rollback behavior.

Before restoring legacy `workspace_id NOT NULL` semantics:

1. drop the team unique index
2. drop the workspace partial unique index
3. drop the exactly-one-target check
4. delete team-target ACL rows:

```sql
DELETE FROM acl_entry WHERE workspace_id IS NULL
```

5. drop the `team_id` FK and column
6. restore `workspace_id NOT NULL`
7. recreate the legacy uniqueness constraint

Add or keep a short comment in the migration explaining that downgrade necessarily deletes team-target ACL rows because those rows cannot be represented in the pre-Phase-5 schema.

**Why this is acceptable:**

- It is better to declare a destructive but correct downgrade than to pretend rollback is lossless when the old schema cannot represent the new data.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- upgrade/downgrade-related tests continue to pass if present
- migration logic remains internally coherent
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Phase 5 completion sweep

**Verifies:** wargame-schema-294.AC5.1 through wargame-schema-294.AC5.5 and query-audit completion

**Files:**
- Review: `src/promptgrimoire/db/models.py:641-692`
- Review: `src/promptgrimoire/db/acl.py:37-143`, `src/promptgrimoire/db/acl.py:196-359`, `src/promptgrimoire/db/acl.py:499-605`
- Review: `src/promptgrimoire/db/acl.py:362-447`
- Review: `alembic/versions/1b59ab790954_add_wargame_schema.py:129-180`
- Review: `tests/integration/test_wargame_schema.py:335-646`
- Review: `tests/integration/test_sharing_controls.py:79-220`

**Checklist:**

1. Confirm ACL rows target exactly one resource.
2. Confirm workspace-target uniqueness still behaves exactly as before.
3. Confirm team-target uniqueness behaves analogously.
4. Confirm `grant_share()` still produces workspace-target ACL rows and explicit `team_id=None` assignments where new rows are constructed.
5. Confirm workspace ACL queries are NULL-safe in the presence of team-target rows and that the code comments explain why the guards exist.
6. Confirm downgrade comments make the destructive rollback behavior explicit.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Run:
```bash
uv run ruff check .
```

Run:
```bash
uv run ruff format .
```

Run:
```bash
uvx ty check
```

Expected:
- all commands pass
- ACL polymorphism works without breaking existing workspace permission behavior
<!-- END_TASK_5 -->
