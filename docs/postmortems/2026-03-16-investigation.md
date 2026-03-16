# Investigation: 2026-03-16 Gateway Failures

*Status: Phase 3b (execution path audit) and Phase 3c (claim verification) in progress.*
*Investigator: Claude (systematic-debugging skill), peer-reviewed by Codex*

## Incident Summary

Between ~11:08-11:14 AEDT on 2026-03-16, ~30 students experienced "cannot access the app" during a live class. 52 DB session rollback errors, 22 JS timeout errors, and 206 "annotation not ready" warnings were logged. Server did not crash (PID 885075 stable). Two students had CRDT tags removed by the reconciliation scrub — confirmed data loss.

## Actual User Counts (from journal)

- **49 unique students** logged in between 11:00-11:15
- **30 students** in the first 60 seconds (11:00:50-11:01:54)
- Peak login rate: 22 logins in the 11:01 minute
- Login burst ended ~11:02; DB errors didn't start until 11:08:41 (7 min gap)
- 3 more logins at 11:11-11:12 (students retrying after errors?)

## Failure Sequence (with confidence ratings)

Each step cites journal evidence. Step 2 includes an inferred link (marked "likely") between uniqueness violations and the CancelledError storm.

### Step 1: Concurrent tag/group creation triggers UniqueViolationError

**Evidence:** `journallog:1183` — `UniqueViolationError: duplicate key value violates unique constraint "uq_tag_workspace_name" DETAIL: Key (workspace_id, name)=(dbf5feaa-..., Important Info) already exists.`

**Mechanism (confirmed from codebase):**

- `db/tags.py:create_tag()` does a plain INSERT with no duplicate check and no ON CONFLICT clause (line 272: `session.add(tag)`, line 273: `await session.flush()`)
- `db/tags.py:create_tag_group()` is identical — plain INSERT, no conflict handling (line 83: `session.add(group)`, line 84: `await session.flush()`)
- `tag_management.py:400` hardcodes `name="New group"` for every "Add group" click — any two students clicking "Add group" on the same workspace will collide
- Tag creation uses `_unique_tag_name(existing_names)` (line 519) which checks a **stale local name set** — the set is populated at page load, not refreshed before each INSERT. The same student's concurrent requests (rapid clicks, retries after error, reconnect) race on the same stale set. Workspaces are per-student, so this is NOT a multi-user race on shared state.

**Error handling gap:** Tag creation (`tag_management_save.py:139-148`) catches `IntegrityError` for `uq_tag_workspace_name` and shows a warning. **Group creation (`tag_management.py:396-407`) only catches `PermissionError`** — `IntegrityError` propagates unhandled to `get_session()` which logs the generic "Database session error, rolling back transaction" and fires the Discord webhook.

**Tag creation errors also hit this path:** Verified in Phase 3b (Path 1 audit): the `IntegrityError` fires inside `get_session()` at `db/tags.py:273` during `session.flush()`. `get_session()` catches it at `engine.py:299`, logs the generic ERROR + Discord webhook, rolls back, and re-raises. `_create_tag_or_notify` in `tag_management_save.py:139` then catches the re-raised exception and shows the user-friendly notification. **Both fire** — the generic error log AND the caller's handler.

**First occurrence:** 11:08:41 (7 minutes after login burst, when students start working with tags)
**Frequency:** 31 `uq_tag_workspace_name` + 8 `uq_tag_group_workspace_name` = 39 uniqueness violations (PG log is authoritative; earlier app journal counts of "49" were inflated by counting constraint name mentions in rich tracebacks)

### Step 2: Rollback cascade invalidates pool connections

**Evidence:** `journallog:7042` (approx) — pool INVALIDATE warnings showing `checked_out=15 overflow=10/10`

Each `UniqueViolationError` causes:
1. `get_session()` catches Exception, calls `logger.exception()` (rich traceback + Discord webhook)
2. `await session.rollback()`
3. Connection returned to pool normally after rollback

