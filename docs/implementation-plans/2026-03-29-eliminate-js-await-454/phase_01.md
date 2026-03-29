# Eliminate Awaited JavaScript Calls — Phase 1: Fire-and-Forget Conversions

**Goal:** Eliminate all awaited JS calls that don't use the return value (Category B + C), covering broadcast loops, editor init, scroll save, navigation, and ban redirect.

**Architecture:** Drop `await` from fire-and-forget sends following the existing `_broadcast_yjs_update()` pattern. Bundle editor init + CRDT sync + markdown seed into a single JS evaluation with an `editor_ready` event for readiness gating. Replace scroll save await with fire-and-forget relying on NiceGUI outbox FIFO ordering.

**Tech Stack:** NiceGUI (run_javascript, emitEvent, ui.on), Python asyncio, structlog

**Scope:** 3 phases from original design (phase 1 of 3)

**Codebase verified:** 2026-03-29

---

## Acceptance Criteria Coverage

This phase implements and tests:

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

### eliminate-js-await-454.AC5: Admin/restart paths are non-blocking
- **eliminate-js-await-454.AC5.1 Success:** Pre-restart client navigation is fire-and-forget
- **eliminate-js-await-454.AC5.2 Success:** Memory-threshold restart navigation is fire-and-forget
- **eliminate-js-await-454.AC5.3 Success:** Ban redirect is fire-and-forget

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Convert broadcast loops to fire-and-forget

**Verifies:** eliminate-js-await-454.AC1.1, eliminate-js-await-454.AC1.2, eliminate-js-await-454.AC1.3, eliminate-js-await-454.AC1.4, eliminate-js-await-454.AC1.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (lines 96-108, 140-176, 179-219, 286-316, 498-534)
- Test: `tests/unit/test_broadcast_fire_and_forget.py` (unit)

**Implementation:**

Convert all 5 broadcast `await ...run_javascript()` sites to fire-and-forget. The pattern for each is identical: remove `await`, keep the `contextlib.suppress(Exception)` wrapper.

**Site 1 — `_broadcast_js_to_others()` (line 108):**
Change `async def _broadcast_js_to_others(...)` to `def _broadcast_js_to_others(...)`. Remove `await` from line 108. The function no longer needs to be async since it has no remaining await points.

**Site 2 — `_broadcast_cursor_update()` (line 173):**
Remove `await` from the `presence.nicegui_client.run_javascript(js, timeout=2.0)` call. The `timeout=2.0` parameter is irrelevant for fire-and-forget calls but harmless to keep (NiceGUI ignores it for non-awaited calls). Since `_broadcast_cursor_update` also calls `_broadcast_js_to_others` (which is now sync), and has no other await points, change its signature to `def _broadcast_cursor_update(...)` (sync).

**Site 3 — `_broadcast_selection_update()` (line 216):**
Remove `await` from the per-client `run_javascript` call. `_broadcast_selection_update` also calls `_broadcast_js_to_others` (now sync via line 193). With both awaits removed, change to `def _broadcast_selection_update(...)`.

**Site 4 — `_handle_client_delete()` (line 309):**
Remove `await` from `presence.nicegui_client.run_javascript(removal_js, timeout=2.0)`. Keep the `_deleted` guard at line 306. Note: `_handle_client_delete` has other awaits (`presence.invoke_peer_left()` at line 315, `pm.force_persist_workspace()` at line 318, `pm.evict_workspace()` at line 322) — remains `async def`.

**Site 5 — `revoke_and_redirect()` (line 520):**
Remove `await` from `presence.nicegui_client.run_javascript(...)`. Move `notified += 1` outside the `contextlib.suppress(Exception)` block — the counter should track sends, not confirmed executions (fire-and-forget has no confirmation).

**Callers of newly-sync functions:** After making `_broadcast_js_to_others`, `_broadcast_cursor_update`, and `_broadcast_selection_update` synchronous, remove `await` from all their call sites. Search for callers in `broadcast.py` itself (e.g., line 193 calls `_broadcast_js_to_others`) and in `respond.py`, `document.py`, or wherever these functions are called. All callers that only call these functions can potentially become sync too — but only change signatures where ALL awaits in the function are removed.

