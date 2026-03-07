# Wargame Schema Implementation Plan

**Goal:** Land and verify the `Activity` discriminator seam so annotation activities keep working unchanged while wargame activities can exist without template workspaces.

**Architecture:** Keep `Activity` as the shared parent row, enforce subtype-specific invariants in PostgreSQL with `CHECK` constraints, and mirror those invariants at the SQLModel layer with a model validator. On this branch, Phase 1 work must be expressed by tightening the existing combined Alembic revision rather than assuming an empty baseline.

**Tech Stack:** Python 3.14, SQLModel, SQLAlchemy, Alembic, PostgreSQL, pytest via `uv run grimoire` harness

**Scope:** 5 phases from original design (phase 1 of 5)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### wargame-schema-294.AC1: Activity type discriminator
- **wargame-schema-294.AC1.1 Success:** Existing annotation activities automatically have `type='annotation'` after migration
- **wargame-schema-294.AC1.2 Success:** New activity with `type='wargame'` and no `template_workspace_id` is accepted
- **wargame-schema-294.AC1.3 Success:** New activity with `type='annotation'` and a `template_workspace_id` is accepted
- **wargame-schema-294.AC1.4 Failure:** Activity with `type='annotation'` and NULL `template_workspace_id` is rejected by CHECK
- **wargame-schema-294.AC1.5 Failure:** Activity with `type='wargame'` and a non-NULL `template_workspace_id` is rejected by CHECK