Separately, client disconnects (students refreshing after seeing errors) generated `CancelledError` on in-flight DB operations. All 61 pool INVALIDATE events show `exception=CancelledError`, not `IntegrityError`. **Supported:** duplicate writes preceded a cancellation/invalidation storm. **Not supported:** each uniqueness failure directly invalidated a connection. The likely chain is: UniqueViolation → user sees error/timeout → refreshes browser → CancelledError on their other in-flight operations → INVALIDATE.

By 11:09:28, the pool shows `checked_in=0 checked_out=15 overflow=10/10` — fully saturated.

### Step 3: Pool exhaustion causes QueuePool timeouts

**Evidence:** 4 explicit `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00` errors at 11:09:28-11:09:32.

With all 15 connections checked out (some held by erroring sessions, some by normal operations), new DB requests block for 30 seconds then timeout. This is a **secondary failure** caused by Step 1/2.

### Step 4: Event loop saturation causes JS timeouts and page-load failures

**Evidence:**
- 22 `JavaScript did not respond within 1.0 s` errors (11:08-11:14)
- **206** `Response for /annotation not ready after 3.0 seconds` warnings, overwhelmingly at 11:11:55-11:11:59 (48 in one second at 11:11:57)
- 37 `The parent element this slot belongs to has been deleted` errors (NiceGUI UI components destroyed while still being accessed)

The event loop is processing 52 rich tracebacks, 61 pool INVALIDATE events, Discord webhook HTTP calls, and ~30 websocket connections simultaneously. It cannot serve new `/annotation` page loads — they timeout at 3 seconds.

**This is what students experienced as "cannot access the app."**

### Step 5: CRDT/DB divergence causes data loss

**Evidence:** Two confirmed CRDT scrub events:
- `journallog:118679` — `Workspace 9d8a4947: CRDT tag db6e44b0 not in DB, removing` (user 76e7ede0, at 11:12:02)
- `journallog:126627` — `Workspace 62624529: CRDT tag 6c0360d8 not in DB, removing` (user cfa13024, at 11:13:50)

**Mechanism (`annotation_doc.py:870-878`):** On every workspace load, `_reconcile_crdt_with_db()` syncs CRDT state with DB state. Tags present in CRDT but missing from DB are **deleted from CRDT**. If a tag was created in the CRDT (client-side) but the DB INSERT was rolled back (due to UniqueViolation or CancelledError), the next page load will remove that tag from CRDT — along with any highlights the student had applied using it.

**This is confirmed data loss.** Students lost tags and associated highlights.

### Step 6: list.index cascade (UI-level crash)

**Evidence:** 11 `list.index(x): x not in list` errors between 11:11:08-11:12:59, plus 11 `tag_creation_failed` errors (per census table; earlier count of "23" was a mixed line-count artifact).

Likely caused by the tag list UI referencing tags that were removed by the CRDT scrub or rolled back. The UI's in-memory tag list is stale relative to the DB/CRDT state.

## Complete Error Census

| Error Type | Count | Window | Cause |
|---|---|---|---|
| UniqueViolationError (tag) | 31 | 11:08-11:11, 11:14 | Race condition in tag creation (PG log authoritative) |
| UniqueViolationError (group) | 8 | 11:08-11:11, 11:14 | Race condition in group creation (PG log authoritative) |
| CancelledError | ~30 | 11:09-11:10 | Client disconnects during DB ops |
| QueuePool timeout | 4 | 11:09:28-11:09:32 | Pool exhaustion (secondary) |
| JS timeout (1.0s) | 22 | 11:08-11:14 | Event loop saturated |
| Annotation not ready (3.0s) | 206 | 11:11:48-11:12:03 | Event loop saturated |
| Slot deleted | 37 | 11:09-11:14 | UI components destroyed mid-access |
| tag_creation_failed | 11 | 11:09-11:10 | Generic create_tag exception |
| list.index not found | 11 | 11:11-11:13 | Stale UI tag list |
| Unclosed client session | 58 | 11:01-11:14 | Stytch SDK resource leak |
| Unclosed connector | 28 | 11:09-11:10 | Related resource leak |
| CRDT tag removed | 2 | 11:12-11:13 | CRDT/DB reconciliation scrub |
| Pool INVALIDATE | 61 | 11:08-11:11 | Connections invalidated by CancelledError (all 61) |
| Failed to persist workspace | 2 | 11:10 | CRDT persistence failure |
| User storage assertion | 2 | 11:11 | NiceGUI storage race (speculative — no code path traced) |
| SSO auth failed | 4 | 11:11 | Stytch `sso_token_not_found` (speculative — timing may be coincidental) |

