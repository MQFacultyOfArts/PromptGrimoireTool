# Eliminate Awaited JavaScript Calls — Test Requirements

**Design:** `docs/design-plans/2026-03-29-eliminate-js-await-454.md`
**Implementation:** `docs/implementation-plans/2026-03-29-eliminate-js-await-454/`

---

## Automated Tests

### eliminate-js-await-454.AC1: Broadcast calls are non-blocking

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC1.1 | Unit | `tests/unit/test_broadcast_fire_and_forget.py` | `_broadcast_cursor_update` is synchronous (`not inspect.iscoroutinefunction()`); mock `run_javascript` is called, not awaited |
| AC1.2 | Unit | `tests/unit/test_broadcast_fire_and_forget.py` | `_broadcast_selection_update` is synchronous; mock `run_javascript` is called, not awaited |
| AC1.3 | Unit | `tests/unit/test_broadcast_fire_and_forget.py` | `_handle_client_delete` calls `run_javascript` for cursor/selection removal JS without awaiting it (mock `.assert_called_once_with`, not `.assert_awaited_once_with`) |
| AC1.4 | Unit | `tests/unit/test_broadcast_fire_and_forget.py` | With N mock clients where one raises `Exception` on `run_javascript`, remaining clients still receive their JS calls |
| AC1.5 | Unit | `tests/unit/test_broadcast_fire_and_forget.py` | A mock client whose `run_javascript` never completes (or raises `TimeoutError`) does not raise in the broadcast function; no exception propagates |

**Rationale:** Phase 1 Task 1 converts 5 broadcast sites from `await` to fire-and-forget. Unit tests with mock NiceGUI clients verify the structural change (sync vs async signature, called vs awaited) and the fault isolation property (one bad client does not block others). Existing tests in `test_broadcast_iteration_safety.py` and `test_broadcast_deleted_client.py` cover iteration and deletion edge cases; Phase 1 Task 7 updates them for the new sync signatures.

### eliminate-js-await-454.AC2: Editor initialisation is non-blocking

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC2.1 | Unit | `tests/unit/test_editor_init_fire_and_forget.py` | `render_respond_tab` does not contain any `await ...run_javascript()` calls; the JS block is sent as fire-and-forget (mock `run_javascript` called, not awaited) |
| AC2.2 | Unit | `tests/unit/test_editor_init_fire_and_forget.py` | The JS string passed to `run_javascript` contains `_applyRemoteUpdate` and `_setMilkdownMarkdown` calls after `crepe.create()` within the same evaluation block (string inspection) |
| AC2.3 | Unit | `tests/unit/test_editor_ready_event.py` | After `render_respond_tab` returns, `state.has_milkdown_editor` is `False`; calling `_on_editor_ready` with `{status: 'ok'}` sets it to `True` on both `PageState` and `_RemotePresence` |
| AC2.4 | Unit | `tests/unit/test_editor_ready_event.py` | `_broadcast_yjs_update` skips clients where `has_milkdown_editor` is `False` (existing behaviour preserved with event-driven flag; mock client with flag=False receives no `_applyRemoteUpdate` call) |
| AC2.5 | Unit | `tests/unit/test_editor_ready_event.py` | `_on_editor_ready` with `{status: 'error', error: 'init failed'}` logs via structlog (captured log assertion) and does NOT set `has_milkdown_editor` on `PageState` or `_RemotePresence` |

**Rationale:** Phase 1 Tasks 3-4 bundle editor init into one fire-and-forget JS block and gate readiness on the `editor_ready` event. AC2.1-2.2 verify the structural bundling. AC2.3-2.5 verify the readiness contract that prevents Yjs relay to uninitialised editors. AC2.4 tests existing behaviour with the new flag-setting mechanism; no new code path, just confirming the gate still works.

