# Idle Tab Eviction Design

**GitHub Issue:** #471

## Summary

PromptGrimoire runs in shared classroom settings where students routinely leave browser tabs open after class ends. Each connected tab holds server memory — a NiceGUI client UI tree, a CRDT subscription, and a presence slot — regardless of whether anyone is actually using it. This feature reclaims those resources automatically by evicting tabs that have been idle for 30 minutes, freeing server capacity for active users without losing any annotation work.

The implementation is deliberately client-side: a small JavaScript module (`idle-tracker.js`) watches for click, keypress, and scroll events and tracks inactivity using wall-clock time rather than accumulated timer intervals. This sidesteps Chrome's background tab throttling, which can slow `setTimeout` to once per minute for hidden tabs. When a tab goes idle, JS navigates to a lightweight `/paused` landing page (a raw Starlette handler with no NiceGUI overhead), and the server's existing disconnect lifecycle cleans up resources. Students are warned 60 seconds before eviction and can dismiss the countdown by interacting with the page. When they return, the admission gate recognises them as recently-evicted and places them at the front of any queue rather than the back. All CRDT annotation state is preserved through the existing `on_delete` persistence path — eviction is transparent to the student's work.

## Definition of Done

1. **Server reclaims resources from idle clients.** After 30 minutes of no click/keypress/scroll, the server disconnects the NiceGUI client, freeing its UI tree, CRDT subscriptions, and presence slot.
2. **Students get a warning before eviction.** A modal appears ~60 seconds before disconnection: "Session will pause in N seconds — click to stay active." On tab refocus (`visibilitychange`), the modal shows immediately if the user is in the warning window.
3. **Evicted students re-enter with priority.** Returning users are placed at the front of the admission queue (`appendleft`), not the back. They still go through the gate — no bypass.
4. **CRDT state is preserved.** Existing `on_delete` persistence means no annotation data is lost on eviction.
5. **Configurable via pydantic-settings.** Timeout and warning period are environment variables (`IDLE__TIMEOUT_SECONDS`, `IDLE__WARNING_SECONDS`).

## Acceptance Criteria

### idle-tab-eviction-471.AC1: Server reclaims resources from idle clients
- **idle-tab-eviction-471.AC1.1 Success:** After 30 minutes of no click/keypress/scroll, the NiceGUI client is disconnected and its UI tree is freed from server memory
- **idle-tab-eviction-471.AC1.2 Success:** Idle eviction applies to all `page_route`-decorated pages (annotation, navigator, courses, roleplay)
- **idle-tab-eviction-471.AC1.3 Success:** CRDT subscriptions and remote presence slots are released on eviction (existing `on_delete` lifecycle)
- **idle-tab-eviction-471.AC1.4 Edge:** A click/keypress/scroll at minute 29 resets the 30-minute timer completely
- **idle-tab-eviction-471.AC1.5 Edge:** Idle timer uses wall-clock time (`Date.now()`), not accumulated `setTimeout` intervals — Chrome tab throttling does not delay eviction beyond the configured timeout

### idle-tab-eviction-471.AC2: Students get a warning before eviction
- **idle-tab-eviction-471.AC2.1 Success:** Warning modal appears 60 seconds before eviction with a live countdown
- **idle-tab-eviction-471.AC2.2 Success:** Clicking "Stay Active" on the modal dismisses it and resets the idle timer
- **idle-tab-eviction-471.AC2.3 Success:** Any click/keypress/scroll during the warning window dismisses the modal and resets the timer
- **idle-tab-eviction-471.AC2.4 Success:** On `visibilitychange` (tab refocus), if in warning window, modal appears immediately with correct remaining time
- **idle-tab-eviction-471.AC2.5 Success:** On `visibilitychange`, if past timeout, navigation to `/paused` occurs immediately without showing the modal
- **idle-tab-eviction-471.AC2.6 Edge:** On `visibilitychange`, if below warning threshold, focus event resets the timer (no modal shown)

