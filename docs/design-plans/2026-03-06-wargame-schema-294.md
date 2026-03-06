# Wargame Data Model and Migrations Design

**GitHub Issue:** #294

## Summary

This design document specifies the database schema and Alembic migrations needed to support wargame activities in PromptGrimoire. The existing `Activity` table is monomorphic — all activities are annotation workspaces. This work makes `Activity` polymorphic by adding a `type` discriminator column, then adds three new tables (`WargameConfig`, `WargameTeam`, `WargameMessage`) that model the wargame-specific structure: configuration (system prompt, scenario text, timer), participating teams (codename, round tracking, game-state artifacts), and a canonical per-team message log. It also extends the existing access control table (`ACLEntry`) to grant permissions at the team level, not just the workspace level.

The approach uses type-specific extension tables keyed by the parent `activity_id`, a standard relational pattern that avoids wide nullable columns on the core `Activity` table. Message history is stored in normalised relational rows (role, content, thinking, metadata) rather than as serialised blobs, which keeps it queryable and editable. All constraints — type-template exclusivity, timer exclusivity, team codename uniqueness, message sequence uniqueness, and ACL target exclusivity — are enforced at the database level via `CHECK` constraints and partial unique indexes. The scope is purely schema: no UI, no business logic, no CRDT integration.

## Definition of Done

1. **Activity gains a type discriminator** — new `type` column on Activity (VARCHAR, NOT NULL, default `'annotation'`), `template_workspace_id` becomes nullable, CHECK constraints enforce type-specific invariants.
2. **WargameConfig table** — 1:1 extension of Activity for wargame-specific fields (system prompt, scenario bootstrap, timer configuration).
3. **WargameTeam table** — resource table with codename, round state, simulation state, game-state and student-summary text columns. FK to Activity.
4. **WargameMessage table** — canonical message table with role, content (TEXT), thinking (TEXT nullable), metadata (JSONB), per-team monotonic `sequence_no` (append-only, never reused). UNIQUE on (team_id, sequence_no).
5. **ACLEntry extended** — nullable `team_id` FK, CHECK constraint ensuring exactly one of workspace_id/team_id is set.
6. **Alembic migration(s)** — all schema changes via migration, following existing naming conventions.
7. **SQLModel classes** — all new tables have corresponding SQLModel classes in the models module.
8. **Tests pass** — existing tests unbroken by Activity changes. New model tests for constraints and relationships.

No UI, no business logic, no CRDT integration — just tables, models, and migrations.

## Acceptance Criteria

### wargame-schema-294.AC1: Activity type discriminator
- **wargame-schema-294.AC1.1 Success:** Existing annotation activities automatically have `type='annotation'` after migration (default applied)
- **wargame-schema-294.AC1.2 Success:** New activity with `type='wargame'` and no `template_workspace_id` is accepted
- **wargame-schema-294.AC1.3 Success:** New activity with `type='annotation'` and a `template_workspace_id` is accepted
- **wargame-schema-294.AC1.4 Failure:** Activity with `type='annotation'` and NULL `template_workspace_id` is rejected by CHECK
- **wargame-schema-294.AC1.5 Failure:** Activity with `type='wargame'` and a non-NULL `template_workspace_id` is rejected by CHECK

### wargame-schema-294.AC2: WargameConfig
- **wargame-schema-294.AC2.1 Success:** WargameConfig with `timer_delta` set and `timer_wall_clock` NULL is accepted
- **wargame-schema-294.AC2.2 Success:** WargameConfig with `timer_wall_clock` set and `timer_delta` NULL is accepted
- **wargame-schema-294.AC2.3 Failure:** WargameConfig with both timer fields NULL is rejected by CHECK
- **wargame-schema-294.AC2.4 Failure:** WargameConfig with both timer fields set is rejected by CHECK

### wargame-schema-294.AC3: WargameTeam
- **wargame-schema-294.AC3.1 Success:** Team created with codename and defaults (round 0, state 'drafting', NULL artifacts)
- **wargame-schema-294.AC3.2 Success:** Multiple teams with different codenames under same activity
- **wargame-schema-294.AC3.3 Failure:** Duplicate codename under same activity rejected by UNIQUE
- **wargame-schema-294.AC3.4 Success:** Deleting the parent activity cascades to delete all teams