### eliminate-js-await-454.AC3: Markdown sync uses client-pushed state

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC3.1 | Unit | `tests/unit/test_markdown_sync_event.py` | `on_yjs_update` handler reads `markdown` from event args and writes to `response_draft_markdown` via atomic CRDT replace; no `run_javascript` call in the handler |
| AC3.2 | Unit | `tests/unit/test_markdown_sync_event.py` | `on_yjs_update` does NOT call `_sync_markdown_to_crdt` or any `run_javascript` variant (mock assertion: `run_javascript` not called) |
| AC3.3 | Unit | `tests/unit/test_pdf_export_markdown.py` | `_extract_response_markdown` is synchronous (`def`, not `async def`); reads from `crdt_doc.get_response_draft_markdown()` directly; returns `""` when `state.crdt_doc is None` |
| AC3.4 | Unit | `tests/unit/test_pre_restart_flush.py` | `_flush_milkdown_to_crdt` sends fire-and-forget `_flushRespondMarkdownNow` to all clients with `has_milkdown_editor`, then `await asyncio.sleep(1.0)`, then reads from `response_draft_markdown` |
| AC3.5 | Unit | `tests/unit/test_pre_restart_flush.py` | `_on_markdown_flush` handler writes to `response_draft_markdown` and calls `mark_dirty_workspace()` (persistence bookkeeping); assert no calls to broadcast relay or badge update functions |
| AC3.6 | Unit | `tests/unit/test_pre_restart_flush.py` | Flush function contains exactly one `asyncio.sleep` call (not N per-client awaits); mock assertion that `asyncio.sleep` is called once with `1.0` regardless of client count; no per-client `await run_javascript` calls (structural check, not wall-clock timing — timing assertions are fragile under xdist) |
| AC3.7 | Unit | `tests/unit/test_pre_restart_flush.py` | When no Yjs events have fired, `response_draft_markdown` holds the initial DB value (empty string or pre-existing content); flush reads this value without error |

**Rationale:** Phase 2 Tasks 1-3 and 5 restructure markdown sync from pull (JS round-trip) to push (event payload). AC3.1-3.2 verify the new producer. AC3.3 verifies the PDF export consumer is now a simple sync CRDT read. AC3.4-3.7 verify the pre-restart flush protocol including its bounded-time property, side-effect isolation, and zero-edit edge case.

### eliminate-js-await-454.AC4: Paste and scroll use non-blocking patterns

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC4.1 | Unit | `tests/unit/test_paste_handler_event_payload.py` | `handle_add_document_submission` receives `paste_html`, `platform_hint`, and `editor_content` as direct parameters; no `run_javascript` calls in the function body |
| AC4.2 | Unit | `tests/unit/test_paste_handler_event_payload.py` | When `paste_html` is `None`, the handler uses `editor_content` (from event payload) as the document content, not `content_input.value` |
| AC4.3 | Unit | `tests/unit/test_scroll_save_fire_and_forget.py` | `_rebuild_organise_with_scroll` is synchronous (`not inspect.iscoroutinefunction()`); calls `run_javascript` without await; `render_fn` is called between the save and restore JS calls (mock call order assertion) |

**Rationale:** AC4.1-4.2 are Phase 2 Task 4 (paste handler restructure). AC4.3 is Phase 1 Task 5 (scroll save) — grouped under AC4 in the design because it addresses the same non-blocking principle for client-side state. The scroll test verifies structural correctness (sync signature, FIFO ordering of save-rebuild-restore); actual scroll preservation is a visual property verified during UAT.

### eliminate-js-await-454.AC5: Admin/restart paths are non-blocking

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC5.1 | Unit | `tests/unit/test_admin_navigation_fire_and_forget.py` | Pre-restart navigation in `restart.py` calls `run_javascript` without await (mock called, not awaited) |
| AC5.2 | Unit | `tests/unit/test_admin_navigation_fire_and_forget.py` | Memory-threshold navigation in `diagnostics.py` calls `run_javascript` without await |
| AC5.3 | Unit | `tests/unit/test_admin_navigation_fire_and_forget.py` | Ban redirect in `client_registry.py` calls `run_javascript` without await; counter increments on send, not on confirmed execution |

**Rationale:** Phase 1 Task 6. These are straightforward await-to-fire-and-forget conversions. Unit tests verify the structural change (called vs awaited) and, for AC5.3, the semantic shift in the counter (sends vs confirmations).

### eliminate-js-await-454.AC6: Guard test prevents regression

| AC | Test Type | Test File | What the test proves |
|----|-----------|-----------|---------------------|
| AC6.1 | Unit | `tests/unit/test_run_javascript_guard.py` | AST scan of `src/promptgrimoire/` finds zero `await ...run_javascript()` calls outside the allowlist |
| AC6.2 | Unit | `tests/unit/test_run_javascript_guard.py` | Allowlist contains exactly `{"milkdown_spike", "text_selection", "highlight_api_demo"}` (hardcoded assertion on the set) |
| AC6.3 | Unit | `tests/unit/test_run_javascript_guard.py` | Temporarily injecting `await ui.run_javascript("test")` into a production file causes the guard to report the violation (tested via a synthetic AST snippet, not by modifying real files) |

