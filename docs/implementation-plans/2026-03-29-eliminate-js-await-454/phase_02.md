# Eliminate Awaited JavaScript Calls — Phase 2: Event-Driven Inversion

**Goal:** Eliminate all awaited JS calls that pull data from the browser (Category A) by restructuring to use server-side state or client-push events.

**Architecture:** Extend `respond_yjs_update` event payload with a `markdown` field so the server always has current markdown without a JS round-trip. Introduce `respond_markdown_flush` as a distinct pre-restart flush event. Restructure paste handler to capture all values at click time via JS event payload. Promote CRDT `response_draft_markdown` from fallback to primary path for all consumers.

**Tech Stack:** NiceGUI (emitEvent, ui.on, run_javascript), Python asyncio, pycrdt, structlog

**Scope:** 3 phases from original design (phase 2 of 3)

**Codebase verified:** 2026-03-29

---

## Acceptance Criteria Coverage

This phase implements and tests:

### eliminate-js-await-454.AC3: Markdown sync uses client-pushed state
- **eliminate-js-await-454.AC3.1 Success:** The `respond_yjs_update` event payload includes a `markdown` field alongside the Yjs binary diff, and the Python handler writes it to `response_draft_markdown` without a JS round-trip
- **eliminate-js-await-454.AC3.2 Success:** `_sync_markdown_to_crdt()` reads markdown from the event payload (or from `response_draft_markdown` already populated by a prior event), not from `getMilkdownMarkdown`
- **eliminate-js-await-454.AC3.3 Success:** PDF export reads markdown from `response_draft_markdown` (promoting the existing fallback to primary path)
- **eliminate-js-await-454.AC3.4 Success:** Pre-restart flush sends fire-and-forget `window._flushRespondMarkdownNow()` to all clients, which emits a distinct `respond_markdown_flush` event (not `respond_yjs_update`), waits 1 second for events to drain, then reads from `response_draft_markdown`
- **eliminate-js-await-454.AC3.5 Success:** The `respond_markdown_flush` handler writes to `response_draft_markdown` and dirty-marks the workspace for persistence — it does NOT relay to peers, update badges, or trigger collaborative edit side-effects
- **eliminate-js-await-454.AC3.6 Edge:** Pre-restart flush is best-effort loss minimisation, not a hard durability guarantee. Any markdown received before the 1-second drain deadline is persisted; late or non-responsive clients may lose their last unsynced edits. This is the explicit brownout trade-off: bounded shutdown latency over waiting for every client
- **eliminate-js-await-454.AC3.7 Edge:** If no Yjs updates have been received (user opened tab but never typed), `response_draft_markdown` holds the last-persisted value from the database — this is correct for pre-restart flush and PDF export (no unsaved edits exist)

### eliminate-js-await-454.AC4: Paste and scroll use non-blocking patterns
- **eliminate-js-await-454.AC4.1 Success:** Paste submit handler receives all three values in the event payload: paste HTML, platform hint, AND live editor content as fallback — no JS round-trip
- **eliminate-js-await-454.AC4.2 Success:** When no paste data exists, the handler uses the editor content from the event payload (not server-side `content_input.value`), avoiding the stale-value socket ordering problem that `on_submit_with_value` was designed to prevent

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Extend `respond_yjs_update` event payload with markdown field

**Verifies:** eliminate-js-await-454.AC3.1, eliminate-js-await-454.AC3.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (lines 593-594 — Yjs update callback in the Python-rendered JS f-string, lines 421-454 — `on_yjs_update` handler, lines 351-395 — `_sync_markdown_to_crdt`)
- Test: `tests/unit/test_markdown_sync_event.py` (unit)

**Implementation:**

**JS change — Python f-string in `respond.py:593-594`:**

The `emitEvent('respond_yjs_update', ...)` call is NOT in the static JS bundle — it is embedded as a Python f-string in `render_respond_tab()` at `respond.py:593-594`. After Phase 1's bundled init, the Yjs update callback is part of the single fire-and-forget JS block. Currently it emits:
```javascript
emitEvent('respond_yjs_update', {update: b64Update});
```

Extend the f-string to include the markdown field:
```javascript
emitEvent('respond_yjs_update', {
    update: b64Update,
    markdown: window._getMilkdownMarkdown()
});
```

`_getMilkdownMarkdown()` (defined in `static/milkdown/src/index.js:109`) is synchronous (reads ProseMirror state from the same transaction), so this adds negligible overhead. Test the change via unit test string inspection of the JS passed to `run_javascript`, not via vitest (since this JS is server-rendered, not a static bundle).

**Python change — `respond.py` `on_yjs_update` handler:**

