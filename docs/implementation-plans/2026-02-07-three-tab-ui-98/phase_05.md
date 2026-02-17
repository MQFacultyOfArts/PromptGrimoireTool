# Three-Tab Annotation Interface — Phase 5: Milkdown Editor in Tab 3

**Goal:** Embed the collaborative Milkdown editor in Tab 3 with `response_draft` XmlFragment binding, plus a read-only highlight reference panel.

**Architecture:** Create a new `pages/annotation_respond.py` module with Tab 3 rendering logic. The JS bundle's `_createMilkdownEditor` is extended with an optional `fragmentName` parameter (default `'prosemirror'`, Tab 3 passes `'response_draft'`). On the JS side, `CollabService.bindXmlFragment(fragment)` binds the named fragment instead of `bindDoc()`. Python CRDT relay reuses the existing `AnnotationDocument` broadcast mechanism — Yjs updates targeting the `response_draft` XmlFragment travel through the same Doc update channel as highlights and tag_order. A reference panel on the right shows highlights grouped by tag (read-only, using `TagInfo` from Phase 3).

**Tech Stack:** Milkdown 7.x (Crepe), `@milkdown/plugin-collab` (CollabService), y-prosemirror, pycrdt (`XmlFragment`, `Doc`), NiceGUI `ui.element`, `ui.run_javascript`

