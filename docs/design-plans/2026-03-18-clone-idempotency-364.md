# Clone Idempotency and Duplicate-Workspace Prevention

**GitHub Issue:** #364

## Summary

When a student clicks "Start Activity" in PromptGrimoire, the application clones a template workspace — copying its documents, tags, and collaborative annotation state — to create a personal copy for that student. This clone operation currently has no guard against being called twice: if a student double-clicks the button, NiceGUI's async event loop processes both clicks as concurrent tasks, and both proceed to clone because neither can see the other's uncommitted database transaction. The result is two separate workspaces for the same student in the same activity. The browser navigates to whichever finishes last; the other is orphaned and invisible but persists in the database.

The fix has two parts with distinct risk profiles. Phase 1 addresses correctness: a PostgreSQL advisory lock serialises concurrent clone attempts for the same `(activity_id, user_id)` pair, and an existence check inside that lock allows the second caller to return the already-created workspace instead of creating a duplicate. This changes only the guard logic, not the clone internals. Phase 2 addresses a separate performance problem in those internals: the current implementation issues one database round-trip per row (document, tag group, tag), when the entire operation could be expressed as a small fixed number of bulk `INSERT ... SELECT` statements. Phase 2 is independently revertable — Phase 1's correctness guarantee holds regardless. A third phase provides a detection query for duplicate workspaces that may already exist in production, where automated deletion is unsafe because either clone might contain student edits.

## Definition of Done

1. `clone_workspace_from_activity` is idempotent: calling it N times for the same `(activity_id, user_id)` returns the same workspace.
2. The invariant holds under concurrent `asyncio.gather` calls.
3. Clone internals use INSERT ... SELECT — round-trip count is O(1) not O(entities).
4. Existing callers (`_start_activity`, `_start_activity_handler`) work without modification.
5. Falsification tests replaced with idempotency-asserting tests.
6. Existing duplicate detection query documented (automated deletion is out of scope — duplicates require manual review).

## Acceptance Criteria

### clone-idempotency-364.AC1: Sequential idempotency
- **clone-idempotency-364.AC1.1 Success:** Calling `clone_workspace_from_activity` twice sequentially for the same `(activity_id, user_id)` returns the same workspace ID both times.

### clone-idempotency-364.AC2: Concurrent idempotency
- **clone-idempotency-364.AC2.1 Success:** Two concurrent `asyncio.gather` calls to `clone_workspace_from_activity` for the same `(activity_id, user_id)` return the same workspace ID.

### clone-idempotency-364.AC3: Clone correctness (regression gate)
- **clone-idempotency-364.AC3.1 Success:** A single clone produces a workspace with all template documents, tag groups, tags, and CRDT state correctly copied.
- **clone-idempotency-364.AC3.2 Success:** Document ID mapping is correct (template doc ID → cloned doc ID).
- **clone-idempotency-364.AC3.3 Success:** Tag group IDs are remapped in cloned tags.
- **clone-idempotency-364.AC3.4 Success:** CRDT highlights, comments, and general notes are replayed with remapped IDs.

### clone-idempotency-364.AC4: Constant round-trip count
- **clone-idempotency-364.AC4.1 Verification:** Round-trip count is constant regardless of template size (no per-row flush loops), verified by a query-counting test fixture that asserts the same number of statements for templates of different sizes.

### clone-idempotency-364.AC5: Return contract
- **clone-idempotency-364.AC5.1 Success:** Fresh clone returns `(workspace, {template_doc_id: cloned_doc_id})` with `len(doc_id_map) == len(template_documents)` — a non-empty map for a non-empty template. This guards against Phase 2 regressions that silently drop documents.
- **clone-idempotency-364.AC5.2 Success:** Idempotent return (existing workspace) returns `(workspace, {})`.

### clone-idempotency-364.AC6: Caller compatibility
- **clone-idempotency-364.AC6.1 Verification:** No changes to `_start_activity` or `_start_activity_handler` in the diff. Callers work without modification.

### clone-idempotency-364.AC7: Duplicate detection
- **clone-idempotency-364.AC7.1 Success:** Detection query correctly identifies `(activity_id, user_id)` pairs with multiple owner-ACL workspaces in test data with known duplicates.

## Glossary