**Testing:**
Tests must verify each AC listed above:
- eliminate-js-await-454.AC1.1: Test that `_broadcast_cursor_update` is synchronous (`not inspect.iscoroutinefunction(...)`) and calls `run_javascript` without await
- eliminate-js-await-454.AC1.2: Test that `_broadcast_selection_update` is synchronous
- eliminate-js-await-454.AC1.3: Test that `_handle_client_delete` calls `run_javascript` for removal without await (check mock was called, not awaited)
- eliminate-js-await-454.AC1.4: Test with mock client whose `run_javascript` raises — other clients still receive their calls
- eliminate-js-await-454.AC1.5: Test that a non-responding mock client doesn't produce a timeout exception in the broadcast function

Follow existing patterns from `tests/unit/test_broadcast_iteration_safety.py` and `tests/unit/test_broadcast_deleted_client.py` for mock setup.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_broadcast_fire_and_forget.py`
Expected: All tests pass

**Commit:** `feat: convert broadcast loops to fire-and-forget (#454)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify broadcast caller chain propagation

**Verifies:** eliminate-js-await-454.AC1.1, eliminate-js-await-454.AC1.2

**Files:**
- Modify: all callers of `_broadcast_js_to_others`, `_broadcast_cursor_update`, `_broadcast_selection_update` that need `await` removed
- Test: existing broadcast tests must still pass

**Implementation:**

After Task 1 converts the three functions to sync, their callers must also be updated. The call chain has an intermediate wrapper layer:

**Direct callers (wrapper closures in `broadcast.py:384-403`):**
- `broadcast_cursor` (closure at `broadcast.py:384`) — `await _broadcast_cursor_update(...)`. Remove `await`, convert closure from `async def` to `def`.
- `broadcast_selection` (closure at `broadcast.py:394`) — `await _broadcast_selection_update(...)`. Remove `await`, convert closure from `async def` to `def`.
- These closures are assigned to `state.broadcast_cursor` (line 392) and `state.broadcast_selection` (line 403).

**Callers of the wrappers (in `document.py`):**
- `document.py:39` — `await state.broadcast_selection(...)`. Remove `await`.
- `document.py:49` — `await state.broadcast_selection(None, None)`. Remove `await`.
- `document.py:56` — `await state.broadcast_cursor(char_index)`. Remove `await`.

**Internal caller:**
- `_broadcast_js_to_others` is called at `broadcast.py:193` (inside `_broadcast_selection_update`, already handled in Task 1)

If the calling functions in `document.py` (`_handle_selection`, `_handle_selection_cleared`, `_handle_cursor_move`) have no remaining await points after removing these awaits, convert them to sync too. Propagate up until you reach a function with legitimate async operations.

**Testing:**
Run all existing broadcast and document tests to verify no regressions. The async-to-sync signature change must not break any mock expectations.

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass, no regressions

**Commit:** `refactor: propagate sync signatures through broadcast caller chain (#454)`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Bundle editor init into single fire-and-forget JS block

**Verifies:** eliminate-js-await-454.AC2.1, eliminate-js-await-454.AC2.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (lines 582-624)
- Test: `tests/unit/test_editor_init_fire_and_forget.py` (unit)

**Implementation:**

In `render_respond_tab()`, replace the awaited editor init (lines 589-605) and the two subsequent fire-and-forget calls (lines 607-624) with a single fire-and-forget JS block.

The new pattern:
1. Compute `full_state` bytes and `initial_md` markdown Python-side from the CRDT *before* sending JS
2. Encode full_state as base64, escape initial_md for JS embedding
3. Send one fire-and-forget `ui.run_javascript()` (no await) that:
   a. Checks for `root` element and `window._createMilkdownEditor`
   b. Inside a try block: `await window._createMilkdownEditor(root, '', onYjsUpdate, fragmentName)` — this calls the static bundle's `createEditor()` at `static/milkdown/src/index.js:40` which internally does `await crepe.create()`. The page JS must NOT reference `crepe` directly — it is an internal symbol owned by the bundle.
   c. After `_createMilkdownEditor` resolves: if full_state exists, call `window._applyRemoteUpdate(b64State)`
   d. If initial_md exists and XmlFragment is empty: call `window._setMilkdownMarkdown(md)`
   e. On success: `emitEvent('editor_ready', {status: 'ok'})`
   f. On failure (catch): `emitEvent('editor_ready', {status: 'error', error: e.message})`

This mirrors the existing pattern at `respond.py:589-605` — the current code already calls `window._createMilkdownEditor(root, '', function(b64Update) { emitEvent(...) }, fragmentName)` and awaits its result. The change is to move the full-state sync and markdown seed into the same JS block (after the await resolves) and make the entire block fire-and-forget from Python's perspective.

The function `render_respond_tab()` returns immediately after sending the JS — it no longer awaits the browser.

**Important:** The `await ui.context.client.connected()` at line 583 must REMAIN — this waits for the WebSocket connection, which is a NiceGUI internal operation, not a browser JS call.

**Important:** Remove the separate fire-and-forget calls at lines 607-624 (full-state sync and markdown seed). They are now bundled into the single JS block.

**Testing:**
- eliminate-js-await-454.AC2.1: Verify `render_respond_tab` does not contain any `await ...run_javascript()` calls (can use a source scan or mock check)
- eliminate-js-await-454.AC2.2: Verify the JS block includes full-state sync and markdown seed after `crepe.create()` resolves

**Verification:**
Run: `uv run grimoire test run tests/unit/test_editor_init_fire_and_forget.py`
Expected: All tests pass

**Commit:** `feat: bundle editor init into single fire-and-forget JS block (#454)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add `editor_ready` event handler for readiness gating

**Verifies:** eliminate-js-await-454.AC2.3, eliminate-js-await-454.AC2.4, eliminate-js-await-454.AC2.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (add `ui.on('editor_ready', ...)` handler)
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (lines 291-296 — remove immediate flag setting)
- Test: `tests/unit/test_editor_ready_event.py` (unit)

**Implementation:**

**Step 1: Register the `editor_ready` event handler in `respond.py`.**

In `render_respond_tab()`, after the fire-and-forget JS block, register:
```python
ui.on('editor_ready', _on_editor_ready)
```

The handler `_on_editor_ready` receives `events.GenericEventArguments` with `e.args`:
- If `e.args['status'] == 'ok'`: set `state.has_milkdown_editor = True` and update `_RemotePresence` entry
- If `e.args['status'] == 'error'`: log structured error via `logger.error("editor_init_failed", error=e.args['error'], ...)`. Do NOT set `has_milkdown_editor`.

**Closure variables:** The handler must capture `state` (PageState), `workspace_key` (str), and `client_id` (str) from `render_respond_tab`'s local scope. Follow the existing closure pattern from `on_yjs_update` at `respond.py:421` which captures `crdt_doc`, `workspace_key`, `workspace_id`, `client_id`, and `state`. The `_RemotePresence` update requires looking up `_workspace_presence[workspace_key][client_id]` — both keys must be captured in the closure, not derived at event time. If the closure fails to capture `client_id`, the `_RemotePresence` entry will not be updated and Yjs relay will silently skip the client despite `PageState.has_milkdown_editor` being True.

**Step 2: Remove immediate flag setting from `tab_bar.py`.**

**Cross-phase dependency note:** Do NOT remove `_sync_respond_on_leave` or `state.sync_respond_markdown` in this task. They remain live until Phase 2 Task 5, which eliminates the tab-leave markdown sync. Between Phase 1 completion and Phase 2 Task 5, `_sync_respond_on_leave` still calls `state.sync_respond_markdown()` which calls `_sync_markdown_to_crdt()` (the `await run_javascript` call). This is expected — Phase 2 removes that await. Only the `has_milkdown_editor` flag-setting is moved here.

Remove lines 291-296 in `_initialise_respond_tab`:
```python
state.has_milkdown_editor = True
ws_key = str(workspace_id)
clients = _workspace_presence.get(ws_key, {})
if state.client_id in clients:
    clients[state.client_id].has_milkdown_editor = True
```

The flag is now set exclusively by the `editor_ready` event handler.

**Step 3: Update `render_respond_tab` return type if needed.**

Since the function no longer awaits the editor init, it returns before the editor is actually ready. The caller at `tab_bar.py:280` (`await render_respond_tab(...)`) may need adjustment — if `render_respond_tab` has no remaining await points, it can become sync. However, it likely still has `await ui.context.client.connected()`, so it stays async.

**Testing:**
- eliminate-js-await-454.AC2.3: Test that `has_milkdown_editor` is False after `render_respond_tab` returns, and True only after `_on_editor_ready` is called with `{status: 'ok'}`
- eliminate-js-await-454.AC2.4: Test that `_broadcast_yjs_update` (existing code at `broadcast.py:469`) skips clients where `has_milkdown_editor` is False — this is existing behavior, verify it still works with the new event-driven flag
- eliminate-js-await-454.AC2.5: Test that `_on_editor_ready` with `{status: 'error', error: 'test'}` logs via structlog and does NOT set `has_milkdown_editor`

**Verification:**
Run: `uv run grimoire test run tests/unit/test_editor_ready_event.py`
Expected: All tests pass

**Commit:** `feat: add editor_ready event for readiness gating (#454)`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Convert scroll save to fire-and-forget

**Verifies:** eliminate-js-await-454.AC1.1 (indirectly — scroll is Category C, not broadcast, but same non-blocking principle)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (lines 169-187)
- Test: `tests/unit/test_scroll_save_fire_and_forget.py` (unit)

**Implementation:**

Replace the `await` at `tab_bar.py:177` with a fire-and-forget pattern:

1. Change `_rebuild_organise_with_scroll` from `async def` to `def` (synchronous)
2. Replace `scroll = await ui.run_javascript(_SCROLL_SAVE_JS)` with a fire-and-forget save to `window._organiseSavedScroll`:
   ```python
   ui.run_javascript(
       "(function() {"
       "  var el = document.querySelector('[data-testid=\"organise-columns\"]');"
       "  window._organiseSavedScroll = el ? {x: el.scrollLeft, y: el.scrollTop} : null;"
       "})()"
   )
   ```
3. Call `render_fn()` synchronously (unchanged — already sync)
4. Replace the restore to read from the saved global:
   ```python
   ui.run_javascript(
       "requestAnimationFrame(function() {"
       "  var s = window._organiseSavedScroll;"
       "  var el = document.querySelector('[data-testid=\"organise-columns\"]');"
       "  if (s && el) { el.scrollLeft = s.x; el.scrollTop = s.y; }"
       "  delete window._organiseSavedScroll;"
       "});"
   )
   ```

The NiceGUI outbox FIFO guarantees the save JS executes before the DOM clear from `render_fn()`. All three operations (save, rebuild, restore) queue in the same task turn with no yield points.

Update all callers of `_rebuild_organise_with_scroll` to remove `await` since the function is now sync.

**Testing:**
- Verify `_rebuild_organise_with_scroll` is synchronous (`not inspect.iscoroutinefunction(...)`)
- Verify it calls `ui.run_javascript` without await (mock check)
- Verify `render_fn` is called between the save and restore JS calls

**Verification:**
Run: `uv run grimoire test run tests/unit/test_scroll_save_fire_and_forget.py`
Expected: All tests pass

**Commit:** `feat: convert scroll save to fire-and-forget with FIFO ordering (#454)`
<!-- END_TASK_5 -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->

<!-- START_TASK_6 -->
### Task 6: Convert admin/restart navigation to fire-and-forget

**Verifies:** eliminate-js-await-454.AC5.1, eliminate-js-await-454.AC5.2, eliminate-js-await-454.AC5.3

**Files:**
- Modify: `src/promptgrimoire/pages/restart.py` (line 160)
- Modify: `src/promptgrimoire/diagnostics.py` (line 236)
- Modify: `src/promptgrimoire/auth/client_registry.py` (line 61)
- Test: `tests/unit/test_admin_navigation_fire_and_forget.py` (unit)

**Implementation:**

**restart.py:160 — Pre-restart navigation:**
Remove `await` from `client.run_javascript(...)`. The surrounding `try/except` becomes redundant for the JS call itself since fire-and-forget doesn't raise on client failure. Keep the try/except but change the exception handler to be more targeted, or simplify to `contextlib.suppress(Exception)` matching the broadcast pattern.

**diagnostics.py:236 — Memory-threshold restart navigation:**
Same pattern as restart.py. Remove `await`, simplify error handling.

**client_registry.py:61 — Ban redirect:**
Remove `await` from `client.run_javascript(...)`. Change `redirected` counter to count sends (increment unconditionally after the `run_javascript` call) rather than confirmed redirections. Update the function docstring to reflect best-effort semantics. The try/except still catches exceptions from `client.run_javascript` if the client object is in a bad state — keep it for robustness but note the semantics change.

**Testing:**
- eliminate-js-await-454.AC5.1: Verify restart navigation uses fire-and-forget (mock `run_javascript` not awaited)
- eliminate-js-await-454.AC5.2: Verify memory-threshold navigation uses fire-and-forget
- eliminate-js-await-454.AC5.3: Verify ban redirect uses fire-and-forget and counts sends not confirmations

**Verification:**
Run: `uv run grimoire test run tests/unit/test_admin_navigation_fire_and_forget.py`
Expected: All tests pass

**Commit:** `feat: convert admin/restart navigation to fire-and-forget (#454)`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update existing tests for async-to-sync signature changes

**Verifies:** None (infrastructure — ensures existing tests pass with new signatures)

**Files:**
- Modify: `tests/unit/test_broadcast_iteration_safety.py`
- Modify: `tests/unit/test_broadcast_deleted_client.py`
- Modify: `tests/unit/test_client_registry.py`
- Modify: any other tests that `await` the functions converted to sync

**Implementation:**

After Tasks 1-6, several functions changed from `async def` to `def`. Existing tests that `await` these functions will fail with `TypeError: object NoneType can't be used in 'await' expression` or similar.

Search for all test files that call the converted functions and remove `await` from those calls. Key changes:
- Tests calling `_broadcast_js_to_others`, `_broadcast_cursor_update`, `_broadcast_selection_update` — remove `await`
- Tests calling `_rebuild_organise_with_scroll` — remove `await`
- Tests asserting `run_javascript` was `assert_awaited_once_with` — change to `assert_called_once_with` (since the call is no longer awaited)

**Testing:**
Run full test suite to catch any remaining async/sync mismatches.

**Verification:**
Run: `uv run grimoire test all`
Expected: All existing tests pass, no regressions

**Commit:** `test: update existing tests for async-to-sync signature changes (#454)`
<!-- END_TASK_7 -->

<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Open two browser tabs on the same annotation workspace
3. [ ] In tab A, switch to the Respond tab — the editor should appear and be editable
4. [ ] In tab B, switch to the Respond tab — the editor should appear
5. [ ] Type in tab A — text should sync to tab B within seconds
6. [ ] Verify: no lag spikes in either tab when typing
7. [ ] In tab A, move cursor in the source text — tab B should show the remote cursor indicator
8. [ ] Throttle tab B's network to Slow 3G in DevTools, move cursor in tab A — tab A should remain responsive (no 2-second freeze)
9. [ ] On the Organise tab, scroll the card columns horizontally, then add a new annotation from the source tab — after rebuild, scroll position should be preserved
10. [ ] Use `uv run grimoire admin ban <test-email>` on a user with an active session — the browser should redirect to `/banned`

## Evidence Required
- [ ] Test output showing green for `uv run grimoire test all`
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uvx ty@0.0.24 check` passes
- [ ] Complexipy results: `uv run complexipy src/promptgrimoire/pages/annotation/broadcast.py src/promptgrimoire/pages/annotation/respond.py src/promptgrimoire/pages/annotation/tab_bar.py src/promptgrimoire/pages/restart.py src/promptgrimoire/diagnostics.py src/promptgrimoire/auth/client_registry.py`
