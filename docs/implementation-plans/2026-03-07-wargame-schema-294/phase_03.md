# Wargame Schema Implementation Plan

**Goal:** Create a `WargameTeam` table that supports round-tracking defaults, per-activity codename uniqueness, and database-enforced ownership only by `Activity(type='wargame')`.

**Architecture:** Use a regular child table keyed by its own UUID primary key, but require subtype-correct parent ownership through the same discriminator-enforcing composite foreign key pattern used for `WargameConfig`. Team identity remains `id`; parent typing is enforced through `(activity_id, activity_type) -> activity(id, type)`.

**Tech Stack:** Python 3.14, SQLModel, SQLAlchemy, Alembic, PostgreSQL, pytest via `uv run grimoire` harness

**Scope:** 5 phases from original design (phase 3 of 5)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### wargame-schema-294.AC3: WargameTeam
- **wargame-schema-294.AC3.1 Success:** Team created with codename and defaults (round 0, state 'drafting', NULL artifacts)
- **wargame-schema-294.AC3.2 Success:** Multiple teams with different codenames under same activity
- **wargame-schema-294.AC3.3 Failure:** Duplicate codename under same activity rejected by UNIQUE
- **wargame-schema-294.AC3.4 Success:** Deleting the parent activity cascades to delete all teams

Additional invariant for this branch:
- `WargameTeam` may only reference `Activity(type='wargame')`

---

<!-- START_TASK_1 -->
### Task 1: Convert `WargameTeam` to the same subtype-enforcing parent contract as `WargameConfig`

**Verifies:** wargame-schema-294.AC3.1 through wargame-schema-294.AC3.4

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:67-101`
- Modify: `src/promptgrimoire/db/models.py:395-424`

**Implementation:**

Update `wargame_team` to carry an explicit parent discriminator column:

```sql
activity_type VARCHAR(50) NOT NULL DEFAULT 'wargame'
```

Then enforce:

1. Local child-table correctness:

```sql
CONSTRAINT ck_wargame_team_activity_type
  CHECK (activity_type = 'wargame')
```

2. Cross-table subtype correctness:

```sql
CONSTRAINT fk_wargame_team_activity_wargame
  FOREIGN KEY (activity_id, activity_type)
  REFERENCES activity (id, type)
  ON DELETE CASCADE
```

This replaces the current simple FK from `activity_id` to `activity.id`.

In `src/promptgrimoire/db/models.py`:

1. Add `activity_type: str` to `WargameTeam`.
2. Give it:
   - default `"wargame"`
   - non-null DB column
   - server default matching the migration
3. Add the local `CHECK (activity_type = 'wargame')`.
4. Add the composite foreign key using table-level SQLAlchemy metadata.

**Why this is the right pattern:**

- It matches the revised Phase 2 `WargameConfig` design.
- It prevents annotation activities from silently owning teams.
- It keeps the subtype contract declarative and visible in the schema.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- existing team tests still pass after constructor defaults are updated
- no regression in cascade or uniqueness behavior

Run:
```bash
uv run ruff check src/promptgrimoire/db/models.py alembic/versions/1b59ab790954_add_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Preserve the real team keys and defaults without over-indexing constants

**Verifies:** wargame-schema-294.AC3.1 through wargame-schema-294.AC3.3

**Files:**
- Modify: `src/promptgrimoire/db/models.py:395-424`
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:67-101`

**Implementation:**

Keep the team table’s real identity and business keys clean:

1. Primary key remains:

```sql
PRIMARY KEY (id)
```

2. Codename uniqueness remains:

```sql
UNIQUE (activity_id, codename)
```

Do not widen this to `(activity_id, activity_type, codename)`. `activity_type` is constant and adds no real selectivity.

3. Keep the parent lookup index as:

```sql
CREATE INDEX ix_wargame_team_activity_id ON wargame_team (activity_id);
```

Do not add `activity_type` to the index unless profiling later shows a real query need.

4. Preserve these defaults exactly:
   - `current_round = 0`
   - `round_state = 'drafting'`
   - `current_deadline = NULL`
   - `game_state_text = NULL`
   - `student_summary_text = NULL`

5. Mirror those defaults in the SQLModel class so constructor behavior and persisted behavior match.

**Why this matters:**

- The discriminator column exists to enforce subtype ownership, not to bloat every secondary key.
- The unique codename rule is about one activity’s namespace; `activity_id` already expresses that.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- default-value assertions still pass
- duplicate codename rejection still passes
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add missing ownership-failure coverage for annotation parents

**Verifies:** wargame-schema-294.AC3.1 through wargame-schema-294.AC3.4, plus the stronger subtype invariant

**Files:**
- Modify: `tests/integration/test_wargame_schema.py:198-246`
- Optionally modify: `tests/unit/test_wargame_models.py:1-163`

**Implementation:**

Keep the existing integration tests for:

- defaults
- codename uniqueness
- cascade delete from activity to team

Add one explicit DB-boundary negative test proving annotation activities cannot own teams.

Required integration case:

1. Create a valid annotation activity.
2. Attempt to insert:

```python
WargameTeam(activity_id=annotation_activity.id, codename="Alpha")
```

3. Assert `IntegrityError` on the composite FK or local discriminator constraint.

Optional unit coverage:

- If you add model-level validation for `activity_type`, add one unit test proving a non-`wargame` value is rejected.
- Keep this secondary. The DB test is the primary falsifier.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- existing team tests pass
- new annotation-parent rejection test passes

Run:
```bash
uv run ruff check tests/integration/test_wargame_schema.py tests/unit/test_wargame_models.py
```

Expected: clean pass.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 3 completion sweep

**Verifies:** wargame-schema-294.AC3.1 through wargame-schema-294.AC3.4, plus the stronger subtype invariant

**Files:**
- Review: `src/promptgrimoire/db/models.py:395-424`
- Review: `alembic/versions/1b59ab790954_add_wargame_schema.py:67-101`
- Review: `tests/integration/test_wargame_schema.py:198-246`

**Checklist:**

1. Confirm `WargameTeam` rows default correctly without extra constructor noise.
2. Confirm only `Activity(type='wargame')` can own teams.
3. Confirm codename uniqueness is still scoped by `activity_id`.
4. Confirm deleting a wargame activity still cascades to its teams.
5. Confirm the discriminator column is not needlessly duplicated into non-essential indexes and unique keys.

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
- the team table now matches the stronger DBA-level subtype contract adopted in Phase 2
<!-- END_TASK_4 -->