In `on_yjs_update` (line 421), after applying the CRDT update:
1. Read `markdown` from the event payload: `md = e.args.get("markdown", "")`
2. Write directly to `response_draft_markdown` using the atomic replace pattern from `_sync_markdown_to_crdt` lines 380-388
3. **Ordering constraint:** The markdown write (step 2) MUST precede the word count badge read at line 439 (`markdown = str(crdt_doc.response_draft_markdown)`). The badge reads from the CRDT field, so it must be updated first. Place the write immediately after applying the Yjs update (line 426) and before the badge update block.
4. Remove the `await _sync_markdown_to_crdt(...)` call at line 436

**Python change — remove or deprecate `_sync_markdown_to_crdt`:**

`_sync_markdown_to_crdt` (lines 351-395) is no longer called from `on_yjs_update`. Check if it has any other callers. If the only remaining caller is the tab-leave path (`_sync_respond_on_leave` referenced at `tab_bar.py:299`), that path also needs conversion — it should read from `response_draft_markdown` directly (the mirror is always current after each Yjs event). Remove `_sync_markdown_to_crdt` entirely if all callers are eliminated.

**Testing:**
- eliminate-js-await-454.AC3.1: Test that `on_yjs_update` reads `markdown` from event args and writes to `response_draft_markdown`
- eliminate-js-await-454.AC3.2: Test that `on_yjs_update` does NOT call `_sync_markdown_to_crdt` or any `run_javascript` variant