### wargame-schema-294.AC4: WargameMessage
- **wargame-schema-294.AC4.1 Success:** Message appended with next sequence_no
- **wargame-schema-294.AC4.2 Success:** Messages with different roles ('user', 'assistant', 'system') accepted
- **wargame-schema-294.AC4.3 Failure:** Duplicate (team_id, sequence_no) rejected by UNIQUE
- **wargame-schema-294.AC4.4 Success:** Deleting team cascades to delete all messages

### wargame-schema-294.AC5: ACLEntry extension
- **wargame-schema-294.AC5.1 Success:** ACL grant with workspace_id set and team_id NULL (existing behaviour)
- **wargame-schema-294.AC5.2 Success:** ACL grant with team_id set and workspace_id NULL (new team grant)
- **wargame-schema-294.AC5.3 Failure:** ACL grant with both workspace_id and team_id set rejected by CHECK
- **wargame-schema-294.AC5.4 Failure:** ACL grant with both NULL rejected by CHECK
- **wargame-schema-294.AC5.5 Success:** Existing workspace ACL grants remain valid after migration

### wargame-schema-294.AC6: Migration integrity
- **wargame-schema-294.AC6.1 Success:** Migration applies to a database with existing data without errors
- **wargame-schema-294.AC6.2 Success:** Migration downgrades cleanly

### wargame-schema-294.AC7: SQLModel classes
- **wargame-schema-294.AC7.1 Success:** All new tables (WargameConfig, WargameTeam, WargameMessage) have corresponding SQLModel classes
- **wargame-schema-294.AC7.2 Success:** Modified tables (Activity, ACLEntry) have updated SQLModel classes with new fields

