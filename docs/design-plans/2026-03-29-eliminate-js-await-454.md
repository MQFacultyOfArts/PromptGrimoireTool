# Eliminate Awaited JavaScript Calls Design

**GitHub Issue:** #454

## Summary

The annotation page's "respond" tab uses NiceGUI's `await ui.run_javascript()` to communicate with browser tabs — asking them "what's your current markdown?", "what's the scroll position?", or sending cursor/selection broadcasts and waiting for acknowledgement. Each call blocks a Python asyncio task for between 1 and 5 seconds waiting for one specific browser to respond. At 120+ concurrent users, the broadcast loops are the worst case: a single cursor movement iterates all connected clients and awaits each one individually, accumulating up to 240 cumulative seconds of event loop hold time per broadcast cycle. Production evidence shows 200–600ms lag spikes correlating directly with these timeouts.

The fix inverts the communication direction. Instead of the server pulling data from browsers, browsers push data to the server at the moment it is produced (via `emitEvent()` / `ui.on()` events). Instead of the server awaiting confirmation of JS commands it sends, those commands become fire-and-forget. For the three "what's your markdown?" call sites, the existing `respond_yjs_update` event is extended to include the current markdown alongside the Yjs binary diff — the client already has the markdown, so adding it to the existing event means zero new round-trips and the server always has a current copy. This pattern is already used for the highest-frequency interactions in the codebase; the work extends it to the 15 remaining `await run_javascript()` call sites and adds a guard test to prevent regression.

## Definition of Done

All `await ui.run_javascript()` and `await client.run_javascript()` calls in production code (`src/promptgrimoire/`, excluding spike/demo pages) are eliminated. The server never blocks the asyncio event loop waiting for a browser response. A guard test prevents regression. All existing functionality (editor init, markdown sync, scroll preservation, paste handling, broadcast, pre-restart flush) maintains functional equivalence. Event loop lag spikes of 200-600ms at 120+ concurrent users are structurally impossible because no handler holds an asyncio task waiting on a single client.

## Acceptance Criteria

### eliminate-js-await-454.AC1: Broadcast calls are non-blocking
- **eliminate-js-await-454.AC1.1 Success:** Cursor broadcast to N connected clients completes without holding the event loop for more than one message send cycle
- **eliminate-js-await-454.AC1.2 Success:** Selection broadcast to N connected clients completes without holding the event loop
- **eliminate-js-await-454.AC1.3 Success:** Cursor/selection removal on client disconnect is fire-and-forget
- **eliminate-js-await-454.AC1.4 Failure:** A disconnected/slow client does not block broadcasts to other clients
- **eliminate-js-await-454.AC1.5 Failure:** A client that never responds to JS does not cause a timeout exception in the broadcast loop

### eliminate-js-await-454.AC2: Editor initialisation is non-blocking
- **eliminate-js-await-454.AC2.1 Success:** `render_respond_tab()` returns without awaiting browser JS execution
- **eliminate-js-await-454.AC2.2 Success:** Full-state CRDT sync and editor seeding execute after `crepe.create()` resolves (bundled in the same JS evaluation block, no separate round-trip)
- **eliminate-js-await-454.AC2.3 Success:** `has_milkdown_editor` flag on `PageState` and `_RemotePresence` is set only after the browser emits `editor_ready`, not when `render_respond_tab()` returns
- **eliminate-js-await-454.AC2.4 Success:** `_broadcast_yjs_update()` does not send `_applyRemoteUpdate()` to a client until that client's `editor_ready` event has been received
- **eliminate-js-await-454.AC2.5 Edge:** If `_createMilkdownEditor` fails on the client (JS exception), `editor_ready` fires with `{status: 'error', error: msg}`. The Python handler logs the failure and does NOT set `has_milkdown_editor`, excluding the client from Yjs relay

