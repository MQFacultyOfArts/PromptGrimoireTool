# Causal Analysis: Deferred Load E2E Test Failures (#377)

Date: 2026-03-28
Investigator: Claude (opus-4-6)
Status: Phase 3 — 8/9 test files fixed, 1 remaining (Mode C)
Branch: debug/377-workspace-performance
Merge base: 09a555db (origin/main)

## Summary

Moving the annotation page from synchronous rendering (`await _render_workspace_view()`)
to deferred background rendering (`background_tasks.create(_load_workspace_content(...))`)
breaks scripts that rely on page-load-time guarantees. 9 of 46 Playwright tests fail
across three distinct failure modes, all traceable to the same architectural change:
**scripts and JavaScript calls injected during a NiceGUI background task execute after
the browser's page lifecycle events have already fired and before async script fetches
have completed.**

## Differential Baseline

```
git merge-base HEAD origin/main  →  09a555db
git log 09a555db..HEAD --oneline  →  20 commits, 65 files changed
```

Key change in `src/promptgrimoire/pages/annotation/__init__.py`:

**main (synchronous):**
```python
async def annotation_page(client: Client) -> None:
    ...
    ws = await get_workspace(workspace_id)
    await _render_workspace_view(workspace_id, client, ws, footer=footer_el)
```

**branch (deferred):**
```python
async def annotation_page(client: Client) -> None:
    ...
    content_container = ui.column().classes("w-full items-center q-pa-lg")
    with content_container:
        ui.spinner("dots", size="xl")
    task = background_tasks.create(
        _load_workspace_content(workspace_id, client, content_container, footer=footer_el)
    )
```

On main, `_render_workspace_view` runs inside the page handler — NiceGUI includes
all `ui.add_body_html()` content in the initial page HTML, and `DOMContentLoaded`
fires after all scripts are in the DOM.

On the branch, `_load_workspace_content` runs as a fire-and-forget background task —
the page handler returns immediately (rendering a skeleton spinner), the browser
renders the skeleton, `DOMContentLoaded` fires, the WebSocket connects, and THEN the
background task starts sending UI updates, script injections, and JS calls over the
WebSocket.

## Failure Mode A: Paste Handler Never Attaches (7 tests)

**Tests:** test_chatcraft_ingest_232, test_document_upload, test_edit_mode,
test_html_paste_whitespace, test_emoji_export, test_para_screenshot,
test_translation_student

**Symptom:** Editor element resolves in the DOM (locator finds
`<div contenteditable="true" class="q-editor__content">`) but remains empty after
synthetic paste. `"Content pasted"` never appears. 9 retries over 5000ms all show
`unexpected value ""`.

**Mechanism (evidence grade: demonstrated — both borders tested):**

NiceGUI's `ui.add_body_html()` implementation (nicegui/functions/html.py:31) uses
`insertAdjacentHTML("beforebegin", ...)` when the WebSocket is connected. **Browsers
do not execute `<script>` tags inserted via `insertAdjacentHTML` or `innerHTML`.**
This is a browser security feature, not a NiceGUI bug.

During the synchronous page handler (main branch), `add_body_html` appends to
`client._body_html` which is included in the initial HTTP response — browsers DO
execute scripts in the initial page HTML. From a background task, the socket is
already connected, so the `insertAdjacentHTML` path fires and the script is dead.

Initial hypothesis (DOMContentLoaded wrapper) was **falsified**: removing the
wrapper did not fix the tests because the entire `<script>` block never executes.

**Fix:** Changed `content_form.py` from `ui.add_body_html(script)` to
`ui.run_javascript(js_body)` (stripping the `<script>` tags). `run_javascript`
sends JS for direct eval via WebSocket — always executes.

**Negative border:** Reverting to `ui.add_body_html()` reproduces the failure.
**Positive border:** Using `ui.run_javascript()` fixes all 7 paste tests.

**Why passing tests aren't affected:** They either:
- Use `_create_workspace_via_db` + `content_input.fill()` (Playwright native fill,
  bypasses paste handler entirely)
- Pre-populate workspace content in the DB (content form never rendered, paste script
  never needed)

## Failure Mode B: Card Positioning Never Runs (4 tests)

**Tests:** test_card_layout: test_initial_positioning_non_zero_no_overlap,
test_scroll_recovery_no_solitaire_collapse, test_race_condition_highlights_ready,
test_push_down_on_expand

**Symptom:** Cards are visible (highlight creation succeeds, card elements appear)
but `style.top` is never set. `_wait_for_position_cards` times out at 15s.

**Mechanism (evidence grade: plausible — causal chain from differential, not yet
tested directly):**

`document.py:261-262` adds script tags via `ui.add_body_html`:
```python
ui.add_body_html('<script src="/static/annotation-card-sync.js"></script>')
```

`document.py:428` then calls:
```python
ui.run_javascript(f"setupCardPositioning('{doc_id}', '{ann_id}', 8)")
```

