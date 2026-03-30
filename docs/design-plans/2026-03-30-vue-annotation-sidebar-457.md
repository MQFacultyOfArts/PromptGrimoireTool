# Vue Annotation Sidebar Design

**GitHub Issue:** #457

## Summary

The annotation sidebar currently builds its UI by looping over highlights in Python and constructing a NiceGUI element tree for each card — roughly 190 trees, each requiring ~0.5ms of server-side blocking work. Every CRDT change (a comment added, a tag changed, a highlight deleted) tears down and rebuilds this entire tree on the server, then sends the resulting DOM diff over a WebSocket to every connected client. At 190 cards that rebuild takes ~100ms of blocking time per mutation, and it contends with all other clients sharing the same asyncio event loop.

This design replaces that approach with a single custom NiceGUI Vue component (`AnnotationSidebar`). Python now has one job: serialise the current CRDT highlight state into a flat list of plain dictionaries (one per card) and push it as a prop. The Vue component renders all cards client-side, manages local interaction state (expand/collapse, input drafts, para_ref editing) without any server round-trip, and emits named events back to Python only when a CRDT mutation is required. The server's role per mutation drops from rebuilding 190 element trees to updating a single prop value. All existing behaviour — permission gating, overlay absolute positioning, CRDT authority, E2E test contracts — is preserved; only the rendering mechanism changes.

## Definition of Done

Replace the per-card Python element loop (190 NiceGUI element trees, ~100ms blocking) with a single custom NiceGUI Vue component (`AnnotationSidebar`) that renders all cards client-side. All 16 existing card interactions must work identically. Server-authoritative CRDT sync via existing broadcast infrastructure. Overlay absolute positioning preserved.

**Success criteria:**
- All 16 card interactions work identically (expand/collapse, tag change, comment CRUD, para_ref edit, highlight delete, locate, hover highlight)
- Permission-gated actions enforced (server-side checks preserved, UI conditionally renders controls)
- Overlay absolute positioning preserved (cards aligned to document highlights)
- DOM contract preserved (all `data-testid`, `data-highlight-id`, `data-start-char` attributes)
- Server-authoritative CRDT sync via existing broadcast infrastructure
- Per-card server-side blocking drops from ~0.5ms to near-zero (one prop update instead of 190 element trees)
- All existing E2E and NiceGUI integration tests pass (or are adapted to equivalent assertions)

**Out of scope:** Virtualisation/viewporting (Phase B, separate design), changes to the CRDT layer, changes to the positioning algorithm.

## Acceptance Criteria

### vue-annotation-sidebar-457.AC1: Card Interactions
- **vue-annotation-sidebar-457.AC1.1 Success:** Clicking header row expands card, detail section visible
- **vue-annotation-sidebar-457.AC1.2 Success:** Clicking expanded header collapses card, detail hidden but retained
- **vue-annotation-sidebar-457.AC1.3 Success:** Cards in `expanded_ids` render with detail visible on load
- **vue-annotation-sidebar-457.AC1.4 Success:** Tag dropdown change updates card border colour and CRDT
- **vue-annotation-sidebar-457.AC1.5 Success:** Comment submit adds comment to list, clears input, increments badge
- **vue-annotation-sidebar-457.AC1.6 Success:** Comment delete removes comment, decrements badge
- **vue-annotation-sidebar-457.AC1.7 Success:** Highlight delete removes card from sidebar and CRDT
- **vue-annotation-sidebar-457.AC1.8 Success:** Para_ref click enters edit mode, blur/enter saves to CRDT
- **vue-annotation-sidebar-457.AC1.9 Success:** Locate button scrolls document to highlight range with throb animation
- **vue-annotation-sidebar-457.AC1.10 Success:** Hover over card highlights text range in document
- **vue-annotation-sidebar-457.AC1.11 Failure:** Comment submit with empty/whitespace text is rejected (no CRDT mutation)
- **vue-annotation-sidebar-457.AC1.12 Edge:** Tag dropdown shows recovery entry when highlight references deleted tag