### eliminate-js-await-454.AC3: Markdown sync uses client-pushed state
- **eliminate-js-await-454.AC3.1 Success:** The `respond_yjs_update` event payload includes a `markdown` field alongside the Yjs binary diff, and the Python handler writes it to `response_draft_markdown` without a JS round-trip
- **eliminate-js-await-454.AC3.2 Success:** `_sync_markdown_to_crdt()` reads markdown from the event payload (or from `response_draft_markdown` already populated by a prior event), not from `getMilkdownMarkdown`
- **eliminate-js-await-454.AC3.3 Success:** PDF export reads markdown from `response_draft_markdown` (promoting the existing fallback to primary path)
- **eliminate-js-await-454.AC3.4 Success:** Pre-restart flush sends fire-and-forget `window._flushRespondMarkdownNow()` to all clients, which emits a distinct `respond_markdown_flush` event (not `respond_yjs_update`), waits 1 second for events to drain, then reads from `response_draft_markdown`
- **eliminate-js-await-454.AC3.5 Success:** The `respond_markdown_flush` handler writes to `response_draft_markdown` only — it does NOT relay to peers, update badges, or trigger collaborative edit side-effects
- **eliminate-js-await-454.AC3.6 Edge:** Pre-restart flush is best-effort loss minimisation, not a hard durability guarantee. Any markdown received before the 1-second drain deadline is persisted; late or non-responsive clients may lose their last unsynced edits. This is the explicit brownout trade-off: bounded shutdown latency over waiting for every client
- **eliminate-js-await-454.AC3.7 Edge:** If no Yjs updates have been received (user opened tab but never typed), `response_draft_markdown` holds the last-persisted value from the database — this is correct for pre-restart flush and PDF export (no unsaved edits exist)

### eliminate-js-await-454.AC4: Paste and scroll use non-blocking patterns
- **eliminate-js-await-454.AC4.1 Success:** Paste submit handler receives all three values in the event payload: paste HTML, platform hint, AND live editor content as fallback — no JS round-trip
- **eliminate-js-await-454.AC4.2 Success:** When no paste data exists, the handler uses the editor content from the event payload (not server-side `content_input.value`), avoiding the stale-value socket ordering problem that `on_submit_with_value` was designed to prevent
- **eliminate-js-await-454.AC4.3 Success:** Organise tab scroll position is preserved across container rebuilds using client-side state only

### eliminate-js-await-454.AC5: Admin/restart paths are non-blocking
- **eliminate-js-await-454.AC5.1 Success:** Pre-restart client navigation is fire-and-forget
- **eliminate-js-await-454.AC5.2 Success:** Memory-threshold restart navigation is fire-and-forget
- **eliminate-js-await-454.AC5.3 Success:** Ban redirect is fire-and-forget

### eliminate-js-await-454.AC6: Guard test prevents regression
- **eliminate-js-await-454.AC6.1 Success:** A test scans `src/promptgrimoire/` for `await ...run_javascript()` and fails if any are found outside the allowlist
- **eliminate-js-await-454.AC6.2 Success:** Allowlist covers only spike/demo pages (`milkdown_spike.py`, `text_selection.py`, `highlight_api_demo.py`)
- **eliminate-js-await-454.AC6.3 Failure:** Adding a new `await ui.run_javascript()` in production code causes the guard test to fail

## Glossary