On main, the `<script src="...">` tags are in the initial page HTML — the browser
fetches and parses them synchronously during page load. By the time WebSocket-delivered
`ui.run_javascript` calls arrive, all functions are defined.

On the branch, both the script tags and the JS calls come over the WebSocket from
the background task. The `<script src="...">` tag triggers an async fetch. The
`ui.run_javascript("setupCardPositioning(...)")` fires before the fetch completes.
`setupCardPositioning` is undefined → silent JS error → mutation observer never set
up → `positionCards()` never fires on subsequently created cards.

The init_js code (document.py:289-298) handles this race for its OWN functions by
checking `typeof walkTextNodes` and falling back to dynamic loading with onload
callbacks. But `setupCardPositioning(...)` is called separately, outside that guard.

**Why 4 TestCollapsedCards tests pass:** They check card content and visibility, not
`style.top` positioning. They never call `_wait_for_position_cards`.

## Failure Mode C: Late Joiner Cursor Replay (1 test)

**Test:** test_remote_presence_e2e::test_late_joiner_sees_existing_presence (4/5 pass)

**Symptom:** 0 `.remote-cursor` elements when 1 expected. Timeout 5000ms.

**Mechanism (evidence grade: speculative):** Not yet investigated. Likely timing-related
with the deferred load on the second user's page — cursor replay may fire before the
second user's presence infrastructure is fully initialised.

## Generalisation

All three modes share a single root cause: **code that worked when executed during
the synchronous page handler breaks when executed from a background task**, because:

1. **`DOMContentLoaded` has already fired** — any `DOMContentLoaded` listener added
   after page load will never execute (Mode A)
2. **External script fetches are async** — `<script src="...">` added via WebSocket
   doesn't block; subsequent `ui.run_javascript()` calls may fire before the script
   is available (Mode B)
3. **Timing assumptions change** — operations that were atomic during the page handler
   become interleaved with browser event processing (Mode C, speculative)

The fix should address the structural pattern, not patch individual symptoms.

## Evidence Grading

| # | Finding | Grade | Positive border | Negative border | Upgrade path |
|---|---------|-------|----------------|-----------------|--------------|
| 1 | Paste script dead: insertAdjacentHTML ignores `<script>` | Demonstrated | `ui.run_javascript()` fixes all 7 tests | `ui.add_body_html()` reproduces failure | — |
| 2 | setupCardPositioning races with script fetch | Demonstrated | Moving call into init_js fixes all 4 tests | Standalone call reproduces failure | — |
| 3 | Late joiner cursor replay timing | Speculative | Only 1/5 tests fails; deferred load changes timing | Not tested | Investigate cursor replay path |

## Phase 2: Full Audit and Generalisation

### Audit: All script injection in the deferred path

Traced the entire `_load_workspace_content` call chain. Only **2 sites** are
affected. Everything else already has guards or doesn't depend on external scripts:

| Site | File:Line | Anti-pattern | Status |
|------|-----------|-------------|--------|
| Paste handler | `paste_script.py:42` | `DOMContentLoaded` wrapper | **AFFECTED** |
| Card positioning | `document.py:428` | `ui.run_javascript` before script loaded | **AFFECTED** |
| Copy protection | `header.py:81` | `typeof` guard + `_pendingCopyProtection` stash | Safe |
| Highlight init | `document.py:289` | Dynamic script loader with `onload` callbacks | Safe |
| Page title | `workspace.py:164` | No script dependency | Safe |
| Load complete | `workspace.py:365` | No script dependency | Safe |
| Milkdown bundle | `__init__.py:418` | In synchronous page handler, not bg task | Safe |
| Layout docsearch | `layout.py:143` | `DOMContentLoaded` but in `add_head_html` during page handler | Safe |

### Root cause pattern

Both affected sites share one anti-pattern: **assuming scripts injected via
`ui.add_body_html` are available synchronously when `ui.run_javascript` fires**.
This holds during the page handler (scripts are in the initial HTML, parsed
before WebSocket connects). It breaks in background tasks (scripts arrive via
WebSocket, external fetches are async).

The existing `init_js` code (document.py:266–299) already has the **correct
pattern**: check `typeof walkTextNodes === 'function'`, and if not available,
dynamically create `<script>` elements with `onload` callbacks. This is the
reference implementation for deferred-safe script injection.

### Proposed fixes

#### Fix A: Paste script — remove `DOMContentLoaded` wrapper

`paste_script.py:42`: The `tryAttach()` polling loop already handles the "element
not yet in DOM" case with `setTimeout(tryAttach, 50)`. The `DOMContentLoaded`
wrapper was belt-and-suspenders that becomes a blocker in the deferred path.

Replace with a `readyState` guard that works in both synchronous and deferred
contexts:

```javascript
// Works during page handler (readyState='loading') AND background task (readyState='complete')
(function() {
    var tryAttach = function() { ... };  // existing polling logic, unchanged
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', tryAttach);
    } else {
        tryAttach();
    }
})();
```