**Scope:** 7 phases from original design (phase 5 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC4: Tab 3 collaborative editor
- **three-tab-ui.AC4.1 Success:** Milkdown WYSIWYG editor renders in Tab 3 with full toolbar
- **three-tab-ui.AC4.2 Success:** Two clients editing Tab 3 see character-level merged changes in real time
- **three-tab-ui.AC4.3 Success:** Client opening Tab 3 after others have edited receives full state sync
- **three-tab-ui.AC4.4 Success:** Reference panel shows highlights grouped by tag (read-only)
- **three-tab-ui.AC4.5 Edge:** Tab 3 visited before any highlights exist shows empty reference panel and functional editor

---

## Codebase Verification Findings

- ✓ Milkdown spike at `pages/milkdown_spike.py:124-131` — route `/demo/milkdown-spike`, fully functional
- ✓ JS entry point: `static/milkdown/src/index.js:35-85` — `createEditor(rootEl, initialMd, onYjsUpdate)`, exported as `window._createMilkdownEditor` (line 89)
- ✓ Additional JS exports: `window._getMilkdownMarkdown()`, `window._applyRemoteUpdate(b64)`, `window._getYjsFullState()` (lines 89-92)
- ✓ Spike uses `collabServiceCtx.bindDoc(ydoc)` at `index.js:69` — design calls for `bindXmlFragment()` instead
- ✓ `CollabService.bindXmlFragment(xmlFragment)` exists in `@milkdown/plugin-collab/src/collab-service.ts:158-167` — returns `this` for chaining; `bindDoc()` is a convenience wrapper that hardcodes fragment name `'prosemirror'`
- ✓ Python CRDT relay pattern at `milkdown_spike.py:61-225` — `_broadcast_to_others()`, `on_yjs_update()`, full-state sync for late joiners
- ✗ Spike uses isolated module-level Doc (`milkdown_spike.py:51-67`), NOT the annotation workspace's `AnnotationDocument` — Phase 5 must integrate with `AnnotationDocument` registry instead
- ✓ Two-column layout at `annotation.py:1189-1290` — document left (flex: 2), sidebar right (flex: 1), reusable pattern for Tab 3
- ✓ Echo prevention: JS `origin === "remote"` (`index.js:77`), Python client_id filter (`milkdown_spike.py:74`)
- ✗ `AnnotationDocument` does not yet have `response_draft` property — Phase 2 adds it
- ✗ No tab UI exists yet — Phase 1 creates it; Phase 5 populates Tab 3 panel within that container

**External dependency findings:**
- ✓ `CollabService.bindXmlFragment()` is the correct API for binding a named fragment within a shared Doc (vs `bindDoc()` which hardcodes `'prosemirror'`)
- ✓ Multiple Milkdown editors can bind to different XmlFragments in the same Doc — each gets its own CollabService instance, sharing Awareness
- ✓ y-websocket protocol: SyncStep1 (state vector), SyncStep2 (missing state), then Update messages — existing relay pattern handles this
- ✓ Awareness protocol handles cursor/presence tracking — share one Awareness across all editors

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Extend JS bundle to support named XmlFragment binding

**Verifies:** three-tab-ui.AC4.1 (partially — provides the JS infrastructure)

**Files:**
- Modify: `src/promptgrimoire/static/milkdown/src/index.js`

**Implementation:**

Modify the `createEditor()` function to accept an optional `fragmentName` parameter:

1. Change signature from `createEditor(rootEl, initialMd, onYjsUpdate)` to `createEditor(rootEl, initialMd, onYjsUpdate, fragmentName)` where `fragmentName` defaults to `undefined`.

2. When `fragmentName` is provided:
   - Instead of `collabServiceCtx.bindDoc(ydoc)`, use:
     ```javascript
     const fragment = ydoc.getXmlFragment(fragmentName)
     collabServiceCtx.bindXmlFragment(fragment)
     ```
   - This binds the editor to the named fragment within the shared Doc

3. When `fragmentName` is `undefined` (default), keep existing `bindDoc(ydoc)` behaviour for backward compatibility with the spike page.

4. Rebuild the bundle: `cd src/promptgrimoire/static/milkdown && npm run build`

5. Export additional helpers scoped to the fragment:
   - `window._createMilkdownEditor` already handles the editor. The `_applyRemoteUpdate` and `_getYjsFullState` functions operate on the Doc level (not fragment), so they continue to work as-is — the Doc contains all fragments and updates are Doc-scoped.

**Testing:**
No separate unit tests — JS changes verified via E2E tests in Task 4.

**Verification:**
Run: `cd src/promptgrimoire/static/milkdown && npm run build`
Expected: Build succeeds with no errors

**Commit:** `feat: extend Milkdown JS bundle to support named XmlFragment binding`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Tab 3 rendering module

**Verifies:** three-tab-ui.AC4.1, three-tab-ui.AC4.4, three-tab-ui.AC4.5

**Files:**
- Create: `src/promptgrimoire/pages/annotation_respond.py`
- Modify: `src/promptgrimoire/pages/annotation.py` (the `_on_tab_change` handler from Phase 1)

**Implementation:**

Create a new module `pages/annotation_respond.py` with a function:

```python
async def render_respond_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    state: PageState,
) -> None:
```

This function:
1. Clears the placeholder label from the panel
2. Creates a two-column layout (same pattern as `annotation.py:1189-1290`):
   - **Left panel (flex: 2):** Milkdown editor container
   - **Right panel (flex: 1):** Read-only highlight reference cards grouped by tag
3. Left panel setup:
   - Creates a `ui.element("div")` with a unique ID for the editor root element
   - Adds the Milkdown JS/CSS via `ui.add_head_html()` (following the spike pattern at `milkdown_spike.py:131-157`)
   - Calls `ui.run_javascript()` to invoke `window._createMilkdownEditor(rootEl, '', onYjsUpdate, 'response_draft')` — passing the fragment name
   - Registers a Python-side callback for `onYjsUpdate` that:
     - Applies the base64-encoded Yjs update to `crdt_doc.doc` (the pycrdt Doc)
     - Broadcasts the update to other connected clients via the existing broadcast mechanism
4. Right panel setup:
   - For each `TagInfo`, shows a collapsible section with the tag name and colour
   - Lists read-only highlight cards (text snippet, tag, author) from `crdt_doc.get_all_highlights()` filtered by tag
   - If no highlights exist (AC4.5), shows "No highlights yet" message
5. Full-state sync for late joiners:
   - After editor creation, checks if `crdt_doc` already has content in the `response_draft` XmlFragment
   - If so, sends the full Doc state to the newly connected editor via `window._applyRemoteUpdate(b64)`
   - This follows the same pattern as `milkdown_spike.py:207-225`

In `annotation.py`, modify the `_on_tab_change` handler (created in Phase 1 Task 2) so that when `tab_name == "Respond"`:
1. Import and call `render_respond_tab()` with the tab panel, tag info list, CRDT doc, and page state
2. The Milkdown JS/CSS is loaded once — the `initialised_tabs` set on `PageState` (added in Phase 1 Task 2) prevents re-entry: the `_on_tab_change` handler returns early if `"Respond"` is already in `state.initialised_tabs`. Additionally, store a `has_milkdown_editor: bool = False` flag on `PageState` (set to `True` after Milkdown is created) which Phase 7 uses to choose the JS-first vs CRDT-fallback path for PDF export.

**Key design decision:** Tab 3 rendering is a **separate module** (`annotation_respond.py`) to avoid further bloating `annotation.py`. The module imports `TagInfo` but NOT `BriefTag`, maintaining the tag-agnostic boundary.

**Testing:**
Tests in Task 4 verify AC4.1, AC4.4, AC4.5.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation_respond.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: render Tab 3 with Milkdown editor and reference panel`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire CRDT relay for response_draft collaboration

**Verifies:** three-tab-ui.AC4.2, three-tab-ui.AC4.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation_respond.py` (add broadcast integration)
- Modify: `src/promptgrimoire/pages/annotation.py` (extend broadcast handler for Tab 3)

**Implementation:**

The Milkdown editor's Yjs updates flow through the same pycrdt Doc as highlights and tag_order. The key integration points:

1. **Receiving updates from JS editor:**
   - The `onYjsUpdate` callback in `annotation_respond.py` receives base64-encoded Yjs updates from the client
   - Apply to `crdt_doc.doc` via `crdt_doc.apply_update(base64.b64decode(b64_update))` (or the equivalent pycrdt method)
   - Broadcast to other clients using the existing broadcast pattern

2. **Sending updates to JS editor:**
   - Register a CRDT `observe` callback on the `response_draft` XmlFragment (or on the Doc level) that, when triggered by a remote update, sends the update to the client's Milkdown editor via `client.run_javascript(f"window._applyRemoteUpdate('{b64}')")`
   - The echo prevention pattern prevents the originating client from receiving its own update

3. **Full-state sync for late joiners (AC4.3):**
   - When a client first visits Tab 3, send the full Doc state via `bytes(crdt_doc.doc.get_update())` encoded as base64
   - The client's Milkdown editor applies this via `window._applyRemoteUpdate(b64)`
   - This ensures all existing content (from other users' edits) is synced

4. **Integration with existing broadcast:**
   - The existing `broadcast_update()` in `annotation.py` calls each client's callback
   - Extend the per-client callback to check: if the client has Tab 3 initialised and the update contains `response_draft` changes, relay the Yjs update to the editor
   - Alternatively, use a separate Yjs-update-specific broadcast channel for editor updates (simpler: keep Doc-level updates flowing through the same channel)

**Key architectural note:** Yjs updates are **Doc-level**, not fragment-level. When a user edits `response_draft` in Milkdown, the resulting Yjs update encodes changes to the Doc that happen to modify the `response_draft` XmlFragment. Applying this update to another client's Doc correctly modifies only the `response_draft` fragment — highlights and tag_order are unaffected (CRDT merge semantics). This means the existing relay mechanism works without fragment-level routing.

**Testing:**
Tests in Task 4 verify AC4.2 and AC4.3.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation_respond.py src/promptgrimoire/pages/annotation.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: wire CRDT relay for real-time Milkdown collaboration in Tab 3`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E tests for Tab 3 editor and collaboration

**Verifies:** three-tab-ui.AC4.1, three-tab-ui.AC4.2, three-tab-ui.AC4.3, three-tab-ui.AC4.4, three-tab-ui.AC4.5

**Files:**
- Create or modify: `tests/e2e/test_annotation_tabs.py` (add Tab 3 tests)

**Implementation:**

No code changes — this task adds E2E tests verifying Tab 3 behaviour.

**Testing:**
Tests must verify each AC listed above:
- three-tab-ui.AC4.1: Milkdown editor renders with toolbar in Tab 3
- three-tab-ui.AC4.2: Two clients see each other's changes in real time
- three-tab-ui.AC4.3: Late-joining client receives full state
- three-tab-ui.AC4.4: Reference panel shows highlights grouped by tag
- three-tab-ui.AC4.5: Empty highlights shows functional editor with empty reference panel

Write E2E tests in `tests/e2e/test_annotation_tabs.py`:

- `test_respond_tab_shows_milkdown_editor` — Navigate to annotation page with content, switch to Respond tab, verify a Milkdown editor container is visible with toolbar elements (bold, italic, heading buttons or similar WYSIWYG controls)

- `test_respond_tab_two_clients_real_time_sync` — Open two browser contexts on the same workspace, both navigate to Respond tab. Client 1 types "Hello World" in the editor. Verify Client 2's editor shows "Hello World" (use Playwright's `wait_for` with timeout). This verifies character-level merging (AC4.2).

- `test_respond_tab_late_joiner_sync` — Client 1 navigates to Respond tab and types "Initial content". Client 2 then navigates to the same workspace and switches to Respond tab. Verify Client 2's editor contains "Initial content" after sync completes (AC4.3).

- `test_respond_tab_reference_panel_shows_highlights` — Create several highlights with different tags on the Annotate tab, then switch to Respond tab. Verify the right panel shows highlights grouped under tag headings with correct tag names and colours (AC4.4).

- `test_respond_tab_no_highlights_shows_empty_reference` — Navigate to annotation page with content but no highlights, switch to Respond tab. Verify the reference panel shows an empty/placeholder message and the Milkdown editor is functional (can type text) (AC4.5).

Follow existing E2E patterns from `tests/e2e/test_annotation_basics.py` and the milkdown spike tests. For typing in the Milkdown editor, use Playwright's `click()` on the editor container then `type()` or `fill()`.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_respond`
Expected: All tests pass

**Commit:** `test: add E2E tests for Tab 3 Milkdown editor and collaboration`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run E2E tests: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_respond`
2. [ ] Rebuild JS bundle: `cd src/promptgrimoire/static/milkdown && npm run build`
3. [ ] Start the app: `uv run python -m promptgrimoire`
4. [ ] Navigate to `/annotation`, create a workspace, add content
5. [ ] Create several highlights with different tags
6. [ ] Click "Respond" tab
7. [ ] Verify: Milkdown WYSIWYG editor appears with toolbar (bold, italic, headings, etc.)
8. [ ] Verify: Reference panel on the right shows highlights grouped by tag with coloured headers
9. [ ] Type some content in the editor
10. [ ] Open a second browser tab to the same workspace, navigate to Respond tab
11. [ ] Verify: Second browser shows the content typed in step 9 (full-state sync)
12. [ ] Type additional content in the second browser — verify it appears in the first browser in real time
13. [ ] Navigate to Respond tab on a workspace with NO highlights — verify editor works and reference panel shows empty message

## Evidence Required
- [ ] Test output showing green for Tab 3 E2E tests
- [ ] Screenshot showing Milkdown editor in Tab 3 with toolbar visible
- [ ] Screenshot showing reference panel with highlights grouped by tag
- [ ] Screenshot or confirmation of real-time sync between two browser tabs