- **asyncio event loop**: Python's single-threaded concurrency mechanism. Each "turn" of the loop runs one coroutine until it yields. Blocking the loop (e.g. waiting on a browser response) prevents all other requests from being handled until that wait completes.
- **`await ui.run_javascript()`**: NiceGUI API that sends a JavaScript string to a specific browser tab via WebSocket and suspends the calling Python coroutine until the browser executes it and returns a result. The return value may or may not be used.
- **fire-and-forget**: Sending a message or command without waiting for a response or acknowledgement. The sender continues immediately; success or failure is not checked synchronously.
- **`emitEvent()` / `ui.on()`**: NiceGUI's client → server event mechanism. JavaScript calls `emitEvent('event_name', data)` in the browser; Python registers `ui.on('event_name', handler)` to receive the data. Non-blocking by design — the server handles the event when the event loop is free.
- **NiceGUI outbox FIFO**: NiceGUI queues all outgoing messages to a client (both JavaScript commands and DOM updates) in a single `deque` per client. Messages execute in send order. This guarantees that fire-and-forget JS sent before a DOM clear arrives at the browser before the clear does.
- **CRDT / pycrdt**: Conflict-free Replicated Data Type. The application uses pycrdt (a Python Yjs binding) to store document state — including `response_draft_markdown` — in a structure that merges concurrent edits without conflicts. The server has the current CRDT state; it does not need to ask the browser.
- **Yjs / `respond_yjs_update`**: Yjs is the CRDT protocol the editor uses to synchronise state. When the user types, the Milkdown editor emits a `respond_yjs_update` event carrying the binary diff. The server's `on_yjs_update` handler applies it to the server-side CRDT, updating the `response_draft` XmlFragment. Currently, `_sync_markdown_to_crdt()` then does a separate JS round-trip to extract the markdown mirror — this design replaces that round-trip by extending the event payload to include the markdown directly.
- **Milkdown / `_createMilkdownEditor`**: Milkdown is a WYSIWYG markdown editor built on ProseMirror, embedded in the annotation page's respond tab. `_createMilkdownEditor` is the JavaScript function that initialises the editor instance (`crepe.create()` is async on the browser side).
- **`editor_ready` event**: A new `emitEvent` fired by the browser at the end of the bundled editor init JS block. On success (after `crepe.create()` resolves, full-state sync, and markdown seeding): `{status: 'ok'}`. On failure (JS exception during init): `{status: 'error', error: msg}`. The Python handler sets `has_milkdown_editor = True` only on `'ok'`, and logs structured failure on `'error'`. This gates Yjs relay — without this event, `_broadcast_yjs_update()` would send `_applyRemoteUpdate()` to a client whose editor hasn't finished initialising.
- **`respond_markdown_flush` event**: A new `emitEvent` fired by the browser in response to a fire-and-forget `window._flushRespondMarkdownNow()` call during pre-restart. Carries `{markdown, client_id}`. The Python handler writes to `response_draft_markdown` only — no peer relay, no badge update, no collaborative side-effects. Distinct from `respond_yjs_update` because shutdown flush is not a collaborative edit.
- **`on_submit_with_value` (value-capture pattern)**: A codebase helper that reads a DOM input value client-side at click time and passes it in the event payload, avoiding a server-side round-trip to query input state. The paste handler conversion extends this pattern to paste buffer data.
- **`_background_tasks` set**: A module-level `set[asyncio.Task]` used to retain references to fire-and-forget asyncio tasks, preventing the garbage collector from cancelling them before they complete.
- **Category A / B / C**: The design's taxonomy for `await run_javascript()` call sites. A = server pulls data from browser (requires inversion). B = server sends a command and awaits confirmation it never uses (drop the await). C = ephemeral client state that never needed to leave the browser (keep client-side).
- **AST guard test**: A unit test that parses the source code as an Abstract Syntax Tree to find `await ...run_javascript()` expressions. Fails if any are found outside an allowlist of spike/demo pages. More reliable than a grep-based check because it cannot be fooled by comments or string literals.
- **structlog**: The structured logging library used throughout the application. Produces JSON log lines. Every `except` block must log via structlog — no silent exception swallowing.

## Architecture

### The Problem

NiceGUI's `await ui.run_javascript(code)` sends JavaScript to a specific browser tab via WebSocket and blocks the Python asyncio event loop until the browser executes the code and returns a result. Each call holds an asyncio task for up to the timeout duration (1–5 seconds depending on the call site).