**Rationale:** Phase 3 Task 1. The guard test IS the acceptance criterion — it structurally prevents regression. AC6.3 is tested by feeding a synthetic AST with a violation to the scanning function, confirming it would be caught. This follows the pattern of `test_value_capture_guard.py` and `test_async_fixture_safety.py`.

---

## Human Verification (UAT)

### eliminate-js-await-454.AC1.4 + AC1.5: Slow/disconnected client fault isolation under real network conditions

**Justification:** Unit tests verify fault isolation with mock clients, but the real failure mode is a browser on a degraded network connection. Mock `run_javascript` raising exceptions is a structural proxy; the actual experience of "tab A remains responsive while tab B is on Slow 3G" requires a real browser with DevTools network throttling.

**Verification approach (Phase 1 UAT step 8):**
1. Open two browser tabs on the same annotation workspace
2. In tab B, open DevTools and throttle network to Slow 3G
3. In tab A, move cursor in the source text
4. Verify tab A remains responsive (no 2-second freeze)
5. Verify tab B eventually receives cursor updates (or gracefully misses them)

### eliminate-js-await-454.AC2.2: Bundled JS block executes init, sync, and seed in correct order on browser

**Justification:** Unit tests verify the JS string contains the right function calls in the right textual order. They cannot verify that the browser actually executes `crepe.create()` before `_applyRemoteUpdate()` and `_setMilkdownMarkdown()`, or that the editor becomes functional after the bundled init. The sequential execution guarantee depends on JavaScript runtime semantics of `await` inside an async IIFE.

**Verification approach (Phase 1 UAT steps 3-5):**
1. Open the Respond tab — editor should appear and be editable
2. Type text — it should render correctly in the WYSIWYG editor
3. Open a second tab — text should sync from tab A to tab B (proving CRDT sync was applied after init)

### eliminate-js-await-454.AC3.4 + AC3.6: Pre-restart flush captures edits under real brownout

**Justification:** Unit tests verify the flush protocol structure (fire-and-forget signal, 1-second drain, CRDT read). They cannot verify that a real browser receives the flush signal, executes `_flushRespondMarkdownNow`, emits `respond_markdown_flush`, and that the event arrives within the 1-second drain window. The "best-effort loss minimisation" property (AC3.6) is inherently probabilistic under real network conditions.

**Verification approach (Phase 2 UAT step 7):**
1. Open the Respond tab and type distinctive text
2. Trigger a restart via the admin panel (`/api/pre-restart`)
3. After restart, reload the page
4. Verify the text typed before restart is present
5. Accept that under extreme brownout, the final sub-second of edits may be lost (this is the explicit design trade-off)

### eliminate-js-await-454.AC4.1: Paste HTML processing with real clipboard data

**Justification:** Unit tests verify the function signature and parameter routing. They cannot verify that the browser's paste event listener correctly captures HTML from a real clipboard paste, that platform detection works across OS variants, or that the JS click handler correctly reads all three values at click time. The paste pipeline involves browser-specific clipboard APIs and DOM event ordering.

**Verification approach (Phase 2 UAT steps 5-6):**
1. Copy an AI conversation from Claude or ChatGPT (rich HTML with turn structure)
2. Paste into the source content area
3. Click "Add Document" — the pasted HTML should be processed correctly with platform detection
4. Also test: type directly into the editor (no paste) and click "Add Document" — content should be captured from the event payload, not stale server-side state

### eliminate-js-await-454.AC4.3: Scroll position preserved across container rebuilds

**Justification:** Unit tests verify the fire-and-forget JS call ordering (save before rebuild, restore after). They cannot verify that the browser actually preserves and restores a visible scroll position, because that depends on DOM rendering, `requestAnimationFrame` timing, and the NiceGUI outbox FIFO guarantee holding under real WebSocket conditions.

**Verification approach (Phase 1 UAT step 9):**
1. On the Organise tab, scroll the card columns horizontally to a non-zero position
2. Add a new annotation from the source tab (triggers a container rebuild)
3. Verify the Organise tab scroll position is preserved after rebuild

### eliminate-js-await-454.AC5.3: Ban redirect reaches active browser session