### idle-tab-eviction-471.AC3: Evicted students re-enter with priority
- **idle-tab-eviction-471.AC3.1 Success:** Evicted user navigates to `/paused?return={original_path}` and sees Resume button pointing to the original page
- **idle-tab-eviction-471.AC3.2 Success:** Clicking Resume with admission gate open returns user directly to their original page
- **idle-tab-eviction-471.AC3.3 Success:** Clicking Resume with admission gate at capacity places user at front of queue (`appendleft`), not the back
- **idle-tab-eviction-471.AC3.4 Failure:** `/paused?return=https://evil.com` defaults to `/` (open-redirect guard)
- **idle-tab-eviction-471.AC3.5 Failure:** `/paused` with no `return` parameter defaults Resume to `/`
- **idle-tab-eviction-471.AC3.6 Success:** `/paused` page creates no NiceGUI client (raw Starlette handler)

### idle-tab-eviction-471.AC4: CRDT state is preserved
- **idle-tab-eviction-471.AC4.1 Success:** After eviction and resume, all previously saved annotations are intact (CRDT state persisted via existing `on_delete` handler)
- **idle-tab-eviction-471.AC4.2 Edge:** If user was mid-edit (unsaved text in an input field) when evicted, the unsaved text is lost but all previously committed CRDT state is preserved

### idle-tab-eviction-471.AC5: Configurable via pydantic-settings
- **idle-tab-eviction-471.AC5.1 Success:** `IDLE__TIMEOUT_SECONDS=900` sets idle timeout to 15 minutes
- **idle-tab-eviction-471.AC5.2 Success:** `IDLE__WARNING_SECONDS=120` sets warning countdown to 2 minutes
- **idle-tab-eviction-471.AC5.3 Success:** `IDLE__ENABLED=false` disables idle eviction entirely (no script injected, no event listeners attached)
- **idle-tab-eviction-471.AC5.4 Success:** Defaults are 1800s timeout, 60s warning, enabled=true

### idle-tab-eviction-471.AC6: Login page element reduction — DROPPED

**Rationale:** Dropped during implementation planning (2026-04-03). `ui.card()` context managers cannot be replaced with `ui.html()` without breaking NiceGUI's slot model for child event handlers. The achievable reduction (~20 to ~10-12 elements) did not justify the effort. Replaced by AC7 (pre-auth landing page).

### idle-tab-eviction-471.AC7: Pre-auth landing page
- **idle-tab-eviction-471.AC7.1 Success:** `GET /welcome` returns static HTML with "Login to PromptGrimoire" button linking to `/login?return=/`
- **idle-tab-eviction-471.AC7.2 Success:** `/welcome` creates no NiceGUI client (raw Starlette handler, no WebSocket)
- **idle-tab-eviction-471.AC7.3 Success:** Clicking Login on `/welcome` navigates to `/login?return=/`, and after authentication returns user to `/`
- **idle-tab-eviction-471.AC7.4 Success:** `/welcome` renders correctly with same visual style as `/paused` and `/queue` pages

## Glossary

