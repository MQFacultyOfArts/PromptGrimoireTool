# Index candidates — ADR 0004 follow-up (tracker ledger 11)

**Status:** measurement plan only. No migration file, no index created, no
query run. Written by static read of `db/*.py`, `search_worker.py`,
`cli/export.py`, `cli_loadtest.py`, `db/models.py`, and every
`alembic/versions/*.py` create/drop-index call, on the ty-bump branch,
2026-08-17. Measurement (the `EXPLAIN (ANALYZE, BUFFERS)` before/after pairs)
is deferred until `e2e all` finishes and a `grimoire loadtest`-scale dataset
exists — see the exact commands in §4.

**Scope note vs. the original 2026-04-23 design plan:** that plan's Phase 6
required a production `pg_restore`, paused without one, and bundled a
5-vote `EXPLAIN`-gated effectiveness test. ADR 0004 supersedes the mechanism
(tstring, not text) and explicitly drops the bundled index phase, deferring
"index-candidate enumeration" as a standalone follow-up (its own §
"Consequences", and tracker ledger item 11). This document is that
follow-up's first half — enumeration — not the measurement gate. §4 gives
the exact before/after commands for whoever runs the measurement.

## Method

1. Read every raw-SQL (`tstring`/`text`) and remaining ORM query in the
   target files, recording tables/JOIN/WHERE/ORDER BY columns.
2. Derived the **actual current index state** by replaying every
   `op.create_index`/`op.drop_index` call across all 41 `alembic/versions/`
   files in migration-chain order (via `down_revision` links), not by
   trusting `models.py`'s `index=True` annotations alone. This matters: many
   indices exist in the DB with no model-level annotation at all (see §1).
3. Classified frequency by tracing actual callers (`rg` into `pages/`,
   `cli/`, `auth/`) rather than guessing from function names — several
   functions turned out to have **zero** production callers despite
   plausible names and docstrings (§5.B).
4. Ranked candidates by **row count × call frequency**, not either alone. A
   query with an "uncovered" sort column that only ever touches a dozen rows
   (e.g. weeks-per-course, capped at ~13-20 by academic-calendar reality)
   is explicitly *not* a candidate no matter how hot the call path is —
   Postgres sorts a dozen rows in microseconds regardless of index. A
   query with the same shape touching hundreds-to-low-thousands of rows,
   run on every page load, is.

## §1. Current index inventory (verified, not just `models.py`)

`models.py` reports only 4 columns with `index=True`-equivalent Field
markers as flagged by the original April design's survey. That count is
misleading: most FK indices in this schema were added by **hand-written
`op.create_index` calls in early migrations**, with no matching
`index=True` back on the model. Trusting `models.py` alone would have
produced a report full of false "missing index" candidates. Verified table
(PK/unique always create an implicit backing btree in Postgres, so those
count as coverage too):

| Table | Indices (all confirmed live at HEAD) |
|---|---|
| `permission` | PK(name), UNIQUE(level) |
| `course_role` | PK(name), UNIQUE(level) |
| `user` | PK(id), UNIQUE+idx(email), UNIQUE+idx(stytch_member_id), UNIQUE(student_id) |
| `course` | PK(id), idx(code), idx(semester) |
| `course_enrollment` | PK(id), UNIQUE(course_id, user_id) composite, idx(user_id) standalone |
| `week` | PK(id), UNIQUE(course_id, week_number) composite |
| `activity` | PK(id), UNIQUE(id, type) composite, UNIQUE(template_workspace_id), idx(week_id) standalone |
| `wargame_config` | PK(activity_id) — shelved feature (2026-08-06), excluded below |
| `wargame_team` | PK(id), UNIQUE(activity_id, codename) composite, idx(activity_id) — shelved |
| `wargame_message` | PK(id), UNIQUE(team_id, sequence_no) composite, idx(team_id) — shelved |
| `workspace` | PK(id), idx(activity_id), idx(course_id), idx(updated_at), GIN idx(search_text) — **`created_at` NOT indexed, `search_dirty` NOT indexed, `shared_with_class` NOT indexed** |
| `workspace_document` | PK(id), idx(workspace_id), idx(source_document_id), GIN idx(content) — **`type` NOT indexed, `order_index` NOT indexed** |
| `tag_group` | PK(id), UNIQUE(workspace_id, name) composite, idx(workspace_id) standalone — **`order_index` NOT indexed** |
| `tag` | PK(id), UNIQUE(workspace_id, name) composite, idx(workspace_id) standalone, idx(group_id) standalone — **`order_index` NOT indexed** |
| `acl_entry` | PK(id), idx(user_id) standalone, partial UNIQUE idx(workspace_id, user_id) WHERE workspace_id IS NOT NULL, partial UNIQUE idx(team_id, user_id) WHERE team_id IS NOT NULL — **`permission` NOT indexed** |
| `student_group` | PK(id), UNIQUE(course_id, name) composite, idx(course_id) standalone |
| `export_job` | PK(id), idx(user_id), idx(workspace_id), idx(status), idx(created_at), idx(token_expires_at), partial UNIQUE idx(download_token) WHERE NOT NULL, partial UNIQUE idx(user_id) WHERE status IN ('queued','running') — fully covered on every model column |
| `student_group_membership` | PK(id), UNIQUE(student_group_id, user_id) composite, idx(student_group_id), idx(user_id) |

A composite UNIQUE/index on `(A, B)` covers equality on `A` alone
(leftmost-prefix rule) but not `B` alone — used throughout below. Partial
indices with `WHERE X IS NOT NULL` still serve plain `WHERE col = :x`
queries, because the planner can prove the equality implies the partial
predicate.