### vue-annotation-sidebar-457.AC2: DOM Contract
- **vue-annotation-sidebar-457.AC2.1 Success:** Cards have `data-testid="annotation-card"`, `data-highlight-id`, `data-start-char`, `data-end-char`
- **vue-annotation-sidebar-457.AC2.2 Success:** Detail section has `data-testid` for `card-detail`, `tag-select`, `comment-input`, `post-comment-btn`, `comment-count`

### vue-annotation-sidebar-457.AC3: Overlay Positioning
- **vue-annotation-sidebar-457.AC3.1 Success:** Cards positioned absolutely aligned to highlight vertical position in document
- **vue-annotation-sidebar-457.AC3.2 Success:** Scroll, expand/collapse, and item changes trigger repositioning with collision avoidance

### vue-annotation-sidebar-457.AC4: Permissions
- **vue-annotation-sidebar-457.AC4.1 Success:** Users with `can_annotate` see tag dropdown, comment input, and post button
- **vue-annotation-sidebar-457.AC4.2 Failure:** Viewers without `can_annotate` do not see edit controls
- **vue-annotation-sidebar-457.AC4.3 Success:** Delete buttons shown only for content owner or privileged user

### vue-annotation-sidebar-457.AC5: Performance
- **vue-annotation-sidebar-457.AC5.1 Success:** Initial render of 190 cards completes with <5ms server-side blocking (prop serialisation only)
- **vue-annotation-sidebar-457.AC5.2 Success:** CRDT mutation triggers prop update delivered to all clients within one event loop tick

### vue-annotation-sidebar-457.AC6: CRDT Sync
- **vue-annotation-sidebar-457.AC6.1 Success:** Remote CRDT change (from another client) updates cards via prop push
- **vue-annotation-sidebar-457.AC6.2 Success:** `cards_epoch` increments after each items prop update (E2E sync contract)

### vue-annotation-sidebar-457.AC7: Test Coverage
- **vue-annotation-sidebar-457.AC7.1 Success:** All 8 test lanes pass with no test deletions without equivalent replacement

## Glossary

- **NiceGUI**: Python web UI framework that renders server-defined component trees over a persistent WebSocket connection. The Python process owns the element tree; changes are sent as DOM patches to connected browsers.
- **Vue component (custom)**: A self-contained UI unit written using the Vue 3 JavaScript framework. Registered with NiceGUI so Python can pass data in (as props) and receive user actions out (as events).
- **Composition API**: The Vue 3 style for writing component logic using `setup()` and composable functions (`ref`, `watch`, etc.), as opposed to the older Options API.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure that supports concurrent edits from multiple clients and can always be merged without conflicts. The annotation workspace uses pycrdt as the authoritative store.
- **pycrdt**: Python bindings for the Yjs CRDT library. Stores highlights, para refs, comments, and tags with real-time collaborative merging.
- **Prop (Vue)**: Data passed from Python via NiceGUI into a Vue component. Reactive: when the value changes on the Python side, Vue re-renders the affected parts of the DOM automatically.
- **Event (Vue / NiceGUI)**: A named signal emitted by the Vue component (`$emit`) carrying a payload, delivered to a registered Python handler.
- **items prop**: The primary data channel — a serialised flat list of highlight dictionaries pushed from Python to the Vue component after every CRDT change.
- **cards_epoch / `__annotationCardsEpoch`**: A monotonically incrementing counter on `window`. E2E tests use it to detect when a card render cycle has completed.
- **Overlay absolute positioning**: Cards positioned absolutely so they align vertically with the highlight they annotate in the document pane.
- **Collision avoidance**: Positioning algorithm pushes overlapping cards apart to maintain a minimum gap.
- **Lazy detail build (`detailBuiltIds`)**: Detail section of a card only constructed on first expand, then retained in DOM.
- **para_ref**: A paragraph reference label attached to a highlight. Click-to-edit in the detail section.
- **throb animation**: Visual pulse applied to a highlight range when the user clicks "locate" on a card.
- **fire-and-forget `run_javascript`**: NiceGUI pattern where `ui.run_javascript()` is called without `await` to avoid blocking the server event loop.
- **`rAF` (requestAnimationFrame)**: Browser API used to throttle scroll-triggered repositioning to the display refresh rate.
- **`run_method`**: NiceGUI API for calling a method on a custom Vue component from Python. Mentioned as fallback for incremental updates.
- **`watch` with `{ flush: 'post' }`**: Vue option that defers a watcher callback until after DOM update, ensuring epoch increments only after rendering completes.