- **Activity**: A teaching activity configured by an instructor, which has a template workspace that students clone when they start.
- **Workspace**: A personal copy of an activity's template documents, owned by one student. Contains documents, tags, tag groups, and CRDT state.
- **Template workspace**: The instructor-authored workspace that serves as the source for cloning. Referenced by `activity.template_workspace_id`.
- **ACLEntry**: Access control list entry — a row linking a user to a workspace (or team) with a named permission level (e.g., `owner`). The only record of who owns a workspace.
- **clone_workspace_from_activity**: The database function in `db/workspaces.py` that copies a template workspace and all its contents to a new workspace owned by the requesting student.
- **doc_id_map / group_id_map**: Python dicts mapping old (template) row IDs to new (cloned) row IDs. Required to rewrite ID references inside CRDT state after copying.
- **CRDT / CRDT replay**: Conflict-free Replicated Data Type — the binary data structure (via `pycrdt`) that stores collaborative annotation state (highlights, comments, notes). "Replay" refers to deserialising the template's CRDT, remapping document and tag IDs to cloned equivalents, and reserialising into the new workspace.
- **Advisory lock (`pg_advisory_xact_lock`)**: A PostgreSQL mechanism for application-level mutual exclusion. Unlike row locks, advisory locks are keyed by arbitrary integers chosen by the application. Transaction-scoped: auto-released on commit or rollback.
- **TOCTOU race (Time-Of-Check / Time-Of-Use)**: A concurrency bug where a condition checked at one point ("does this user have a workspace?") is no longer valid at the point of action ("create a workspace") because another concurrent request changed state in between.
- **READ COMMITTED isolation**: PostgreSQL's default transaction isolation level. A query only sees rows committed before that query began — not rows written by concurrent transactions that haven't committed yet.
- **get_session()**: An async context manager in `db/engine.py` that opens a database transaction, auto-commits on success, and rolls back on exception. Each call is one transaction.
- **INSERT ... SELECT**: A SQL pattern that copies rows from one table to another in a single server-side statement, without round-tripping each row through the application.
- **RETURNING clause**: A PostgreSQL SQL extension that returns column values from inserted rows in the same statement — used to get new IDs assigned to cloned rows without a second SELECT.
- **falsification test**: A test written to assert that a bug exists (e.g., asserting two distinct workspace IDs are returned from a double clone). These confirm the problem and are replaced by idempotency-asserting tests once the fix is in.

## Problem Statement

### The Call Flow

Two UI handlers trigger workspace cloning:

1. `pages/navigator/_cards.py:_start_activity` (line 348)
2. `pages/courses.py:_start_activity_handler` (line 247)

Both follow the same pattern:

```
Step 1: get_user_workspace_for_activity(activity_id, user_id)  → own transaction (get_session)
Step 2: check_clone_eligibility(activity_id, user_id)          → own transaction (get_session)
Step 3: clone_workspace_from_activity(activity_id, user_id)    → own transaction (get_session)
```

Each step opens and commits its own database transaction via `get_session()` (db/engine.py:268), which is an `@asynccontextmanager` that auto-commits on successful exit.

### The Race

Under NiceGUI's async event loop, a double-click sends two WebSocket events processed as concurrent async tasks. The sequence is:

```
Request A: Step 1 → returns None (no workspace yet)    → commits
Request B: Step 1 → returns None (A hasn't committed)  → commits
Request A: Step 3 → creates Workspace W1, ACL entry    → commits → navigates to W1
Request B: Step 3 → creates Workspace W2, ACL entry    → commits → navigates to W2
```

PostgreSQL's default READ COMMITTED isolation means Request B's Step 1 cannot see Request A's uncommitted Workspace. Both proceed to clone. The student's browser ends up on whichever navigation fires last — typically W2.

### Why No Constraint Catches This

The existing partial unique index `uq_acl_entry_workspace_user` enforces `UNIQUE(workspace_id, user_id) WHERE workspace_id IS NOT NULL`. This prevents two ACL entries for the **same workspace** and same user. It does **not** prevent the same user owning **two different workspaces** in the same activity — each clone creates a new Workspace row with a distinct `id`, so each gets its own non-conflicting ACL entry.

The uniqueness the system assumes ("one workspace per student per activity") is not enforced at the database level. It is enforced only by the application-layer check in Step 1, which is vulnerable to the TOCTOU race described above.

### The Query Bloat

`clone_workspace_from_activity` (db/workspaces.py:800-912) issues individual `session.add()` + `await session.flush()` for every row:

| Queries | Purpose |
|---------|---------|
| 2 | SELECT activity, SELECT template workspace |
| 1 | INSERT workspace + flush |
| 1 | INSERT acl_entry + flush |
| 1 | SELECT template documents |
| D | INSERT document + flush (per document) |
| 1 | SELECT template tag groups |
| G | INSERT tag_group + flush (per group) |
| 1 | SELECT template tags |
| T | INSERT tag + flush (per tag) |
| 1 | flush (counters + CRDT) |
| 1 | refresh clone |

**Total: 9 + D + G + T round-trips.** A template with 3 docs, 2 groups, 5 tags = 19 round-trips. Each flush is a network round-trip within the transaction.

The per-row flushes exist to read back generated IDs for the mapping dicts. But all models use `default_factory=uuid4` — IDs are generated in Python before the INSERT. The flushes are unnecessary.

More fundamentally, cloning rows from one workspace to another is an INSERT ... SELECT, not a Python loop pulling rows out and pushing them back.

## Verified Hypotheses

Three hypotheses were formulated and tested. All confirmed.

### H1: `clone_workspace_from_activity` has no existence check

**Claim:** The function unconditionally creates a new workspace. Calling it twice sequentially for the same `(activity_id, user_id)` creates two separate workspaces.

**Evidence:** `test_sequential_double_clone_creates_duplicates` — calls `clone_workspace_from_activity` twice with the same arguments, asserts the returned workspace IDs differ. **Passes.**

**Code reference:** `db/workspaces.py:800-818` — opens a session, fetches the activity and template, creates a `Workspace(activity_id=...)`, and flushes. No query checks whether a workspace already exists for this user.

### H2: No database constraint prevents duplicate (activity_id, user_id) ownership

**Claim:** Both duplicate workspaces persist in the database with separate owner ACL entries. No unique index, check constraint, or trigger prevents this.

**Evidence:** `test_both_clones_persist_with_owner_acl` — after two sequential clones, queries the database for both workspaces and their ACL entries. Both exist with distinct owner ACL entries. **Passes.**

**Schema reference:** `Workspace` has no unique constraint involving `activity_id` scoped to a user. `activity_id` lives on `Workspace`; user ownership lives on `ACLEntry`. The "one workspace per student per activity" invariant spans two tables with no cross-table constraint.

### H3: Concurrent clones both succeed

**Claim:** Two concurrent calls to `clone_workspace_from_activity` for the same `(activity_id, user_id)` both create separate workspaces.

**Evidence:** `test_concurrent_clones_both_succeed` — uses `asyncio.gather` to clone concurrently, both succeed with distinct workspace IDs. **Passes.**

**Note:** The mechanism (READ COMMITTED visibility of uncommitted rows) follows from PostgreSQL's isolation semantics but was not independently proven with a deterministic barrier test. The gather test demonstrates the race is exploitable; the exact interleaving is scheduler-dependent.

### Falsification tests

Three tests in `tests/integration/test_clone_idempotency.py`. They demonstrate the bug by asserting that duplicate workspaces are created. After the fix is implemented, these should be replaced with tests asserting idempotent behaviour.

## Scope of Impact

- **User-facing:** A student who double-clicks "Start Activity" gets two workspaces. The browser navigates to whichever clone completes last. The other is orphaned — invisible in the navigator (`get_user_workspace_for_activity` returns `.first()` with no ordering) but consuming storage (workspace, documents, tags, CRDT state).
- **Data integrity:** No data corruption. The duplicate is a valid workspace. But `has_student_workspaces()` counts it, inflating delete-guard counts.
- **Frequency:** Low under normal use (single-click). Higher risk with slow networks, impatient users, or browser retry-on-timeout.
- **Existing duplicates:** Production may already contain duplicates. The student may have edited either the older or newer clone — there is no safe automated rule for which to keep. Remediation requires manual review per-case.

## Architecture

The fix is split into two phases with distinct risk profiles:

**Phase 1 (correctness):** Advisory lock + existence check inside `clone_workspace_from_activity`. Closes the TOCTOU race with minimal code change. Low risk — adds a lock and a query before the existing clone logic.

**Phase 2 (performance):** Rewrite clone internals to use INSERT ... SELECT instead of per-row flush loops. Reduces round-trips from O(entities) to O(1). Higher risk — touches the entire clone pipeline. Phase 1 already works independently; Phase 2 is an optimisation that can be reverted without losing correctness.