## Hypothesis Scorecard

| ID | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | Pool exhaustion as primary cause | **FALSIFIED** | Pool exhaustion is secondary — first errors are UniqueViolation, not QueuePool timeout |
| H2 | Stytch SDK leak reduces pool capacity | **FALSIFIED** | aiohttp sessions are HTTP (to Stytch API), not DB connections. No causal link in journal. Resource leak is real but orthogonal |
| H3 | PostgreSQL-level issue | **FALSIFIED** | No PG errors. Connection via Unix socket succeeded. All errors are application-level |
| H4 | Event loop saturation | **CONFIRMED as amplifier** | 206 "not ready" + 22 JS timeouts. Not root cause — amplified impact of H5 |
| **H5** | **Tag/group creation race condition** | **CONFIRMED as trigger** | 39 uniqueness violations (31 tag + 8 group, per PG log). Code has no conflict handling for group creation, stale local name sets for tag creation |

## Open Questions

1. **HAProxy logs — UNAVAILABLE.** `haproxy.log` is 0 bytes (rotated at midnight, nothing logged on 2026-03-16). rsyslog is not routing HAProxy's `local0` facility to the log file. We have **zero HTTP-level data** for this incident — cannot determine what status codes students saw. Fix rsyslog config. See `incident-response.md`.
2. **PostgreSQL logs — CHECKED.** `/var/log/postgresql/postgresql-16-main.log` (timestamps in UTC; AEDT = UTC+11). PG log shows 39 constraint violations (31 tag + 8 group) across 15 workspaces and 24 backend connections. No PG-level resource issues (no connection limits, no lock timeouts, no deadlocks). Checkpoints normal. Two client disconnects (Connection reset by peer, Broken pipe). See analysis below.
3. **No manual restart.** Brian confirmed no `systemctl restart`. The 3-minute gap (11:11:48 → 11:14:39 in DB errors) coincides with 206 "annotation not ready" warnings — the event loop was alive but saturated. Students reported it "working again" after this period, likely because pool connections recycled after the INVALIDATE storm subsided.
4. **Scope of data loss** — only 2 CRDT scrub events logged, but more students may have lost unsaved work that was never persisted to the CRDT in the first place (client-side state lost on refresh).
5. **Stytch unclosed sessions** — cosmetic (resource leak, worth fixing in #359 scope) but not causal. The SDK creates a fresh `aiohttp.ClientSession` per auth call (`factory.py:21`, `client.py:129`) and doesn't close them properly. Separate bug.
6. **`/healthz` is blind to DB** (`__init__.py:303-304`) — returns `PlainTextResponse("ok")` unconditionally. UptimeRobot silence is explained but not solely by this: even if healthz checked DB, it would have passed except during the 4 QueuePool timeout events (30s each).

## Failure Chain (not a single root cause)

Per Codex review: phrase this as a confirmed failure chain, not a fully closed single-cause claim. Split "service degradation cause" from "data loss mechanism" — the first is close to confirmed, the second should stay more cautious.

**Service degradation (HIGH confidence for trigger, MODERATE for bridge):** Concurrent `/annotation` tag and tag-group creation caused repeated uniqueness violations; timeout and cancellation events — likely triggered by students refreshing after errors — then invalidated connections and saturated the SQLAlchemy pool; secondary QueuePool timeouts followed; the event loop became unable to serve `/annotation` page loads.

**Data loss mechanism (MODERATE confidence):** CRDT cleanup warnings (2 logged scrub events) remain the strongest current evidence for user-visible data loss, but the full scope is not known from server logs alone. Students may have lost unsaved work that was never persisted to CRDT.

Workspaces are per-student (cloned via `clone_workspace_from_activity`), so the races are between each student's own concurrent requests (rapid clicks, retries, reconnects), not between different students on shared workspaces. The code lacks conflict handling at the DB layer:

- **Group creation:** Hardcodes `"New group"` with no duplicate check, no IntegrityError handler (`tag_management.py:396-407`)
- **Tag creation:** Uses stale local name set for deduplication; DB-level IntegrityError is caught in `tag_management_save.py:139-148` but the error has already caused a session rollback in `db/tags.py` via `get_session()`

Client-side timeouts and deleted-slot errors preceded request cancellations that invalidated pool connections and drove the pool to 15/15 (the precise mechanism — students refreshing browsers — is inferred, not directly logged). This produced secondary QueuePool timeouts and made `/annotation` unresponsive for all students. Separately, the CRDT reconciliation scrub removed 2 tags that existed in CRDT but not in DB (confirmed data loss for those 2 students; full scope unknown).

## Minimal Fix (pending review)

1. **Eliminate the "New group" hardcode** — use `_unique_tag_name()`-style deduplication for groups
2. **Add IntegrityError handling for `uq_tag_group_workspace_name`** in group creation (matching what tags already have)
3. **Move conflict handling into `db/tags.py`** — use INSERT ON CONFLICT or SELECT-before-INSERT so that expected uniqueness races never surface as generic "Database session error" rollbacks
4. **Refresh the local name set before each INSERT** — or accept that the DB constraint is the authority and handle conflicts gracefully

---

*HAProxy logs unavailable (logging broken). Investigation complete with available evidence. See incident-response.md for observability gaps to fix.*

## Peer Review Response (Codex review, 2026-03-16)

### Accepted

1. **"5 DB rollback errors" was wrong.** That was 5 Discord alerts, not 5 journal errors. Actual count: 52. The original narrative was uncritically carried from the Discord webhook output without verifying against the journal. Corrected.
2. **Pool exhaustion is secondary, not primary.** First errors are UniqueViolation at 11:08:41, not QueuePool timeout. QueuePool timeouts don't appear until 11:09:28 — 47 seconds later and clearly downstream. Original H1 was falsified by the journal evidence.
3. **"New group" hardcode and stale local name set are the concrete mechanisms.** Codex identified `tag_management.py:396`, `tag_management_save.py:139/268`, `models.py:677`. Codebase investigation confirmed these line-for-line.
4. **CRDT/DB divergence at `annotation_doc.py:870` is the strongest data loss lead.** Journal line 118679 shows `CRDT tag db6e44b0 not in DB, removing`. This is the reconciliation scrub deleting tags whose DB INSERT was rolled back.
5. **Stytch SDK leak is real but causal link to DB pool is unsupported.** The SDK creates fresh `aiohttp.ClientSession` per auth call (`factory.py:21`, `client.py:129`). These are HTTP connections to Stytch's API, not database connections. No journal evidence ties them to the tag/group failure pattern. Downgraded to orthogonal resource leak.

### Codex Caught Me

- **Original H1 framing was sloppy.** I predicted QueuePool TimeoutErrors would explain the first rollback alerts. The journal falsified this immediately — first errors were UniqueViolation. I updated this in my Bayesian update but the original document presented pool exhaustion as the leading hypothesis when I didn't have evidence for it. The prior should have been lower given that NiceGUI's websocket model doesn't map 1:1 to DB sessions.
- **Student count was wrong.** I stated "~600 students" from the initial prompt without verifying. Actual count from journal: 49 unique logins, ~30 in the first minute. This changes the entire load profile — 30 students triggering 52 DB errors is a correctness bug, not a scale problem.

### Claim Requiring Verification

Codex flagged whether the IntegrityError catch in `tag_management_save.py:139` actually prevents the generic "Database session error" log. Analysis: `create_tag()` in `db/tags.py` owns its own `get_session()` context manager. The IntegrityError fires during `session.flush()` (line 273) inside that context. `get_session()` catches it at line 299-300, logs "Database session error, rolling back transaction", rolls back, and re-raises. `_create_tag_or_notify()` in `tag_management_save.py` then catches the re-raised exception and shows the user-friendly notification. **Both fire.** The generic error log + Discord webhook fire even for "handled" duplicates. This is a contributing factor to the cascade — expected business logic errors trigger the same alarming path as unexpected failures.

## PostgreSQL Log Analysis

Source: `/var/log/postgresql/postgresql-16-main.log`, times in UTC (AEDT-11).

**39 constraint violations** (31 tag + 8 group) across **15 unique workspaces** and **24 PG backend PIDs**. (Earlier count of "47" was wrong — it included duplicate counting from the app journal. PG log is authoritative.)

| Workspace | Tag/Group Name | Violations | Type | Notes |
|---|---|---|---|---|
| ba1a8a16 | "New group" | 8 | group | Hardcoded default, repeated attempts |
| f00d2933 | "Name" | 6 | tag | 4 different PG backends racing |
| 19eea40e | "Test" | 5 | tag | 3 different PG backends |
| 62624529 | "test tag" | 3 | tag | |
| 3e0668e2 | "test" | 3 | tag | |
| 11b4bc0b | "test" | 3 | tag | |
| 4fed894d | "Blue" | 2 | tag | |
| 071dedf3 | "hello" | 2 | tag | |
| 7 others | various | 1 each | tag | "Judgement", "Summary of case", "Important Info", "Key words", "case", "test", "yes" |

**Key observations:**

1. **These are student-authored tag names, not template clones.** "test", "hello", "Blue", "Name" — students manually creating tags that already exist in their workspace.
2. **Workspaces are per-student** (cloned via `clone_workspace_from_activity`). The race is NOT between two students on the same workspace. It is the **same student's concurrent requests** on their own workspace — rapid clicking, page refresh while a request is in flight, or websocket reconnect triggering duplicate setup. *(Corrected: earlier analysis incorrectly claimed students were racing on shared workspaces.)*
3. **The stale local name set enables re-attempts.** After a failed tag creation (rolled back), the UI may retry or the student may click again. The local name set was populated before the first attempt and still thinks the name is available.
4. **"New group" is the worst offender.** 8 collisions on workspace `ba1a8a16` from a hardcoded default with zero deduplication. Every "Add group" click sends `name="New group"`. This could be one student clicking the button 9 times (1 success + 8 failures).
5. **Multiple PG backends hit the same workspace simultaneously.** Workspace `f00d2933` shows PIDs 927128, 927130, 927190, 927191, 920414 all trying to insert "Name" — 5 backends contending. Since workspaces are per-student, these are 5 concurrent requests from the same student (possibly from retries, reconnects, or multiple tabs).
6. **Two client disconnects during the cascade:** `Connection reset by peer` at 00:09:54 UTC, `Broken pipe` + `FATAL: connection to client lost` at 00:11:59 UTC. These correlate with CancelledError in the app journal.
7. **PostgreSQL was healthy.** No resource limits hit. Checkpoints ran normally. All errors are application logic.

## Phase 3b: Execution Path Audit

### Path 1: Manual tag creation (user clicks "Add tag")

```
User clicks "Add tag" button
→ tag_management.py:517 _add_tag_in_group()
  → tag_management.py:518-519: builds existing_names from state.tag_info_list (STALE — loaded at page init)
  → tag_management.py:521: _unique_tag_name(existing_names) generates "New tag" / "New tag 2" etc.
  → tag_management_save.py:115 _create_tag_or_notify()
    → db/tags.py:207 create_tag()
      → db/tags.py:246: _check_tag_creation_permission() — can raise PermissionError
      → db/tags.py:248: get_session() opens NEW session (its own transaction)
        → db/tags.py:249-255: UPDATE workspace SET next_tag_order (atomic counter)
        → db/tags.py:263-271: construct Tag object
        → db/tags.py:272: session.add(tag)
        → db/tags.py:273: session.flush() ← EXCEPTION HERE if duplicate name
          → IF IntegrityError: engine.py:299 catches Exception
            → engine.py:300: logger.exception("Database session error") + DISCORD WEBHOOK
            → engine.py:301: session.rollback()
            → engine.py:302: raise ← re-raises to caller
      → db/tags.py:276-285: CRDT dual-write (only reached on success)
    → tag_management_save.py:139: except Exception catches the re-raised IntegrityError
      → line 142: checks "uq_tag_workspace_name" in str(exc)
      → line 143-144: logs warning + ui.notify("already exists") ← USER SEES THIS
    → returns None
  → tag_management.py:525: if tag is None: return (skips render_tag_list)
```

**Critical finding:** The `IntegrityError` fires INSIDE `get_session()` at `db/tags.py:273`. `get_session()` catches it at `engine.py:299`, logs the generic error + Discord webhook, rolls back, and re-raises. THEN `_create_tag_or_notify` catches it again and shows the user-friendly message. **Both error paths fire.** The user sees a warning, but the system has already logged an ERROR and fired Discord.

The `next_tag_order` counter is incremented by the UPDATE at line 249-255, which happens BEFORE the INSERT. If the INSERT fails, the counter is rolled back with the session — so no counter gap. Confirmed: the counter uses the same session.

### Path 2: Manual group creation (user clicks "Add group")

```
User clicks "Add group" button
→ tag_management.py:396 _add_group()
  → db/tags.py:48 create_tag_group()
    → db/tags.py:75: _check_tag_creation_permission()
    → db/tags.py:77: get_session() opens NEW session
      → db/tags.py:78-84: UPDATE workspace SET next_group_order (atomic counter)
      → db/tags.py:93-96: construct TagGroup with name="New group" (HARDCODED from caller)
      → db/tags.py:98: session.add(group)
      → db/tags.py:99: session.flush() ← EXCEPTION HERE if "New group" already exists
        → IF IntegrityError: engine.py:299 catches → logs ERROR + Discord → rollback → re-raise
  → tag_management.py:403: except PermissionError ← DOES NOT CATCH IntegrityError
  → IntegrityError propagates UNHANDLED up the NiceGUI call stack
```

**Critical finding:** Group creation has NO IntegrityError handler. The exception propagates unhandled after `get_session()` logs it. NiceGUI catches it at the framework level and logs another error.

### Path 3: Workspace cloning (student opens activity for first time)

```
clone_workspace_from_activity() at workspaces.py:768
→ Single get_session() transaction (line 797)
  → Creates workspace, ACL, documents, groups, tags ALL in one session
  → Uses session.add() + session.flush() directly (NOT create_tag/create_tag_group)
  → Atomic: if any step fails, entire clone rolls back
```

**This path is NOT the source of the incident errors.** The PG log shows errors from `create_tag` (the CRUD function), not from direct `session.add()` inside the clone transaction. The clone path would produce errors in `workspaces.py`, not `tags.py:273`.

### Path 4: Tag import from another workspace

```
import_tags_from_workspace() at tags.py:593
→ Calls create_tag_group() and create_tag() individually (lines 631, 642)
→ Each opens its own get_session() — NOT atomic as a batch
→ Group creation at line 631: NO duplicate check (creates unconditionally)
→ Tag creation at line 638-640: checks existing_names (case-insensitive) BEFORE calling create_tag()
```

**Vulnerability:** If the import is called concurrently (same student, two requests), group creation will collide. Tag creation is safer because of the pre-check, but the pre-check races with concurrent inserts.

## Phase 3c: Claim Verification

| # | Claim | Data | Falsification | Result |
|---|-------|------|---------------|--------|
| 1 | `create_tag_group` hardcodes `"New group"` | `tag_management.py:400` passes `name="New group"` | Read the line | **Confirmed** — line 400: `name="New group"` |
| 2 | Group creation only catches `PermissionError` | `tag_management.py:403` | Read lines 396-407 | **Confirmed** — `except PermissionError:` is the only handler |
| 3 | Tag creation catches `IntegrityError` for `uq_tag_workspace_name` | `tag_management_save.py:139-144` | Read the code | **Confirmed** — checks `isinstance(exc, IntegrityError) and "uq_tag_workspace_name" in str(exc)` |
| 4 | `get_session()` logs ERROR + fires Discord before caller can catch | `engine.py:299-302` | Read the code; corroborate with journal showing both "Database session error" AND "duplicate_tag_name" for same event | **Confirmed** — journal shows both log lines for the same incident |
| 5 | `_unique_tag_name` uses stale `state.tag_info_list` | `tag_management.py:518-519` | Read: `existing_names` built from `state.tag_info_list` | **Confirmed** — but need to verify when `tag_info_list` is refreshed |
| 6 | Clone path uses direct `session.add()`, not `create_tag()` | `workspaces.py:886-896` | Read clone code vs `create_tag` code | **Confirmed** — clone does `session.add(cloned_tag)` at line 895, not `create_tag()` |
| 7 | Clone path runs in single transaction | `workspaces.py:797` | Read: single `async with get_session()` wrapping entire function | **Confirmed** |
| 8 | PG log errors come from `create_tag`, not clone path | PG log shows INSERT INTO tag with parameters matching CRUD path | The clone path would show in a `workspaces.py` traceback, not `tags.py:273` | **Confirmed** — journal tracebacks all show `tags.py:273` |
| 9 | `import_tags_from_workspace` doesn't check for group duplicates | `tags.py:630-634` | Read: loops `source_groups`, calls `create_tag_group` unconditionally | **Confirmed** — no `existing_group_names` check, unlike tag path at line 639 |
| 10 | Counter increment and INSERT are in the same session/transaction | `tags.py:248-273` | Read: both inside `async with get_session()` block | **Confirmed** — same session, rollback reverts both |
| 11 | Workspaces are per-student (not shared) | `clone_workspace_from_activity` creates new workspace per user | Queried DB: all 6 sampled workspace IDs have `owner_count=1, permissions={owner}` | **Confirmed** — single owner per workspace. Race is same-student concurrent requests. Earlier claim about "students seeing each other's stale work" was wrong and retracted. No security issue. |

### Epistemic Boundary

- **High confidence:** Claims 1-4, 6-10. The code paths, error handling gaps, and session lifecycle are verified.
- **Moderate confidence:** Claim 5. `tag_info_list` is stale at page load, but I haven't traced exactly when/how it's refreshed (could be refreshed between rapid clicks via `_refresh_tag_state`). Note: I verbally told Brian "all 11 claims verified" which was ahead of this document — claim 5 remains moderate.
- **Confirmed (was indeterminate):** Claim 11. DB query on 6 affected workspace IDs: all have `owner_count=1, permissions={owner}`. No shared workspaces. Race is same-student concurrent requests. Earlier claim about cross-student races was wrong and retracted — no security issue.

## Codex Review #2 Response

### Accepted

1. **Tests assert broken behaviour, not target behaviour.** Fixed: added `TestGracefulDuplicateHandling` with 4 xfail tests defining the acceptance criterion: `DuplicateNameError` (domain exception in `db/tags.py`) replaces `IntegrityError`. `DuplicateNameError` class created but not yet raised — tests correctly xfail. 5 reproduction tests + 3 target-state tests.

2. **Causal chain from UniqueViolation → pool INVALIDATE is overstated.** Fixed in both documents. All 61 INVALIDATE events show `exception=CancelledError`, not `IntegrityError`. Changed wording to: "Supported: duplicate writes preceded a cancellation/invalidation storm. Not supported: each uniqueness failure directly invalidated a connection."

3. **Count contradictions.** Fixed. Authoritative counts from source logs:
   - PG log (authoritative for uniqueness violations): 31 `uq_tag_workspace_name` + 8 `uq_tag_group_workspace_name` = **39** total
   - App journal: **52** DB session errors, **61** INVALIDATE events
   - Earlier counts of "47", "49", and "90" were wrong and have been corrected with explanations.

4. **Claim 5 moderate but I said "all 11 verified."** Epistemic boundary already said moderate in the document; my verbal summary to Brian was ahead of the document. Added note to the boundary section.

### Codex's Stronger Hypothesis — Adopted

"Concurrent /annotation tag/group operations generated duplicate inserts; client-side timeouts and deleted-slot errors caused request cancellations; those cancellations invalidated connections and drove the pool to 15/15, which then produced secondary QueuePool timeouts and slow /annotation responses. The later CRDT scrub warnings fit that same failure chain."

This is the accepted working explanation. HIGH confidence for the trigger (uniqueness violations). MODERATE confidence for the precise cancellation/invalidation bridge (students refreshing → CancelledError is inferred from temporal ordering, not directly observed in logs).