## Architecture

Single custom NiceGUI Vue component (`AnnotationSidebar`) that replaces the entire per-card Python element loop. Python serialises CRDT highlight state into a flat items list and pushes it as a prop. Vue renders all cards client-side, handles local UI state (expand/collapse, draft text, para_ref editing), and emits semantic events back to Python for CRDT mutations.

### Python Side

**`src/promptgrimoire/pages/annotation/sidebar.py`** — `AnnotationSidebar(ui.element)` with `component='annotation-sidebar.js'`.

Props:

| Prop | Type | Description |
|------|------|-------------|
| `items` | `list[dict]` | Highlight data: `{id, tag_key, tag_display, color, start_char, end_char, para_ref, author, display_author, initials, comments: [{id, author, text, created_at, can_delete}], user_id, can_delete}` |
| `expanded_ids` | `list[str]` | Currently expanded card IDs |
| `tag_options` | `dict[str, str]` | `tag_key -> display_name` for dropdown |
| `permissions` | `dict` | `{can_annotate: bool}` |

Event handlers registered on the Python side:

| Event | Payload | Handler |
|-------|---------|---------|
| `toggle_expand` | `{id, expanded}` | Update `expanded_ids` prop |
| `change_tag` | `{id, new_tag}` | CRDT `update_highlight_tag`, broadcast |
| `submit_comment` | `{id, text}` | CRDT `add_comment`, broadcast |
| `delete_comment` | `{highlight_id, comment_id}` | CRDT `delete_comment`, broadcast |
| `delete_highlight` | `{id}` | CRDT `remove_highlight`, broadcast |
| `edit_para_ref` | `{id, value}` | CRDT `update_highlight_para_ref`, broadcast |
| `locate_highlight` | `{start_char, end_char}` | Fire-and-forget `ui.run_javascript` for scroll + throb |

**Items serialisation** is a pure function: CRDT state + permissions → items list. Called on initial load and after every CRDT mutation or broadcast. Replaces `_diff_annotation_cards`, `_snapshot_highlight`, and all closure factories.

### Vue Side

**`src/promptgrimoire/static/annotation-sidebar.js`** — Vue component using Composition API.

**Template:** Root `<div style="position: relative">` containing a `v-for` over `items`, keyed by `item.id`. Each card is a `<div>` with `data-highlight-id`, `data-start-char`, `data-end-char`, `data-testid="annotation-card"`, positioned absolutely.

**Card structure:**
- Compact header (always rendered): colour dot, tag name, initials, para ref, comment badge, chevron button, locate button, conditional delete button
- Detail section (lazy, built on first expand): tag dropdown, full author, highlighted text preview, para_ref click-to-edit editor, comment list with conditional delete buttons, comment input + post button

**Sidebar-level state (keyed maps, not per-card instance state):**
- `expandedIds: reactive(new Set())` — synced to Python via `toggle_expand` event
- `detailBuiltIds: reactive(new Set())` — tracks which cards have had detail rendered
- `commentDrafts: reactive(new Map())` — `highlightId → draft text`, local until submit
- `paraRefEditMode: reactive(new Map())` — `highlightId → boolean`, display ↔ edit toggle

All mutable UI state lives in sidebar-level maps keyed by highlight ID, not in card component instances. Card components are stateless renderers that read from these maps and emit events upward. This ensures state survives prop replacement, card reordering, and future viewporting (card unmount/remount).