### Advisory lock specification

```sql
SELECT pg_advisory_xact_lock(
    hashtext('clone_workspace_from_activity'),
    hashtext(cast(:activity_id AS text) || '-' || cast(:user_id AS text))
)
```

- **First argument:** Fixed namespace hash. Using the function name as the namespace string ensures no collision with advisory locks used elsewhere.
- **Second argument:** Hash of `{activity_id}-{user_id}` with a `-` separator to prevent UUID concatenation ambiguity (e.g., `...abc` + `def...` vs `...ab` + `cdef...`).
- **Scope:** Transaction-level (`pg_advisory_xact_lock`). Auto-releases on commit or rollback. No manual cleanup needed.
- **Contention:** Only same-user-same-activity clones serialise. Different users cloning the same activity proceed in parallel.
- **Hash collisions:** `hashtext` returns 32-bit. Two unrelated `(activity_id, user_id)` pairs could collide, causing false serialisation (unnecessary waiting). This does not affect correctness — the existence check inside the lock is the actual guard. The probability is negligible for the expected workload (hundreds of students, not millions).

### Existence check

Inside the locked transaction, before any clone work:

```sql
SELECT workspace.id FROM workspace
JOIN acl_entry ON acl_entry.workspace_id = workspace.id
WHERE workspace.activity_id = :activity_id
  AND acl_entry.user_id = :user_id
  AND acl_entry.permission = 'owner'
LIMIT 1
```

If a workspace is found, return it immediately with an empty doc_id_map (`{}`).

### Return contract

`clone_workspace_from_activity` returns `tuple[Workspace, dict[UUID, UUID]]`. On the idempotent path (existing workspace found), the dict is `{}`. Neither current caller (`_start_activity`, `_start_activity_handler`) uses the doc_id_map — both navigate to `workspace.id` only. The docstring must document this dual behaviour.

**Note:** A fresh clone of a zero-document template also returns `{}` today (per `tests/integration/test_workspace_cloning.py:245`). Callers therefore cannot distinguish "idempotent hit" from "new clone, zero documents" via the dict alone. This is acceptable because no current caller needs the distinction. If a future caller does, a structured result type can be introduced then.

### INSERT ... SELECT rewrite (Phase 2)

Replace per-row add+flush loops with bulk SQL:

- **Documents:** `INSERT INTO workspace_document (...) SELECT gen_random_uuid(), :clone_id, ... FROM workspace_document WHERE workspace_id = :template_id RETURNING id, source_document_id` — yields the doc_id_map directly from `source_document_id`.
- **TagGroups:** INSERT ... SELECT with RETURNING, paired to build group_id_map (old→new) via a CTE that joins on the template's group rows.
- **Tags:** INSERT ... SELECT with group_id remapping via JOIN on the group map CTE.

**CRDT replay stays in Python.** `_replay_crdt_state` does binary pycrdt manipulation with remapped IDs. It consumes the three ID maps built above. This cannot move to SQL.

**Target:** ~7 statements regardless of entity count (vs 9 + D + G + T today).

### Existing duplicate remediation

Automated deletion is **unsafe**. In the race scenario, the student's browser navigates to whichever clone finishes last — that may be the newer one. The student may have edited either clone. There is no reliable heuristic for which to keep.

**Approach:** Detection query + manual review.

```sql
SELECT w.activity_id, ae.user_id, array_agg(w.id ORDER BY w.created_at) AS workspace_ids,
       count(*) AS duplicate_count
FROM workspace w
JOIN acl_entry ae ON ae.workspace_id = w.id AND ae.permission = 'owner'
WHERE w.activity_id IS NOT NULL
GROUP BY w.activity_id, ae.user_id
HAVING count(*) > 1;
```

This query will be documented in the design plan and can be exposed as a CLI command (`grimoire admin duplicates`) in a follow-up. No automated deletion in this PR.

### Approaches considered and rejected

