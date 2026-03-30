# Dynamic Lag-Based Admission Gate

**GitHub Issue:** #459

## Summary

PromptGrimoire is a collaborative web application built on NiceGUI that can experience event loop saturation under sustained load — a condition that causes page latency to degrade and, at high enough load, triggers a memory-threshold restart. This feature introduces an admission gate at the `page_route` middleware layer that prevents new users from entering the server when it is already under stress, rather than waiting for the memory backstop to fire. The gate is scoped narrowly: existing authenticated users, staff, and users reconnecting within NiceGUI's 15-second reconnect grace period all pass through without restriction. Only genuinely new authenticated sessions are subject to it.

The control algorithm is AIMD (Additive Increase, Multiplicative Decrease), borrowed from TCP congestion control. It uses event loop lag — already measured every 30 seconds by the existing diagnostic loop — as its congestion signal. When lag is low and the server is near capacity, the admission cap grows by a fixed batch. When lag exceeds a threshold, the cap halves. Users who arrive when the server is at cap are placed in a FIFO queue and shown a lightweight polling page; when the cap rises, a batch is admitted at once. After a restart, the cap begins at a conservative floor and ramps up organically as lag stays low. This avoids the hard restart that would otherwise occur and gives the server time to stabilise before accepting full traffic.

## Definition of Done

Dynamic admission gate that throttles new authenticated users based on event loop lag, preventing server restarts under load.

1. **Lag-based dynamic cap:** The diagnostic logger publishes a current admission cap derived from `event_loop_lag_ms`. When lag exceeds a configurable threshold, the cap decreases. When lag is low, the cap increases. The cap never causes eviction of existing users.

2. **Post-restart ramp-up:** After a server restart, the cap starts at a configurable initial value (default ~20) and increases by a configurable batch size (default ~20) every diagnostic interval (~30s) until lag pushes it back down.

3. **FIFO queue with batch admission:** Users who arrive when the server is at cap see a lightweight queue page with their position. When the cap rises, the next batch of queued users is admitted (not one-at-a-time).

4. **Gate scope:** Only new authenticated users are gated. Users already in `client_registry._registry` pass through freely. The 15s `reconnect_timeout` grace period is unaffected — brief disconnects don't lose your spot. Staff (privileged users) bypass the gate entirely.

5. **Queue page is lightweight:** The queue page must not create expensive NiceGUI UI trees. It polls for admission status.

6. **Observable state:** The current cap, queue depth, and lag are visible in diagnostic logs.

**Out of scope:**