- **NiceGUI client**: The server-side object created for each connected browser tab. Holds the full UI element tree in memory. Created on WebSocket connect, deleted after the socket closes and `reconnect_timeout` expires.
- **CRDT (Conflict-free Replicated Data Type)**: The data structure used to store annotation state. Designed so concurrent edits from multiple users merge without conflicts. Implemented via the `pycrdt` library.
- **`on_delete` handler**: A NiceGUI lifecycle callback that fires when a client is permanently removed from the server. Used here to persist CRDT state and release presence slots before memory is freed.
- **`page_route` decorator**: The central middleware function (`pages/registry.py`) that wraps all authenticated page handlers. Performs ban checks, admission gate evaluation, and client registration before handing off to the page.
- **Admission gate**: An AIMD-based server overload protection mechanism that queues incoming users when event-loop lag is high. Governs how many new NiceGUI clients can connect simultaneously.
- **AIMD (Additive Increase / Multiplicative Decrease)**: A congestion-control algorithm borrowed from TCP. The admission gate increases its capacity cap linearly when lag is low and halves it when lag spikes.
- **`appendleft`**: Python `deque` operation that inserts at the front rather than the back. Used to give priority queue position to returning idle-evicted users.
- **`reconnect_timeout`**: A NiceGUI server setting (currently 15 seconds) that controls how long the server waits after a WebSocket disconnect before permanently deleting the client and firing `on_delete`.
- **`visibilitychange`**: A browser DOM event fired when a tab is hidden or made visible again (switching tabs, minimising the window). Used here to immediately evaluate idle state when a student returns to a backgrounded tab.
- **Starlette handler**: A raw ASGI request handler, used here for `/paused` (and already used for `/queue`). Returns a plain HTTP response with no NiceGUI client overhead.
- **pydantic-settings**: The library used for typed, environment-variable-backed configuration. The `IDLE__` prefix group follows the same pattern as existing `ADMISSION__`, `FEATURES__`, and `EXPORT__` groups.
- **Wall-clock time**: Absolute elapsed time measured via `Date.now()` in JavaScript, as opposed to accumulated `setTimeout` intervals. Resistant to Chrome's background tab throttling.
- **`ui.html()`**: A NiceGUI element that renders raw HTML on the server without creating additional server-side element objects. Used in the login page reduction to lower per-client memory cost.
- **`window.__idleConfig`**: A JavaScript global injected by `page_route` carrying the server-side idle configuration (timeout, warning period, enabled flag) as a JSON object read by `idle-tracker.js`.
- **Remote presence slot**: A registration in the server's presence tracking system that marks a user as "currently viewing" a workspace. Released when the NiceGUI client is deleted.
- **Vitest + happy-dom**: The JavaScript unit test stack used for testing `idle-tracker.js` logic in isolation, without a real browser.

## Architecture

Pure client-side idle eviction. A global JavaScript module (`idle-tracker.js`) tracks user inactivity via wall-clock timestamps, shows a warning modal before eviction, and navigates to a lightweight `/paused` page when the timeout expires. The server performs no idle tracking — standard NiceGUI disconnect lifecycle (`reconnect_timeout=15.0` → `client.delete()`) handles resource cleanup.

**Data flow:**

1. `page_route` injects `idle-tracker.js` and `window.__idleConfig` on every page load
2. JS records `Date.now()` on click/keypress/scroll events
3. A polling loop (`min(10s, warningMs / 2)` interval) compares current time against last interaction timestamp
4. At `(timeout - warning)` seconds idle: warning modal appears with live countdown
5. At `timeout` seconds idle: JS navigates to `/paused?return={current_path}`
6. NiceGUI detects WebSocket disconnect → 15s grace → `client.delete()` fires
7. `on_delete` handlers persist CRDT state, broadcast peer departure, deregister from client registry
8. User clicks Resume on `/paused` → page load → `page_route` → admission gate
9. Admission gate sees expired ticket for known `user_id` → `appendleft` (priority re-entry)

**Why pure client-side:** The target scenario is connected-but-idle tabs — the WebSocket is alive, JS is running, but the user isn't interacting. Browser-initiated tab freezing (which kills the WebSocket) is already handled by `reconnect_timeout`. Adding server-side idle tracking would duplicate effort for negligible gain in a classroom context where adversarial clients are not a concern.

**Wall-clock time, not timer accumulation:** Chrome's intensive throttling (after 5 minutes hidden) caps `setTimeout` to ~1 check/minute. The idle tracker stores `lastInteractionTime = Date.now()` and compares against `Date.now()` on each poll, ensuring accurate idle measurement regardless of timer throttling. A tab hidden for 25 minutes then refocused will correctly show ~5 minutes remaining in the warning window.

**`visibilitychange` integration:** On tab refocus, the handler immediately evaluates idle state:
- Past timeout → navigate to `/paused` immediately
- In warning window → show modal with correct remaining seconds
- Below threshold → focus counts as interaction, reset timer

**Warning modal:** Rendered by JS as a DOM overlay (not a NiceGUI element). Contains a countdown timer updated every 1 second (this inner timer only runs while the tab is visible and the modal is shown). A "Stay Active" button dismisses the modal and resets the idle timer. Any click/keypress/scroll also dismisses and resets.