JS test: Verify that the Yjs update callback includes both `update` and `markdown` fields in the emitEvent payload.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_markdown_sync_event.py`
Run: `uv run grimoire test js`
Expected: All tests pass

**Commit:** `feat: extend respond_yjs_update with markdown field, remove JS round-trip (#454)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Promote CRDT fallback to primary path for PDF export

**Verifies:** eliminate-js-await-454.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py` (lines 209-233 — `_extract_response_markdown`)
- Test: `tests/unit/test_pdf_export_markdown.py` (unit)

**Implementation:**

Simplify `_extract_response_markdown()` to read directly from the CRDT:

```python
def _extract_response_markdown(state: PageState) -> str:
    """Extract response draft markdown from the CRDT mirror.

    The response_draft_markdown field is kept current by the
    respond_yjs_update event handler (which includes markdown in
    every event payload). No JS round-trip needed.
    """
    if state.crdt_doc is not None:
        return state.crdt_doc.get_response_draft_markdown()
    return ""
```

This is now a **sync function** (`def`, not `async def`). Remove the `has_milkdown_editor` check, the `await ui.run_javascript("window._getMilkdownMarkdown()")` call, and the `TimeoutError`/`OSError` exception handling. Update all callers to remove `await` from calls to this function (search for `await _extract_response_markdown`).

**Testing:**
- eliminate-js-await-454.AC3.3: Test that `_extract_response_markdown` reads from `crdt_doc.get_response_draft_markdown()` without any JS call. Mock the CRDT doc with a markdown value and verify it's returned.
- Edge case: Test with `state.crdt_doc is None` returns empty string.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_pdf_export_markdown.py`
Expected: All tests pass

**Commit:** `feat: promote CRDT fallback to primary path for PDF export (#454)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `respond_markdown_flush` event for pre-restart

**Verifies:** eliminate-js-await-454.AC3.4, eliminate-js-await-454.AC3.5, eliminate-js-await-454.AC3.6, eliminate-js-await-454.AC3.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` — add `_flushRespondMarkdownNow` definition to the bundled init JS block (Phase 1 Task 3's f-string), register `respond_markdown_flush` handler
- Modify: `src/promptgrimoire/pages/restart.py` (lines 80-128 — `_flush_single_client`, `_flush_milkdown_to_crdt`)
- Test: `tests/unit/test_pre_restart_flush.py` (unit)

**Implementation:**

**JS — define `window._flushRespondMarkdownNow`:**

Add this function definition to the Phase 1 bundled init JS block in `respond.py` `render_respond_tab()`. Since the bundled init is a Python f-string rendered into the page, append the function definition after the `editor_ready` emit (inside the same JS evaluation block, after the try/catch). This ensures the function is available in the browser context as soon as the editor init JS executes:

```javascript
window._flushRespondMarkdownNow = function() {
    var md = window._getMilkdownMarkdown();
    emitEvent('respond_markdown_flush', {markdown: md});
};
```

This is a thin wrapper — it reads the current markdown and emits a distinct event. It is defined inside the bundled init block (not in `static/milkdown/src/index.js`) because it depends on `emitEvent` being available in the NiceGUI page context. The fire-and-forget `run_javascript("window._flushRespondMarkdownNow()")` call from `restart.py` can reach it because the function is set on `window` after the init block executes.

**Note:** If the editor init fails (JS exception in the try/catch), `_flushRespondMarkdownNow` will still be defined (it's outside the try/catch for `crepe.create()`). This is correct — a failed editor has nothing to flush, and `_getMilkdownMarkdown()` returns `""` when `__milkdownCrepe` is null.

**Python — register `respond_markdown_flush` handler in `respond.py`:**

In `_setup_yjs_event_handler` or alongside it, register:
```python
ui.on("respond_markdown_flush", _on_markdown_flush)
```

The handler `_on_markdown_flush`:
1. Read `md = e.args["markdown"]`
2. Write to `response_draft_markdown` using the atomic replace pattern
3. Call `mark_dirty_workspace()` to ensure the persistence layer will write this workspace. **This is required:** `persist_all_dirty_workspaces()` (called at `restart.py:152`) only persists workspaces previously registered via `mark_dirty_workspace()`. Without this call, a flush-only update (user typed after the last Yjs-triggered dirty mark) stays in memory and is lost on restart.
4. Log at debug level
5. Do NOT relay to peers or update badges — this is a shutdown capture, not a collaborative edit. Dirty-marking is persistence bookkeeping (safe during shutdown), not a collaborative side-effect.

**Python — rewrite `_flush_milkdown_to_crdt` in `restart.py`:**

Replace the per-client `await run_javascript("getMilkdownMarkdown")` loop with:
1. Fire-and-forget `run_javascript("window._flushRespondMarkdownNow()")` to every client with `has_milkdown_editor` (no await, iterate all clients in one pass)
2. `await asyncio.sleep(1.0)` — bounded drain deadline
3. Read `response_draft_markdown` from each workspace's CRDT doc and persist

Remove `_flush_single_client` function entirely — it's replaced by the event-driven pattern.

The drain wait is fixed at 1 second regardless of client count. Under normal conditions, events arrive within milliseconds. Under brownout, this is strictly better than O(N × 3s) sequential timeouts.

**Testing:**
- eliminate-js-await-454.AC3.4: Test that `_flush_milkdown_to_crdt` sends fire-and-forget `_flushRespondMarkdownNow` to all clients and waits 1 second
- eliminate-js-await-454.AC3.5: Test that `_on_markdown_flush` writes to CRDT and calls `mark_dirty_workspace()` (persistence bookkeeping) — assert no calls to broadcast relay or badge update functions
- eliminate-js-await-454.AC3.6: Test structurally that `_flush_milkdown_to_crdt` calls `asyncio.sleep` exactly once with `1.0` (not N times per client) and contains no per-client `await run_javascript` calls — do NOT use wall-clock timing assertions (fragile under xdist)
- eliminate-js-await-454.AC3.7: Test that when no Yjs updates occurred, `response_draft_markdown` holds the DB value (empty string or persisted content) — verify this is the value read during flush

**Verification:**
Run: `uv run grimoire test run tests/unit/test_pre_restart_flush.py`
Expected: All tests pass

**Commit:** `feat: add respond_markdown_flush event for pre-restart drain (#454)`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: Restructure paste handler to capture all values in event payload

**Verifies:** eliminate-js-await-454.AC4.1, eliminate-js-await-454.AC4.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/paste_handler.py` (lines 37-48)
- Modify: `src/promptgrimoire/pages/annotation/content_form.py` (lines 71-83 — submit button wiring)
- Test: `tests/unit/test_paste_handler_event_payload.py` (unit)

**Implementation:**

**content_form.py — Rewire submit button:**

Replace the current `ui.button("Add Document", on_click=handle_add_document)` pattern with a custom JS submit handler that captures all three values at click time:

1. The paste buffer: `window.{paste_var}`
2. The platform hint: `window.{platform_var}`
3. The editor content fallback: the DOM value of the content input element

The JS handler calls `emitEvent` with all three values. Register a Python `ui.on` handler to receive them.

This extends the `on_submit_with_value` pattern from `ui_helpers.py:25` but captures 3 values instead of 1. Rather than modifying `on_submit_with_value` (which is a clean single-value helper used elsewhere), write a custom wiring specific to the paste form.

**paste_handler.py — Update `handle_add_document_submission`:**

Change the function signature to receive the three values directly instead of pulling them via JS:
```python
async def handle_add_document_submission(
    workspace_id: UUID,
    paste_html: str | None,
    platform_hint: str | None,
    editor_content: str,
    on_document_added: Callable[[], object],
) -> None:
```

Remove the two `await ui.run_javascript()` calls at lines 45-46. Use `paste_html` and `editor_content` directly:
```python
content, from_paste = (paste_html, True) if paste_html else (editor_content, False)
```

Remove the `content_input` parameter — the editor content now arrives via the event payload, avoiding the stale-value socket ordering problem.

**content_form.py — Update wiring:**

Wire the submit button with JS that captures all three values and emits them as event args. The Python handler receives them and passes to `handle_add_document_submission`.

After submission, clear the paste buffer: `ui.run_javascript(f"window.{paste_var} = null")` (fire-and-forget).

**Testing:**
- eliminate-js-await-454.AC4.1: Test that `handle_add_document_submission` receives paste_html, platform_hint, and editor_content without any `run_javascript` calls
- eliminate-js-await-454.AC4.2: Test that when paste_html is None/empty, editor_content (from event payload) is used, not `content_input.value`

**Verification:**
Run: `uv run grimoire test run tests/unit/test_paste_handler_event_payload.py`
Expected: All tests pass

**Commit:** `feat: restructure paste handler to capture values in event payload (#454)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Remove tab-leave markdown sync JS call

**Verifies:** eliminate-js-await-454.AC3.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (around line 299 — `_sync_respond_on_leave`)
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (remove `_sync_markdown_to_crdt` if no longer called)
- Test: existing tests must pass

**Implementation:**

The tab-leave handler (`_sync_respond_on_leave` at `tab_bar.py:299`) currently calls `state.sync_respond_markdown()` which invokes `_sync_markdown_to_crdt()` — the function that does `await ui.run_javascript("getMilkdownMarkdown")`.

After Task 1, `response_draft_markdown` is already current (updated on every Yjs event). Tab-leave sync is redundant. Either:
- Remove the tab-leave sync call entirely, OR
- Replace it with a no-op (read from `response_draft_markdown` to confirm it's current, log for observability)

The simpler approach is to remove it. The CRDT mirror is authoritative after every keystroke.

Also remove `sync_respond_markdown` from `PageState` (line 310) if it's no longer used, and any callable assigned to it in `tab_bar.py`.

**Testing:**
Verify no regressions in existing E2E tests that exercise tab switching (test_organise_respond_flow.py).

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `refactor: remove redundant tab-leave markdown sync (#454)`
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_6 -->
### Task 6: Clean up paste window variables if no longer needed

**Verifies:** None (cleanup — dead code removal)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/paste_script.py` (evaluate if `window.{paste_var}` and `window.{platform_var}` are still needed)
- Modify: `src/promptgrimoire/pages/annotation/content_form.py` (remove paste_var/platform_var params if unused)

**Implementation:**

After Task 4, the paste submit handler no longer pulls `window.{paste_var}` and `window.{platform_var}` via JS round-trip. However, the paste script still SETS these variables (the paste event listener writes HTML to `window.{paste_var}` and detects platform to `window.{platform_var}`).

Check if the new submit JS (from Task 4) reads these window variables directly in the click handler. If yes, the variables are still needed (just read client-side instead of server-side). If the click JS reads them inline, the window variables remain necessary.

If the paste script variables are still read by the submit JS, keep them. Only remove if they become truly dead code.

Clean up any now-unused parameters or imports.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass, no dead code warnings

**Commit:** `refactor: clean up paste handler dead code (#454)`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update existing tests for Phase 2 changes

**Verifies:** None (infrastructure — ensures existing tests pass)

**Files:**
- Modify: any existing tests that mock `_sync_markdown_to_crdt`, `_extract_response_markdown`, `_flush_single_client`, or `handle_add_document_submission`
- Modify: any E2E tests that depend on the old function signatures

**Implementation:**

After Tasks 1-6, several functions changed signatures or were removed:
- `_sync_markdown_to_crdt` — removed (callers use event payload)
- `_extract_response_markdown` — simplified to sync CRDT read
- `_flush_single_client` — removed (replaced by event-driven flush)
- `_flush_milkdown_to_crdt` — rewritten to fire-and-forget + drain pattern
- `handle_add_document_submission` — new signature with explicit params instead of content_input

Search for all test files that reference these functions and update accordingly.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `test: update existing tests for Phase 2 event-driven changes (#454)`
<!-- END_TASK_7 -->

---

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Open the Respond tab and type some text
3. [ ] Switch to the Organise tab and back to Respond — text should persist (markdown sync via event payload)
4. [ ] Click Export PDF — the response section should contain the text you typed
5. [ ] Paste an AI conversation (from Claude/ChatGPT) into the source content area and click "Add Document" — the pasted HTML should be processed correctly with platform detection
6. [ ] Type directly into the source editor (no paste) and click "Add Document" — content should be captured correctly
7. [ ] With the editor open and unsaved text, trigger a restart via the admin panel — after restart, reload the page and verify the text you typed is present

## Evidence Required
- [ ] Test output showing green for `uv run grimoire test all`
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uvx ty@0.0.24 check` passes
- [ ] Complexipy results: `uv run complexipy src/promptgrimoire/pages/annotation/respond.py src/promptgrimoire/pages/annotation/pdf_export.py src/promptgrimoire/pages/restart.py src/promptgrimoire/pages/annotation/paste_handler.py src/promptgrimoire/pages/annotation/content_form.py`