- Idle detection / active eviction
- Memory-based gating (existing graceful restart remains the memory backstop)
- Blue/green deploy (#419 — separate design)

## Acceptance Criteria

### lag-admission-gate.AC1: Cap adjusts dynamically based on event loop lag
- **lag-admission-gate.AC1.1 Success:** Cap increases by `batch_size` when lag < `lag_increase_ms` and admitted count >= cap - batch_size
- **lag-admission-gate.AC1.2 Success:** Cap unchanged when lag is between `lag_increase_ms` and `lag_decrease_ms` (hysteresis band)
- **lag-admission-gate.AC1.3 Success:** Cap halves when lag > `lag_decrease_ms`
- **lag-admission-gate.AC1.4 Success:** After restart, cap starts at `initial_cap` and ramps up naturally via AIMD as lag stays low
- **lag-admission-gate.AC1.5 Edge:** Cap never drops below `initial_cap` even under sustained high lag
- **lag-admission-gate.AC1.6 Edge:** Cap does not increase when admitted count is well below current cap (no speculative growth)

### lag-admission-gate.AC2: FIFO queue with batch admission
- **lag-admission-gate.AC2.1 Success:** Users arriving when at cap are added to queue in arrival order
- **lag-admission-gate.AC2.2 Success:** When cap rises above admitted count, queued users are popped in FIFO order up to available capacity
- **lag-admission-gate.AC2.3 Success:** Batch admission admits multiple users per diagnostic cycle (not one-at-a-time)
- **lag-admission-gate.AC2.4 Failure:** Users in queue longer than `queue_timeout_seconds` are dropped from queue
- **lag-admission-gate.AC2.5 Edge:** User already in queue is not double-enqueued on subsequent page loads

### lag-admission-gate.AC3: Gate only affects new authenticated users
- **lag-admission-gate.AC3.1 Success:** User already in `client_registry._registry` passes through gate freely (page navigation while admitted)
- **lag-admission-gate.AC3.2 Success:** Privileged users (`is_privileged_user`) bypass gate regardless of cap
- **lag-admission-gate.AC3.3 Failure:** New authenticated user redirected to `/queue` when admitted count >= cap
- **lag-admission-gate.AC3.4 Edge:** User who disconnects and reconnects within 15s `reconnect_timeout` remains in `_registry` and is not gated

### lag-admission-gate.AC4: Queue page is lightweight and functional
- **lag-admission-gate.AC4.1 Success:** Queue page shows user's position and total queue size
- **lag-admission-gate.AC4.2 Success:** Queue page polls `/api/queue/status` and redirects to original page on admission
- **lag-admission-gate.AC4.3 Success:** `/api/queue/status` returns `{position, total, admitted}` JSON
- **lag-admission-gate.AC4.4 Edge:** Direct navigation to `/queue` when not queued returns `admitted: true` and redirects out

### lag-admission-gate.AC5: Admission state visible in diagnostic logs
- **lag-admission-gate.AC5.1 Success:** `memory_diagnostic` structlog event includes `admission_cap`, `admission_admitted`, `admission_queue_depth`
- **lag-admission-gate.AC5.2 Success:** All config values (`initial_cap`, `batch_size`, `lag_increase_ms`, `lag_decrease_ms`) configurable via env vars

## Glossary

- **AIMD (Additive Increase, Multiplicative Decrease)**: A congestion-control algorithm used in TCP. The admission cap grows slowly under good conditions (additive increase) and shrinks rapidly under bad conditions (multiplicative decrease — halving). This creates asymmetric but stable behaviour: gradual ramp-up, fast back-off.
- **Admission cap**: The maximum number of distinct authenticated users allowed to hold active NiceGUI sessions simultaneously. Controlled dynamically by the AIMD algorithm.
- **Admission gate**: The middleware check inserted into `page_route` that compares the current active user count against the admission cap and either passes or queues a new user.
- **`app.storage.user`**: NiceGUI's per-user server-side storage, keyed by browser session. Used here to stash the original destination URL before redirecting to `/queue`, so the user can be returned after admission.
- **Batch admission**: Admitting multiple queued users in a single diagnostic cycle rather than one at a time. Prevents the queue from draining too slowly under light-but-recovering load.
- **`client_registry`**: A module-level dictionary (`dict[UUID, set[Client]]`) in `auth/client_registry.py` that maps authenticated user IDs to their active NiceGUI clients. Its size is the "admitted count"; presence in it is the pass-through check.
- **Diagnostic loop**: The background task in `diagnostics.py` that fires every ~30 seconds, measuring event loop lag and memory usage. The admission cap update hooks directly into this loop rather than adding a new background task.
- **Event loop lag**: The delay between scheduling a callback on the asyncio event loop and it actually running. Under high concurrency, NiceGUI's async event loop can saturate, and lag grows. Used here as the congestion signal because it directly reflects server responsiveness.
- **Graceful memory shutdown**: The existing mechanism in `diagnostics.py` that triggers a controlled restart when process memory exceeds a threshold (currently 3 GB). The admission gate is a preventative layer that reduces the likelihood of reaching this threshold.
- **Hysteresis band**: The lag range between `lag_increase_ms` and `lag_decrease_ms` where the cap neither grows nor shrinks. This prevents oscillation when lag is near a threshold.
- **NiceGUI**: The Python web UI framework the application is built on. Each connected browser client creates a server-side Python object tree (the "UI tree"), which consumes memory and event loop time. This is why session count directly affects server load.
- **`page_route`**: A decorator in `pages/registry.py` that wraps all protected page handlers with auth checks, ban checks, and client registration. The admission gate is inserted at this layer, after the ban check and before the page handler runs.
- **Privileged user**: A user for whom `is_privileged_user()` returns `True` — org-level admins and users with `instructor` or `stytch_admin` roles. They bypass the gate entirely.
- **`reconnect_timeout`**: NiceGUI's grace period (15 seconds) during which a disconnected client's server-side state is preserved. A user who refreshes or has a brief network blip stays in `client_registry._registry` and never hits the gate.
- **Starlette route**: A raw HTTP route registered directly on the underlying ASGI application (before NiceGUI's page routing). Used for lightweight JSON endpoints (`/healthz`, `/api/queue/status`) that must not create NiceGUI client trees.
- **Structlog**: The structured logging library used throughout the project. Log events are emitted as JSON with typed fields; the admission state fields (`admission_cap`, `admission_admitted`, `admission_queue_depth`) are added to the existing `memory_diagnostic` event.

## Architecture

AIMD (Additive Increase, Multiplicative Decrease) admission control using event loop lag as the congestion signal.

**Components:**

- **`src/promptgrimoire/admission.py`** (new) — module-level `AdmissionState` dataclass holding current cap, latest lag, and FIFO queue. Exposes `update_cap(lag_ms)`, `try_admit(user_id)`, and `get_queue_status(user_id)`.
- **`src/promptgrimoire/diagnostics.py`** (modified) — after measuring lag each interval, calls `admission.update_cap(lag_ms)` and runs batch admission from queue.
- **`src/promptgrimoire/pages/registry.py`** (modified) — `page_route` wrapper gains gate check after ban check: if user not in `client_registry._registry` and not privileged and server at cap, redirect to `/queue`.
- **`src/promptgrimoire/pages/queue.py`** (new) — lightweight `@ui.page("/queue")` following `/restarting` pattern. Minimal NiceGUI elements, fire-and-forget JS polling.
- **`GET /api/queue/status`** (new Starlette route) — returns JSON `{position, total, admitted}` for queue page polling.

**Data flow:**

```
Diagnostic loop (30s)
  → measure event_loop_lag_ms
  → admission.update_cap(lag_ms)
    → lag < 10ms AND admitted near cap → cap += batch_size
    → lag > 50ms → cap //= 2
    → 10–50ms → no change
  → if cap > admitted and queue non-empty → pop batch, mark admitted
  → log admission_cap, admission_admitted, admission_queue_depth

Page load (page_route)
  → resolve user_id from session
  → ban check
  → if user_id in client_registry._registry → pass (already in)
  → if is_privileged_user → pass (staff bypass)
  → if len(client_registry._registry) < cap → pass (under cap)
  → else → add to queue, redirect /queue

Queue page (/queue)
  → JS polls GET /api/queue/status every 5s
  → when admitted=true → redirect to original page

User disconnects (all tabs closed, 15s reconnect_timeout expires)
  → client_registry.deregister fires via on_delete callback
  → user removed from _registry
  → next diagnostic cycle: cap > admitted → queued users admitted
```

## Existing Patterns

**Diagnostic logger** (`src/promptgrimoire/diagnostics.py`): Already runs a 30s loop measuring event loop lag and memory. Cap computation hooks directly into this loop — no new background task.

**Client registry** (`src/promptgrimoire/auth/client_registry.py`): Module-level `dict[UUID, set[Client]]` tracking authenticated users to NiceGUI clients. Auto-deregisters via `on_delete` callback. The admission gate reads `len(_registry)` for admitted count and checks `user_id in _registry` for pass-through.

**`page_route` middleware** (`src/promptgrimoire/pages/registry.py`): Decorator wrapping all protected pages with auth checks, ban checks, and client registration. Gate check inserts at the same level as the ban check — after user_id resolution, before page handler.

**`/restarting` page** (`src/promptgrimoire/pages/restarting.py`): Lightweight `@ui.page` with minimal NiceGUI elements and fire-and-forget JS polling `/healthz`. Queue page follows this exact pattern — `@ui.page("/queue")`, a few labels, JS polling `/api/queue/status`.

**Raw Starlette routes** (`src/promptgrimoire/__init__.py`): `app.routes.insert(0, Route(...))` for `/healthz`, `/api/admin/kick`, `/api/pre-restart`, `/api/connection-count`. Queue status endpoint follows this pattern.

**`app.storage.user`** for return URL stashing: Login flow stashes `post_login_return` in `app.storage.user`. Gate uses the same pattern — stashes the original URL before redirecting to `/queue`, queue page redirects back after admission.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Admission State Module

**Goal:** Core admission state and AIMD cap computation, independent of NiceGUI.

**Components:**
- `src/promptgrimoire/admission.py` — `AdmissionState` dataclass, `update_cap(lag_ms)` with AIMD logic, `try_admit(user_id)`, `get_queue_status(user_id)`, queue management (enqueue, batch pop, expiry)
- `src/promptgrimoire/config.py` — new `AdmissionConfig` sub-model with `initial_cap`, `batch_size`, `lag_increase_ms`, `lag_decrease_ms`, `queue_timeout_seconds`

**Dependencies:** None (pure logic, no NiceGUI dependency).

**Covers:** lag-admission-gate.AC1.*, lag-admission-gate.AC2.*

**Done when:** Unit tests verify AIMD behaviour — cap increases when lag low and server near cap, halves when lag high, stays unchanged in hysteresis band. Queue FIFO ordering and batch admission work. Queue expiry drops stale entries.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Diagnostic Integration

**Goal:** Wire cap computation into the existing diagnostic loop.

**Components:**
- `src/promptgrimoire/diagnostics.py` — after `measure_event_loop_lag()`, call `admission.update_cap(lag_ms)` and `admission.admit_batch()`. Add `admission_cap`, `admission_admitted`, `admission_queue_depth` to `memory_diagnostic` log event.
- `src/promptgrimoire/__init__.py` — initialise admission state on app startup with config values.

**Dependencies:** Phase 1 (admission module exists).

**Covers:** lag-admission-gate.AC5.*

**Done when:** Diagnostic log events include admission fields. Cap updates every diagnostic interval. Integration tests verify cap changes appear in structured logs.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Gate in page_route

**Goal:** Admission gate check in the `page_route` decorator.

**Components:**
- `src/promptgrimoire/pages/registry.py` — add gate check in `_with_log_context` after ban check: check `client_registry._registry` membership, check `is_privileged_user`, check cap, enqueue and redirect to `/queue` if over cap. Stash original URL in `app.storage.user["queue_return"]`.

**Dependencies:** Phase 1 (admission module), Phase 2 (cap is being updated).

**Covers:** lag-admission-gate.AC3.*

**Done when:** Unit tests verify: existing users pass through, privileged users bypass, new users redirected when at cap, return URL stashed. Tests use mock admission state (no NiceGUI server needed).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Queue Page and Status API

**Goal:** Lightweight queue page and polling endpoint.

**Components:**
- `src/promptgrimoire/pages/queue.py` — `@ui.page("/queue")` with minimal elements (heading, position message, auto-refresh). Fire-and-forget JS polling `/api/queue/status` every 5s. Redirects to stashed URL on admission.
- `GET /api/queue/status` Starlette route in `src/promptgrimoire/__init__.py` — reads user_id from signed token or session, returns `{position, total, admitted}` JSON. Returns `admitted: true` for users not actually queued (direct navigation edge case).

**Dependencies:** Phase 1 (queue state), Phase 3 (redirect to /queue works).

**Covers:** lag-admission-gate.AC4.*

**Done when:** E2E test verifies: user redirected to queue page sees position, polling endpoint returns correct JSON, admission triggers redirect back to original page. Direct navigation to `/queue` when not queued redirects out immediately.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Restart Integration

**Goal:** Clean admission state on restart, queue survives graceful shutdown notification.

**Components:**
- `src/promptgrimoire/diagnostics.py` — `graceful_memory_shutdown()` clears admission queue (users will re-queue after restart). Cap resets to `initial_cap` on next startup (natural from module initialisation).
- `src/promptgrimoire/pages/queue.py` — queue page handles server restart gracefully (same pattern as `/restarting` — polls healthz, redirects when server is back, user re-enters queue if at cap).

**Dependencies:** Phase 4 (queue page exists).

**Covers:** lag-admission-gate.AC3.4 (reconnect grace period), lag-admission-gate.AC1.4 (post-restart ramp)

**Done when:** Integration test verifies cap resets to initial value on startup. Queue page doesn't error when server restarts.
<!-- END_PHASE_5 -->

## Additional Considerations

**Queue page memory cost:** The queue page creates a NiceGUI client with a minimal element tree (a few labels). Under extreme load with hundreds of queued users, these clients still consume some memory. If this becomes a problem, the queue page could be migrated to a raw Starlette HTML response (no NiceGUI client), but the `/restarting` pattern should be adequate for expected queue sizes.

**Interaction with `reconnect_timeout`:** The 15s reconnect timeout means a user who refreshes their page or has a brief network blip retains their NiceGUI client and stays in `_registry`. They never hit the gate. Only after 15s of total disconnection does the client get deleted and the user lose their spot. This is the intended behaviour.

**Cap floor:** The cap never drops below `initial_cap` (default 20), even under extreme lag. This ensures some minimum number of users can always access the system. The existing `graceful_memory_shutdown` at 3GB remains the last resort.

**No persistence:** Admission state is entirely in-memory. Server restart resets everything — cap goes back to `initial_cap`, queue is cleared. This is acceptable because restart invalidates all sessions anyway.