**FK columns without a dedicated index** (Postgres never auto-indexes the
referencing side of a FK): exactly three exist in this schema —
`course.default_instructor_permission`, `course_enrollment.role`, and
`acl_entry.permission` — all three reference a 4-5-row reference table
(`permission`/`course_role`). In every query site read for this report,
each appears only as a **secondary residual filter on an already-narrowed
row set** (e.g. `acl.permission = 'owner'` after `acl.workspace_id = w.id`
has already cut to a handful of rows), never as the sole driving predicate
against a large table. Not recommended — flagged here per the task brief,
not carried into §3.

## §2. Query catalogue by frequency class

Full site-by-site notes are folded into §3/§5 to avoid a 900-line wall of
tables; this section gives the frequency-class groupings the ranking in §3
depends on, with the caller evidence for each.

### Page-load-critical (confirmed via caller trace, not inferred)

- **`resolve_annotation_context`** (`db/workspaces.py:436`) — annotation
  page load, single round trip by design (`pages/annotation/workspace.py:221`).
- **`load_navigator_page` / `search_navigator`** (`db/navigator.py:457,558`)
  — route `/`, called on every page load and every search keystroke.
- **`is_user_banned`** (`db/users.py:247`) — runs before every
  `page_route`-gated page handler (confirmed against `pages/registry.py`
  per CLAUDE.md). Already PK-covered; no candidate.
- Everything `resolve_annotation_context` calls inline: `_resolve_effective_permission`
  → `_resolve_enrollment_permission` (course_enrollment composite exact
  match), `_resolve_privileged_user_ids` (user.is_admin scan — §3.1), the
  inline tag/tag_group fetch (§3.5), `get_active_job_for_user` (§3.6).
- **`list_documents_with_first_content`** (`db/workspace_documents.py:120`)
  — confirmed caller `pages/annotation/workspace.py:242`, same page load.
- **`list_tags_for_workspace` / `list_tag_groups_for_workspace`**
  (`db/tags.py:311,623`) — called a second time from
  `crdt/annotation_doc.py:_ensure_crdt_tag_consistency`, whose own docstring
  says "Called on every workspace load."

### Confirmed page-load-adjacent (course/week navigation, not every page but frequent)

- `get_user_workspace_for_activity`, `check_clone_eligibility` (`db/workspaces.py`)
  — confirmed callers in `pages/courses.py` and `pages/navigator/_cards.py`
  (per-click "Start/Resume" handler, not a per-card render loop — verified,
  not an N+1).
- `list_activities_for_week` (`db/activities.py:219`) — confirmed callers
  `pages/courses.py:551`, `pages/annotation/placement.py:103`.
- `get_visible_weeks` (`db/weeks.py:291`) — student course-navigation;
  page-load-hot by call site, but `week` rows are capped at ~13-20 per
  course by academic-calendar reality, so no index changes its cost (§3, Tier 3).

### Admin / instructor-only

`courses.py` (course CRUD, enrolment roster, `list_students_without_workspaces`),
`weeks.py` (publish/schedule), `enrolment.py` (bulk XLSX import),
`db/users.py`'s `get_banned_users`/`list_users`, `acl.py`'s `grant_share`/
sharing-audit paths, `export_jobs.py`'s `create_export_job`/`get_job_by_token`.
Bounded row counts even at loadtest scale (≤ ~1200 enrollments/course, 30
courses, few hundred export jobs) — evaluated in §3 Tier 3, none promoted.

### Background worker

`search_worker.py::process_dirty_workspaces` (30s poll, tighter under
backlog) and `export_jobs.py::claim_next_job`/`fail_orphaned_jobs`.

### CLI-only

`cli/export.py` (batch PDF export tooling) and `cli_loadtest.py` (seed-data
generation, `uv run grimoire loadtest`). Catalogued in full for
completeness (§5.D) but ranked below every page-load/admin candidate
regardless of coverage, per the task's own framing.

### Confirmed unreachable from any page or CLI (tested only)

See §5.B — six functions in `acl.py` and `workspaces.py`, including the
entire `check_workspace_access → resolve_permission` chain, have zero
production callers. Excluded from the ranking below; their query shapes are
recorded in §5.B in case the decision is "wire it up" rather than "delete it."

## §3. Candidate index table, ranked

### Tier 1 — confirmed page-load-hot, real row counts at scale

