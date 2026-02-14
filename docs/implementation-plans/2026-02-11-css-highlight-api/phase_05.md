# CSS Custom Highlight API — Phase 5: Remote Presence

**Goal:** Replace CSS-injection-based remote cursor/selection rendering with JS-driven rendering using DOM elements (cursors) and CSS Custom Highlight API (selections). Simplify the server-side presence model.

**Architecture:** Remote cursors are positioned `<div>` elements (CSS Highlight API cannot style borders/positioning). Remote selections are `CSS.highlights` entries per user. Server broadcasts via `ui.run_javascript()` / `client.run_javascript()` targeting specific NiceGUI clients. In-memory dict tracks presence state (not pycrdt Awareness — server-hub architecture doesn't match Awareness's peer-to-peer model).

**Tech Stack:** NiceGUI, CSS Custom Highlight API, JavaScript DOM API

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-02-12

**Design deviation:** Design specified pycrdt Awareness for presence sync. Implementation uses NiceGUI's server-hub model with an in-memory dict and direct JS broadcast instead, because Awareness's `set_local_state()` only tracks one client — the server-mediated WebSocket architecture requires per-client state that Awareness's peer-to-peer protocol cannot provide without complex `apply_awareness_update()` encoding. All AC3 acceptance criteria are still met via the alternative mechanism; `client.on_disconnect` provides faster cleanup (~1-2s) than Awareness's 30s timeout.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### css-highlight-api.AC3: Remote presence via pycrdt Awareness
- **css-highlight-api.AC3.1 Success:** A second user's cursor appears as a coloured vertical line with name label at the correct character position
- **css-highlight-api.AC3.2 Success:** A second user's text selection appears as a coloured background highlight (via `CSS.highlights`) distinct from annotation highlights
- **css-highlight-api.AC3.3 Success:** When a remote user disconnects, their cursor and selection are removed within 30 seconds (Awareness timeout)
- **css-highlight-api.AC3.4 Success:** The local user's own cursor/selection is not rendered as a remote indicator
- **css-highlight-api.AC3.5 Failure:** `_connected_clients` dict, `_ClientState` class, `_build_remote_cursor_css()`, and `_build_remote_selection_css()` no longer exist in `pages/annotation.py`

**Note on AC3.3:** Design specified "Awareness timeout" but this implementation uses NiceGUI's `client.on_disconnect` callback, which fires within ~1-2 seconds — faster than the 30s AC requirement.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
## Subcomponent A: JS Remote Presence Rendering

<!-- START_TASK_1 -->
### Task 1: Add remote cursor rendering to annotation-highlight.js

**Verifies:** css-highlight-api.AC3.1 (partial — JS rendering side)

**Files:**
- Modify: `src/promptgrimoire/static/annotation-highlight.js`

**Implementation:**

Add these functions to the existing `annotation-highlight.js` module (which already has `walkTextNodes`, `charOffsetToRange`, etc. from Phase 2):