### wargame-schema-294.AC8: Existing tests
- **wargame-schema-294.AC8.1 Success:** All existing unit and integration tests pass without modification (except where Activity's template_workspace_id nullability requires model-level validation updates)

## Glossary

- **Activity**: The PromptGrimoire model for a single learnable task within a Week. Previously monomorphic (always an annotation workspace); this work makes it polymorphic via a `type` column.
- **ACLEntry**: The access control list table that records which user has which permission on which resource (workspace or, after this work, team).
- **Alembic**: The Python database migration tool used by this project. All schema changes must be expressed as Alembic migrations.
- **CHECK constraint**: A SQL constraint that rejects rows whose column values violate a boolean expression. Used here to enforce type-specific invariants.
- **CRDT (Conflict-free Replicated Data Type)**: The real-time collaboration mechanism used for annotation workspace content (via `pycrdt`). Deliberately out of scope for this seam.
- **Extension table (PK-as-FK)**: A 1:1 relational pattern where a table's primary key is also a foreign key to a parent table, enforcing at most one extension row per parent row. Used here for `WargameConfig`.
- **Discriminator-enforcing composite FK**: A pattern where child tables carry a constant type column and reference the parent via composite FK `(id, type)`, making the database reject children attached to the wrong parent subtype. Used here on `WargameConfig` and `WargameTeam`.
- **GM (Game Master)**: The instructor running a wargame scenario. Certain columns (e.g. `game_state_text`) are visible only to the GM; enforced by application logic.
- **JSONB**: PostgreSQL's binary JSON column type. Used for `WargameMessage.metadata`.
- **ModelMessage / message_history**: PydanticAI types representing AI conversation turns. The design stores messages in normalised columns and reconstructs `list[ModelMessage]` at call time.
- **num_nonnulls()**: A PostgreSQL built-in function that counts non-null arguments. Used in CHECK constraints for "exactly one FK set" patterns.
- **Partial unique index**: A PostgreSQL index with a `WHERE` clause, enforcing uniqueness only over matching rows. Used to preserve `(workspace_id, user_id)` uniqueness after `workspace_id` becomes nullable.
- **PydanticAI**: The AI client library used by PromptGrimoire for model calls.
- **sequence_no**: Per-team monotonically increasing integer ordering messages. Append-only, never reused.
- **SQLModel**: The ORM layer (Pydantic + SQLAlchemy) used throughout PromptGrimoire.
- **TIMESTAMPTZ**: PostgreSQL timestamp with time zone. All datetime columns use this type, stored in UTC.
- **Type discriminator**: A column indicating which subtype (and extension table) applies to a row. Here, `Activity.type` takes values like `'annotation'` or `'wargame'`.

## Architecture

### Approach: Type Discriminator + Extension Tables

Activity becomes polymorphic via a `type` VARCHAR column. The existing Activity table retains all shared fields (title, description, week placement, timestamps). Type-specific configuration lives in 1:1 extension tables keyed by `activity_id`. Child tables enforce subtype correctness via discriminator-enforcing composite FKs: each child carries a constant `activity_type = 'wargame'` column and references `activity(id, type)`, so the database itself rejects children attached to the wrong activity type.

For wargame activities, the extension chain is:

```
Course → Week → Activity (type='wargame')
                    ↓ 1:1
               WargameConfig (system prompt, scenario, timer)
                    ↓ 1:many
               WargameTeam (codename, round state, artifacts)
                    ↓ 1:many
               WargameMessage (canonical turn log)
```

Team membership uses the existing ACL system. ACLEntry gains a nullable `team_id` FK alongside its existing `workspace_id` FK, with a CHECK constraint ensuring exactly one target is set. Permission levels (viewer, editor) come from the existing Permission reference table.

### Schema Contracts

**Activity table (modified):**

```sql
ALTER TABLE activity
  ADD COLUMN type VARCHAR(50) NOT NULL DEFAULT 'annotation',
  ALTER COLUMN template_workspace_id DROP NOT NULL;

-- Composite key for discriminator-enforcing child FKs
ALTER TABLE activity ADD CONSTRAINT uq_activity_id_type UNIQUE (id, type);

-- Annotation activities must have a template workspace
ALTER TABLE activity ADD CONSTRAINT ck_activity_annotation_requires_template
  CHECK (type != 'annotation' OR template_workspace_id IS NOT NULL);

-- Wargame activities must not have a template workspace
ALTER TABLE activity ADD CONSTRAINT ck_activity_wargame_no_template
  CHECK (type != 'wargame' OR template_workspace_id IS NULL);
```

**WargameConfig table (new):**

```sql
CREATE TABLE wargame_config (
  activity_id    UUID PRIMARY KEY,
  activity_type  VARCHAR(50) NOT NULL DEFAULT 'wargame',
  system_prompt      TEXT NOT NULL,
  scenario_bootstrap TEXT NOT NULL,
  timer_delta        INTERVAL,
  timer_wall_clock   TIME,
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

**WargameTeam table (new):**

```sql
CREATE TABLE wargame_team (
  id                   UUID PRIMARY KEY,
  activity_id          UUID NOT NULL,
  activity_type        VARCHAR(50) NOT NULL DEFAULT 'wargame',
  codename             VARCHAR(100) NOT NULL,
  current_round        INTEGER NOT NULL DEFAULT 0,
  round_state          VARCHAR(50) NOT NULL DEFAULT 'drafting',
  current_deadline     TIMESTAMPTZ,
  game_state_text      TEXT,
  student_summary_text TEXT,
  created_at           TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_wargame_team_activity_type
    CHECK (activity_type = 'wargame'),
  CONSTRAINT fk_wargame_team_activity_wargame
    FOREIGN KEY (activity_id, activity_type)
    REFERENCES activity (id, type)
    ON DELETE CASCADE,
  CONSTRAINT uq_wargame_team_activity_codename
    UNIQUE (activity_id, codename)
);
CREATE INDEX ix_wargame_team_activity_id ON wargame_team (activity_id);
```

**WargameMessage table (new):**

```sql
CREATE TABLE wargame_message (
  id           UUID PRIMARY KEY,
  team_id      UUID NOT NULL
    REFERENCES wargame_team(id) ON DELETE CASCADE,
  sequence_no  INTEGER NOT NULL,
  role         VARCHAR(50) NOT NULL,
  content      TEXT NOT NULL,
  thinking     TEXT,
  metadata     JSONB,
  edited_at    TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL,
  CONSTRAINT uq_wargame_message_team_sequence
    UNIQUE (team_id, sequence_no)
);
CREATE INDEX ix_wargame_message_team_id ON wargame_message (team_id);
```

**ACLEntry table (modified):**

```sql
ALTER TABLE acl_entry
  ALTER COLUMN workspace_id DROP NOT NULL,
  ADD COLUMN team_id UUID REFERENCES wargame_team(id) ON DELETE CASCADE;

-- Exactly one target FK must be set
ALTER TABLE acl_entry ADD CONSTRAINT ck_acl_entry_exactly_one_target
  CHECK (num_nonnulls(workspace_id, team_id) = 1);

-- Replace composite unique with partial unique indexes
ALTER TABLE acl_entry DROP CONSTRAINT uq_acl_entry_workspace_user;
CREATE UNIQUE INDEX uq_acl_entry_workspace_user
  ON acl_entry (workspace_id, user_id) WHERE workspace_id IS NOT NULL;
CREATE UNIQUE INDEX uq_acl_entry_team_user
  ON acl_entry (team_id, user_id) WHERE team_id IS NOT NULL;
```

### Data Flow

Messages are stored in the application's own schema (role, content, thinking, metadata) rather than as serialised PydanticAI blobs. At AI call time, a builder function reconstructs `list[ModelMessage]` from canonical rows. This keeps messages human-readable, editable by the GM, and queryable, while maintaining round-trip fidelity with PydanticAI's `message_history` parameter.

Game-state artifact and student summary are TEXT columns on WargameTeam, overwritten in place each turn. No revision history for MVP.

### Key Invariants

- `sequence_no` is monotonically increasing per team, append-only, never reused or resequenced.
- Timer configuration requires exactly one of `timer_delta` or `timer_wall_clock` (enforced by CHECK).
- `current_deadline` on WargameTeam is a resolved TIMESTAMPTZ, computed at publish time from the config template.
- `game_state_text` is GM-only; application code enforces visibility (not column-level ACL).

## Existing Patterns

This design follows established PromptGrimoire conventions discovered via codebase investigation:

**UUID primary keys** — all entity tables use `Field(default_factory=uuid4, primary_key=True)`. Helper functions `_cascade_fk_column()` and `_set_null_fk_column()` in `src/promptgrimoire/db/models.py` standardise FK column creation.

**TIMESTAMPTZ convention** — all timestamps use `DateTime(timezone=True)` via `_timestamptz_column()`, defaulting to `_utcnow()`.

**Named constraints** — CHECK constraints use `ck_table_purpose`, unique constraints use `uq_table_columns`, foreign keys use `fk_table_column`, indexes use `ix_table_column`. Expression indexes use `idx_table_description`. (From `docs/database.md`.)

**1:1 extension via PK-as-FK** — not yet used in the codebase, but a standard SQLAlchemy pattern. WargameConfig uses `activity_id` as both PK and FK, enforcing 1:1. This is a new pattern for this project.

**Discriminator-enforcing composite FK** — also new. Child tables (WargameConfig, WargameTeam) carry a constant `activity_type = 'wargame'` column and reference `activity(id, type)` via composite FK. This makes the database reject child rows attached to the wrong activity type, rather than relying on application code. Requires a UNIQUE constraint on `activity(id, type)` as the FK target.

**ACL extensibility** — `docs/database.md` (line 309) documents the planned approach: "When roleplay sessions or other resource types need ACL, add a nullable FK column (e.g., `roleplay_session_id`) with a CHECK constraint ensuring exactly one FK is set." This design follows that documented plan.

**Reference table for permissions** — Permission and CourseRoleRef use string PKs. ACLEntry FKs to `Permission.name` with RESTRICT delete. Wargame team grants reuse the same Permission levels.

**Divergence: Activity type column.** The existing Activity model is monomorphic. Adding `type` is a new pattern. Justified by the user's requirement that wargame, annotation, and (future) roleplay activities all sit under Week in the course hierarchy, sharing title/description/timestamps but diverging in type-specific configuration.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Activity Type Discriminator

**Goal:** Add type column to Activity and make template_workspace_id nullable, without breaking any existing functionality.

**Components:**
- Alembic migration: add `type` VARCHAR(50) NOT NULL DEFAULT `'annotation'` to `activity`, alter `template_workspace_id` to nullable, add CHECK constraints `ck_activity_annotation_requires_template` and `ck_activity_wargame_no_template`
- SQLModel update in `src/promptgrimoire/db/models.py` — add `type` field to Activity class, update `template_workspace_id` to `UUID | None`
- Pydantic validator on Activity: if `type == 'annotation'`, `template_workspace_id` must be set

**Dependencies:** None (first phase)

**Done when:** Migration applies cleanly, existing annotation tests pass unchanged, Activity model accepts `type` field. Covers wargame-schema-294.AC1.1–AC1.5.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: WargameConfig Table

**Goal:** Create the wargame configuration extension table with timer semantics.

**Components:**
- Alembic migration: create `wargame_config` table with PK-as-FK to activity, system_prompt, scenario_bootstrap, timer_delta (INTERVAL), timer_wall_clock (TIME), CHECK constraint on timer exclusivity
- SQLModel class `WargameConfig` in `src/promptgrimoire/db/models.py`

**Dependencies:** Phase 1 (Activity type column must exist)

**Done when:** WargameConfig can be created for a wargame-typed Activity. Timer CHECK constraint enforced. Covers wargame-schema-294.AC2.1–AC2.4.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: WargameTeam Table

**Goal:** Create the team resource table with round tracking and artifact columns.

**Components:**
- Alembic migration: create `wargame_team` table with all columns, UNIQUE on (activity_id, codename), index on activity_id
- SQLModel class `WargameTeam` in `src/promptgrimoire/db/models.py`

**Dependencies:** Phase 1 (FK to activity)

**Done when:** Teams can be created under a wargame activity. Codename uniqueness enforced per activity. Covers wargame-schema-294.AC3.1–AC3.4.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: WargameMessage Table

**Goal:** Create the canonical message table with monotonic sequence enforcement.

**Components:**
- Alembic migration: create `wargame_message` table with UNIQUE on (team_id, sequence_no), index on team_id
- SQLModel class `WargameMessage` in `src/promptgrimoire/db/models.py`

**Dependencies:** Phase 3 (FK to wargame_team)

**Done when:** Messages can be appended with sequential numbering. Duplicate sequence_no rejected by UNIQUE constraint. Covers wargame-schema-294.AC4.1–AC4.4.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: ACLEntry Extension

**Goal:** Extend ACLEntry to support team-based grants alongside workspace grants.

**Components:**
- Alembic migration: alter `workspace_id` to nullable, add `team_id` FK, add CHECK constraint `ck_acl_entry_exactly_one_target`, drop existing UNIQUE constraint, create two partial unique indexes
- SQLModel update to ACLEntry in `src/promptgrimoire/db/models.py` — `workspace_id` becomes `UUID | None`, add `team_id: UUID | None`

**Dependencies:** Phase 3 (wargame_team table must exist for FK)

**Done when:** ACL grants can target either a workspace or a team (not both, not neither). Existing workspace ACL tests pass unchanged. Existing queries in `acl.py` that join on or filter by `workspace_id` must be audited and guarded with `WHERE workspace_id IS NOT NULL` where needed. Covers wargame-schema-294.AC5.1–AC5.5.
<!-- END_PHASE_5 -->

## Additional Considerations

**Migration ordering.** Phases 2 and 3 both depend on Phase 1 but are independent of each other. They could be a single migration or separate migrations — implementation decision. Phase 4 depends on Phase 3. Phase 5 depends on Phase 3. A reasonable split is two migrations: one for Phases 1–3 (all new tables) and one for Phase 5 (ACLEntry modification), since the latter modifies a live table with existing data.

**Existing ACL resolution code.** `src/promptgrimoire/db/acl.py` assumes `workspace_id` is NOT NULL on ACLEntry. Phase 5 changes this assumption. The partial unique index preserves the existing uniqueness guarantee, but queries that join on or filter by `workspace_id` without an `IS NOT NULL` guard could silently include team-targeted rows. Phase 5 must audit these queries and add guards as part of the migration — this is query correctness, not business logic.

**sequence_no generation.** The schema enforces sequence uniqueness via UNIQUE constraint but does not prescribe *how* the next value is generated. Concurrent inserts reading `MAX(sequence_no)` would race. The generation strategy (advisory lock, SELECT FOR UPDATE, retry loop) is a Seam 3 (Turn Cycle Engine) concern. The schema is correct — it makes races visible as constraint violations rather than silent corruption.

**round_state values.** The initial set is `'drafting'`, `'locked'`, `'simulation_ended'`. These are not enforced by CHECK constraint — the turn cycle engine (Seam 3) owns state transitions. Keeping them as plain VARCHAR allows the engine to evolve states without schema changes.

**No CRDT columns on WargameTeam.** The move buffer and notes panel use CRDT (Seam 4), but CRDT storage is a Seam 4 concern. This seam provides the relational structure only.