| # | Column(s) | Table | Site(s) | Shape | Scale driver |
|---|---|---|---|---|---|
| 1 | `id` WHERE `is_admin` | `user` | `db/workspaces.py:392` (`_resolve_privileged_user_ids`, inline UNION), `db/acl.py:762` (dead-code twin, §5.B) | Full-table boolean scan → tiny admin subset | Every annotation-page load scans the **entire `user` table** (loadtest: 30 courses × up to ~1195 enrolled per course, tens of thousands of rows) to find ~5-10 admins |
| 2a | `activity_id` WHERE `shared_with_class` | `workspace` | `db/navigator.py:219-236` (section 4a) | Filter FK-indexed already, but the *selective* predicate (`shared_with_class`) is unindexed and applied only after the activity join, so every workspace under a matched activity is scanned | One popular activity can have up to 1100 workspaces (one per student); navigator scans all of them per page load to find the tiny opted-in-to-peer-sharing subset |
| 2b | `course_id` WHERE `shared_with_class` | `workspace` | `db/navigator.py:269-283` (section 4b, loose workspaces) | Same shape, course-scoped instead of activity-scoped | Smaller population (loose workspaces are rarer than activity clones) but same missing predicate |
| 3 | `id` WHERE `search_dirty` | `workspace` | `search_worker.py:52` | Full-table boolean scan every poll cycle | Continuous background poll (30s, tighter under load) over the **entire** `workspace` table across all courses |
| 4 | `(workspace_id, order_index)` | `workspace_document` | `db/workspace_documents.py:108,134-152,164` (`list_document_headers`, `list_documents_with_first_content`, `list_documents`) | `workspace_id` indexed, `order_index` sort has no covering index — index-scan-then-sort instead of pure ordered index scan | Every annotation page load builds the document tab bar from this exact query |
| 5a | `(workspace_id, order_index)` | `tag_group` | `db/tags.py:311` | Same shape as #4 | Runs from `resolve_annotation_context` AND from `crdt/annotation_doc.py`'s "every workspace load" CRDT-consistency check — called up to twice per page load |
| 5b | `(workspace_id, order_index)` | `tag` | `db/tags.py:623` | Same shape as #4 | Same double-call pattern as 5a |
| 6 | `(user_id, workspace_id)` | `export_job` | `db/export_jobs.py:203-212` (`get_active_job_for_user`) | Two separately-indexed columns filtered together — planner must BitmapAnd two index scans or pick one and residually filter the other, instead of one composite scan | Called from `resolve_annotation_context` on **every** annotation page load (line 548 of `db/workspaces.py`) — small per-query cost, but it's the sixth query on the hottest path in the app |

### Tier 2 — real shape, bounded or lower-frequency; worth measuring, not urgent

| # | Column(s) | Table | Site(s) | Why lower priority |
|---|---|---|---|---|
| 7 | `(status, created_at)` | `export_job` | `db/export_jobs.py:94-99` (`claim_next_job`) | Background-worker poll, but table size is *self-limiting*: the existing partial unique index caps concurrent `queued`/`running` rows at one per user, so the candidate set `claim_next_job` sorts is bounded by concurrently-exporting users, not total export history |
| 8 | `(week_id, created_at)` | `activity` | `db/activities.py:219-225` (`list_activities_for_week`) | Confirmed page-load-adjacent (course/week nav), `week_id` already covered — but activities-per-week is small (a handful), so the missing sort index saves microseconds per call, not a meaningful win until proven otherwise |

### Tier 3 — evaluated and explicitly NOT recommended (small/reference-scale tables)

Recorded so nobody re-discovers these and proposes them without the
row-count context:

- `week.is_published`, `week.visible_from` (`get_visible_weeks`,
  page-load-hot by call site) — capped at ~13-20 rows/course by academic
  calendar structure. No index changes the cost of scanning 20 rows.
- `course.is_archived`, `course.semester` composite (`list_courses`) — 30
  courses total even at loadtest scale.
- `user.is_banned` (`get_banned_users`) — admin-only, small result set,
  same unindexed-boolean shape as #1/#3 but at admin-page frequency, not
  page-load frequency. If #1 lands and the pattern proves out, this is the
  next cheapest follow-up, not before.
- `course_enrollment.role` sort in `list_course_enrollments`/`list_enrollment_rows`
  (admin roster view) — bounded to ≤ ~1200 rows even for the largest
  loadtest course; an in-memory sort of ~1200 rows costs microseconds,
  dwarfed by render/network overhead. Composite index would be measurable
  noise, not signal.
- The FK-without-index trio from §1 (`permission`-referencing columns) —
  always a residual filter on an already-narrowed set in every site read.
- `export_job.completed_at` (`export_jobs.py::cleanup_expired_jobs`) —
  unindexed, but this is a periodic background sweep over a table whose
  total row count stays small (PDF export volume is low); the function also
  does a SELECT-then-DELETE-by-id-list instead of one
  `DELETE ... WHERE completed_at < :cutoff`, a two-round-trip shape worth
  noting alongside the missing index but, again, not worth acting on at
  this table's size.

## §4. Measurement plan per Tier-1 candidate