**`/paused` page:** Raw Starlette handler (same pattern as `/queue` in `queue_handlers.py`). No NiceGUI client created. Renders static HTML with "Your session was paused due to inactivity" and a Resume button linking to the `return` URL. Open-redirect guard (`_SAFE_RETURN_RE`) validates the return path.

**Login page reduction:** Separate from idle eviction but compensates for excluding `/login` from idle tracking. Static/decorative NiceGUI elements (`ui.label`, `ui.card` wrappers, dividers) are replaced with `ui.html()` blocks, reducing per-client server-side element count from ~15-20 to ~5-6 (buttons + email input only).

## Existing Patterns

**`/queue` raw Starlette handler** (`src/promptgrimoire/queue_handlers.py`): The `/paused` page follows this exact pattern — raw HTML response with vanilla JS, zero NiceGUI client overhead. Registered as a Starlette route alongside `/queue`.

**`page_route` middleware** (`src/promptgrimoire/pages/registry.py:218-309`): Central decorator through which all authenticated pages pass. Handles ban checks, admission gate, client registration. The idle config injection hooks into this decorator after client registration.

**Admission gate priority re-entry** (`src/promptgrimoire/admission.py:85-118`): `enqueue()` already detects returning users with expired tickets (`user_id in _user_tokens` with stale ticket) and sets `priority = True` → `appendleft`. No changes needed — idle-evicted users follow this existing path.

**`app.storage.user` persistence**: Server-side persistent storage survives NiceGUI client deletion. The `user_id` embedded in `auth_user` dict persists across eviction/reconnection, ensuring the admission gate recognises returning users.

**Static JS loading** (`src/promptgrimoire/static/`): Existing JS files (`annotation-highlight.js`, `annotation-card-sync.js`) are served from `/static/` via `app.add_static_files()` in `src/promptgrimoire/__init__.py:282-283`. `idle-tracker.js` follows the same pattern.

**Config sub-models** (`src/promptgrimoire/config.py`): Existing nested pydantic-settings groups (`DATABASE__`, `ADMISSION__`, `FEATURES__`, `EXPORT__`) provide the pattern for `IDLE__`.

**`return=` URL chaining**: `/login` already honours `?return=<path>` via `post_login_return` in `app.storage.user`. `/paused` uses the same pattern, and the return URL chains through `/queue` and `/login` if needed.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Configuration
**Goal:** Add `IdleConfig` pydantic-settings sub-model with kill switch

**Components:**
- `IdleConfig` class in `src/promptgrimoire/config.py` — `IDLE__TIMEOUT_SECONDS` (int, default 1800), `IDLE__WARNING_SECONDS` (int, default 60), `IDLE__ENABLED` (bool, default True)
- Unit test verifying defaults and env var override

**Dependencies:** None

**Done when:** `IdleConfig` loads from environment variables, defaults are correct, `get_settings().idle` accessible
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: `/paused` Page
**Goal:** Lightweight Starlette handler for the paused landing page

**Components:**
- `/paused` route handler in `src/promptgrimoire/queue_handlers.py` — renders static HTML with "Session paused" message and Resume button
- Return URL passthrough via `?return=` query parameter
- Open-redirect guard (same `_SAFE_RETURN_RE` pattern as `/login`)
- Unit tests for return URL validation and HTML rendering

**Dependencies:** None (can be built in parallel with Phase 1)

**Done when:** `GET /paused?return=/annotation/uuid` renders page with Resume button pointing to `/annotation/uuid`, invalid return URLs default to `/`
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: `idle-tracker.js`
**Goal:** Client-side idle detection with warning modal and eviction navigation

**Components:**
- `src/promptgrimoire/static/idle-tracker.js` — event listeners (click, keypress, scroll), wall-clock idle polling (adaptive interval: `min(10s, warningMs / 2)`), warning modal rendering, `visibilitychange` handler, navigation to `/paused?return=...`
- Reads config from `window.__idleConfig` (`timeoutMs`, `warningMs`, `enabled`)
- Warning modal: DOM overlay with countdown, "Stay Active" button
- Vitest + happy-dom unit tests in `tests/js/` — timer logic, config reading, visibility handler, modal show/dismiss, navigation trigger