- `renderRemoteCursor(container, clientId, charIdx, name, color)`:
  - Look for existing `<div id="remote-cursor-{clientId}">` in container's parent, remove if found
  - Call `charOffsetToRect(textNodes, charIdx)` to get a DOMRect (this function, added in Phase 4, handles the StaticRange → live Range conversion internally)
  - Create a `<div class="remote-cursor" id="remote-cursor-{clientId}">` with:
    - Absolute positioning at `rect.left`, `rect.top` (relative to `#doc-container`)
    - `border-left: 2px solid {color}`
    - Height matching `rect.height`
    - A child `<span class="remote-cursor-label">` with `name` text, background `color`
  - Append to `container.parentElement` (so it's positioned relative to the scroll container)

- `removeRemoteCursor(clientId)`:
  - Find and remove `#remote-cursor-{clientId}` from DOM

- `updateRemoteCursorPositions(container)`:
  - Called on scroll/resize. For each `.remote-cursor` element, recalculate position from stored `charIdx` data attribute using `charOffsetToRect(textNodes, charIdx)`

**Verification:**
Run: `uv run ruff check src/promptgrimoire/static/`
Expected: No Python files to lint (JS file). Manual browser inspection during E2E.

**Commit:** `feat: add remote cursor rendering to annotation-highlight.js`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add remote selection rendering to annotation-highlight.js

**Verifies:** css-highlight-api.AC3.2 (partial — JS rendering side)

**Files:**
- Modify: `src/promptgrimoire/static/annotation-highlight.js`

**Implementation:**

Add these functions to `annotation-highlight.js`:

- `renderRemoteSelection(clientId, startChar, endChar, name, color)`:
  - Build text node map if not cached: `walkTextNodes(container)`
  - Create Range objects spanning `startChar` to `endChar` using `charOffsetToRange(textNodes, startChar, endChar)`
  - Create a `new Highlight(range)` object
  - Set `highlight.priority = -1` (below annotation highlights which default to 0)
  - Register: `CSS.highlights.set('hl-sel-' + clientId, highlight)`
  - Inject a `<style id="remote-sel-style-{clientId}">` with:
    ```css
    ::highlight(hl-sel-{clientId}) { background-color: {color}30; }
    ```
  - Optionally render a small name label at the selection start (same pattern as cursor label but for selection)

- `removeRemoteSelection(clientId)`:
  - `CSS.highlights.delete('hl-sel-' + clientId)`
  - Remove `#remote-sel-style-{clientId}` from DOM

- `removeAllRemotePresence()`:
  - Remove all `.remote-cursor` elements
  - Remove all `CSS.highlights` entries starting with `hl-sel-`
  - Remove all `[id^="remote-sel-style-"]` style elements

**Key design point:** Remote selection highlights get `priority = -1` so annotation highlights (priority 0) always render on top. This ensures annotation data is always visible over transient presence indicators.

**Verification:**
Manual browser inspection during E2E tests.

**Commit:** `feat: add remote selection rendering via CSS Highlight API`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add CSS styles for remote cursor elements

**Verifies:** css-highlight-api.AC3.1 (partial — CSS side)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` — add to `_PAGE_CSS` string

**Implementation:**

Add these CSS rules to the `_PAGE_CSS` string constant in `annotation.py` (around line 316, after existing styles):

```css
/* Remote cursor indicators */
.remote-cursor {
    position: absolute;
    width: 2px;
    pointer-events: none;
    z-index: 20;
    transition: left 0.15s ease, top 0.15s ease;
}
.remote-cursor-label {
    position: absolute;
    top: -1.4em;
    left: -2px;
    font-size: 0.6rem;
    color: white;
    padding: 1px 4px;
    border-radius: 2px;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0.9;
}
```

No CSS needed for remote selections — those use dynamically injected `::highlight()` rules per client (see Task 2).

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Expected: Passes (string constant change only)

**Commit:** `feat: add CSS for remote cursor elements`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->
## Subcomponent B: Server-Side Presence Refactor

<!-- START_TASK_4 -->
### Task 4: Replace _ClientState with _RemotePresence dataclass

**Verifies:** css-highlight-api.AC3.5 (partial — _ClientState deletion)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:75-118`

**Implementation:**

Replace `_ClientState` class (L75-111) and `_connected_clients` dict (L115) with:

```python
@dataclass
class _RemotePresence:
    """Lightweight presence state for a connected client."""
    name: str
    color: str
    nicegui_client: Any  # NiceGUI Client for JS relay
    callback: Any  # Async callback for annotation/UI updates
    cursor_char: int | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    has_milkdown_editor: bool = False

# Track connected clients per workspace for broadcasting
# workspace_id -> {client_id -> _RemotePresence}
_workspace_presence: dict[str, dict[str, _RemotePresence]] = {}
```

Add `from dataclasses import dataclass` to imports if not present.

Update ALL references from `_connected_clients` to `_workspace_presence` and from `_ClientState` to `_RemotePresence` throughout the file. Grep for `_connected_clients` to find every reference (approximately 15 occurrences across lines 1525-2876).

The `callback` field is kept because it's used for annotation update broadcasting (highlights, cards, organise tab) — not just cursor/selection. Only cursor/selection rendering changes; the annotation callback mechanism stays.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Run: `uv run test-debug`
Expected: Lint passes. Tests pass (rename only, no behaviour change yet).

**Commit:** `refactor: replace _ClientState with _RemotePresence dataclass`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Replace CSS injection with JS-targeted broadcast for cursors and selections

**Verifies:** css-highlight-api.AC3.1, css-highlight-api.AC3.2, css-highlight-api.AC3.4, css-highlight-api.AC3.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Implementation:**

**Delete these functions entirely:**
- `_build_remote_cursor_css()` (L568-595) — generates `[data-char-index]` CSS
- `_build_remote_selection_css()` (L598-634) — generates `[data-char-index]` CSS
- `_update_cursor_css()` (L1520-1529) — injects cursor CSS into style element
- `_update_selection_css()` (L1532-1541) — injects selection CSS into style element

**Replace `broadcast_cursor` function** in `_setup_client_sync()` (currently L1593-1604):

Old: updates `_ClientState.cursor_char`, calls all other clients' callbacks (which regenerate CSS).

New: updates `_RemotePresence.cursor_char`, then directly calls `run_javascript()` on each OTHER client's NiceGUI Client object:

```python
async def broadcast_cursor(char_index: int | None) -> None:
    clients = _workspace_presence.get(workspace_key, {})
    if client_id in clients:
        clients[client_id].cursor_char = char_index
    for cid, presence in clients.items():
        if cid == client_id:
            continue  # AC3.4: don't render own cursor
        if presence.nicegui_client is None:
            continue
        with contextlib.suppress(Exception):
            if char_index is not None:
                js = (
                    f"renderRemoteCursor("
                    f"document.getElementById('doc-container'), "
                    f"'{client_id}', {char_index}, "
                    f"'{state.user_name}', '{state.user_color}')"
                )
            else:
                js = f"removeRemoteCursor('{client_id}')"
            await presence.nicegui_client.run_javascript(js, timeout=2.0)
```

**Replace `broadcast_selection` function** (currently L1606-1617):

Same pattern — directly call JS on each other client:

```python
async def broadcast_selection(start: int | None, end: int | None) -> None:
    clients = _workspace_presence.get(workspace_key, {})
    if client_id in clients:
        clients[client_id].selection_start = start
        clients[client_id].selection_end = end
    for cid, presence in clients.items():
        if cid == client_id:
            continue
        if presence.nicegui_client is None:
            continue
        with contextlib.suppress(Exception):
            if start is not None and end is not None:
                js = (
                    f"renderRemoteSelection("
                    f"'{client_id}', {start}, {end}, "
                    f"'{state.user_name}', '{state.user_color}')"
                )
            else:
                js = f"removeRemoteSelection('{client_id}')"
            await presence.nicegui_client.run_javascript(js, timeout=2.0)
```

**Update `handle_update_from_other` callback** (L1620-1632):

Remove the calls to `_update_cursor_css(state)` and `_update_selection_css(state)` — cursor/selection rendering is now JS-driven, not callback-driven. Keep all other calls (highlight CSS, annotations, organise, respond).

**Delete cursor/selection `<style>` elements** from page setup:

Remove `state.cursor_style` and `state.selection_style` creation (wherever they're created in the annotation page setup). These were containers for dynamically generated CSS; no longer needed.

**Add late-join presence sync** in `_setup_client_sync()`:

When a new client connects, send them all existing cursors/selections:

```python
# Send existing remote cursors/selections to newly connected client
for cid, presence in _workspace_presence.get(workspace_key, {}).items():
    if cid == client_id:
        continue
    if presence.cursor_char is not None:
        js = (
            f"renderRemoteCursor("
            f"document.getElementById('doc-container'), "
            f"'{cid}', {presence.cursor_char}, "
            f"'{presence.name}', '{presence.color}')"
        )
        ui.run_javascript(js)
    if presence.selection_start is not None and presence.selection_end is not None:
        js = (
            f"renderRemoteSelection("
            f"'{cid}', {presence.selection_start}, {presence.selection_end}, "
            f"'{presence.name}', '{presence.color}')"
        )
        ui.run_javascript(js)
```

**Testing:**
Tests must verify each AC listed above:
- css-highlight-api.AC3.1: Remote cursor appears at correct character position with name label and colour
- css-highlight-api.AC3.2: Remote selection appears as coloured CSS highlight distinct from annotations
- css-highlight-api.AC3.4: Local user's own cursor/selection not rendered as remote indicator
- css-highlight-api.AC3.5: `_connected_clients`, `_ClientState`, `_build_remote_cursor_css`, `_build_remote_selection_css` do not exist in source

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Run: `uv run test-debug`
Expected: Passes.

**Commit:** `feat: replace CSS injection with JS-targeted presence broadcast`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Wire disconnect cleanup and broadcast removal

**Verifies:** css-highlight-api.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` — `on_disconnect` handler in `_setup_client_sync()`

**Implementation:**

Update the `on_disconnect` handler (currently L1655-1666) to broadcast cursor/selection removal to all remaining clients via JS:

```python
async def on_disconnect() -> None:
    if workspace_key in _workspace_presence:
        _workspace_presence[workspace_key].pop(client_id, None)
        # Broadcast removal of this client's cursor/selection to all remaining
        for cid, presence in _workspace_presence.get(workspace_key, {}).items():
            if presence.nicegui_client is None:
                continue
            with contextlib.suppress(Exception):
                js = (
                    f"removeRemoteCursor('{client_id}');"
                    f"removeRemoteSelection('{client_id}')"
                )
                await presence.nicegui_client.run_javascript(js, timeout=2.0)
        # Broadcast UI updates (user count, etc.)
        for cid, presence in _workspace_presence.get(workspace_key, {}).items():
            if presence.callback:
                with contextlib.suppress(Exception):
                    await presence.callback()
    pm = get_persistence_manager()
    await pm.force_persist_workspace(workspace_id)
```

NiceGUI's `client.on_disconnect` fires within ~1-2 seconds of browser tab close, well within the AC3.3 requirement of "within 30 seconds."

**Testing:**
Tests must verify:
- css-highlight-api.AC3.3: Remote user's cursor and selection are removed after disconnect

**Verification:**
Run: `uv run test-debug`
Expected: Passes.

**Commit:** `feat: broadcast presence removal on disconnect`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 7) -->
## Subcomponent C: Dead Code Cleanup

<!-- START_TASK_7 -->
### Task 7: Delete unused Awareness presence methods from annotation_doc.py

**Verifies:** css-highlight-api.AC3.5 (partial — dead code removal)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:511-576`

**Implementation:**

Delete these three methods from `AnnotationDoc`:
- `update_cursor()` (L511-529) — calls `self.awareness.set_local_state()` but was never called
- `update_selection()` (L531-559) — same
- `clear_cursor_and_selection()` (L561-576) — same

These methods were designed as seams for Awareness integration but the server-hub architecture decision means presence is managed in `annotation.py` directly, not through the CRDT document.

**Do NOT delete:**
- `self.awareness = Awareness(self.doc)` at L70 — Awareness is still used for `register_client()` state (L172-174) and may be needed for future features
- `register_client()` / `unregister_client()` methods — these manage Doc-level metadata, not cursor/selection presence

**Verification:**
Run: `uv run ruff check src/promptgrimoire/crdt/annotation_doc.py`
Run: `uv run test-debug`
Expected: Passes. No tests should break (methods were never called).

**Commit:** `refactor: delete unused Awareness cursor/selection methods`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 8-9) -->
## Subcomponent D: Tests

<!-- START_TASK_8 -->
### Task 8: Unit tests for JS remote presence rendering

**Verifies:** css-highlight-api.AC3.1, css-highlight-api.AC3.2

**Files:**
- Create: `tests/e2e/test_remote_presence_rendering.py`

**Implementation:**

Write Playwright-based tests that load the annotation-highlight.js module in a test page and verify:

1. **Cursor rendering:** Call `renderRemoteCursor(container, 'test-user', 10, 'Alice', '#2196F3')` → verify a `.remote-cursor` div exists at approximately the correct position, with the name label "Alice" and correct colour.

2. **Cursor removal:** Call `removeRemoteCursor('test-user')` → verify `.remote-cursor` div is gone.

3. **Selection rendering:** Call `renderRemoteSelection('test-user', 5, 20, 'Alice', '#2196F3')` → verify `CSS.highlights.has('hl-sel-test-user')` is true and the style element exists.

4. **Selection removal:** Call `removeRemoteSelection('test-user')` → verify `CSS.highlights.has('hl-sel-test-user')` is false and style element is removed.

5. **Multiple users:** Render cursors/selections for two different client IDs → verify both exist independently.

6. **Cleanup:** Call `removeAllRemotePresence()` → verify all remote indicators are gone.

Use a workspace fixture HTML file loaded into a test page with the annotation-highlight.js module. Mark tests with `@pytest.mark.e2e`.

**Testing:**
These ARE the tests.

**Verification:**
Run: `uv run pytest tests/e2e/test_remote_presence_rendering.py -v`
Expected: All tests pass.

**Commit:** `test: add unit tests for JS remote presence rendering`
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Multi-context E2E smoke test for remote presence

**Verifies:** css-highlight-api.AC3.1, css-highlight-api.AC3.2, css-highlight-api.AC3.3, css-highlight-api.AC3.4

**Files:**
- Create: `tests/e2e/test_remote_presence_e2e.py`

**Implementation:**

Write a single E2E smoke test using two Playwright browser contexts connected to the same annotation workspace:

1. **Setup:** Create a workspace with a document. Open it in two browser contexts (context_a, context_b) with different user names.

2. **Cursor visibility (AC3.1):** In context_a, click at a text position. In context_b, verify a `.remote-cursor` element appears with context_a's name label.

3. **Selection visibility (AC3.2):** In context_a, select a text range. In context_b, verify `CSS.highlights.has('hl-sel-{context_a_client_id}')` is true via JS evaluation.

4. **Own cursor not shown (AC3.4):** In context_a, verify no `.remote-cursor` element exists for context_a's own client_id.

5. **Disconnect cleanup (AC3.3):** Close context_a. In context_b, wait up to 5 seconds and verify the remote cursor and selection for context_a are removed.

Mark with `@pytest.mark.e2e`. This test requires a live app server (excluded from `test-all` per project convention).

**Testing:**
This IS the test.

**Verification:**
Run: `uv run pytest tests/e2e/test_remote_presence_e2e.py -v`
Expected: Smoke test passes.

**Commit:** `test: add multi-context E2E smoke test for remote presence`
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_D -->
