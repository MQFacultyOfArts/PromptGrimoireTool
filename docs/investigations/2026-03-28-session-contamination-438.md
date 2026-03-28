# Investigation: Cross-User Session Contamination (#438)

Date: 2026-03-28
Investigator: Claude (Opus 4.6)
Status: Phase 3 complete — E2E reproducer did not trigger H7; student interviews now highest priority

## Incident Summary

Two students reported seeing another student's workspace on 2026-03-27.
Both were on personal devices (not shared computers). Both reported the
issue after their laptop had been asleep and the page reloaded.

Reports received at **17:30 and 17:44 AEDT** (source: Brian, relayed
from students in conversation 2026-03-27). The contamination therefore
occurred roughly **16:30–17:30 AEDT** (05:30–06:30 UTC).

**Report 1 (LAWS1000 student):** "I just reloaded the page, and somehow
I've been logged into another students annotations."

**Report 2 (LAWS8001 JD student):** "When I awoke the device and
reconnected to the wifi my Grimoire account automatically refreshed and
when it finished loading it had somehow taken me into a random student's
Grimoire account. I refreshed the tool to see if it would take me back to
my own account but it persisted with the other student's account at which
point I immediately logged out."

Key detail from Report 2: **refreshing did not fix it** — the user had
to explicitly log out and log back in.

## Source Inventory

Telemetry: `/tmp/incident-20260327-session-leak/`
Reference timezone: Australia/Sydney (AEDT = UTC+11)

| Source | Lines | First (AEDT) | Last (AEDT) | TZ in file |
|--------|-------|-------------|-------------|------------|
| structlog.jsonl | 171,297 | 27 Mar 15:26 | 28 Mar 09:57 | UTC |
| journal.json | 18,428 | 26 Mar 10:00 | 28 Mar 09:57 | µs epoch (UTC) |
| haproxy.log | 103,039 | 27 Mar 00:00 | 28 Mar 09:57 | AEDT |
| postgresql.json | 7,122 | 16 Mar 22:33 | 28 Mar 09:54 | UTC |
| pgbouncer.log | 12,126 | 24 Mar 19:54 | 28 Mar 09:57 | AEDT |

## Server Events on 2026-03-27

| Time (AEDT) | Event | Exit code | HAProxy drain? |
|-------------|-------|-----------|----------------|
| 12:12:50 | SIGABRT crash (4.3 GB peak) | 134 | **NO** |
| 12:12:55 | Auto-restart (systemd) | — | — |
| 14:31:35 | Manual stop (deploy) | 0 | Yes (14:30:22) |
| 14:31:36 | Started | — | — |
| 18:25:51 | Manual stop (deploy) | 0 | Yes (18:24:41) |
| 18:25:52 | Started | — | — |

