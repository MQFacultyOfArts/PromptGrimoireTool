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

### lag-admission-gate.AC2: FIFO queue with batch admission and entry tickets
- **lag-admission-gate.AC2.1 Success:** Users arriving when at cap are added to queue in arrival order and receive an opaque queue token (UUID4)
- **lag-admission-gate.AC2.2 Success:** When cap rises above admitted count, queued users are popped in FIFO order up to available capacity and granted entry tickets
- **lag-admission-gate.AC2.3 Success:** Batch admission admits multiple users per diagnostic cycle (not one-at-a-time)
- **lag-admission-gate.AC2.4 Failure:** Users in queue longer than `queue_timeout_seconds` (default 1800s / 30 min) are dropped from queue
- **lag-admission-gate.AC2.5 Edge:** User already in queue is not double-enqueued on subsequent page loads — same token returned, same position preserved
- **lag-admission-gate.AC2.6 Success:** Admitted user holds an entry ticket valid for `ticket_validity_seconds` (default 600s / 10 min); page_route consumes the ticket on first page load
- **lag-admission-gate.AC2.7 Edge:** User who closes tab and returns while still in queue sees their existing queue position (not re-queued at back)
- **lag-admission-gate.AC2.8 Edge:** User who closes tab and returns after batch admission (ticket still valid) passes through gate directly — sees main page, not queue
- **lag-admission-gate.AC2.9 Edge:** User who returns after ticket expires is treated as a fresh arrival — enters if under cap, queues if at cap

### lag-admission-gate.AC3: Gate only affects new authenticated users
- **lag-admission-gate.AC3.1 Success:** User already in `client_registry._registry` passes through gate freely (page navigation while admitted)
- **lag-admission-gate.AC3.2 Success:** Privileged users (`is_privileged_user`) bypass gate regardless of cap
- **lag-admission-gate.AC3.3 Failure:** New authenticated user redirected to `/queue?t=<token>&return=<url>` when admitted count >= cap
- **lag-admission-gate.AC3.4 Edge:** User who disconnects and reconnects within 15s `reconnect_timeout` remains in `_registry` and is not gated
- **lag-admission-gate.AC3.5 Success:** User with valid entry ticket passes through gate; ticket is consumed on use
- **lag-admission-gate.AC3.6 Success:** User still in queue is redirected to `/queue?t=<existing_token>` preserving their position

### lag-admission-gate.AC4: Queue page is lightweight and functional
- **lag-admission-gate.AC4.1 Success:** Queue page shows user's position and total queue size
- **lag-admission-gate.AC4.2 Success:** Queue page polls `/api/queue/status?t=<token>` every 5s via vanilla JS and redirects to original page on admission
- **lag-admission-gate.AC4.3 Success:** `/api/queue/status?t=<token>` returns `{position, total, admitted, expired}` JSON
- **lag-admission-gate.AC4.4 Edge:** `/api/queue/status` with invalid or missing token returns `{admitted: false, expired: true}` — queue page shows "rejoin" link
- **lag-admission-gate.AC4.5 Success:** Queue page is a raw Starlette HTML response — zero NiceGUI client overhead
- **lag-admission-gate.AC4.6 Edge:** Queue page shows "your place has expired" with rejoin link when `expired: true`

### lag-admission-gate.AC5: Admission state visible in diagnostic logs
- **lag-admission-gate.AC5.1 Success:** `memory_diagnostic` structlog event includes `admission_cap`, `admission_admitted`, `admission_queue_depth`, `admission_tickets`
- **lag-admission-gate.AC5.2 Success:** All config values (`initial_cap`, `batch_size`, `lag_increase_ms`, `lag_decrease_ms`, `queue_timeout_seconds`, `ticket_validity_seconds`) configurable via env vars

## Glossary

- **AIMD (Additive Increase, Multiplicative Decrease)**: A congestion-control algorithm used in TCP. The admission cap grows slowly under good conditions (additive increase) and shrinks rapidly under bad conditions (multiplicative decrease — halving). This creates asymmetric but stable behaviour: gradual ramp-up, fast back-off.
- **Admission cap**: The maximum number of distinct authenticated users allowed to hold active NiceGUI sessions simultaneously. Controlled dynamically by the AIMD algorithm.
- **Admission gate**: The middleware check inserted into `page_route` that compares the current active user count against the admission cap and either passes or queues a new user.
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
- **Entry ticket**: A time-limited server-side record (`_tickets: dict[UUID, float]`) granting a batch-admitted user permission to enter the application. Created when a user is popped from the queue during batch admission. Valid for `ticket_validity_seconds` (default 600s / 10 min). Consumed (deleted) when the user loads their first page via `page_route`. Allows "get coffee and come back" — user returns to the main page, not the queue.
- **Queue token**: An opaque UUID4 string issued when a user is enqueued. Passed as a URL parameter (`/queue?t=<token>&return=<url>`) and used by the queue page's polling JS to identify itself to `/api/queue/status`. The same token is returned if the user revisits while still queued, preserving their position.
- **Structlog**: The structured logging library used throughout the project. Log events are emitted as JSON with typed fields; the admission state fields (`admission_cap`, `admission_admitted`, `admission_queue_depth`) are added to the existing `memory_diagnostic` event.