**Positioning (absorbed from `annotation-card-sync.js:44-83`):**
- `positionCards()` using `charOffsetToRect()` from `window._textNodes`
- Triggered on: mount, `items` watch, scroll (throttled via rAF), card expand/collapse
- Collision avoidance (minGap=8px)

**Hover highlight (no server round-trip):**
- Card mouseenter: calls `window.showHoverHighlight(window._textNodes, startChar, endChar)` directly
- Card mouseleave: calls `window.clearHoverHighlight()`

### Event Flow

```
User action in Vue → $emit(event, payload)
→ NiceGUI delivers to Python handler
→ Python mutates CRDT, persists, broadcasts
→ Broadcast callback serialises CRDT → items list
→ sidebar._props['items'] = items; sidebar.update()
→ NiceGUI sends ~25KB prop update over WebSocket
→ Vue reactivity diffs → DOM updates
```

Locate highlight is special: Vue emits `locate_highlight`, Python fires `ui.run_javascript()` for scroll + throb. No CRDT mutation.

### Epoch Synchronisation

Vue component sets `window.__annotationCardsEpoch` (and per-doc `window.__cardEpochs[docId]`) after processing an items prop update. E2E tests wait on epoch change to detect render completion. Same contract as current, different producer.

## Existing Patterns

**NiceGUI custom Vue components** — the codebase does not currently have custom Vue components. Pattern follows NiceGUI's official example: `counter.py`/`counter.js` in `nicegui/examples/custom_vue_component/`. NiceGUI's own `ui.table` wrapping Quasar's QTable is the closest reference for a data-driven component.

**Server-authoritative CRDT sync** — existing pattern in `src/promptgrimoire/pages/annotation/broadcast.py:333-359`. Remote CRDT changes trigger `_handle_remote_update()` which rebuilds tag state, updates CSS, and calls `refresh_annotations`. This design replaces the last step (refresh_annotations → card element rebuild) with a prop update. The authority model is unchanged.

**Permission checks at display time** — existing pattern in `cards.py`. Delete buttons, tag dropdowns, and comment inputs are conditionally rendered based on `can_annotate` and `can_delete_content()`. This design preserves the pattern: permissions are serialised into the items prop (per-item `can_delete`) and the `permissions.can_annotate` flag, and Vue conditionally renders controls.

**Fire-and-forget JavaScript** — existing pattern (`#377`). All `ui.run_javascript()` calls are non-awaited. The locate highlight handler continues this pattern.

**Value-capture for comment submission** — existing pattern (`on_submit_with_value`). Not needed in the Vue component because Vue owns input state locally via `v-model`. The async task reordering problem that motivated value-capture doesn't apply when the value never leaves Vue until submit.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Custom Component Spike

**Goal:** Validate that NiceGUI custom Vue component wiring works in this codebase before building on it. Go/no-go gate.

**Components:**
- Minimal `src/promptgrimoire/pages/annotation/sidebar.py` — `AnnotationSidebar(ui.element)` with `component='annotation-sidebar.js'`, one `items` prop
- Minimal `src/promptgrimoire/static/annotation-sidebar.js` — Vue component that renders a `<div>` per item with `data-testid="annotation-card"` and `data-highlight-id`
- Spike test validating the full round-trip

**Dependencies:** None

**Go/no-go criteria:**
1. Component registration works (NiceGUI serves the JS file, component renders)
2. Python props arrive in Vue (`items` prop with test data visible in rendered DOM)
3. Vue emits reach Python (`$emit('test_event', {id: '...'})` triggers Python handler)
4. Prop updates from Python re-render correctly (change `items`, verify DOM updates)
5. DOM exposes required `data-testid` / `data-*` attributes (Playwright can find them)

**Done when:** All 5 go/no-go criteria pass. If any fail, halt and reassess before proceeding.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Scaffold Card Rendering

**Goal:** Full compact header rendering from items prop, with no interactivity.