The memory-threshold restart (#436, exit code 75) **never fired** — it
does not appear anywhere in the journal. The initial hypothesis that
#436's thundering-herd reconnection caused session mixing is
**falsified**.

The incident window (16:30–17:30 AEDT) falls **between** the 14:31
deploy and the 18:25 deploy. No crash or restart occurred in this
window; the server was running under normal load.

## Identity Chain

The session identity flows through:

```
Browser session cookie (signed, contains UUID)
  → Starlette SessionMiddleware decodes cookie
    → request.session['id'] = UUID
      → RequestTrackingMiddleware creates _users[UUID]
        → request_contextvar.set(request)
          → page handler (background task) reads request_contextvar
            → app.storage.user resolves _users[session_id]
              → PersistentDict['auth_user'] = {email, user_id, ...}
                → page_route reads auth_user → resolves workspace access
```

Contamination at any link causes one user to see another's data.

## Storage Assertion Failures

Five `AssertionError: user storage for {uuid} should be created before
accessing it` events appear in the structlog. Two fall in the incident
window:

| Time (UTC) | Time (AEDT) | Session UUID |
|------------|-------------|-------------|
| 04:36:23 | 15:36 | 64ea0d5f-... |
| 04:42:10 | 15:42 | 83bd9be5-... |
| 05:03:54 | 16:03 | 4b4b685e-... |
| **05:39:04** | **16:39** | f20af41d-... |
| **05:44:25** | **16:44** | f0e97819-... |

```bash
# [structlog.jsonl, UTC]
jq -c 'select(.event | test("should be created before accessing"))
  | {timestamp, event}' structlog.jsonl
```

The stack trace for the 16:39 error shows:

```
registry.py:157  →  app.storage.user.get("auth_user")
storage.py:137   →  assert session_id in self._users  ← FAILS
```

**What this proves:** The page handler's `app.storage.user` call
resolved a `session_id` from `request_contextvar` that does not exist
in `_users`. The `RequestTrackingMiddleware` creates storage for the
session_id it sees (`storage.py:37-38`), and `SessionMiddleware` sets
`request.session['id']` from the cookie. So the page handler is reading
a **different request** than the one whose session_id had storage
created for it.

**What this does NOT prove:** Whether the middleware "didn't run" or
"ran but the page handler got a different request's context." The
latter is more precise — NiceGUI's page decorator spawns the page
handler in a separate asyncio Task via `background_tasks.create()`
(`page.py:172`, which calls `core.loop.create_task()` at
`background_tasks.py:27`). The new Task copies the current context at
creation time. If `request_contextvar` has been overwritten by another
concurrent request before the Task copies the context, the page handler
inherits the wrong request.

**Co-occurring symptoms in incident window (16:30–17:30 AEDT):**
```bash
# [structlog.jsonl, UTC, filtered 05:30-06:30]
jq -r 'select(.level == "error" or .level == "warning")
  | select(.timestamp >= "2026-03-27T05:30"
    and .timestamp < "2026-03-27T06:30")
  | .event' structlog.jsonl | sort | uniq -c | sort -rn
```
- 26 × "Response for /auth/callback not ready after 3.0 seconds"
- 13 × "SSO auth failed: sso_token_not_found"
- 15 × "JavaScript did not respond within 5.0 s"
- Connection pool INVALIDATE warnings (pool size=80, overflows)

These indicate event loop saturation, which increases the probability
of context timing mismatches between concurrent requests.

## Hypotheses

### H7: request_contextvar mismatch on page path (LEADING)

**Mechanism:** Under event loop saturation, `request_contextvar` carries
the wrong request into a page handler's background task. The middleware
runs correctly for each request (creates storage, sets contextvar), but
`core.loop.create_task()` copies the context at a moment when another
request's `request_contextvar.set()` has already overwritten the value.

The assertion failures are the **detectable** variant — the inherited
session_id doesn't exist in `_users`, so the assert fires. The
dangerous **silent** variant: the inherited `request_contextvar` points
to a session_id that DOES exist in `_users` (belonging to a different
concurrent user). `app.storage.user` returns that user's storage without
any assertion failure. If this happens during a write path (SSO callback
storing `auth_user`), the wrong user's storage gets overwritten with the
current user's identity — or vice versa.

**Evidence:**
- 5 storage assertion failures, 2 in incident window (confirmed fact)
- Event loop saturation co-occurring (confirmed fact)
- Silent contamination variant (inference — same mechanism, no
  assertion to catch it)
- Starlette version: 0.50.0 (pinned in `uv.lock`)
- `background_tasks.create()` is `loop.create_task()` — standard
  asyncio context copying, no special isolation

**Evidence grade:** Plausible — assertion failures are confirmed.
Silent contamination is inferred but not directly demonstrated.

**Consistency with reports:**
- Happens during normal operation (no crash needed): **Yes**
- Persists across refresh: **Yes, if contamination occurs during a
  write path** (SSO callback writing auth_user to wrong storage)
- Timing: 16:39 and 16:44 AEDT match the incident window

### H5: Shared workspace access (not a bug)

**Mechanism:** Students viewed a workspace legitimately shared via ACL.

**Consistency with reports:**
- Report 1 could be explained this way
- Report 2 says "taken me into a random student's Grimoire account" —
  implies the navigator showed the other student's workspaces, not
  just a shared workspace. Inconsistent with H5.

**Evidence grade:** Possible for Report 1, inconsistent with Report 2.

**Discriminating test:** Ask both students what they saw — another
student's workspace, or another student's entire account (navigator,
name, all workspaces)?

### H2: SSO callback race during SIGABRT crash

Same mechanism as H7 but specifically during the 12:12 crash. The crash
is a confirmed fact, as are the concurrent SSO callbacks in the HAProxy
log. However, the crash occurred at **12:12 AEDT** and reports came at
**~17:30 AEDT** — five hours apart. For H2 to explain the reports, the
contamination from the crash window would need to have persisted through
the 14:31 deploy restart, which cleared `_users` in memory. The
persistent storage files on disk could carry contaminated `auth_user`
data across restarts, so this is not impossible but requires an
additional link in the causal chain.

**Evidence grade:** Possible, but H7 is more parsimonious (no need to
explain persistence across restart).

### H3: NiceGUI Client/socket.io mismatch during reconnection

**Mechanism:** Socket.io routes a reconnecting websocket to the wrong
Client object, which sets the wrong `request_contextvar`.

**Evidence grade:** Speculative, and **contradicts Report 2** (a full
page reload creates a new Client, so the contamination would not
persist).

### Falsified / Discarded

- **H1 (HAProxy response caching):** Falsified. NiceGUI sets
  `Cache-Control: no-store` on all page responses
  (`.venv/.../nicegui/client.py:197`).
- **H4 (Storage file UUID collision):** UUID4 collision space is 2^122.
  Not credible.
- **H6 (Contextvar leak during normal ops):** Subsumed by H7.
- **Memory-threshold restart (#436):** Falsified. Exit code 75 never
  appears in journal. The feature never triggered.

## Student Reports (anonymised, received 2026-03-28)

### Report 1 (LAWS1000 student)

> I just opened my computer up after not using it since this morning,
> and the annotation software was still open in my browser. The page
> had timed out. I just reloaded the page, and somehow I've been logged
> into another student's annotations. I can see all of their annotations.

### Report 2 (LAWS8001 JD student)

> I was logged into and working in my own account, took a phone call at
> which point my laptop went to sleep. When I awoke the device and
> reconnected to the wifi my Grimoire account automatically refreshed
> and when it finished loading it had somehow taken me into a random
> student's Grimoire account. I refreshed the tool to see if it would
> take me back to my own account but it persisted with the other
> student's account at which point I immediately logged out and I have
> managed to log back into my own account.

Key details from Report 2:
- "is not a [student in my unit]" — **cross-unit contamination**
- **Persisted across refresh** — required explicit logout to fix
- Trigger: laptop sleep → wifi reconnection → automatic page refresh

### What the reports discriminate

1. **H5 (shared workspace) is weakened.** Report 2 describes seeing
   another student's entire *account*, and that student is from a
   different unit.  Workspace sharing is unit-scoped — cross-unit
   visibility cannot be explained by ACL sharing.  Report 1 says
   "another student's annotations" which could be either a shared
   workspace or full identity contamination.

2. **Persistence across refresh rules out transient state.** The
   contamination survived a full page reload.  This means the
   server-side `app.storage.user` (a `FilePersistentDict` keyed by
   session cookie UUID) contains the wrong `auth_user` blob.  The
   contamination is in the persistent storage file, not in a transient
   contextvar.

3. **Sleep/reconnection trigger pattern.** Both reports involve laptop
   sleep followed by reconnection.  This points at the websocket
   reconnection path (`client.py:305`) or at the page reload path
   (full HTTP request through middleware).

## Phase 3 Results: E2E Concurrency Reproducer

### request_contextvar set-sites (code review finding)

`request_contextvar` is set in **three** places in NiceGUI, not just
the middleware:

1. `storage.py:32` — `RequestTrackingMiddleware.dispatch` (HTTP request)
2. `client.py:305` — `storage.request_contextvar.set(self.request)`
   (websocket reconnection)
3. `element.py:393` — `storage.request_contextvar.set(listener.request)`
   (event handling)

Sites 2 and 3 run in their own asyncio tasks, so they *should* not
cross-contaminate page handler tasks.  But they represent additional
mutation points that deserve monitoring.  **This is inference from code
reading, not demonstrated.**

### Context propagation chain (code review — inference, not demonstrated)

Traced the full context copy chain:

```
ASGI server task (uvicorn) creates Task per request
  → BaseHTTPMiddleware.__call__ enters anyio.TaskGroup
    → dispatch_func (RequestTrackingMiddleware) sets request_contextvar
      → call_next → task_group.start_soon(coro)
        → child task (copies parent context, has correct contextvar)
          → FastAPI router → page._wrap.decorated
            → background_tasks.create(wait_for_result())
              → core.loop.create_task (copies child context)
                → page handler reads request_contextvar
```

Each task creation (`start_soon` at anyio `_spawn:884`, `create_task`
at `background_tasks.py:27`) copies the current context.  Concurrent
requests run in separate ASGI tasks with independent context copies.
**Code review suggests** the chain correctly isolates contexts, but this
has not been demonstrated under production-equivalent load.

Versions: anyio 4.12.1, starlette 0.50.0, nicegui 3.9.0.

### E2E reproducer test (inconclusive)

**Test:** `tests/e2e/test_h7_session_contamination.py`

**Design:**
- 20 independent Playwright instances (separate processes/event loops)
- Each authenticates with a distinct mock user email
- `threading.Barrier` synchronises all 20 navigations to fire at the
  same instant
- Each navigates to `/test/session-identity` (a real `@ui.page`)
- Page handler reads `app.storage.user.get("auth_user")` BEFORE and
  AFTER 10 yield points
- Test captures both emails and compares to expected
- 5 rounds = 100 total concurrent page loads

**Result:** All 100 page loads returned the correct email, both before
and after yield points.  No contamination detected.

**Critical limitation:** The test page does effectively zero work
(`asyncio.sleep(0)` x10).  Production annotation pages load from
PostgreSQL, deserialise CRDT blobs (up to ~150KB), set up presence
tracking, and render thousands of DOM nodes.  The test does not
reproduce event loop saturation, which is the precondition for H7.
**This result is inconclusive — the test does not simulate production
conditions.**  A follow-up test must use the PABAI fixture (190
highlights, 5,020 text nodes) to create realistic load.

## Hypothesis Ranking (updated 2026-03-28, post-student-reports)

| # | Hypothesis | Consistent? | Evidence grade | Priority |
|---|-----------|-------------|---------------|----------|
| **H7** | **request_contextvar mismatch** | **Yes** | **Plausible (not yet reproduced)** | **Highest** |
| H5 | Shared workspace | **Weakened by Report 2** | Possible for Report 1 only | **Demoted** |
| H2 | SSO race during crash | Possible | Possible | Low |
| H3 | Socket.io mismatch | No | Speculative | Low |

**Rationale:** Report 2's cross-unit contamination weakens H5
significantly.  H7 remains the leading hypothesis: the 5 storage
assertion failures (confirmed facts) prove that `request_contextvar`
resolves to wrong session_ids under production load.  The E2E test did
not reproduce this, but the test is acknowledged as insufficient (no
production-equivalent workload).

## Revised Next Steps

1. **Rebuild E2E reproducer with PABAI fixture.** Each of the 20
   sessions must load the full 150KB PABAI workspace (190 highlights,
   5,020 text nodes) to create realistic event loop contention.  The
   current toy endpoint is insufficient.

2. **Instrument the identity chain in production.** Add structured
   logging at `RequestTrackingMiddleware.dispatch` and `page_route`
   (log session_id + asyncio task name at both points).  If these
   ever diverge, H7 is confirmed.

3. **Monitor for new assertion failures.** The 5 storage assertion
   failures in structlog are the strongest evidence of a real bug.
   Add Discord alerting for these so new occurrences are caught
   immediately.

4. **Investigate the persistent storage write path.** Report 2's
   persistence across refresh means `auth_user` was written to the
   wrong session's `FilePersistentDict`.  The write path is
   `_set_session_user()` at `auth.py:148`.  If the contextvar is
   contaminated during SSO callback processing, the write goes to
   the wrong storage file.  This is the mechanism that creates
   persistent cross-user contamination.

## Defensive Fixes Applied

- **#438:** `_invalidate_all_sessions()` clears `auth_user` from all
  NiceGUI user storage before memory-threshold restart. Defensive
  measure — correct regardless of root cause, but does not address the
  context mismatch during normal operation.

- **`APP__MEMORY_RESTART_THRESHOLD_MB=0`:** Disables the memory restart
  feature. Does not address the incident (which occurred without any
  restart) but removes a potential additional trigger.

## Defensive Fixes Withdrawn

- **~~Add `Cache-Control: no-store` to page responses.~~**
  Already present: NiceGUI sets this on all page responses
  (`client.py:197`).

- **~~Validate Stytch session token on every `page_route`.~~**
  Orthogonal to the bug: if the wrong `auth_user` blob is loaded from
  another user's storage, its Stytch session_token is the contaminated
  user's **legitimate** token — validation would pass. An independent
  identity source (e.g., comparing the session cookie's session_id
  against the auth_user's expected storage slot) would be needed instead.
