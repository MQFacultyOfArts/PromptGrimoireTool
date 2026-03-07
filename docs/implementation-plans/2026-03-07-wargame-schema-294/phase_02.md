# Wargame Schema Implementation Plan

**Goal:** Create a `WargameConfig` extension table that is usable only for `Activity(type='wargame')` rows and that enforces exactly one timer mode.

**Architecture:** Use a PK-as-FK extension table with a discriminator-enforcing composite foreign key. The child row stores a constant `activity_type='wargame'`, checks that constant locally, and references `activity(id, type)` so the database rejects config rows attached to annotation activities.

**Tech Stack:** Python 3.14, SQLModel, SQLAlchemy, Alembic, PostgreSQL, pytest via `uv run grimoire` harness

**Scope:** 5 phases from original design (phase 2 of 5)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### wargame-schema-294.AC2: WargameConfig
- **wargame-schema-294.AC2.1 Success:** WargameConfig with `timer_delta` set and `timer_wall_clock` NULL is accepted
- **wargame-schema-294.AC2.2 Success:** WargameConfig with `timer_wall_clock` set and `timer_delta` NULL is accepted
- **wargame-schema-294.AC2.3 Failure:** WargameConfig with both timer fields NULL is rejected by CHECK
- **wargame-schema-294.AC2.4 Failure:** WargameConfig with both timer fields set is rejected by CHECK

Additional invariant for this branch:
- `WargameConfig` may only reference `Activity(type='wargame')`

---

<!-- START_TASK_1 -->
### Task 1: Strengthen the parent activity key shape for subtype-enforcing child FKs

**Verifies:** wargame-schema-294.AC2.1 through wargame-schema-294.AC2.4

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:24-65`
- Modify: `src/promptgrimoire/db/models.py:258-392`

**Implementation:**

The current branch already references `activity.id` directly from wargame child tables. Replace that with a composite parent key shape that supports discriminator enforcement.

In the `Activity` table definition:

1. Add a table-level unique constraint on `(id, type)`:

```sql
ALTER TABLE activity
  ADD CONSTRAINT uq_activity_id_type UNIQUE (id, type);
```

2. Mirror that constraint in the SQLModel metadata for `Activity` so ORM metadata and Alembic intent stay aligned.

In `src/promptgrimoire/db/models.py`, add the constraint to `Activity.__table_args__` alongside any existing table arguments for that model.

**Why this matters:**

- PostgreSQL requires the referenced column set of a composite foreign key to be covered by a `PRIMARY KEY` or `UNIQUE` constraint.
- `id` alone is already unique, but `(id, type)` must still be declared explicitly if child tables will reference both columns.

**Verification:**

Run:
```bash
uv run grimoire test all -k "wargame_schema or db_schema"
```

Expected:
- schema metadata tests still pass
- no migration-level regressions around `Activity`

Run:
```bash
uv run ruff check src/promptgrimoire/db/models.py alembic/versions/1b59ab790954_add_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Convert `WargameConfig` to a discriminator-enforcing extension table

**Verifies:** wargame-schema-294.AC2.1 through wargame-schema-294.AC2.4, plus the stronger subtype invariant

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:24-65`
- Modify: `src/promptgrimoire/db/models.py:258-392`

**Implementation:**

Update the `wargame_config` table in both Alembic and SQLModel to include a child-side discriminator column:

```sql
activity_type VARCHAR(50) NOT NULL DEFAULT 'wargame'
```

Then enforce three separate invariants:

1. Local discriminator correctness:

```sql
CONSTRAINT ck_wargame_config_activity_type
  CHECK (activity_type = 'wargame')
```

2. Cross-table subtype correctness:

```sql
CONSTRAINT fk_wargame_config_activity_wargame
  FOREIGN KEY (activity_id, activity_type)
  REFERENCES activity (id, type)
  ON DELETE CASCADE
```

3. Timer exclusivity:

```sql
CONSTRAINT ck_wargame_config_timer_exactly_one
  CHECK (num_nonnulls(timer_delta, timer_wall_clock) = 1)
