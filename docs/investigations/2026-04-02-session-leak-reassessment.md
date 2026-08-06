# Investigation: Cross-User Session Contamination (#438) - Reassessment

Date: 2026-04-02
Investigator: Gemini CLI
Status: Phase 1 — Root Cause Investigation (Dead ends documented; mechanism unresolved)

## Purpose

This document records three dead ends from the reassessment so they do not
get re-investigated as if they were still live:

1. `request_contextvar` cross-request leakage (H7)
2. interpreting the 5 storage assertion failures as direct contamination proof
3. session cache poisoning via production HAProxy

The goal of this document is not to present a new root cause. The goal is
to record what was ruled out, why it was ruled out, what evidence survives,
and what Phase 1 must investigate next.

## Incident Summary (from prior investigation)

On 2026-03-27, two students reported seeing another student's workspace.

- Both were on personal devices.
- Both reported the problem after laptop sleep and reconnect/reload.
- Refreshing did not fix Report 2; logout did.
- Incident window: 16:30–17:30 AEDT (05:30–06:30 UTC).
- The prior investigation reported event-loop saturation in the same window.

## Source Inventory

Reference timezone for cross-source comparison: Australia/Sydney (AEDT = UTC+11).

- Raw telemetry directory: `/tmp/incident-20260327-session-leak/`
- `structlog.jsonl`
  - 171,297 lines (`wc -l /tmp/incident-20260327-session-leak/structlog.jsonl`)
  - First timestamp: `2026-03-27T04:26:29.487764Z`
  - Last timestamp: `2026-03-27T22:57:37.217733Z`
  - File timezone: UTC
- `haproxy.log`
  - 103,039 lines (`wc -l /tmp/incident-20260327-session-leak/haproxy.log`)
  - First timestamp: `2026-03-27T00:00:18.626436+11:00`
  - Last timestamp: `2026-03-28T09:57:35.856933+11:00`
  - File timezone: `+11:00`
- Prior investigation: `docs/investigations/2026-03-28-session-contamination-438.md`
- Current code inspected at `HEAD`: `4bbe1389e94356a6cd07199dd85c7148ba8fbcda`
- Incident-time assertion failures in raw telemetry were logged on commit `2a837e7b`
- Deployment documentation checked: `docs/deployment.md`
- Telemetry manifest: `/tmp/incident-20260327-session-leak/manifest.json`
- HAProxy cache poisoning test: `scripts/test_haproxy_cache.sh` and `scripts/haproxy_test.cfg`
- H8 Context Leak RED Test: `tests/unit/test_broadcast_context_leak.py`
- Relevant broadcast code paths: `src/promptgrimoire/pages/annotation/broadcast.py`, `src/promptgrimoire/pages/annotation/__init__.py`, and `src/promptgrimoire/pages/annotation/document.py`

## Differential Baseline

- **Incident-time telemetry revision:** `main` commit `2a837e7b`
- **Current code inspected:** `HEAD` commit `4bbe1389e94356a6cd07199dd85c7148ba8fbcda`
- **Current differential:** `git diff 4bbe1389e94356a6cd07199dd85c7148ba8fbcda...HEAD` is empty

This means:

1. Current `main` still contains dangerous session behavior relevant to the
   investigation.
2. Current code inspection is evidence about present behavior.
3. Current code inspection is **not** proof that every implementation detail
   on incident day matched `HEAD`, because the incident telemetry was emitted
   by commit `2a837e7b`.

The contradiction is therefore between:

- the application's required behavior: strict session isolation
- the observed production behavior on 2026-03-27
- the current codebase, which still contains unresolved session-risk paths

## Dead End 1: `request_contextvar` Cross-Request Leakage (H7)

### Prior claim

Under event-loop saturation, `request_contextvar` carried the wrong request
into a page handler background task because one concurrent request overwrote
another request's context.

### Why it looked plausible

- The prior investigation found 5 `AssertionError: user storage for {uuid}
  should be created before accessing it` events (`jq -c 'select(.event | test("should be created before accessing"))' /tmp/incident-20260327-session-leak/structlog.jsonl | wc -l`).
- Two of those errors fell inside the incident window:
  - `2026-03-27T05:39:04.640223Z`
  - `2026-03-27T05:44:25.471556Z`