### wargame-schema-294.AC8: Existing tests
- **wargame-schema-294.AC8.1 Success:** All existing unit and integration tests pass without modification (except where Activity's template_workspace_id nullability requires model-level validation updates)

---

<!-- START_TASK_1 -->
### Task 1: Audit and tighten the existing discriminator migration

**Verifies:** wargame-schema-294.AC1.1, wargame-schema-294.AC1.4, wargame-schema-294.AC1.5

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:22-204`

**Implementation:**

Treat [1b59ab790954_add_wargame_schema.py](/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/alembic/versions/1b59ab790954_add_wargame_schema.py) as the authoritative migration for this branch. Do not create a second migration for Phase 1 unless you intentionally rewrite migration history for the whole branch.

In the `activity` section of `upgrade()`:

1. Keep the `type` column definition as:
   - `VARCHAR(50)`
   - `NOT NULL`
   - server default `'annotation'`
2. Keep `template_workspace_id` nullable at the database level.
3. Keep both explicit `CHECK` constraints:
   - `ck_activity_annotation_requires_template`
   - `ck_activity_wargame_no_template`
4. Add or retain a short migration comment explaining why the default stays on the column:
   - legacy rows need to upgrade to `annotation` without a data backfill statement
   - annotation creation paths should remain valid during the schema-only seam

In `downgrade()`:

1. Confirm the downgrade order is safe:
   - drop Phase 5/4/3/2 objects first
   - delete `activity` rows where `type = 'wargame'`
   - then restore `activity.template_workspace_id` to `NOT NULL`
   - then drop `activity.type`
2. Keep the destructive downgrade note explicit. This downgrade is only valid because wargame rows cannot satisfy the legacy schema.

**Notes:**

- AC1.1 is about pre-existing rows. The migration must preserve that contract directly, not only through model defaults.
- Because the branch already combines all phases into one revision, this task is primarily an audit-and-tighten task, not greenfield migration authoring.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- `tests/integration/test_wargame_schema.py` passes
- no discriminator constraint regressions

Run:
```bash
uv run ruff check alembic/versions/1b59ab790954_add_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Make annotation creation semantics explicit in application code

**Verifies:** wargame-schema-294.AC1.3

**Files:**
- Modify: `src/promptgrimoire/db/activities.py:24-78`
- Review only: `src/promptgrimoire/db/models.py:258-349`

**Implementation:**

Update `create_activity()` in [activities.py](/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/src/promptgrimoire/db/activities.py) so the created row explicitly sets:

```python
type="annotation"
```

when constructing `Activity(...)`.

Keep the existing template-workspace-first transaction pattern unchanged. Phase 1 is not the place to introduce a generic polymorphic activity factory.

In [models.py](/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/src/promptgrimoire/db/models.py):

1. Keep the `Activity` model validator enforcing:
   - annotation requires `template_workspace_id`
   - wargame forbids `template_workspace_id`
2. Keep `template_workspace_id` as a nullable DB column.
3. Keep the current Python annotation as `UUID` with `default=None` for this issue unless `ty check` proves the wider codebase can absorb `UUID | None` without unrelated churn.
4. Add a brief comment or docstring note if needed to make the compatibility shim explicit for future cleanup.

**Rationale:**

- The database already enforces the invariant.
- The explicit `type="annotation"` assignment makes the annotation code path robust against future default changes.
- Changing the Python type to `UUID | None` now would ripple into many annotation-era callers that are out of scope for this schema seam.

**Verification:**

Run:
```bash
uv run grimoire test all -k "wargame_schema or activity_crud"
```

Expected:
- existing annotation creation path still passes
- discriminator integration coverage still passes

Run:
```bash
uvx ty check
```

Expected:
- clean pass without forcing broad nullable-type fallout
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Fill the missing legacy-row migration proof and keep model-level tests focused

**Verifies:** wargame-schema-294.AC1.1, wargame-schema-294.AC1.2, wargame-schema-294.AC1.4, wargame-schema-294.AC1.5, wargame-schema-294.AC8.1

**Files:**
- Modify: `tests/integration/test_wargame_schema.py:55-112`
- Review only: `tests/unit/test_wargame_models.py:19-48`
- Review only: `tests/integration/test_activity_crud.py:36-121` and `tests/integration/test_activity_crud.py:362-419`

**Implementation:**

Keep discriminator-specific coverage concentrated in [test_wargame_schema.py](/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/tests/integration/test_wargame_schema.py) and [test_wargame_models.py](/home/brian/people/Brian/PromptGrimoireTool/.worktrees/wargame-schema-294/tests/unit/test_wargame_models.py).

Add one explicit integration test for AC1.1 proving the migration contract for legacy rows. The test should verify one of these paths:

1. Preferred if project fixtures already support migration stepping:
   - create an annotation `activity` row under the pre-phase schema
   - apply revision `1b59ab790954`
   - assert the row now has `type='annotation'`
2. If migration stepping is not already available in the test harness:
   - add a constrained schema-level test that inserts an annotation activity without specifying `type`
   - assert the persisted row reads back as `annotation`
   - document in the test docstring that this is the branch-local proxy for legacy upgrade behaviour because the migration uses a server default

Keep the existing tests that already cover:

- new wargame activity accepts `NULL template_workspace_id`
- annotation row without template fails
- wargame row with template fails

Do not rewrite broad annotation CRUD suites just to duplicate this coverage.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- discriminator integration tests pass
- AC1.1 proof is now present in the suite

Run:
```bash
uv run grimoire test changed
```

Expected:
- either the changed-suite passes
- or the harness reports no changed tests collected

Run:
```bash
uv run ruff check tests/integration/test_wargame_schema.py tests/unit/test_wargame_models.py
```

Expected: clean pass.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 1 completion sweep

**Verifies:** wargame-schema-294.AC1.1 through wargame-schema-294.AC1.5, wargame-schema-294.AC8.1

**Files:**
- Review: `src/promptgrimoire/db/models.py:258-349`
- Review: `src/promptgrimoire/db/activities.py:24-78`
- Review: `alembic/versions/1b59ab790954_add_wargame_schema.py:22-204`
- Review: `tests/integration/test_wargame_schema.py:55-112`
- Review: `tests/unit/test_wargame_models.py:19-48`

**Checklist:**

1. Confirm `Activity` accepts both discriminator values used in this issue:
   - `annotation`
   - `wargame`
2. Confirm annotation creation still always produces:
   - `type='annotation'`
   - non-null `template_workspace_id`
3. Confirm no existing annotation tests had to be rewritten to accommodate wargame rows.
4. Confirm all verification commands below pass before declaring the phase done.

**Verification:**

Run:
```bash
uv run grimoire test all -k "wargame_schema or activity_crud"
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
- Phase 1 leaves the codebase in a state where later phases can build on the discriminator seam without breaking annotation behavior
<!-- END_TASK_4 -->