At 120+ concurrent users, multiple simultaneous page interactions (tab switches, broadcasts, editor initialisation) queue these blocking awaits. When any single client is slow (mobile device, poor connection, heavy DOM), its timeout degrades the event loop for all connected users. Evidence from production (2026-03-29): transient lag spikes of 200–600ms correlated with `respond.py:589` timeouts at 120 users.

NiceGUI's own documentation states: "The event loop consumes pieces of computation one at a time with the assumption that each piece is very fast (ideally < 10 ms)." A 5-second await violates this by three orders of magnitude.

### The Principle: Invert the Communication Direction

The current pattern has the server *pulling* data from the browser — "what's your markdown?", "what's your scroll position?" This is architecturally backwards for a WebSocket application. The server blocks waiting for one browser among hundreds to respond.

The fix inverts the direction. Data flows **client → server via events**; commands flow **server → client via fire-and-forget**. The server never waits on a browser.

This is not a novel pattern. The codebase already implements it for the highest-frequency interactions:
- Text selections: `emitEvent('selection_made')` → `ui.on('selection_made', handler)`
- Cursor positions: `emitEvent('cursor_move')` → `ui.on('cursor_move', handler)`
- CRDT updates: `emitEvent('respond_yjs_update')` → `ui.on('respond_yjs_update', handler)`

These paths already handle 120+ users without lag because they never block. This design extends the same pattern to the remaining call sites.

**Why not `asyncio.gather()` on the broadcast loops?** Parallelising the broadcast loop reduces O(n × timeout) to O(timeout), which helps. But it doesn't fix single-client calls (editor init, markdown sync, scroll save, paste data), and those are the call sites that triggered #454. It also doesn't prevent future `await run_javascript()` calls from reintroducing the problem. The event-driven inversion eliminates the entire class of issue; `gather()` only treats one symptom.

**Why not just reduce timeouts?** A 1-second timeout releases the task sooner but still blocks for 1 second per call. Under load, even 1-second holds compound across concurrent requests. And reducing timeouts increases failure rates on slow clients — trading latency for correctness. The inversion avoids this trade-off entirely.

### Three Categories of Awaited Calls

Every `await ...run_javascript()` in `src/promptgrimoire/` falls into one of three categories, each with a different elimination strategy:

| Category | Pattern | Strategy | Call sites |
|----------|---------|----------|------------|
| **A: Server pulls data** | Server asks browser for data, blocks on response | Invert to client-push via `emitEvent()` or restructure to use existing server-side state | 6 sites |
| **B: Server sends command** | Server sends JS to browser, awaits confirmation it doesn't use | Drop the `await` — fire-and-forget | 7 sites |
| **C: Ephemeral client state** | Server round-trips data that never needs to leave the browser | Keep entirely client-side | 1 site |

### Inventory

| # | File | Line | Category | What | Timeout |
|---|------|------|----------|------|---------|
| 1 | `respond.py` | 589 | B | Editor init (`_createMilkdownEditor`) | 5.0s |
| 2 | `respond.py` | 368 | A | `getMilkdownMarkdown` (tab leave sync) | 3.0s |
| 3 | `pdf_export.py` | 218 | A | `getMilkdownMarkdown` (PDF export) | 3.0s |
| 4 | `restart.py` | 92 | A | `getMilkdownMarkdown` (pre-restart flush) | 3.0s |
| 5 | `tab_bar.py` | 177 | C | Scroll position save before rebuild | 1.0s |
| 6–7 | `paste_handler.py` | 45–46 | A | Paste buffer + platform hint | 1.0s |
| 8 | `broadcast.py` | 108 | B | Generic JS broadcast (per-client loop) | 2.0s |
| 9 | `broadcast.py` | 173 | B | Remote cursor render (per-client loop) | 2.0s |
| 10 | `broadcast.py` | 216 | B | Remote selection render (per-client loop) | 2.0s |
| 11 | `broadcast.py` | 309 | B | Cursor/selection removal (per-client loop) | 2.0s |
| 12 | `broadcast.py` | 520 | B | Revocation notification (per-client loop) | 2.0s |
| 13 | `restart.py` | 160 | B | Navigate to /restarting (per-client loop) | 2.0s |
| 14 | `diagnostics.py` | 236 | B | Navigate to /restarting (per-client loop) | 2.0s |
| 15 | `client_registry.py` | 61 | B | Ban redirect | 2.0s |