Not run. Requires the suite currently in progress to finish, plus
`grimoire loadtest`-scale data (`uv run grimoire loadtest run` — NOT run as
part of this report per the task's read-only constraint). Each candidate
gets: BEFORE plan → apply index → AFTER plan → verdict (index name appears
in the AFTER plan's Index Scan/Bitmap Index Scan node AND both cost and
actual time drop). Run each `EXPLAIN` **3×**, record the median, per DR5 in
the superseded design plan (still the right discipline even though DR5's
formal gate isn't binding here).

### 1. `user` partial index on `is_admin`

```sql
-- BEFORE
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM "user" WHERE is_admin = true;

-- CREATE INDEX CONCURRENTLY (run manually via psql, or in an Alembic
-- migration's op.get_context().autocommit_block() — CONCURRENTLY cannot
-- run inside Alembic's default transaction wrapper)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_is_admin_true
    ON "user" (id) WHERE is_admin;

-- AFTER
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM "user" WHERE is_admin = true;
```

Alembic snippet (for whoever writes the eventual migration — not created here):

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_user_is_admin_true",
            "user",
            ["id"],
            unique=False,
            postgresql_concurrently=True,
            postgresql_where=sa.text("is_admin"),
        )
```

### 2a/2b. `workspace` partial indices on `shared_with_class`

```sql
-- BEFORE (representative: one enrolled course from the seeded dataset)
EXPLAIN (ANALYZE, BUFFERS)
SELECT w.id
FROM workspace w
JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
    AND owner_acl.permission = 'owner'
JOIN activity a ON a.id = w.activity_id
JOIN week wk ON wk.id = a.week_id
JOIN course c ON c.id = wk.course_id
WHERE c.id = ANY(ARRAY['<enrolled_course_uuid>']::uuid[])
  AND owner_acl.user_id != '<requesting_user_uuid>'
  AND w.shared_with_class = true;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_workspace_activity_id_shared
    ON workspace (activity_id) WHERE shared_with_class;
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_workspace_course_id_shared
    ON workspace (course_id) WHERE shared_with_class;

-- AFTER: re-run both BEFORE queries (activity-placed and loose variants),
-- plus the full load_navigator_page() query for a representative
-- heavily-enrolled test user, since the isolated arm's plan can differ
-- from the arm's contribution inside the full 5-way UNION ALL.
```

Alembic snippet:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_workspace_activity_id_shared",
            "workspace",
            ["activity_id"],
            postgresql_concurrently=True,
            postgresql_where=sa.text("shared_with_class"),
        )
        op.create_index(
            "ix_workspace_course_id_shared",
            "workspace",
            ["course_id"],
            postgresql_concurrently=True,
            postgresql_where=sa.text("shared_with_class"),
        )
```

### 3. `workspace` partial index on `search_dirty`

```sql
-- BEFORE
EXPLAIN (ANALYZE, BUFFERS)
SELECT w.id, w.crdt_state, COALESCE(w.title, '') AS ws_title,
       COALESCE(a.title, '') AS activity_title
FROM workspace w
LEFT JOIN activity a ON a.id = w.activity_id
WHERE w.search_dirty = true
LIMIT 500
FOR UPDATE OF w SKIP LOCKED;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_workspace_search_dirty
    ON workspace (id) WHERE search_dirty;

-- AFTER: re-run the BEFORE query verbatim.
```

Alembic snippet:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_workspace_search_dirty",
            "workspace",
            ["id"],
            postgresql_concurrently=True,
            postgresql_where=sa.text("search_dirty"),
        )
```

### 4. `workspace_document (workspace_id, order_index)`

```sql
-- BEFORE
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM workspace_document
WHERE workspace_id = '<workspace_uuid>'
ORDER BY order_index;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_workspace_document_workspace_id_order
    ON workspace_document (workspace_id, order_index);

-- AFTER: re-run the BEFORE query.
```

Alembic snippet:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_workspace_document_workspace_id_order",
            "workspace_document",
            ["workspace_id", "order_index"],
            postgresql_concurrently=True,
        )
```

### 5a/5b. `tag_group` / `tag` `(workspace_id, order_index)`

```sql
-- BEFORE
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM tag_group WHERE workspace_id = '<workspace_uuid>' ORDER BY order_index;
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM tag WHERE workspace_id = '<workspace_uuid>' ORDER BY order_index;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tag_group_workspace_id_order
    ON tag_group (workspace_id, order_index);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tag_workspace_id_order
    ON tag (workspace_id, order_index);

-- AFTER: re-run both BEFORE queries.
```

Alembic snippet:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_tag_group_workspace_id_order",
            "tag_group",
            ["workspace_id", "order_index"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_tag_workspace_id_order",
            "tag",
            ["workspace_id", "order_index"],
            postgresql_concurrently=True,
        )
```

### 6. `export_job (user_id, workspace_id)`

```sql
-- BEFORE
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM export_job
WHERE user_id = '<user_uuid>' AND workspace_id = '<workspace_uuid>'
  AND (
    status IN ('queued', 'running')
    OR (status = 'completed' AND token_expires_at > now())
  )
ORDER BY created_at DESC
LIMIT 1;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_export_job_user_id_workspace_id
    ON export_job (user_id, workspace_id);

-- AFTER: re-run the BEFORE query.
```

Alembic snippet:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_export_job_user_id_workspace_id",
            "export_job",
            ["user_id", "workspace_id"],
            postgresql_concurrently=True,
        )
```

### Tier 2 (measure only if Tier 1 lands and there's appetite to continue)

```sql
-- #7
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM export_job WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1
FOR UPDATE SKIP LOCKED;
-- candidate: CREATE INDEX CONCURRENTLY ix_export_job_status_created_at
--     ON export_job (status, created_at);

-- #8
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM activity WHERE week_id = '<week_uuid>' ORDER BY created_at;
-- candidate: CREATE INDEX CONCURRENTLY ix_activity_week_id_created_at
--     ON activity (week_id, created_at);
```

## §5. Findings beyond indexing (report only, not fixed here)

### A. Metadata full-text search has no index at all — already tracked

`navigator.py`'s `search_navigator()` metadata-FTS arm
(`_META_MATCH`/`_META_DISPLAY`, lines 319-397) is a sequential scan over
every workspace visible to the user, and **the code says so itself**:

> `-- No GIN index — sequential scan on visible workspaces. See #316 phase-2.`

This corroborates the existing GitHub issue #316 phase-2 rather than
discovering something new. It's structurally different from the other
Tier-1 candidates: `_META_MATCH` concatenates columns across five joined
tables (`workspace`, `user`, `activity`, `week`, `course`), so a plain
`CREATE INDEX ... USING gin(to_tsvector(...))` — the pattern already used
for `idx_workspace_document_fts` and `idx_workspace_search_text_fts` — is
not directly applicable; those two existing GIN indices are each scoped to
one table's own column. Closing this gap needs the same denormalization
pattern `workspace.search_text` already uses: a materialized text column
populated by (an extension of) `search_worker.py`, then a GIN index on
that column. That's a design decision, not an index-audit line item —
noted here so it isn't lost, not sized as part of this report.