**Components:**
- `src/promptgrimoire/pages/annotation/sidebar.py` — items serialisation pure function
- `src/promptgrimoire/static/annotation-sidebar.js` — Vue component rendering compact headers (colour dot, tag, initials, para ref, comment badge)
- Unit tests for items serialisation function

**Dependencies:** Phase 1 (spike passes go/no-go)

**Verifies:** vue-annotation-sidebar-457.AC2 (DOM contract)

**Done when:** Component renders 190 card headers from items prop. Cards have correct `data-testid`, `data-highlight-id`, `data-start-char` attributes. Items serialisation has unit tests.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Card Positioning

**Goal:** Cards positioned absolutely aligned to document highlights.

**Components:**
- `src/promptgrimoire/static/annotation-sidebar.js` — `positionCards()` method, scroll listener, resize observer
- Positioning logic ported from `src/promptgrimoire/static/annotation-card-sync.js:44-83`

**Dependencies:** Phase 2

**Verifies:** vue-annotation-sidebar-457.AC3 (overlay positioning)

**Done when:** Cards align to their highlights in the document pane. Scroll triggers repositioning. Collision avoidance works. Visual parity with current sidebar.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Expand/Collapse and Lazy Detail

**Goal:** Cards expand to show detail section on click. Detail built lazily on first expand.

**Components:**
- `src/promptgrimoire/static/annotation-sidebar.js` — expand/collapse toggle, lazy detail rendering (tag dropdown, author, text preview, para_ref display, comment list, comment input)
- `src/promptgrimoire/pages/annotation/sidebar.py` — `toggle_expand` event handler, `expanded_ids` prop management

**Dependencies:** Phase 3

**Verifies:** vue-annotation-sidebar-457.AC1.1, AC1.2, AC1.3, AC1.4

**Done when:** Click header expands card. Detail section built on first expand, retained on collapse. Pre-expanded cards (from `expanded_ids` prop) render with detail visible. Repositioning fires after expand/collapse.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Tag Change and Comment CRUD

**Goal:** All CRDT-mutating interactions work through Vue events → Python handlers → prop updates.

**Components:**
- `src/promptgrimoire/static/annotation-sidebar.js` — tag dropdown change handler, comment submit, comment delete, highlight delete
- `src/promptgrimoire/pages/annotation/sidebar.py` — event handlers for `change_tag`, `submit_comment`, `delete_comment`, `delete_highlight`

**Dependencies:** Phase 4

**Verifies:** vue-annotation-sidebar-457.AC1.5, AC1.6, AC1.7, AC1.8, AC1.9, AC4 (permissions)

**Done when:** Tag change updates CRDT and broadcasts. Comments can be added and deleted. Highlights can be deleted. Permission gating enforced (delete buttons, tag dropdown, comment input only shown to permitted users). All mutations trigger prop updates to all connected clients.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Para_ref Editor, Locate, and Hover

**Goal:** Remaining interactions: click-to-edit para_ref, locate highlight, hover highlight.

**Components:**
- `src/promptgrimoire/static/annotation-sidebar.js` — para_ref click-to-edit state machine, locate button emitting event, hover mouseenter/mouseleave calling window functions directly
- `src/promptgrimoire/pages/annotation/sidebar.py` — `edit_para_ref` and `locate_highlight` event handlers

**Dependencies:** Phase 5

**Verifies:** vue-annotation-sidebar-457.AC1.10, AC1.11, AC1.12

**Done when:** Para_ref click-to-edit works (display → edit → save/cancel). Locate scrolls document to highlight and throbs. Hover over card highlights text range in document.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Integration and Switchover

**Goal:** Replace the current card-building code path with the Vue sidebar. Remove dead code.

**Components:**
- `src/promptgrimoire/pages/annotation/document.py` — create `AnnotationSidebar` instead of calling `_refresh_annotation_cards`
- `src/promptgrimoire/pages/annotation/broadcast.py` — `_handle_remote_update` calls items-rebuild + prop-push instead of `refresh_annotations`
- `src/promptgrimoire/pages/annotation/cards.py` — remove `_build_annotation_card`, `_build_compact_header`, `_build_detail_section`, `_render_compact_header_html`, `_diff_annotation_cards`, `_snapshot_highlight`, all closure factories
- `src/promptgrimoire/static/annotation-card-sync.js` — remove card positioning code (keep hover highlight, `charOffsetToRect`, `_textNodes` setup, `throbHighlight`)