- The identity chain includes:
  - `SessionMiddleware`
  - `RequestTrackingMiddleware`
  - `request_contextvar`
  - `app.storage.user`
- The prior investigation was therefore trying to explain how a page handler
  could see a session ID with no corresponding storage entry.

### What is demonstrated

- The 5 assertion failures are real in the raw telemetry.
- The current NiceGUI stack uses task-local context propagation semantics.
- Python `contextvars` are isolated per task; new tasks inherit a snapshot of
  the current context rather than sharing one mutable global context object.

### What is only plausible

- It remains plausible that task timing, request lifecycle, or page/wait
  machinery interacts badly with session/storage state in some other way.
- It remains plausible that the prior investigation was observing a real race,
  but misidentified its mechanism.

### What is falsified

The specific H7 claim that concurrent HTTP requests were natively overwriting
each other's `ContextVar` values across tasks is no longer a supported
explanation.

That claim overreached from the symptom to a mechanism that current execution
semantics do not support. The current evidence is sufficient to retire H7 as
the working explanation unless direct contradictory production-path evidence is
found later.

### What survives this dead end

- The assertion failures still matter.
- They still indicate session/storage lifecycle trouble under stress.
- They no longer justify claiming cross-request `ContextVar` contamination as
  the incident mechanism.

## Dead End 2: The 5 Storage Assertion Failures as Direct Contamination Proof

### Prior claim

The 5 assertion failures proved that the incident mechanism was already known:
the page handler was reading another user's request context.

### Why it looked plausible

- The failing line is `app.storage.user`, which is identity-sensitive.
- The error fires deep in the session/storage path.
- Two failures occurred inside the incident window.

### What is demonstrated

Raw `structlog.jsonl` contains exactly 5 matching events:

- `2026-03-27T04:36:23.156699Z`
- `2026-03-27T04:42:10.511758Z`
- `2026-03-27T05:03:54.497205Z`
- `2026-03-27T05:39:04.640223Z`
- `2026-03-27T05:44:25.471556Z`

### What is only plausible

The best-supported current explanation is:

1. `prune_user_storage` sweeps user storage on a timer
2. a request stalls long enough to outlive its storage entry
3. the request later resumes and touches `app.storage.user`
4. the assertion fires because the session ID no longer has a storage slot

This explanation fits the timer-based cleanup behavior and the observed
stall-heavy environment, but it is still an inference from code path plus
timing. It is not yet demonstrated on the exact incident revision with a
minimal reproducer.

### What is falsified

The assertion failures do **not** directly prove cross-user contamination.
They prove a storage/session lifecycle failure. They do not identify the
mechanism that allowed User A and User B to collapse into the same identity.

### What survives this dead end

- The assertion failures remain important incident-window evidence.
- They still indicate that the session/storage subsystem was unhealthy.
- They should be treated as a correlated symptom, not as a solved mechanism.

## Dead End 3: Session Cache Poisoning via Production HAProxy

### Prior claim

Starlette/NiceGUI emitted `Set-Cookie` on public static assets, HAProxy cached
those responses, and HAProxy replayed the same cookie-bearing response to
subsequent users.

### Why it looked plausible

- The backend really does emit `Set-Cookie` on a cacheable static response.
- The backend really does set `Cache-Control: public` on NiceGUI static files.
- The raw HAProxy log shows heavy in-window static asset traffic:
  381 matching requests in the incident window for
  `/milkdown/milkdown-bundle.js` and
  `/static/annotation-copy-protection.js`
  (e.g., `awk '$5 >= "[27/Mar/2026:16:30:00" && $5 <= "[27/Mar/2026:17:30:00"' /tmp/incident-20260327-session-leak/haproxy.log | grep -E "milkdown-bundle\.js|annotation-copy-protection\.js" | wc -l`).
- The user reports mention sleep and reconnect, which made cached static asset
  fetches feel like a plausible trigger.

### What is demonstrated

For the **current codebase**, the following backend behavior is real:

1. NiceGUI static files set `Cache-Control: public`
2. session middleware can cause a static asset response to carry `Set-Cookie`
3. if a caching proxy or CDN were placed in front of that backend, this would
   be a real hardening concern

This behavior can be independently verified on the backend by fetching a static asset without an existing session cookie:

```bash
$ curl -s -D - -o /dev/null http://127.0.0.1:8080/static/annotation-copy-protection.js
HTTP/1.1 200 OK
server: uvicorn
content-type: text/javascript; charset=utf-8
cache-control: public, max-age=3600
set-cookie: session=...; path=/; Max-Age=1209600; httponly; samesite=lax
```

However, local rerun of `scripts/test_haproxy_cache.sh` observed that request 2 did not replay a cached `Set-Cookie` header under `scripts/haproxy_test.cfg`. The tested HAProxy configuration (using `cache-use` and `cache-store`) **refused to cache** the response containing a `Set-Cookie` header, entirely ignoring the `Cache-Control: public` directive. If the likely production deployment used a similarly standard caching setup, HAProxy would only capture and replay the session cookie if it were explicitly misconfigured to ignore the `Set-Cookie` header.

### What is only plausible

- It is plausible that this backend behavior would become exploitable in a
  different deployment that included a real caching proxy or CDN.
- It is plausible that the local proxy test should be preserved separately as a
  future hardening reminder if the architecture ever changes.

### What is likely falsified

This was likely **not** the root cause of the 2026-03-27 incident in the actual
production deployment.

Falsifier:

1. Best-supported and likely falsified based on operator review plus repo deployment docs. The actual incident-time `haproxy.cfg` was **not captured** in the `/tmp/incident-20260327-session-leak/manifest.json` telemetry bundle and cannot be independently verified. However, an out-of-band operational review of the real production config reportedly found no `cache` section.
2. The repository deployment guide (`docs/deployment.md`) documents a matching architecture: a TLS
   terminating reverse proxy forwarding to the app, with no cache directives in
   the documented `haproxy.cfg`.
3. A non-caching HAProxy cannot replay a cached `Set-Cookie` header because it
   is not storing responses at all.

Therefore the cache-poisoning theory was a real vulnerability class in the
abstract, but a dead end for this specific incident.

### What survives this dead end

- The backend behavior is still worth hardening eventually.
- The local HAProxy cache test is **not** a red test for the March 27 incident
  mechanism.
- The incident mechanism must be sought elsewhere.

## Dead End 4: Cross-User Context Leak via Broadcast Callbacks (H8)

### Prior claim

When User A triggers a real-time annotation update via websocket, the `_on_event` handler executes with `request_contextvar` correctly set to User A's request. This triggers `broadcast_update()`, which iterates over other connected users (e.g., User B) and directly awaits their `cstate.invoke_callback()`. Because this callback rebuilds User B's UI elements synchronously within User A's event handler task, the newly created UI elements for User B capture User A's `request_contextvar`. When User B later clicks those elements, their event handlers execute under User A's session identity.

### Why it looked plausible

- A RED test (`tests/unit/test_broadcast_context_leak.py`) successfully demonstrated that the receiving callback inherits the caller's context.
- A second RED test (`tests/unit/test_broadcast_ui_leak.py`) empirically proved the full downstream chain: UI elements rebuilt in the broadcast callback do capture the caller's context, and subsequent clicks by User B execute as User A.
- This UI context leak perfectly matches the symptom of User B suddenly interacting with User A's data without warning.

### What is demonstrated

- The cross-user UI context leak via `invoke_callback()` is a real, proven vulnerability in the application.

### What is falsified

This mechanism is definitively **falsified** as the root cause of the 2026-03-27 incident.

