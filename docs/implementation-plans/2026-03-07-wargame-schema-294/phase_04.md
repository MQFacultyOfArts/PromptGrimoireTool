# Wargame Schema Implementation Plan

**Goal:** Create a canonical `WargameMessage` table with stable per-team ordering, append-safe uniqueness, and cascade cleanup through team ownership.

**Architecture:** Messages belong to `WargameTeam`, not directly to `Activity`. `sequence_no` is the only durable conversation ordering field. `created_at` and `edited_at` are audit fields only. GM edits and earlier-turn regenerations update existing rows in place rather than inserting replacement rows.

**Tech Stack:** Python 3.14, SQLModel, SQLAlchemy, Alembic, PostgreSQL, pytest via `uv run grimoire` harness

**Scope:** 5 phases from original design (phase 4 of 5)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### wargame-schema-294.AC4: WargameMessage
- **wargame-schema-294.AC4.1 Success:** Message appended with next sequence_no
- **wargame-schema-294.AC4.2 Success:** Messages with different roles ('user', 'assistant', 'system') accepted
- **wargame-schema-294.AC4.3 Failure:** Duplicate (team_id, sequence_no) rejected by UNIQUE
- **wargame-schema-294.AC4.4 Success:** Deleting a team cascades to delete all messages

Additional ordering contract for this branch:
- `sequence_no` is the canonical sort key
- `created_at` and `edited_at` are never used to derive message order
- GM edits and regenerations of earlier turns update rows in place

---

<!-- START_TASK_1 -->
### Task 1: Preserve the message table as a team-owned ordered log

**Verifies:** wargame-schema-294.AC4.2, wargame-schema-294.AC4.3, wargame-schema-294.AC4.4

**Files:**
- Modify: `alembic/versions/1b59ab790954_add_wargame_schema.py:103-127`
- Modify: `src/promptgrimoire/db/models.py:427-457`

**Implementation:**

Keep the current `wargame_message` table shape anchored on `team_id`:

```sql
CREATE TABLE wargame_message (
  id UUID PRIMARY KEY,
  team_id UUID NOT NULL REFERENCES wargame_team(id) ON DELETE CASCADE,
  sequence_no INTEGER NOT NULL,
  role VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  thinking TEXT,
  metadata JSONB,
  edited_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT uq_wargame_message_team_sequence
    UNIQUE (team_id, sequence_no)
);
CREATE INDEX ix_wargame_message_team_id ON wargame_message (team_id);
```

Do not add any discriminator column to `wargame_message`. Once Phase 3 enforces that only wargame activities can own teams, `team_id` already carries the subtype boundary.

Keep the SQLModel mapping aligned:

1. `team_id` remains a cascade FK to `wargame_team.id`.
2. `sequence_no` remains required and non-null.
3. `metadata_json` continues mapping to the `metadata` JSONB column.
4. `thinking` and `edited_at` remain nullable.

**Why this is sufficient:**

- Team ownership already gives the message table the correct subtype lineage.
- Adding more discriminator columns here would duplicate state without blocking additional invalid rows.
- The unique constraint already provides the supporting index shape for ordered team-local retrieval.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- existing message uniqueness and cascade tests continue to pass

Run:
```bash
uv run ruff check src/promptgrimoire/db/models.py alembic/versions/1b59ab790954_add_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Make the ordering contract explicit around `sequence_no`

**Verifies:** wargame-schema-294.AC4.1, wargame-schema-294.AC4.3

**Files:**
- Modify: `src/promptgrimoire/db/models.py:427-457`
- Modify: `tests/integration/test_wargame_schema.py:249-332`

**Implementation:**

Document and test the intended message ordering semantics:

1. `sequence_no` is the canonical per-team order field.
2. Read paths must order by `sequence_no ASC`.
3. `created_at` is append-time metadata only.
4. `edited_at` records later edits or earlier-turn regenerations.
5. There is no requirement for gapless numbering in this schema phase.

Add a short docstring note to `WargameMessage` or an adjacent code comment clarifying:

- order is by `sequence_no`
- timestamps are audit fields

Add one focused integration test that proves canonical order does not depend on timestamps. The test can:

1. create three messages with `sequence_no` values 2, 1, 3 across separate inserts or explicit timestamps if needed
2. query them ordered by `sequence_no`
3. assert the readback order is 1, 2, 3

If the current schema test file does not include a read helper, add a local query in the test using `select(WargameMessage).where(...).order_by(WargameMessage.sequence_no)`.

**Important:**

- Do not introduce trigger-based gap enforcement.
- Do not treat `created_at` as a fallback sort key.
- Do not model earlier-turn regeneration as a new message row in Phase 4.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- the suite now proves stable canonical sort order by `sequence_no`
- duplicate sequence rejection still passes
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add persistence coverage for editable payload fields

**Verifies:** wargame-schema-294.AC4.2, wargame-schema-294.AC4.4

**Files:**
- Modify: `tests/integration/test_wargame_schema.py:249-332`
- Optionally modify: `tests/unit/test_wargame_models.py:1-163`

**Implementation:**

Extend the integration coverage so the message table is not only ordered and unique, but also usable for the GM-edit/regeneration model.

Add tests that prove:

1. `metadata_json` round-trips through the JSONB column.
2. `thinking` persists when set and remains `NULL` when omitted.
3. `edited_at` may be `NULL` on creation and later populated on update.
4. Updating an earlier message row in place does not change its `sequence_no`.

Recommended integration case:

1. Create team and seed messages with sequence numbers 1 and 2.
2. Update message 1 with:
   - revised `content`
   - optional `thinking`
   - `metadata_json={"regenerated": true}`
   - non-null `edited_at`
3. Re-read ordered by `sequence_no`.
4. Assert:
   - ordering remains 1 then 2
   - message 1 keeps its original `sequence_no`
   - edited payload fields round-trip correctly

**Why this matters:**

- The expected order/time divergence in this product is GM edits or earlier-turn regenerations.
- That scenario is only clean if regeneration is modeled as an in-place update, not a replacement row.

**Verification:**

Run:
```bash
uv run grimoire test all -k wargame_schema
```

Expected:
- message payload round-trip tests pass
- ordering remains stable after edits

Run:
```bash
uv run ruff check tests/integration/test_wargame_schema.py
```

Expected: clean pass.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 4 completion sweep

**Verifies:** wargame-schema-294.AC4.1 through wargame-schema-294.AC4.4, plus the branch ordering contract

**Files:**
- Review: `src/promptgrimoire/db/models.py:427-457`
- Review: `alembic/versions/1b59ab790954_add_wargame_schema.py:103-127`
- Review: `tests/integration/test_wargame_schema.py:249-332`

**Checklist:**

1. Confirm `sequence_no` is treated as the only canonical sort field.
2. Confirm duplicate `(team_id, sequence_no)` remains impossible.
3. Confirm team deletion still cascades to messages.
4. Confirm nullable payload fields support GM edit/regeneration workflows.
5. Confirm no design creep toward gapless sequencing or revision-history tables in this phase.

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
- the message table now has a durable ordering contract that survives edits and regenerations of earlier turns
<!-- END_TASK_4 -->