**Justification:** Unit tests verify the `run_javascript` call is fire-and-forget and counts sends. They cannot verify that a real active browser session actually navigates to `/banned` when the ban CLI command runs, because this depends on the WebSocket being alive, the NiceGUI client registry correctly tracking the session, and the browser executing the navigation JS.

**Verification approach (Phase 1 UAT step 10):**
1. Log in as a test user and keep the session active
2. Run `uv run grimoire admin ban <test-email>` from CLI
3. Verify the browser redirects to `/banned`
4. Run `uv run grimoire admin unban <test-email>` to clean up

---

## Test File Summary

| Test File | Type | Phase | ACs Covered |
|-----------|------|-------|-------------|
| `tests/unit/test_broadcast_fire_and_forget.py` | Unit | 1 | AC1.1, AC1.2, AC1.3, AC1.4, AC1.5 |
| `tests/unit/test_editor_init_fire_and_forget.py` | Unit | 1 | AC2.1, AC2.2 |
| `tests/unit/test_editor_ready_event.py` | Unit | 1 | AC2.3, AC2.4, AC2.5 |
| `tests/unit/test_scroll_save_fire_and_forget.py` | Unit | 1 | AC4.3 |
| `tests/unit/test_admin_navigation_fire_and_forget.py` | Unit | 1 | AC5.1, AC5.2, AC5.3 |
| `tests/unit/test_markdown_sync_event.py` | Unit | 2 | AC3.1, AC3.2 |
| `tests/unit/test_pdf_export_markdown.py` | Unit | 2 | AC3.3 |
| `tests/unit/test_pre_restart_flush.py` | Unit | 2 | AC3.4, AC3.5, AC3.6, AC3.7 |
| `tests/unit/test_paste_handler_event_payload.py` | Unit | 2 | AC4.1, AC4.2 |
| `tests/unit/test_run_javascript_guard.py` | Unit | 3 | AC6.1, AC6.2, AC6.3 |

All 10 test files are new. Phase 1 Task 7 and Phase 2 Task 7 update existing tests for signature changes but do not cover new ACs.

---

## Coverage Matrix

| AC | Automated | Human | Notes |
|----|-----------|-------|-------|
| AC1.1 | Yes | — | Structural (sync signature + mock call) |
| AC1.2 | Yes | — | Structural (sync signature + mock call) |
| AC1.3 | Yes | — | Structural (mock called, not awaited) |
| AC1.4 | Yes | Yes | Unit proves fault isolation with mocks; UAT proves it under real network throttling |
| AC1.5 | Yes | — | Structural (no exception propagates from mock) |
| AC2.1 | Yes | — | Structural (no await in function body) |
| AC2.2 | Yes | Yes | Unit proves JS string contents; UAT proves browser executes in correct order |
| AC2.3 | Yes | — | State transition verified by mock event |
| AC2.4 | Yes | — | Existing gate behaviour preserved; mock client with flag=False receives nothing |
| AC2.5 | Yes | — | Structlog capture + flag assertion |
| AC3.1 | Yes | — | Event payload read + CRDT write, no JS call |
| AC3.2 | Yes | — | Negative assertion: no `run_javascript` called |
| AC3.3 | Yes | — | Sync function, direct CRDT read, None edge case |
| AC3.4 | Yes | Yes | Unit proves protocol structure; UAT proves real flush captures edits |
| AC3.5 | Yes | — | Writes CRDT + dirty-marks; no relay, no badge |
| AC3.6 | Yes | Yes | Unit proves bounded time; UAT proves real-world drain behaviour |
| AC3.7 | Yes | — | Zero-edit edge case: initial DB value preserved |
| AC4.1 | Yes | Yes | Unit proves parameter routing; UAT proves real clipboard paste works |
| AC4.2 | Yes | — | Structural: editor_content used when paste_html is None |
| AC4.3 | Yes | Yes | Unit proves JS call ordering; UAT proves visible scroll preservation |
| AC5.1 | Yes | — | Structural (called, not awaited) |
| AC5.2 | Yes | — | Structural (called, not awaited) |
| AC5.3 | Yes | Yes | Unit proves fire-and-forget + counter; UAT proves real browser redirect |
| AC6.1 | Yes | — | The guard test IS the criterion |
| AC6.2 | Yes | — | Hardcoded set assertion |
| AC6.3 | Yes | — | Synthetic AST violation detected by scanner |
