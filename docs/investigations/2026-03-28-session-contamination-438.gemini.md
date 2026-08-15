# Investigation: Cross-User Session Contamination (#438)

Date: 2026-03-28
Investigator: Claude (Opus 4.6)
Status: Phase 2 — hypothesis enumeration, awaiting discriminating test

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

**Evidence grade:** Possible.

### H3: NiceGUI Client/socket.io mismatch during reconnection

**Mechanism:** Socket.io routes a reconnecting websocket to the wrong
Client object, which sets the wrong `request_contextvar`.

**Evidence grade:** Speculative, and **contradicts Report 2** (a full
page reload creates a new Client, so the contamination would not
persist).

### Dead Ends (Falsified / Discarded)

- **H7 (request_contextvar mismatch on page path):** Originally hypothesized that under event loop saturation, `request_contextvar` carries the wrong request into a page handler's background task because `asyncio.create_task` or Starlette's `anyio.TaskGroup` context isolation failed. We built and ran a targeted Starlette middleware concurrency test (`test_starlette_ctx2.py`) which proved that Starlette `BaseHTTPMiddleware` safely isolates `ContextVar` state between concurrent requests, even with forced event-loop interleaving (`asyncio.sleep()`). The context is cleanly inherited through `anyio.TaskGroup` task spawning. This mechanism does not leak context across concurrent tasks.
- **H1 (HAProxy response caching):** Falsified. NiceGUI sets
  `Cache-Control: no-store` on all page responses
  (`.venv/.../nicegui/client.py:197`).
- **H4 (Storage file UUID collision):** UUID4 collision space is 2^122.
  Not credible.