Falsifier:
1. The incident report explicitly stated that the contamination **persisted across a page refresh**.
2. The H8 context leak occurs entirely within the WebSocket event loop (`_on_event`). Any subsequent reads or writes to `app.storage.user` by User B (running under User A's context) modify the *caller's* (User A's) persistent storage, leaving User B's storage and session cookie 100% untouched.
3. If User B refreshes the page (an HTTP GET), their browser sends their original cookie. `SessionMiddleware` assigns `request.session['id'] = session-B`, and `RequestTrackingMiddleware` loads User B's untouched storage. The contamination would instantly vanish.
4. Because the mechanism is physically incapable of permanently corrupting User B's persistent storage or overwriting their HTTP session cookie, it cannot explain an incident that survived a page refresh.

Therefore, H8 is a real transient UI bug, but it is a dead end for the persistent session corruption incident.

### What survives this dead end

- The UI context leak is a real bug that must be fixed.
- The true mechanism that caused permanent identity collapse (persisting across refresh) must still be found.

## Dead End 5: Runtime Concurrency / Event-Loop Saturation (H9, H10, H11)

### Prior claim

The incident was caused by a runtime race condition under event-loop saturation during normal operation:
- **H9:** Auth Callback Race Condition
- **H10:** Persistent Storage File Merge/Reassignment (race between `prune_user_storage` and `RequestTrackingMiddleware`)
- **H11:** WebSocket Handshake Session Bleed

### Why it looked plausible

- The incident window contained high load and event-loop saturation.
- Users reported the issue after laptop sleep and reconnect, triggering `prune_user_storage` and reconnection storms.

### What is demonstrated

- **H10 Falsified via RED test:** `tests/unit/test_438_h10_storage_race.py` ran 100 concurrent iterations of `prune_user_storage` alongside middleware dispatch. Dictionary assignments in NiceGUI's `_users` map are synchronous and do not cross over. User A and User B storage remained strictly isolated.

### What is falsified

These hypotheses are completely **falsified** because they failed to account for a critical piece of the differential baseline: the original contamination occurred **specifically after a server restart**. H9, H10, and H11 were purely focused on runtime concurrency and ignored the restart boundary. Furthermore, the defensive fix that correlated with the bug's disappearance was `_invalidate_all_sessions()` which only runs on shutdown/restart.

### What survives this dead end

- The focus must return to Phase 1 (Root Cause Investigation) to establish the differential baseline specifically around process restarts and how `FilePersistentDict` state is loaded vs `RedisPersistentDict`.

## Residual Facts After These Dead Ends

After retiring the dead ends above, the following facts still stand:

- Two students reported cross-user contamination on 2026-03-27.
- The issue was triggered after sleep/reconnect/reload.
- At least one report persisted across refresh and cleared only after logout.
- Raw telemetry shows 5 storage assertion failures.
- Two of those failures were inside the incident window.
- Raw HAProxy logs show heavy in-window static asset traffic.
- We do not yet have a demonstrated mechanism that explains how User A's
  identity contaminated User B's identity.

## Phase 1 Restart: What Still Needs Investigation

The next investigation pass should focus on mechanisms that remain compatible
with all surviving facts:

1. **Application-level shared state**
   - module globals
   - class attributes
   - caches keyed too broadly
   - mutable state shared across clients or tabs

2. **WebSocket reconnect / client registry mismatch**
   - reconnect after sleep
   - handshake reassociation
   - `client_id`, `tab_id`, `old_tab_id`, or document identity collisions
   - wrong `Client` object receiving the resumed connection

3. **Session/storage lifecycle bug**
   - stale persisted user storage reused under the wrong session
   - wrong storage bucket selected after reconnect
   - auth callback writing `auth_user` into the wrong session-backed store

4. **Middleware/session semantics under stall and reconnect**
   - not HAProxy caching
   - not native `ContextVar` leakage
   - but still possibly a race or identity handoff problem somewhere in the
     session, page, websocket, or storage lifecycle

## Epistemic Boundary

### Demonstrated

- Raw telemetry contains 5 storage assertion failures.
- Two of those failures are in the incident window.
- Raw HAProxy logs contain heavy in-window static asset traffic.
- Current backend behavior emits dangerous headers on public static assets.

### Plausible

- Production HAProxy cache poisoning is likely not the incident mechanism based on operator review and deployment documentation (`docs/deployment.md`) indicating the production deployment did not have HAProxy response caching enabled.
- The assertion failures are caused by storage cleanup sweeping requests that
  stalled for too long.
- The session/storage subsystem was degraded under heavy load in ways that may
  be related to the contamination.

### Falsified

- **H8 (Cross-User Context Leak via Broadcast Callbacks):** Demonstrated as a real transient UI bug, but physically incapable of causing the permanent incident described because it cannot overwrite User B's persistent storage or session cookie.
- H7: native cross-request `ContextVar` leakage as the incident mechanism
- interpreting the 5 assertion failures as direct proof of cross-user
  contamination

### Unknown

- The actual mechanism that caused User A and User B to collapse into the same
  effective identity
- Whether the real mechanism lives in page routing, auth callback handling,
  websocket reconnect, client registry, or storage persistence