The broadcast loops (#8–14) are the worst scaling offenders: each iterates all connected clients and awaits per-client. At 120 clients, a single cursor broadcast blocks for up to O(120 × 2s) = 240s of cumulative event loop hold time.

## Existing Patterns

### Patterns Followed

**`emitEvent()` + `ui.on()` for client → server data (5 existing production events):**
Already used for `selection_made`, `selection_cleared`, `cursor_move`, `keydown`, `respond_yjs_update`. All registered in `pages/annotation/document.py` and `pages/annotation/respond.py`. This design extends the pattern with the `editor_ready` event for readiness gating, adds a `markdown` field to the existing `respond_yjs_update` event payload to replace the `getMilkdownMarkdown` JS round-trip, and introduces `respond_markdown_flush` as a distinct pre-restart flush event (separate from the collaborative edit event to avoid triggering relay/badge side-effects during shutdown).

**Fire-and-forget `run_javascript()` for server → client commands:**
Already used in `broadcast.py:470` (`_broadcast_yjs_update`), `broadcast.py:259/278` (cursor/selection replay), `respond.py:634/649` (scroll save/restore in reference panel), `cards.py:47/378/546` (card positioning). The existing Yjs broadcast at `broadcast.py:470` is the model for converting the remaining broadcast loops.

**Background task retention via `_background_tasks` set:**
`pages/annotation/__init__.py:199` uses a module-level `set[asyncio.Task]` with `add_done_callback(discard)` to prevent GC of fire-and-forget tasks. Used by `_notify_other_clients()` at `broadcast.py:116`.

**NiceGUI outbox FIFO ordering guarantee:**
Messages (both JS commands and DOM updates) queue in a single `deque` per client in `nicegui/outbox.py`. Socket.IO preserves per-connection message ordering. This means sequential fire-and-forget JS calls execute in send order on the client — verified by reading NiceGUI source (`outbox.py:84–128`, `awaitable_response.py`, `client.py`).

### Pattern Divergence

**No existing pattern divergence.** All strategies use patterns already established in the codebase. The only new elements are the `editor_ready` event (extending the existing `emitEvent` pattern to a new event type) and the markdown field added to the `respond_yjs_update` event payload.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Fire-and-Forget Conversions (Category B + C)

**Goal:** Eliminate all awaited JS calls that don't use the return value. This covers the broadcast loops (worst scaling offender) and the editor init (the call site that triggered #454).

**Components:**

- `broadcast.py` (5 sites: lines 108, 173, 216, 309, 520) — Drop `await` from per-client JS sends. Follow the existing `_broadcast_yjs_update()` pattern at line 470 which already does fire-and-forget. Keep `contextlib.suppress(Exception)` for disconnected client handling.

- `respond.py:589` (editor init) — Bundle the editor init, full-state CRDT sync (current line 608), and markdown seeding (current line 620) into a single fire-and-forget JS block. The full-state bytes and initial markdown are computed Python-side from the CRDT before the JS fires, then embedded as constants in the JS. Inside the JS, `await crepe.create()` completes first, then `_applyRemoteUpdate()` and `_setMilkdownMarkdown()` run sequentially — all within one JS evaluation, so no race with the async init. The JS block wraps the init in try/catch: on success, `emitEvent('editor_ready', {status: 'ok'})` fires after sync/seed complete; on failure, `emitEvent('editor_ready', {status: 'error', error: msg})` fires with the exception message. **Why bundle instead of separate fire-and-forget calls?** `crepe.create()` is async on the browser side. Separate fire-and-forget messages would arrive while the init `await` is still in-flight, causing `_applyRemoteUpdate()` to no-op because `__milkdownCrepe` isn't set yet. Bundling ensures sequential execution within one JS evaluation. **Why the `editor_ready` event?** Not for sync/seeding (that's bundled in the JS), but for the readiness flag. Currently `tab_bar.py:291` sets `has_milkdown_editor = True` on `PageState` and `tab_bar.py:296` sets it on `_RemotePresence` immediately after `render_respond_tab()` returns. `_broadcast_yjs_update()` at `broadcast.py:469` checks this flag before sending `_applyRemoteUpdate()` to a client. If init is fire-and-forget, the function returns before `crepe.create()` finishes — setting the flag too early. The `editor_ready` event moves flag-setting from "Python function returned" to "browser confirmed editor is live," preserving the readiness contract that gates Yjs relay.