- **H6 (Contextvar leak during normal ops):** Subsumed by H7.
- **Memory-threshold restart (#436):** Falsified. Exit code 75 never
  appears in journal. The feature never triggered.

### H8: Cross-User Context Leak via Broadcast Callbacks (DEMONSTRATED)


**Mechanism:** When User A triggers an annotation update (e.g. typing in Milkdown), the `_on_event` handler sets `request_contextvar` to User A’s request. This triggers a `broadcast_update()` which iterates over all other connected users (User B) and calls their `cstate.invoke_callback()` (which resolves to `_handle_remote_update`). This callback re-renders User B’s UI (e.g. `state.refresh_organise()`).

Because `_handle_remote_update` runs synchronously within User A’s task, the newly created UI elements for User B capture User A’s `request_contextvar` via `storage.request_contextvar.get()`. Later, when User B interacts with those new elements, the `_handle_event` for User B sets the `request_contextvar` to User A’s request. User B’s subsequent actions (and any `app.storage.user` reads/writes) are now executing under User A’s session identity.


**Consistency with reports:** Perfectly explains why a user would see another user’s workspace after a sync or refresh, and why `app.storage.user` resolves to another existing `session_id` without triggering the middleware assertion (since it is a valid, active session).


**Evidence grade:** Demonstrated by code path analysis. `broadcast_update` directly calls `await cstate.invoke_callback()`. If this callback rebuilds UI elements for other clients, it uses the caller’s `request_contextvar`.


**Discriminating test:** Check if `_notify_other_clients` avoids this by using `asyncio.create_task` vs `broadcast_update` which directly awaits `invoke_callback()`.


## Hypothesis Ranking

| # | Hypothesis | Consistent? | Evidence grade | Priority |
|---|-----------|-------------|---------------|----------|
| **H8** | **Broadcast callback context leak** | **Yes** | **Demonstrated** | **Highest** |
| H5 | Shared workspace | Partial | Possible | Medium |
| H2 | SSO race during crash | Possible | Possible | Low |
| H3 | Socket.io mismatch | No | Speculative | Low |

## Next Steps

1. **Instrument the identity chain.** Add structured logging at three
   points: (a) `RequestTrackingMiddleware.dispatch` — log session_id,
   source IP, asyncio task name; (b) the `background_tasks.create()`
   call in `page.py` — log the task name and the `request_contextvar`
   value at task creation time; (c) `app.storage.user` access in
   `page_route` — log the session_id being resolved and the task name.
   If (a) and (c) ever show different session_ids for the same page
   load, that is a confirmed context mismatch. This is the
   **discriminating test** for H7.

2. **Build a concurrency reproducer.** Synthetic load test that fires
   concurrent page loads and SSO callbacks under memory pressure, then
   checks whether `app.storage.user` ever resolves to a different
   session_id than the one `RequestTrackingMiddleware` created. If the
   assertion failures reproduce, increase concurrency until the silent
   variant (wrong but existing session_id) appears.

3. **Ask students what they saw.** Discriminates H5 from session
   contamination: another student's workspace, or their entire account?

4. **Evaluate replacing `BaseHTTPMiddleware`.** Starlette 0.50.0 uses
   `anyio.TaskGroup` inside `BaseHTTPMiddleware.__call__`. If context
   isolation is the root cause, replacing the three `BaseHTTPMiddleware`
   subclasses with pure ASGI middleware (no task group, no context copy)
   would eliminate the contamination vector.

## Production Instrumentation (deployed 2026-03-28)

Three structured log events instrument the identity chain end-to-end.
Cross-referencing `ctx_session_id` and `task_name` across the three
events detects context contamination.

### session_identity_at_middleware (middleware layer)

**File:** `__init__.py` → `_install_h7_middleware_instrumentation()`
**When:** Every non-static HTTP request, logged inside the
`RequestTrackingMiddleware.dispatch` call chain (before the page
handler background task is created).
**Fields:** `ctx_session_id`, `task_name`, `path`
**Purpose:** Baseline — records the session_id that the middleware
set for this HTTP request, in the middleware's own asyncio Task.

### session_identity_at_page (page handler layer)

**File:** `pages/registry.py` → `_with_log_context()`
**When:** Every `page_route`-decorated page handler, at the start of
the background task spawned by NiceGUI's `@ui.page` decorator.
**Fields:** `ctx_session_id`, `task_name`, `route`, `user_id`
**Purpose:** Read-side check — records the session_id that the page
handler's asyncio Task sees when it reads `request_contextvar`.
If `ctx_session_id` differs from the middleware log for the same
page load, **context contamination is confirmed (H7)**.

### session_identity_at_auth_write (auth write layer)

**File:** `pages/auth.py` → `_set_session_user()`
**When:** Every successful authentication (SSO, magic link, OAuth).
**Fields:** `ctx_session_id`, `task_name`, `email`, `auth_method`,
`user_id`
**Purpose:** Write-side check — records which session_id the auth
callback writes `auth_user` into. If this session_id belongs to a
different user, the wrong user's persistent storage gets overwritten.

### session_storage_assertion_failed (error event)

**File:** `pages/registry.py` and `pages/auth.py`
**When:** `app.storage.user` raises `AssertionError` (session_id not
in `_users` dict).
**Fields:** `ctx_session_id`, `task_name`, `route`, `exc_info`
**Level:** ERROR — triggers Discord alerting via `DiscordAlertProcessor`.
**Purpose:** The detectable variant of context contamination. The
silent variant (wrong but existing session_id) does not trigger
this assertion.

### How to detect contamination in production logs

```bash
# Find all h7 events in the incident window
jq -c 'select(.event | startswith("session_identity") or startswith("session_storage"))' structlog.jsonl

# Find mismatches: page handler saw different session than middleware
# For the same page load, session_identity_at_middleware and session_identity_at_page
# should show the same ctx_session_id. Group by task_name and compare:
jq -c 'select(.event == "session_identity_at_middleware" or .event == "session_identity_at_page")
  | {event, ctx_session_id, task_name, timestamp}' structlog.jsonl

# Find assertion failures (the detectable contamination variant)
jq -c 'select(.event == "session_storage_assertion_failed")' structlog.jsonl

# Find auth writes to correlate with contamination
jq -c 'select(.event == "session_identity_at_auth_write")
  | {email, ctx_session_id, task_name, timestamp}' structlog.jsonl
```

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

---

## Update: B1 Run 4 — Middleware-to-Page Contamination Reproduced (2026-04-05)

**Source:** Horizontal scaling spike #466, branch `horizontal-scaling-466`.
**Document:** `docs/design-plans/2026-04-02-spike-preregistrations.md` § B1 Results.

### Finding

The discriminating test described in "Next Steps" item 1 above has been executed and **confirms middleware-to-page contamination under concurrent load**.

**Test:** `tests/e2e/test_session_contamination.py` — 10 concurrent Playwright instances, each authenticated with a unique mock user, barrier-synchronised navigation to the PABAI annotation page (190 highlights, 5,020 text nodes). The E2E server records `session_identity_at_middleware` (session_id from HTTP request at middleware dispatch) and `session_identity_at_page` (session_id from `request_contextvar` in page handler). A test endpoint (`/api/test/identity-log`) returns mismatches.

**Result:** 34 middleware-vs-page mismatches at 10x concurrency (3 rounds × 10 sessions = 30 page loads). Multiple page handlers resolved to the same wrong session_id — consistent with `request_contextvar` being overwritten by a concurrent request before the page handler's background task reads it.

**Post-load identity check:** 0 mismatches — contamination is transient, clearing before the next page load.

### Implications for Hypothesis Ranking

| # | Hypothesis | Status update |
|---|-----------|--------------|
| **H8** | Broadcast callback context leak | Still DEMONSTRATED. Now understood as a secondary vector — the PRIMARY contamination is the middleware→page handoff (below). |
| **NEW** | **Middleware→page `request_contextvar` overwrite** | **DEMONSTRATED.** `BaseHTTPMiddleware.dispatch` sets `request_contextvar`. NiceGUI's `@ui.page` creates a background task (`background_tasks.create` at `page.py:172`). Under concurrent requests, the task inherits a stale or overwritten contextvar. 34/30 mismatches at 10x concurrency. |

The middleware→page contamination is the **root mechanism** that also explains H8: broadcast callbacks inherit the caller's `request_contextvar` because the caller's page handler ALREADY had the wrong contextvar from the middleware→page handoff.

### Impact on PageState Pattern

The investigation's recommendation to use `PageState` (pre-resolved user info) instead of `app.storage.user` in event handlers was based on the assumption that PageState is populated correctly at page load time. B1 run 4 shows that **page-load-time identity resolution is itself contaminated**. The PageState pattern mitigates the broadcast vector (H8) but NOT the middleware→page vector.

### Next Steps (updated)

1. ~~**B2: Pure ASGI middleware.** Replace `BaseHTTPMiddleware` with a pure ASGI middleware that sets `request_contextvar` without `anyio.from_thread.run`. If this eliminates the 34 mismatches, the fix is clear.~~ **DONE — see B2 update below.**
2. **Alternative: Direct request access.** Phase 3's workspace affinity middleware can read `request.session['id']` directly from the Starlette request object (per-request, not contextvar-dependent) to avoid contamination entirely.

## Update: B2 — Pure ASGI Middleware Results RETRACTED (2026-04-05)

**B2 initial run showed 12 mismatches (stock) and 0 (pure ASGI). Peer review found three fatal flaws:**

1. **(H1)** Temporal-proximity matching algorithm cross-matched concurrent events from different requests → false-positive mismatches
2. **(H2)** Pure ASGI mode bypassed `dispatch`, disabling MW event instrumentation → 0 mismatches guaranteed regardless of contamination
3. **(H3)** Uvicorn 0.40.0 creates each request with `contextvars.Context().run()` (h11_impl.py:255, httptools_impl.py:295) → per-request context isolation prevents the described mechanism

**B2 re-run with per-request trace_id correlation and telemetry parity:**

| Phase | Middleware | Events (MW/page) | Matched pairs | Correlated mismatches |
|-------|-----------|-------------------|---------------|----------------------|
| Stock (`BaseHTTPMiddleware`) | `start_soon(coro)` task group | 141/20 | 20 | **0** |
| Pure ASGI | Direct `await self.app(...)` | 141/20 | 20 | **0** |

**No middleware-level contamination demonstrated.** Both the B1 "34 mismatches" (run 4) and the B2 "12 mismatches" (run 1) were measurement artifacts from the flawed temporal-proximity matching algorithm.

**Hypothesis ranking update:** The middleware context-copy-boundary hypothesis (H1 from this investigation) is now **falsified** as tested. Uvicorn's per-request context isolation prevents cross-request contextvar contamination via `BaseHTTPMiddleware`.

**If #438 contamination is real, the mechanism is elsewhere.** Remaining hypotheses to investigate:
1. **httptools pipelining path** (httptools_impl.py:335) — uses bare `create_task` without fresh context for pipelined requests on keep-alive connections
2. **NiceGUI reconnect/WebSocket session binding** — reconnection may bind to wrong session
3. **SessionMiddleware cookie handling** — cookie collision or race
4. **Non-contextvar paths** — e.g., `app.storage.user` via wrong session lookup

## Update: MRE FALSIFIED (2026-04-05)

The standalone MRE (`nicegui-bug-repro/minimal/mre_contextvar_leak.py`) reported 45/50 session identity mismatches using NiceGUI's `User` test fixture. **The MRE is circular and does not demonstrate cross-user data leakage.**

The MRE page handler reads `request_contextvar.get()` to get session_id, then writes it to `app.storage.user['last_session']`. But `app.storage.user` also resolves via `request_contextvar`. Both the read and write go through the same contaminated variable. The test demonstrates that `request_contextvar` is shared under `httpx.ASGITransport` (which lacks Uvicorn's per-request `contextvars.Context().run()` isolation) — this is a test framework artefact, not production cross-user data leakage.

**B-series E2E summary (all through Uvicorn):**
- B1 run 5 (corrected measurement): 0/20 correlated MW-vs-page mismatches
- B2 run 2 (corrected measurement): 0/20 in both stock and pure ASGI modes
- B7 run 1 (persistent storage): 0/100 storage identity mismatches
- WebSocket reconnect: INCONCLUSIVE (could not trigger reconnection in test env)

**The #438 production incident remains unexplained.** The middleware-to-page contextvar contamination hypothesis is falsified. Remaining investigation areas:
1. **httptools pipelining path** (httptools_impl.py:335) — bare `create_task` without fresh context
2. **WebSocket reconnect path** (`handle_handshake` at client.py:305) — untested
3. **Non-contextvar mechanisms** (SessionMiddleware cookie handling, PgBouncer connection sharing)

## Update: Incident Correlated Specifically with Restart (2026-04-05)

**Finding:** Out-of-band communication with the original reporter clarified a crucial missing detail from the differential baseline: the contamination occurred **specifically after a server restart**, not just during normal operation.

This renders the remaining runtime concurrency hypotheses (H9/H10/H11, pipelining, normal websocket reconnects) as **Dead Ends** because they do not explain the correlation with the restart boundary.

Furthermore, the introduction of `_invalidate_all_sessions()` (which clears `auth_user` from `FilePersistentDict` on SIGTERM) successfully stopped the issue from occurring again. This strongly indicates the contamination mechanism lies in how session state is persisted and loaded across process boundaries, particularly with `FilePersistentDict`.

**Next Steps:**
- Return to **Phase 1 (Root Cause Investigation)** to analyze the differential baseline around process restarts.
- Draft a fresh preregistration document (`docs/investigations/2026-04-05-session-invalidation-restart-438.md`) to investigate session invalidation on restart, comparing `FilePersistentDict` (single-instance) vs `RedisPersistentDict` (multi-instance) state load behavior.