**Dependencies:** Phase 6

**Verifies:** vue-annotation-sidebar-457.AC5 (performance), AC6 (CRDT sync)

**Done when:** Annotation page uses Vue sidebar. Old card-building code removed. Broadcast triggers prop updates. No regressions in E2E or integration tests.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Test Adaptation

**Goal:** All existing tests pass or are adapted to equivalent assertions on the Vue component.

**Components:**
- `tests/integration/test_annotation_cards_charac.py` — adapt from NiceGUI element inspection to sidebar prop/event assertions or HTML testid search
- `tests/integration/test_lazy_card_detail.py` — adapt to Vue lazy detail behaviour
- `tests/e2e/test_card_layout.py` — verify unchanged (Playwright sees same DOM)
- `tests/integration/test_event_loop_render_lag.py` — update timing assertions (should pass easily with Vue rendering)
- `tests/unit/test_card_header_html.py` — replace with unit tests for items serialisation

**Dependencies:** Phase 7

**Verifies:** vue-annotation-sidebar-457.AC7 (test coverage)

**Done when:** All 8 test lanes pass. No test deletions without equivalent replacement. Timing test passes with adjusted thresholds.
<!-- END_PHASE_8 -->

## Additional Considerations

**State ownership contract.** Three tiers of state, designed to survive prop replacement, card reordering, and future viewporting:

| Owner | State | Survives prop update | Survives virtualisation |
|-------|-------|---------------------|------------------------|
| Server (CRDT) | Canonical annotation data (highlights, comments, tags, para_refs) | Yes (it IS the prop) | Yes |
| Sidebar-level keyed maps | `expandedIds`, `commentDrafts`, `paraRefEditMode` — keyed by highlight ID, held in `reactive()` maps on the sidebar component | Yes (maps are independent of items prop) | Yes (maps survive card unmount/remount) |
| Card component | Presentational only — receives data from props + sidebar maps, emits semantic events upward | N/A (no local state) | N/A |

This separation means card components are stateless renderers. All mutable UI state lives in sidebar-level keyed maps, not in card instances. A future viewporting phase can unmount/remount cards freely without losing drafts or expansion state.

**Concurrent-editing verification.** After implementation, measure under a multi-client replay scenario (10 clients, each submitting a comment in sequence):

| Metric | How to measure | Acceptable |
|--------|----------------|------------|
| `payload_bytes_per_update` | Log `len(json.dumps(items))` in sidebar prop setter | < 50KB |
| `server_update_ms` | `time.monotonic()` around items serialisation + prop push | < 5ms |
| `client_apply_render_ms` | Vue `watch` callback timing (start of handler to post-flush) | < 50ms |
| Multi-client replay | 10 concurrent `nicegui_user` fixtures each submitting a comment, measure total wall clock and per-client prop delivery | All clients see all 10 comments within 2s |

This is a post-implementation verification step, not a gate on the design.

**Prop payload size:** Full items prop for 190 highlights is ~25KB. Sent on initial load and after each CRDT mutation. Mutations are infrequent (user actions, not per-keystroke). If profiling reveals issues, `run_method('updateCard', id, delta)` is a fallback for incremental updates.

**Tag dropdown recovery:** Current code adds a `"⚠ recovered"` option when a highlight references a deleted tag. The Vue component must replicate this: if `item.tag_key` is not in `tag_options`, render a recovery entry in the dropdown.

**Epoch contract:** E2E tests rely on `window.__annotationCardsEpoch` incrementing after card renders. The Vue component must set this after processing each items prop update. Use a Vue `watch` on items with `{ flush: 'post' }` to guarantee DOM is updated before incrementing.