- **B: Materialised `owner_user_id` on Workspace** — Creates two sources of truth for ownership (column vs ACLEntry). Every owner mutation path (clone, share, transfer) must keep both in sync. Backfill required. Blast radius touches ACL resolution (`db/acl.py:225`), navigator queries, sharing rules (`db/acl.py:453`), delete guards. Rejected as over-engineered for the problem.
- **A: SELECT FOR UPDATE on Activity row** — Serialises ALL clones for an activity, not just same-user. Unnecessary contention for the 30-student-first-login scenario where many students start simultaneously. Advisory lock is narrower.
- **Client-side button disable** — Defence in depth but not a substitute for server-side protection. Worth adding but not in scope for this PR.
- **Automated duplicate deletion** — Unsafe. Cannot determine which duplicate the student edited. See "Existing duplicate remediation" above.

## Existing Patterns

**Transaction-scoped operations:** All DB functions use `async with get_session()` for a single transaction. The advisory lock follows this — `pg_advisory_xact_lock` is scoped to the transaction lifetime.

**Existing advisory lock usage:** None found in the codebase. This is the first use of PostgreSQL advisory locks. The pattern is well-documented in PostgreSQL and used for exactly this kind of application-level serialisation.

**Existing idempotency patterns:** `db/enrolment.py` uses upsert (`ON CONFLICT DO UPDATE`) for course enrolment — conceptually similar (prevent duplicate enrolment). The clone case is more complex because it spans two tables (Workspace + ACLEntry) and involves bulk child-row creation.

**Existing INSERT ... SELECT usage:** None found. Current bulk operations use Python loops with per-row flush. Phase 2 introduces this pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Idempotent Clone (Correctness Fix)

**Goal:** Make `clone_workspace_from_activity` idempotent via advisory lock + existence check. Minimal diff — no changes to clone internals.

**Components:**
- Advisory lock acquisition at start of `clone_workspace_from_activity` in `src/promptgrimoire/db/workspaces.py`
- Existence check (SELECT workspace via ACL join) before any clone work
- Early return with `(existing_workspace, {})` on idempotent hit
- Updated docstring documenting dual return behaviour

**Dependencies:** None (first phase)

**Covers:** clone-idempotency-364.AC1, clone-idempotency-364.AC2, clone-idempotency-364.AC5, clone-idempotency-364.AC6

**Done when:**
- Sequential double clone returns same workspace ID
- Concurrent (gather) double clone returns same workspace ID
- Existing clone test suite passes without regression
- Falsification tests replaced with idempotency-asserting tests
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: INSERT ... SELECT Rewrite (Performance)

**Goal:** Replace per-row flush loops with bulk INSERT ... SELECT statements. Reduce round-trips from O(entities) to O(1).

**Components:**
- Document cloning via INSERT ... SELECT with RETURNING in `src/promptgrimoire/db/workspaces.py`
- TagGroup cloning via INSERT ... SELECT with RETURNING + CTE for ID mapping
- Tag cloning via INSERT ... SELECT with group_id remapping JOIN
- Workspace counter update (`next_tag_order`, `next_group_order`)
- CRDT replay unchanged — consumes ID maps from RETURNING clauses

**Dependencies:** Phase 1 (advisory lock already in place, reduces risk of concurrent issues during rewrite)

**Covers:** clone-idempotency-364.AC3, clone-idempotency-364.AC4

**Done when:**
- All existing clone tests pass (documents, tags, tag groups, CRDT, provenance)
- No per-row flush loops remain in clone path
- Round-trip count verified by query-counting test
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Duplicate Detection

**Goal:** Provide a detection query for pre-existing duplicate workspaces.

**Components:**
- Detection query documented in design plan (see Architecture § Existing duplicate remediation)
- Optional: CLI command `grimoire admin duplicates` in `src/promptgrimoire/cli/admin.py`

**Dependencies:** None (independent of Phases 1-2, but logically follows)

**Covers:** clone-idempotency-364.AC7

**Done when:**
- Detection query returns correct results against test data with known duplicates
- Query or CLI command documented
<!-- END_PHASE_3 -->

## Additional Considerations

**Phase 2 is independently revertable.** If the INSERT ... SELECT rewrite introduces regressions, it can be reverted without losing the correctness fix from Phase 1. They are separate commits.

**No Alembic migration required.** Advisory locks are runtime-only — no schema changes. The INSERT ... SELECT rewrite changes application SQL, not the schema.

**Future consideration: unique constraint.** A partial unique index enforcing one-owner-workspace-per-activity would provide belt-and-suspenders protection. This requires solving the cross-table problem (`activity_id` on Workspace, `user_id` on ACLEntry) and cleaning up existing duplicates first. Deferred as a separate issue.