## Architecture

AIMD (Additive Increase, Multiplicative Decrease) admission control using event loop lag as the congestion signal.

**Components:**

- **`src/promptgrimoire/admission.py`** (new) — module-level `AdmissionState` dataclass holding current cap, FIFO queue (`deque`), queue tokens (`dict[str, UUID]`), user-to-token reverse map (`dict[UUID, str]`), and entry tickets (`dict[UUID, float]`). Exposes `update_cap(lag_ms, admitted_count)`, `enqueue(user_id) -> str` (returns token), `admit_batch(admitted_count)`, `try_enter(user_id) -> bool` (consumes ticket), `get_queue_status(token) -> dict`, `sweep_expired()`.
- **`src/promptgrimoire/diagnostics.py`** (modified) — after measuring lag each interval, calls `admission.update_cap(lag_ms)` and runs batch admission from queue.
- **`src/promptgrimoire/pages/registry.py`** (modified) — `page_route` wrapper gains gate check after ban check: checks registry membership, then ticket, then privileged, then cap, then queue status. Redirects to `/queue?t=<token>&return=<url>`.
- **`/queue`** (new Starlette route in `__init__.py`) — raw HTML response with vanilla JS polling. Zero NiceGUI client overhead. Token and return URL passed as query parameters.
- **`GET /api/queue/status?t=<token>`** (new Starlette route) — returns JSON `{position, total, admitted, expired}` for queue page polling.

**Data flow:**

```
Diagnostic loop (30s)
  → measure event_loop_lag_ms
  → admission.update_cap(lag_ms, len(client_registry._registry))
    → lag < 10ms AND admitted near cap → cap += batch_size
    → lag > 50ms → cap = max(cap // 2, initial_cap)
    → 10–50ms → no change
  → admission.admit_batch(len(client_registry._registry))
    → if cap > admitted and queue non-empty → pop batch from queue
    → popped users get entry tickets (_tickets[user_id] = expiry)
  → admission.sweep_expired()
    → remove queue entries older than queue_timeout_seconds
    → remove tickets older than ticket_validity_seconds
  → log admission_cap, admission_admitted, admission_queue_depth, admission_tickets

Page load (page_route)
  → resolve user_id from session
  → ban check
  → if user_id in client_registry._registry → pass (already in)
  → if admission.try_enter(user_id) → pass (consume entry ticket)
  → if is_privileged_user → pass (staff bypass)
  → if len(client_registry._registry) < cap → pass (under cap)
  → if user_id already in queue → redirect /queue?t=<existing_token>&return=<url>
  → else → token = admission.enqueue(user_id) → redirect /queue?t=<token>&return=<url>

Queue page (/queue) — raw Starlette HTML
  → vanilla JS polls GET /api/queue/status?t=<token> every 5s
  → when admitted=true → window.location = returnUrl
  → when expired=true → show "your place expired" + rejoin link

User disconnects (all tabs closed, 15s reconnect_timeout expires)
  → client_registry.deregister fires via on_delete callback
  → user removed from _registry
  → next diagnostic cycle: cap > admitted → queued users get tickets

User returns from coffee (tab closed, ticket valid)
  → hits page_route → not in _registry → admission.try_enter(user_id) → True
  → ticket consumed → user enters app normally → sees main page
```

## Existing Patterns

**Diagnostic logger** (`src/promptgrimoire/diagnostics.py`): Already runs a 30s loop measuring event loop lag and memory. Cap computation hooks directly into this loop — no new background task.

**Client registry** (`src/promptgrimoire/auth/client_registry.py`): Module-level `dict[UUID, set[Client]]` tracking authenticated users to NiceGUI clients. Auto-deregisters via `on_delete` callback. The admission gate reads `len(_registry)` for admitted count and checks `user_id in _registry` for pass-through.

**`page_route` middleware** (`src/promptgrimoire/pages/registry.py`): Decorator wrapping all protected pages with auth checks, ban checks, and client registration. Gate check inserts at the same level as the ban check — after user_id resolution, before page handler.

**Raw Starlette routes** (`src/promptgrimoire/__init__.py`): `app.routes.insert(0, Route(...))` for `/healthz`, `/api/admin/kick`, `/api/pre-restart`, `/api/connection-count`. Both the queue page (`/queue`) and status endpoint (`/api/queue/status`) follow this pattern — raw Starlette, zero NiceGUI overhead.

**Return URL via query parameter:** The gate redirects to `/queue?t=<token>&return=<url-encoded-path>`. The return URL is passed as a query parameter rather than stashed in `app.storage.user`, because the queue page is a raw Starlette response without access to NiceGUI session storage. The vanilla JS reads the `return` parameter and redirects to it on admission.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Admission State Module