- `tab_bar.py:177` (scroll save, Category C) — Replace the awaited JS call with a fire-and-forget save to `window._organiseSavedScroll`. The NiceGUI outbox FIFO guarantee ensures the save JS executes on the client before the subsequent DOM clear arrives. Restore remains fire-and-forget (already is at line 181). **Why a global slot is safe:** `render_fn` is `Callable[[], None]` — synchronous, no `await`. The entire save → rebuild → restore sequence runs in one asyncio task turn with no yield points. Cooperative concurrency means no other handler can interleave a second rebuild between save and restore. Two concurrent rebuild calls from different asyncio tasks cannot overlap because the save, `render_fn()`, and restore all enqueue in the same task turn, and the outbox flushes them as one batch. **Why not `app.storage.client` or `sessionStorage`?** The scroll position is needed for exactly one moment — across a synchronous container rebuild within a single handler call. A `window._` variable is the simplest correct solution; storage adds persistence semantics that aren't needed and would survive across rebuilds that don't preserve scroll intent.

- `restart.py:160`, `diagnostics.py:236` (navigate to /restarting) — Drop `await`. Navigation is best-effort during shutdown; if the browser is unreachable, the server is restarting anyway.

- `client_registry.py:61` (ban redirect) — Drop `await`. Count sends rather than confirmed redirections — a best-effort metric is fine for admin actions.

**Dependencies:** None (first phase)

**Done when:** All Category B and C `await` calls removed. Broadcast loops no longer block event loop. Editor init no longer blocks for 5s. Bundled JS block performs init + sync + seed in one evaluation. `editor_ready` event correctly gates `has_milkdown_editor` flag on both `PageState` and `_RemotePresence`. Unit tests verify fire-and-forget patterns and readiness contract.

**Covers:** eliminate-js-await-454.AC1, eliminate-js-await-454.AC2, eliminate-js-await-454.AC5
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Event-Driven Inversion (Category A)

**Goal:** Eliminate all awaited JS calls that pull data from the browser by restructuring to use server-side state or client-push events.

**Components:**