### B. Fourteen functions across `acl.py`/`activities.py`/`workspaces.py`/`auth/__init__.py` are unreachable from any page or CLI

Confirmed by tracing every caller across `pages/`, `cli/`, and `auth/` (not
just grepping the function's own file):

- `acl.py::list_accessible_workspaces`, `list_course_workspaces`,
  `list_activity_workspaces`, `list_peer_workspaces` (the non-`_with_owners`
  variant), `get_privileged_user_ids_for_workspace`, `list_entries_for_user`
- `activities.py::list_activities_for_course`
- `workspaces.py::list_workspaces_for_activity`, `list_loose_workspaces_for_course`
- **`auth/__init__.py::check_workspace_access`** and everything it alone
  calls — `acl.py::resolve_permission` → `_resolve_permission_with_session`
  → `_derive_enrollment_permission` → `_resolve_workspace_course`. All four
  are exported, documented (CLAUDE.md describes `check_workspace_access` as
  the ACL resolution entry point), covered by `tests/integration/`, and
  called by **nothing else in `src/`**.

Two more are *plausibly* dead but only checked against non-test production
code in one pass, not confirmed with the same rigor as the list above —
flagged with less confidence rather than silently dropped:
`courses.py::list_course_enrollments` (the admin roster page uses the
similarly-named `list_enrollment_rows` instead) and `weeks.py::can_access_week`.

The annotation page uses `resolve_annotation_context`'s own inline
permission resolution instead (verified: `pages/annotation/*.py` imports
`resolve_annotation_context`, never `check_workspace_access` or
`resolve_permission`). This reads as consolidation debt from the
`AnnotationContext` refactor (its own docstring says it "replaces 5+
separate DB function calls") rather than a live authorization gap — but
it's worth a decision either way, same shape as tracker ledger item 12
(`_parallel.py::_run_parallel_e2e`, also dead-but-tested, also a decide:
delete-or-wire-up call for Brian). If `check_workspace_access` is supposed
to be *the* general-purpose access gate for non-annotation pages, its
current unreachability is worth flagging on its own regardless of this
report's indexing focus.

### C. `_resolve_workspace_course`'s sequential round trips (only relevant if §5.B decides "wire it up")

`acl.py::_resolve_workspace_course` walks Workspace → Activity → Week →
Course via up to four sequential `session.get()` calls. Every hop is a PK
lookup (no index gap), so this is a round-trip-count observation, not an
indexing one — and it's currently dead code per §5.B, so it costs nothing
in production today. `resolve_annotation_context` solves the identical
problem with one joined query (`workspaces.py:459-482`); if `check_workspace_access`
is revived, the fix is "reuse that pattern," not "add an index." Feeds the
deferred `ty-sa-n-plus-one-audit` follow-up issue referenced in the
superseded 2026-04-23 design plan.

### D. Per-row loops instead of batched writes (recurring shape, several sites, none urgent)

All of these are write-side, not read-side, so outside this report's
literal scope — noted because the task asked for "any query shape that
suggests a problem beyond indexing":

- `tags.py::reorder_tags`/`reorder_tag_groups`, `workspace_documents.py::reorder_documents`
  — one `session.get()`+update per item in a caller-supplied order list.
  Item counts are small (tags/documents per workspace), low impact.
- `courses.py::delete_course`, `weeks.py::delete_week` — both carry their
  own `# TODO(perf)` comments already acknowledging "one count query per
  activity" for the student-workspace guard. Corroborated, not
  newly discovered.
- `enrolment.py::_resolve_users`/`_create_enrolments`/`_create_groups_and_memberships`
  — one find-or-create + one enroll + one group-upsert-and-select-back
  **per roster row**. At the loadtest-scale roster size (up to ~1100
  students), a single import run is several thousand round trips. This is
  a real, user-triggered (course-coordinator) admin action with a large N,
  not a rare background task — the most worth revisiting of this group if
  bulk-enrolment latency ever becomes a complaint, but it is a write-batching
  problem, not a missing-index one.
- `cli_loadtest.py::_create_activity_workspaces_for_student` (existence
  check per student × activity, ~8,800 round trips at 1100-student ×
  8-activity scale) and `_fetch_candidate_workspaces` (one session per
  course in a 30-course loop). Both already-covered by existing indices
  (§1); CLI-only, developer-run, out of scope for prioritization.

### E. `list_students_without_workspaces` — plan-shape risk, not a coverage gap

`courses.py::list_students_without_workspaces` (admin analytics) is a
`NOT EXISTS` subquery correlated on `acl.user_id = ce.user_id`, conceptually
re-evaluated once per enrolled student. Every join/filter column already
carries a covering index (§1), so there is no missing-index candidate here
— the open question is whether Postgres produces a cheap Hash/Merge
Anti-Join or degrades to a Nested Loop re-executing the subplan per outer
row at the 1100-student loadtest tier. That's a plan-shape question,
answerable only by `EXPLAIN (ANALYZE, BUFFERS)` against loadtest-scale data,
not by adding an index sight unseen. Add to the measurement queue in §4 if
the admin analytics page is ever reported slow.

### F. Leading-wildcard `LIKE` in `cli_loadtest.py` — an index-*shape* problem, not a coverage gap

`cli_loadtest.py::_print_summary` (loadtest-only, `uv run grimoire loadtest`)
filters `"user".email LIKE '%@test.local'`. This is a distinct problem class
from every other row in this report: a **leading-wildcard** `LIKE` cannot be
served by a plain B-tree index at all (B-tree serves a prefix pattern like
`'foo%'`, never a suffix pattern like `'%foo'`), so `CREATE INDEX ... (email)`
would not change this query's plan regardless of the existing unique index
on `email`. The actual fix, if this predicate is ever hot enough to matter,
is a `pg_trgm` GIN index or a functional index on `reverse(email)` —
neither proposed here since this is CLI-only, developer-run, once-per-invocation
code, ranked below every page-load/admin candidate per the task's own framing.
Noted because the task asked for shapes that suggest a problem beyond
indexing, and "no index of this kind will ever help" is exactly that.

### G. One suspected duplication, checked and ruled out

`pages/annotation/header.py::_render_placement_chip` takes a
`prefetched_ctx: PlacementContext | None` and only calls
`get_placement_context()` (a second DB round trip) when re-rendering after
an explicit `.refresh()` — i.e. after the user edits placement via the
dialog, when a fresh read is actually required. The initial page load uses
the context `resolve_annotation_context` already computed. Not a Class-C
duplicate-registry-pass (per CLAUDE.md's page-load failure-mode taxonomy);
verified by reading the call site rather than assumed from the
function-pair's names.

## Summary

| Frequency class | Candidates found |
|---|---|
| Page-load-critical (Tier 1) | 6 |
| Page-load-adjacent / bounded background (Tier 2) | 2 |
| Evaluated, not recommended (Tier 3) | 5 column groups, explicit reasoning |
| FK columns without index | 3, all low-risk reference-table targets |
| Beyond-indexing findings | 7 (A-G): one already-tracked FTS gap, 14
  confirmed unreachable/dead-code functions across `acl.py`/`activities.py`/
  `workspaces.py`/`auth/__init__.py` (incl. the apparent ACL-gate entry-point
  chain) plus 2 more flagged with lower confidence, one dead-code round-trip
  chain, five write-batching sites, one correlated-subquery plan-shape
  risk, one index-shape mismatch (leading-wildcard `LIKE`), one ruled-out
  false lead |

Query shapes suggesting a problem beyond indexing, surfaced per the task
brief: **§5.A** (FTS gap, already tracked as #316 phase-2), **§5.B**
(the `check_workspace_access`/`resolve_permission` chain — 5 functions —
plus 9 further functions across `acl.py`/`activities.py`/`workspaces.py`
have zero production callers — worth a decision independent of this
report's indexing scope), **§5.E** (`list_students_without_workspaces`'s
correlated subquery — measure the plan shape before deciding anything), and
**§5.F** (`cli_loadtest.py`'s leading-wildcard `LIKE` — no B-tree index
could ever serve this predicate; a different index type entirely, and only
worth building if this CLI-only query ever becomes a bottleneck).

## §6. Measurement results, 2026-08-17

**Environment.** Dev database `promptgrimoire_ty_bump` (this worktree's
branch-suffixed DB per `config.py`'s per-worktree isolation — never
production). It held schema but zero data at the start of this pass;
`alembic upgrade head` brought it to the 41-migration HEAD, then
`uv run load-test-data` (the correct invocation — `uv run grimoire
loadtest` from the task brief does not exist; see "Surprising things"
below) seeded it. All Tier-1/Tier-2 tables `ANALYZE`d before every BEFORE
run and again after every `CREATE INDEX`. Every `EXPLAIN (ANALYZE,
BUFFERS)` below ran 3× per DR5 discipline; costs/times quoted are the
median run except where noted. **All 8 candidate indices remain live in
`promptgrimoire_ty_bump` as of this writing. No Alembic migration file was
created** — migration authoring is deferred until the branch stack is
assembled (this branch rebases onto another; chain order matters), per the
task brief's explicit constraint.

**Actual seeded scale** (`uv run load-test-data`, full run, ~4 min):
3 courses (LT-LAWS1100: 1100 students, LT-LAWS2200: 80, LT-ARTS1000: 15),
1159 users, 1201 enrollments, 14 activities, 7683 workspaces (5663
activity-placed + 2020 loose), 17610 workspace_documents, 77 ACL shares,
1187 `shared_with_class` workspaces. `export_job` stayed at **0 rows** —
`load-test-data` does not seed it at all (§ Surprising things).

### Verdict table

| # | Candidate | Chosen? | Cost before → after | Time before → after (median) | Buffers before → after | Verdict |
|---|---|---|---|---|---|---|
| 1 | `user(id) WHERE is_admin` | Yes — Index Only Scan | 28.59 → 4.14 | 0.105 ms → 0.032 ms | 17 hit → 2 hit | **PROMOTE** |
| 2a | `workspace(activity_id) WHERE shared_with_class` | Yes — Bitmap Index Scan | 1870.47 → 1108.69 (whole-query) | 5.09 ms → 3.15 ms | ~1542 hit (workspace scan alone) → 596 hit (whole query) | **PROMOTE** |
| 2b | `workspace(course_id) WHERE shared_with_class` | Partially — see note | 790.78 → 355.61 (whole-query) | 2.70 ms → 0.09 ms | 997 hit → 472 hit | **PROMOTE** (with caveat) |
| 3 | `workspace(id) WHERE search_dirty` | Yes — Bitmap Index Scan | 3059.60 → 191.42 | 5.23 ms → 0.15 ms | 2971 hit → 17 hit | **PROMOTE** |
| 4 | `workspace_document(workspace_id, order_index)` | Yes, but Sort node stayed | 16.02 → 16.02 (unchanged) | 0.14 ms → 0.07 ms (noise) | 5-6 → 4-6 (noise) | **REJECT** |
| 5a | `tag_group(workspace_id, order_index)` | Yes, but Sort node stayed | 11.73 → 11.73 (unchanged) | 0.08 ms → 0.08 ms (noise) | 6 → 6 (noise) | **REJECT** |
| 5b | `tag(workspace_id, order_index)` | Yes, but Sort node stayed | 30.60 → 30.60 (unchanged) | 0.21 ms → 0.06 ms (noise) | 6 → 6 (noise) | **REJECT** |
| 6 | `export_job(user_id, workspace_id)` | N/A — 0 rows | 0.02 → 0.02 | 0.028 ms → 0.027 ms | 3 → 3 | **INCONCLUSIVE** — table empty at this data scale |
| 7 | `export_job(status, created_at)` | N/A — 0 rows | trivial both | trivial both | trivial both | **INCONCLUSIVE** — table empty at this data scale |
| 8 | `activity(week_id, created_at)` | No — still Seq Scan | 1.21 → 1.21 (unchanged) | 0.11 ms → 0.09 ms (noise) | 4 → 4 (unchanged) | **REJECT** |

**§5.E plan-shape answer:** `list_students_without_workspaces` at
LT-LAWS1100 scale (1100 enrolled students, 7683 workspaces, 7683 owner
`acl_entry` rows) produces a **`Hash Right Anti Join`**, not a Nested
Loop. Postgres flattens the correlated `NOT EXISTS` subquery into a
proper anti-join, building the hash table once from the
`workspace ⋈ acl_entry ⋈ activity ⋈ week` chain (dominant cost: two Seq
Scans, `workspace` at 3047.97 and `acl_entry` at 186.00) rather than
re-executing the subplan per outer row. Total query cost 3611.59, median
execution 7.9-8.5 ms, zero rows returned (every enrolled non-staff student
in this course already owns a workspace, so there's nothing to list — the
query still had to build the full anti-join to determine that). This
confirms the report's §5.E hope: no missing-index candidate here, and the
plan-shape risk it flagged does not materialise at loadtest scale.

### Detail per candidate

**#1 `user.is_admin`.** Only 1 admin user existed in the 1159-row seeded
set (report's own §3 Tier-1 text assumed "~5-10 admins" — see Surprising
things). `Index Only Scan` chosen cleanly, `Heap Fetches: 0`. Clear win
even at this small scale; the report's own justification ("tens of
thousands of rows") did not hold at the actual seeded scale (§ Surprising
things), but the win holds regardless of table size once `is_admin` stays
a small minority.

**#2a/2b `workspace.shared_with_class`.** Measured against LT-LAWS1100
(1100 students) using the exact representative query from §4, with a
real enrolled-but-non-owning student UUID as `:requesting_user_uuid`.
`shared_with_class` is **not** a small subset at this scale — 1187 of
7697 workspaces (15.4%) — so a naive `col = true` index risked the
planner preferring the existing seq scan (high-selectivity partial
indices can lose to seq scans). It didn't: the planner picked
`ix_workspace_activity_id_shared` via `Bitmap Index Scan` inside a
per-activity `Nested Loop`, because the partial index's *population* is
exactly the 1187-row `shared_with_class` set, independent of the 15.4%
figure against the whole table. For the loose-workspace variant (2b),
`pg_stat_user_indexes` showed **`ix_workspace_course_id_shared` at
`idx_scan = 0`** after all three representative-query runs — the planner
instead reused `ix_workspace_activity_id_shared` (matching `activity_id
IS NULL` directly) `BitmapAnd`-ed with the pre-existing plain
`ix_workspace_course_id`. Isolating a direct
`WHERE course_id = :c AND shared_with_class = true` query (no
`activity_id IS NULL` companion predicate) *did* select
`ix_workspace_course_id_shared` (`Index Scan`, cost 524.86, 0.07 ms) —
so the index is real and gets chosen for its own query shape, just not
inside the specific §4 loose-workspace representative query, where a
different combination of existing + new indices already covers it. Net
effect on the query the report cared about: PROMOTE both, but note 2b's
value is partly redundant with 2a's for this exact call site — flag for
whoever writes the migration to decide if 2b earns its write-amplification
cost given 2a already covers the compound case in practice.

**#3 `workspace.search_dirty`.** First BEFORE run showed **all 7697
workspaces** with `search_dirty = true` — 100% of the table, a seeding
artifact (the background `search_worker.py` poller had never run against
this freshly-seeded, freshly-migrated dev DB — see Surprising things). At
100% selectivity a partial index gives zero benefit over a seq scan by
construction, so that measurement would have been misleading either way.
Corrected to a realistic steady-state backlog by setting
`search_dirty = false` on all rows then `true` on a random 50 (0.65% of
the table, modelling the small backlog a 30s-interval worker leaves under
normal load) before re-measuring. This is a **deliberate, disclosed data
mutation** made for measurement validity, not a change requested by the
task — recorded here so it isn't mistaken for organic seed data if anyone
re-queries `promptgrimoire_ty_bump` later. At corrected selectivity: the
clearest win of the whole set — cost 3059.60 → 191.42 (16×), execution
~5.7 ms → ~0.15 ms (30-40×), buffers 2971 hit → 17 hit.

**#4/5a/5b (`workspace_document`, `tag_group`, `tag` — `(workspace_id,
order_index)`).** Real per-workspace row counts turned out to be tiny:
`workspace_document` averages **2.29** rows/workspace (max 3);
`tag_group` is **exactly 2** per workspace, no variance; `tag` is
**exactly 7** per workspace, no variance (loadtest data generation is
deterministic per workspace here, not sampled). This is precisely the
Tier-3 "weeks capped at ~13-20, sorts in microseconds regardless of
index" pattern the report itself used to reject other candidates — it
just wasn't applied to these three before the row counts were known. All
three planner choices did switch the underlying `Bitmap Index Scan` to
the new composite index, but the `Sort` node above it never disappeared
(cost identical before/after to 2 decimal places) because there are too
few rows for an index-order scan to be worth choosing over a quicksort of
2-7 rows. REJECT all three — the report's Tier-1 classification for #4/5a/5b
was frequency-driven (called on every page load) without checking the
per-workspace row count, which is the same mistake the report's own
method explicitly warns against in the Tier-3 section for `week`.

**#6/7 `export_job`.** Zero rows — `load-test-data` never populates this
table (§ Surprising things). Both BEFORE and AFTER plans are trivial
`Seq Scan (cost=0.00..0.00)` regardless of index; no signal either
direction. Indices created and left in place per the task's Tier-1/Tier-2
scope, but genuinely unmeasured — re-run once `export_job` has
loadtest-representative data (either extend `cli_loadtest.py` to seed
some, or measure against a DB that has organic dev usage).

**#8 `activity.week_id`.** Whole `activity` table is 14 rows; max 3
activities/week (avg 2.00, matches the report's own Tier-2 "activities
per week is small" caveat exactly). Planner didn't even switch indices —
still `Seq Scan`, cost unchanged 1.18→1.18. REJECT, exactly as the report
predicted going in; measured for completeness per the task brief.

### Surprising things

1. **`uv run grimoire loadtest` does not exist.** The task brief's
   suggested invocation is wrong — there is no `loadtest` subcommand
   under `grimoire`. The actual entry point is `uv run load-test-data`
   (a `[project.scripts]` entry in `pyproject.toml` wrapping
   `cli_loadtest.py:load_test_data`), confirmed by reading
   `pyproject.toml` and `cli_loadtest.py` directly. It has no `--help`
   handler either — passing `--help` runs the full seed with `--help`
   silently ignored as an unrecognised sys.argv token... except in this
   case it failed first on `DATABASE__URL` pointing at a database that
   didn't exist yet (see next point), which is what actually surfaced the
   real command name.
2. **No dev database existed for this worktree.** Per-worktree DB
   isolation (`config.py::_suffix_db_url`) means branch `ty-bump` reads
   `promptgrimoire_ty_bump`, which had never been created — not even an
   empty one (only `promptgrimoire_test_ty_bump` and its
   `_clone_source` template existed, both test-lane artifacts). Had to
   `createdb` and `alembic upgrade head` (all 41 migrations, clean run,
   no errors) before seeding could start. `promptgrimoire_dev` (the
   template I first tried) turned out to be empty too — every
   schema-bearing dev DB on this box is worktree- or test-scoped; there
   is no shared baseline dev DB with organic data at all.
3. **The report's "30 courses" scale assumption doesn't match the actual
   generator.** `cli_loadtest.py::COURSE_DEFS` is a fixed 3-course list
   (1100/80/15 students) — there is no configurable course count. The
   report's Tier-3 reasoning for `course.is_archived`/`course.semester`
   ("30 courses total even at loadtest scale") appears to have
   generalised from a different figure (course *capacity*, or a stale
   assumption) rather than reading `COURSE_DEFS` directly. Doesn't change
   any Tier-3 verdict — 3 courses is smaller than 30, so the "trivial
   either way" conclusion holds even more strongly — but it's worth
   correcting for whoever reads this report next.
4. **Real `user` table scale (1159 rows) is nowhere near the report's
   "tens of thousands" claim for candidate #1**, and only 1 of those 1159
   is an admin (report assumed "~5-10"). The mechanism justification
   (full seq scan for a rare boolean) is still correct in kind, and the
   measured win (§ #1 above) holds regardless — but the magnitude
   argument in the original report was inflated relative to what the
   project's own loadtest generator actually produces. If the "tens of
   thousands" figure was meant to model post-launch, multi-semester
   accumulation rather than a single loadtest run, that's worth stating
   explicitly next time rather than presenting it as the loadtest number.
5. **`workspace.search_dirty` was 100% `true` for the entire table
   immediately after seeding** (all 7697 rows) — not a "continuous
   background poll keeps this small" steady state at all, but a seeding
   artifact from the fact that nothing had run `search_worker.py`'s
   poller against this DB yet. Anyone measuring this candidate against a
   freshly-seeded DB without correcting for it would get a **wrong
   REJECT** (100%-selective partial index is worse than useless) for what
   is actually the strongest PROMOTE in the whole set once the backlog is
   corrected to a realistic size. This is the single most consequential
   methodological trap in this measurement pass — flagging prominently
   in case anyone else runs `load-test-data` fresh and measures this
   candidate without noticing.
6. **`export_job` has zero loadtest coverage.** Not a bug in this task,
   but worth a decision: either `cli_loadtest.py` should seed a
   representative export-job backlog (queued/running/completed mix) so
   candidates #6/#7 and the export worker's own query shapes can ever be
   measured against realistic data, or that's explicitly out of scope for
   the load-test generator and someone should say so in its docstring.
7. **Real per-workspace `workspace_document`/`tag_group`/`tag` counts are
   far smaller than the report's row-count framing implied** (§ #4/5a/5b
   above) — this is the same failure mode the report itself named and
   guarded against for `week` in Tier 3, just not applied to these three
   before now. Worth a general lesson for future index-candidate audits
   on this codebase: check the *per-parent* row count from real data
   before trusting "called on every page load" as sufficient justification
   for a sort-covering index, even when the call-frequency evidence is
   solid.