**Goal:** Core admission state and AIMD cap computation, independent of NiceGUI.

**Components:**
- `src/promptgrimoire/admission.py` — `AdmissionState` dataclass with AIMD cap computation, FIFO queue (`deque`), queue tokens (`dict[str, UUID]` and reverse `dict[UUID, str]`), entry tickets (`dict[UUID, float]`). Functions: `update_cap(lag_ms, admitted_count)`, `enqueue(user_id) -> str`, `admit_batch(admitted_count)`, `try_enter(user_id) -> bool`, `get_queue_status(token) -> dict`, `sweep_expired()`.
- `src/promptgrimoire/config.py` — new `AdmissionConfig` sub-model with `initial_cap`, `batch_size`, `lag_increase_ms`, `lag_decrease_ms`, `queue_timeout_seconds`, `ticket_validity_seconds`

**Dependencies:** None (pure logic, no NiceGUI dependency).

**Covers:** lag-admission-gate.AC1.*, lag-admission-gate.AC2.*

**Done when:** Unit tests verify AIMD behaviour — cap increases when lag low and server near cap, halves when lag high, stays unchanged in hysteresis band. Queue FIFO ordering and batch admission work. Entry tickets created on batch admission and consumed on try_enter. Queue expiry drops stale entries. Ticket expiry drops stale tickets.
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
- `src/promptgrimoire/pages/registry.py` — add gate check in `_with_log_context` after ban check. Check order: (1) `client_registry._registry` membership → pass, (2) `admission.try_enter(user_id)` → consume ticket and pass, (3) `is_privileged_user` → pass, (4) under cap → pass, (5) already in queue → redirect `/queue?t=<existing_token>&return=<url>`, (6) else → `admission.enqueue(user_id)` → redirect `/queue?t=<token>&return=<url>`. Return URL passed as URL-encoded query parameter (not `app.storage.user`).

**Dependencies:** Phase 1 (admission module), Phase 2 (cap is being updated).

**Covers:** lag-admission-gate.AC3.*

**Done when:** Unit tests verify: existing users pass through, ticketed users consume ticket and pass, privileged users bypass, new users redirected when at cap with token and return URL, users already in queue get same token. Tests use mock admission state (no NiceGUI server needed).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Queue Page and Status API

**Goal:** Lightweight queue page and polling endpoint.

**Components:**
- `GET /queue` Starlette route in `src/promptgrimoire/__init__.py` — raw HTML response (no NiceGUI client). Reads `t` (queue token) and `return` (original URL) from query parameters. Inline vanilla JS polls `/api/queue/status?t=<token>` every 5s. On `admitted: true`, redirects to return URL. On `expired: true`, shows "your place expired" with a rejoin link (the return URL, which re-triggers the gate).
- `GET /api/queue/status?t=<token>` Starlette route in `src/promptgrimoire/__init__.py` — validates token against admission module, returns `{position, total, admitted, expired}` JSON. Invalid/missing token returns `{admitted: false, expired: true}`.

**Dependencies:** Phase 1 (queue state), Phase 3 (redirect to /queue works).

**Covers:** lag-admission-gate.AC4.*

**Done when:** Unit tests verify status endpoint returns correct JSON for queued, admitted, expired, and invalid tokens. Integration test verifies queue page HTML contains correct JS polling logic. Direct navigation to `/queue` with invalid token shows expired state.
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

**Queue page is zero-overhead:** The queue page is a raw Starlette HTML response — no NiceGUI client, no server-side UI tree, no memory cost per queued user. This is intentional: the feature exists to protect against memory pressure, so the safety valve itself must not consume memory.

**Entry ticket model ("get coffee and come back"):** When a user's batch is admitted, they receive a time-limited entry ticket (default 10 minutes). The ticket is server-side state (`_tickets: dict[UUID, float]`), consumed when the user loads their first page. This means a user who goes for coffee during the wait returns to the main page, not the queue. If the ticket expires before they return, they re-enter the gate fresh (enters if under cap, queues if at cap).

**Queue position is durable:** A user's queue position is keyed by `user_id`, not by connection. Closing the tab and returning while still in the queue preserves their position — the gate detects their existing queue entry and redirects to `/queue` with the same token.

**Interaction with `reconnect_timeout`:** The 15s reconnect timeout means a user who refreshes their page or has a brief network blip retains their NiceGUI client and stays in `_registry`. They never hit the gate. Only after 15s of total disconnection does the client get deleted and the user lose their spot. After disconnection, if the user was batch-admitted while away, their entry ticket lets them back in without re-queuing.

**Cap floor:** The cap never drops below `initial_cap` (default 20), even under extreme lag. This ensures some minimum number of users can always access the system. The existing `graceful_memory_shutdown` at 3GB remains the last resort.

**No persistence:** Admission state is entirely in-memory. Server restart resets everything — cap goes back to `initial_cap`, queue is cleared, tickets are invalidated. This is acceptable because restart invalidates all sessions anyway.