**Scope:** 1 file, ~3 lines changed. No functional change to the paste handler
logic itself.

#### Fix B: Card positioning — roll into init_js script loader

`document.py:428`: `setupCardPositioning(...)` is called via a standalone
`ui.run_javascript` that races with the async script fetch. The `init()` function
(document.py:273–287) already guarantees all 3 scripts are loaded before it runs.

Move the `setupCardPositioning(...)` call into `init()`:

```javascript
function init() {
    // ... existing walkTextNodes, applyHighlights, setupAnnotationSelection ...
    setupCardPositioning(docContainerId, sidebarId, 8);  // ADD
}
```

This requires passing `ann_container_id` into the init_js template (currently
only `doc_container_id` and `highlight_menu_id` are passed). Straightforward —
add one more t-string interpolation.

**Scope:** 1 file, ~5 lines changed. Removes the standalone `ui.run_javascript`
call, adds the call inside `init()`.

#### Fix C: E2E readiness helper — `wait_for_annotation_ready()`

Add a test infrastructure helper that explicitly waits for the deferred load to
complete. This is the "fail early" safety net that catches future regressions
where new deferred code is added without proper timing.

```python
# In src/promptgrimoire/docs/helpers.py (alongside wait_for_text_walker)

def wait_for_annotation_ready(page: Page, *, timeout: int = 15000) -> None:
    """Wait for the annotation page's deferred load to complete.

    The annotation page uses background_tasks.create() to load content
    after the page handler returns.  This helper waits for the background
    task to signal completion via window.__loadComplete.

    Must be called after navigating to /annotation?workspace_id=...
    Fails fast with diagnostic state if the deferred load doesn't complete.
    """
    try:
        page.wait_for_function(
            "() => window.__loadComplete === true",
            timeout=timeout,
        )
    except Exception as exc:
        if "Timeout" not in type(exc).__name__:
            raise
        url = page.url
        diag = page.evaluate(
            "() => ({"
            "  loadComplete: window.__loadComplete,"
            "  spinner: !!document.querySelector('[data-testid=\"workspace-loading-spinner\"]'),"
            "  statusMsg: (document.querySelector('[data-testid=\"workspace-status-msg\"]') || {}).textContent || null,"
            "  scripts: Array.from(document.querySelectorAll('script[src]'))"
            "    .map(s => s.src).filter(s => s.includes('annotation'))"
            "})"
        )
        msg = (
            f"Annotation page deferred load timeout ({timeout}ms). URL: {url}"
            f" __loadComplete: {diag['loadComplete']}"
            f" spinner visible: {diag['spinner']}"
            f" status: {diag['statusMsg']!r}"
            f" scripts: {diag['scripts']}"
        )
        raise type(exc)(msg) from None
```

**Readiness hierarchy** for annotation page tests:

| Level | Helper | What it gates | When to use |
|-------|--------|---------------|-------------|
| 1 | `wait_for_annotation_ready()` | Background task complete, UI built | After any navigation to `/annotation?workspace_id=...` |
| 2 | `wait_for_text_walker()` | Document rendered, text nodes walked | Before highlight/selection interactions |

Level 2 implies Level 1 for workspaces with documents (text walker can only be
ready after the background task renders the document). Level 1 alone is needed
for empty workspaces (content form, no document yet).

#### Fix D: Apply readiness helper to affected navigation patterns

Update `fixture_loaders.py` to call `wait_for_annotation_ready()` after
`page.wait_for_url(re.compile(r"workspace_id="))`:

```python
# fixture_loaders.py — _load_fixture_via_paste
page.goto(f"{app_server}/annotation")
page.get_by_test_id("create-workspace-btn").click()
page.wait_for_url(re.compile(r"workspace_id="))
wait_for_annotation_ready(page)  # NEW — deferred load done
# Now content form is rendered, paste handler attached
```

Same for `setup_workspace_with_content` and any test that creates a workspace
via UI then immediately interacts.

### Why this generalises

The pattern is: **every navigation to an annotation workspace URL must wait for
`__loadComplete` before interacting.** Tests that already call
`wait_for_text_walker` are implicitly waiting (text walker requires init_js to
run, which requires the background task to complete). Tests that DON'T call
`wait_for_text_walker` (paste tests, empty workspace tests) need the explicit
`wait_for_annotation_ready` gate.

The server-side contract is: `window.__loadComplete = true` is set at the END
of `_load_workspace_content`, after ALL scripts are injected, ALL UI is built,
ALL event handlers are attached. This is the single source of truth for "the
page is ready."

### Mode C: Late joiner (deferred to Phase 3)

The `test_late_joiner_sees_existing_presence` failure needs separate
investigation. It may be a timing issue with cursor replay that the readiness
helper alone doesn't fix, or it may resolve once Fix A/B/C are applied (the
test navigates a second page to the annotation workspace).