**Dependencies:** None (standalone JS module, tested independently)

**Done when:** Vitest tests pass for: idle detection triggers at correct wall-clock time, warning modal appears at correct threshold, interaction resets timer, `visibilitychange` evaluates idle state correctly, disabled config prevents attachment
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: `page_route` Integration
**Goal:** Inject idle tracker and config into all `page_route`-decorated pages

**Components:**
- `page_route` decorator in `src/promptgrimoire/pages/registry.py` — after client registration, inject `ui.add_head_html()` with `window.__idleConfig` JSON and `<script src="/static/idle-tracker.js"></script>` when `IDLE__ENABLED` is True
- Integration tests verifying: config injection present when enabled, absent when disabled, correct timeout values from settings

**Dependencies:** Phase 1 (config), Phase 3 (idle-tracker.js)

**Done when:** Every `page_route` page includes the idle tracker script and config when enabled, omits both when disabled
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Login Page Element Reduction
**Goal:** Reduce NiceGUI server-side element count on `/login` by migrating static elements to `ui.html()`

**Components:**
- `src/promptgrimoire/pages/auth.py` login page handler — replace decorative `ui.label` (page title, section headings, "— or —" dividers) and `ui.card` wrappers with `ui.html()` blocks
- Keep interactive elements as NiceGUI: `ui.button` (on_click handlers), `ui.input` (value binding), `ui.notify` calls
- Test verifying reduced element count (count `client.elements` or equivalent)

**Dependencies:** None (independent of idle eviction)

**Done when:** Login page renders identically in the browser, interactive elements still function, server-side element count reduced from ~15-20 to ~5-6
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: E2E Idle Eviction Flow
**Goal:** End-to-end tests covering the full idle → warning → eviction → resume cycle

**Components:**
- Playwright E2E tests in `tests/e2e/` with `@pytest.mark.noci` and `@pytest.mark.slow` markers
- Test scenarios:
  - Idle timeout triggers warning modal, then navigates to `/paused`
  - Clicking "Stay Active" during warning resets the timer
  - Resume button on `/paused` returns to original page through admission gate (gate open)
  - Resume with admission gate at capacity routes through `/queue` with priority
  - `visibilitychange` on refocus: immediate eviction if past timeout, warning if in window
- Test config: `IDLE__TIMEOUT_SECONDS=5`, `IDLE__WARNING_SECONDS=2`
- Login page element reduction: verify buttons and input still work after `ui.html()` migration

**Dependencies:** Phases 1-5 (all components integrated)

**Done when:** All E2E scenarios pass in `e2e slow` lane, both gate-open and gate-full resume paths verified
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Documentation
**Goal:** Update user-facing documentation to reflect idle eviction behaviour

**Components:**
- Update `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — document session timeout behaviour, warning modal, how to resume
- Update `docs/configuration.md` — document `IDLE__` environment variables
- `uv run grimoire docs build` must succeed

**Dependencies:** Phases 1-6 (document what was built)

**Done when:** Docs build succeeds, idle timeout behaviour documented for students, configuration documented for operators
<!-- END_PHASE_7 -->

## Additional Considerations

**Browser-initiated tab freezing overlap:** Chrome Energy Saver can freeze tabs after ~5 minutes hidden, killing the WebSocket. This is handled by existing `reconnect_timeout=15s` → `client.delete()`, not by idle eviction. The two mechanisms are complementary: idle eviction handles connected-but-inactive tabs; reconnect timeout handles disconnected tabs. If a tab is frozen by the browser, JS stops executing, so the idle tracker's polling loop pauses. When unfrozen, the `visibilitychange` handler fires and evaluates wall-clock idle time, which may trigger immediate eviction if 30+ minutes have passed.

**Classroom stampede scenario:** When a lecturer says "open your laptops", 100+ previously-idle students may resume simultaneously. The admission gate handles this naturally — priority re-entry via `appendleft` puts them at the front, but `admit_batch()` processes them in controlled batches governed by the AIMD cap. No special handling needed beyond the existing admission gate behaviour.