```

The resulting Alembic table shape should be conceptually:

```sql
CREATE TABLE wargame_config (
  activity_id UUID PRIMARY KEY,
  activity_type VARCHAR(50) NOT NULL DEFAULT 'wargame',
  system_prompt TEXT NOT NULL,
  scenario_bootstrap TEXT NOT NULL,
  timer_delta INTERVAL,
  timer_wall_clock TIME,
  CONSTRAINT ck_wargame_config_activity_type
    CHECK (activity_type = 'wargame'),
  CONSTRAINT fk_wargame_config_activity_wargame
    FOREIGN KEY (activity_id, activity_type)
    REFERENCES activity (id, type)
    ON DELETE CASCADE,
  CONSTRAINT ck_wargame_config_timer_exactly_one
    CHECK (num_nonnulls(timer_delta, timer_wall_clock) = 1)
);
```

In `src/promptgrimoire/db/models.py`:

1. Add `activity_type: str = Field(...)` to `WargameConfig`.
2. Give it:
   - default `"wargame"`
   - `nullable=False`
   - `server_default="wargame"` or equivalent SQLAlchemy text form
3. Add a table-level `CheckConstraint` for `activity_type = 'wargame'`.
4. Add the composite foreign key using SQLAlchemy table arguments, not ad hoc runtime validation.
5. Keep the existing `model_validator` that enforces exactly one timer field.
6. Add a second lightweight validator if needed to reject non-`wargame` `activity_type` values before hitting the DB.

**Important:**

- Do not rely only on a Python validator for subtype enforcement.
- Do not replace this with a trigger.
- Keep the extension-table pattern declarative and inspectable in schema dumps.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- timer tests still pass
- any new subtype-enforcement tests pass

Run:
```bash
uvx ty check
```

Expected: clean pass with the new `activity_type` field on the model.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add missing `WargameConfig` subtype and lifecycle tests

**Verifies:** wargame-schema-294.AC2.1 through wargame-schema-294.AC2.4, plus schema-only ownership by wargame activities

**Files:**
- Modify: `tests/unit/test_wargame_models.py:50-109`
- Modify: `tests/integration/test_wargame_schema.py:39-196`

**Implementation:**

The branch already has timer exclusivity tests. Extend them to prove the stronger DBA contract.

Add unit-level coverage in `tests/unit/test_wargame_models.py`:

1. `activity_type="wargame"` is accepted.
2. Any non-`wargame` `activity_type` value is rejected by model validation if you add that validator.

Add integration-level coverage in `tests/integration/test_wargame_schema.py`:

1. `WargameConfig` row attached to a `wargame` activity succeeds.
2. `WargameConfig` row attached to an `annotation` activity fails on the composite FK or local discriminator constraint.
3. Deleting the parent wargame activity cascades to delete the config row.
4. Optional but useful: inserting a row with `activity_type='annotation'` for a wargame activity fails the local `CHECK`.

The critical new negative test is:

```python
with pytest.raises(IntegrityError):
    session.add(
        WargameConfig(
            activity_id=annotation_activity.id,
            activity_type="wargame",
            system_prompt="...",
            scenario_bootstrap="...",
            timer_delta=timedelta(minutes=10),
        )
    )
```

This must fail because `(annotation_activity.id, "wargame")` does not exist in `activity`.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- existing timer tests still pass
- annotation-parent rejection is now explicitly proven
- cascade behaviour is proven

Run:
```bash
uv run ruff check tests/integration/test_wargame_schema.py tests/unit/test_wargame_models.py
```

Expected: clean pass.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 2 completion sweep

**Verifies:** wargame-schema-294.AC2.1 through wargame-schema-294.AC2.4, plus the stronger subtype invariant

**Files:**
- Review: `src/promptgrimoire/db/models.py:258-392`
- Review: `alembic/versions/1b59ab790954_add_wargame_schema.py:24-65`
- Review: `tests/unit/test_wargame_models.py:50-109`
- Review: `tests/integration/test_wargame_schema.py:39-196`
- Review: `tests/unit/test_db_schema.py:16-75`

**Checklist:**

1. Confirm `WargameConfig` remains a PK-as-FK one-to-one extension.
2. Confirm `activity_type` is present and constant at `'wargame'`.
3. Confirm the database rejects config rows for annotation activities.
4. Confirm timer exclusivity is enforced in both SQLModel validation and PostgreSQL.
5. Confirm metadata registration tests still include `wargame_config`.

**Verification:**

Run:
```bash
uv run grimoire test all -k "wargame_schema or db_schema"
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
- the database now enforces that only wargame activities can own `WargameConfig`
<!-- END_TASK_4 -->