- `respond.py:368`, `pdf_export.py:218`, `restart.py:92` (getMilkdownMarkdown — 3 sites) — **The current `response_draft_markdown` mirror is populated by `_sync_markdown_to_crdt()`, which itself calls `await ui.run_javascript("window._getMilkdownMarkdown()")`.** Removing the await without replacing the producer would leave the mirror stale. The fix has two parts:

  **(a) New producer:** Extend the `respond_yjs_update` event payload to include a `markdown` field: `emitEvent('respond_yjs_update', {update: b64Update, markdown: currentMd})`. The Milkdown editor can extract its markdown synchronously (`window._getMilkdownMarkdown()`), so adding it to the existing event costs one synchronous JS call on the client per keystroke — no server round-trip. The Python `on_yjs_update` handler writes the markdown to `response_draft_markdown` directly from the event payload, replacing the `_sync_markdown_to_crdt()` JS round-trip.

  **(b) New consumers:** All three `getMilkdownMarkdown` call sites become reads from `crdt_doc.get_response_draft_markdown()`. The PDF export path (`pdf_export.py:218`) already has this as a fallback — promote it to the primary path. Tab-leave sync (`respond.py:368`) switches to the same pattern. Pre-restart flush (`restart.py:92`) sends a fire-and-forget `window._flushRespondMarkdownNow()` to each client, which emits a distinct `respond_markdown_flush` event carrying `{markdown, client_id}`. A dedicated Python handler writes to `response_draft_markdown` only — no relay to peers, no badge update, no collaborative edit side-effects. After sending flush signals, the pre-restart path does `await asyncio.sleep(1.0)` then reads from `response_draft_markdown` and persists. **This is best-effort loss minimisation, not a durability guarantee.** Under brownout, the system prefers bounded shutdown latency (1 second total, regardless of client count) over waiting for every client. Any markdown received before the drain deadline is persisted; late or non-responsive clients may lose their last unsynced edits. This is strictly better than the current O(N × 3s) sequential awaits that time out under brownout and drop ALL unsaved edits for timed-out clients.

  **Why is this safe?** The Yjs handler fires on every editor change (keystroke-level granularity via Milkdown's ProseMirror transaction model). After each event, `response_draft_markdown` is current. **Staleness window:** If the user opens the Respond tab but never types, no `respond_yjs_update` fires, and `response_draft_markdown` holds the last-persisted value from the database. This is correct: no unsaved edits exist, so the database value IS the current state. **Risk:** If the client-side `_getMilkdownMarkdown()` call in the event payload returns stale or empty markdown, the mirror would be wrong. Mitigation: the Milkdown editor's `_getMilkdownMarkdown()` reads from the ProseMirror state that just changed (same transaction), so it cannot be stale relative to the Yjs update it accompanies.

- `paste_handler.py:45–46` (paste buffer + platform hint) — Currently the paste capture JS (`paste_script.py`) stores HTML in `window.{paste_var}` and platform info in `window.{platform_var}`. The submit handler then pulls both back via awaited JS. **Restructure:** The submit JS captures **all three** client-side values at click time and passes them as event args: (1) `window.{paste_var}` (paste HTML or null), (2) `window.{platform_var}` (platform hint), and (3) the live editor DOM content as fallback. The Python handler receives all three directly — no round-trip needed. **Why all three values?** The current `on_submit_with_value` helper captures one string from one input (`ui_helpers.py:25`). The paste handler needs the paste buffer, platform hint, AND the editor content fallback for the non-paste path. If the event payload omits the editor content, the non-paste case would fall back to reading `content_input.value` server-side, which has the same stale-value socket ordering problem that `on_submit_with_value` was built to avoid. **Why not `app.storage.client`?** The data originates in JS (paste event capture) and is consumed in Python (document processing). Passing it in the event is the most direct path — no intermediate storage layer to maintain or clean up.

**Dependencies:** Phase 1 (editor init event must work before removing markdown sync await, since both touch `respond.py`)

**Done when:** All Category A `await` calls removed. Markdown sync reads from CRDT. Paste handler receives data in event args. Tests verify functional equivalence for each converted call site.

**Covers:** eliminate-js-await-454.AC3, eliminate-js-await-454.AC4
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Guard Test and Cleanup

**Goal:** Prevent regression and clean up dead code from the old patterns.

**Components:**

- Guard test in `tests/unit/` — AST-scanning or grep-based test that collects all `await` expressions where the callee matches `run_javascript` across `src/promptgrimoire/`. Allowlist excludes spike/demo pages (`milkdown_spike.py`, `text_selection.py`, `highlight_api_demo.py`). Any match outside the allowlist fails with a message pointing at this design doc. **Why AST over grep?** Grep would match comments and strings; AST matches only actual `await` expressions. Follows the pattern of existing guard tests: `test_async_fixture_safety.py` (AST scan for `@pytest.fixture` on async functions), the `print()` guard, the `setLevel()` guard.

- Dead code removal — Remove any unused timeout parameters, helper functions, or variables left over from the old awaited patterns. Remove `window.{paste_var}` / `window.{platform_var}` globals if no longer needed after paste restructure.

- Epic #142 update — Add #454 as a tracked item under the performance epic.

**Dependencies:** Phase 2 (all awaits must be eliminated before the guard test can pass)

**Done when:** Guard test passes and would catch any new `await run_javascript()`. No dead code from old patterns remains. #142 references this work.

**Covers:** eliminate-js-await-454.AC6
<!-- END_PHASE_3 -->

## Additional Considerations

**Broadcast error observability:** Current awaited broadcasts surface failures via `contextlib.suppress(Exception)` — exceptions are silently eaten. Fire-and-forget doesn't change this (the suppress is already there), but we lose the implicit "if the await raised, the client is probably disconnected" signal. The existing `_deleted` check on NiceGUI clients (`broadcast.py:306`) already handles this. No additional error handling needed.

**Editor init failure handling:** The bundled JS block wraps `crepe.create()` in try/catch. On failure, `emitEvent('editor_ready', {status: 'error', error: msg})` fires. The Python handler logs the error via structlog and does NOT set `has_milkdown_editor`, so the client is excluded from Yjs relay. This gives a structured signal distinguishable from "user disconnected" (no event at all) or "event never registered" (different log pattern). On success, sync/seed run and `{status: 'ok'}` fires.

**Pre-restart drain mechanism:** The current pre-restart flush (`restart.py:80–107`) does `await getMilkdownMarkdown()` per client — which times out under load, dropping all unsaved edits for that client. The new approach uses a **distinct flush protocol**: fire-and-forget `window._flushRespondMarkdownNow()` to all clients → clients emit `respond_markdown_flush` (NOT `respond_yjs_update`) → dedicated handler writes to `response_draft_markdown` only (no peer relay, no badges, no dirty-marking side-effects) → `await asyncio.sleep(1.0)` → read from mirror → persist. **Why a separate event?** `respond_yjs_update` carries collaborative edit semantics: apply Yjs binary diff, relay to peers, update word count badge, mark workspace dirty. A shutdown flush is not a collaborative edit — it's a last-chance state capture. Overloading the edit event would trigger unnecessary relay and badge updates during shutdown. **Brownout trade-off (explicit):** Pre-restart flush is best-effort loss minimisation, not a hard durability guarantee. The system prefers bounded shutdown latency (1 second total, regardless of client count) over waiting for every client. Under normal conditions, events arrive within milliseconds and the mirror is current. Under brownout, the current system already drops edits (3s timeouts fire for every client); the new system loses at most the edits from the final 1 second for non-responsive clients, while the fixed event loop makes successful drain more likely.

**Ordering guarantee dependency:** The scroll save (Category C) relies on NiceGUI's outbox FIFO ordering — fire-and-forget JS executes before subsequent DOM updates sent in the same handler. This is verified by reading NiceGUI source and is structurally guaranteed by the single `deque` per client. **Synchronous rebuild invariant:** `render_fn` is `Callable[[], None]` (synchronous). The save → `render_fn()` → restore sequence runs in one asyncio task turn with no yield points. Cooperative concurrency prevents interleaving from other handlers. This invariant must be preserved — if `render_fn` ever becomes async, the scroll save would need a per-rebuild isolation mechanism (e.g., a unique token pairing save/restore).

**No new dependencies introduced.** All strategies use existing NiceGUI APIs (`emitEvent`, `ui.on`, fire-and-forget `run_javascript`) and existing codebase patterns.
