# Vue Annotation Sidebar Implementation Plan — Phase 9

**Goal:** Replace the current Python card-building code path with the Vue sidebar. Remove dead code. Wire broadcast to push Vue props.

**Architecture:** `document.py` creates `AnnotationSidebar` instead of calling `_refresh_annotation_cards`. `broadcast.py:_handle_remote_update()` rebuilds items and pushes prop instead of calling `refresh_annotations`. `cards.py` deleted entirely (19 dead functions). `annotation-card-sync.js` stripped of `setupCardPositioning()`, utility functions preserved.

**Tech Stack:** NiceGUI 3.9.0, Vue 3, Python 3.14

**Scope:** Phase 9 of 10 from original design

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

This phase implements and tests:

### vue-annotation-sidebar-457.AC5: Performance
- **vue-annotation-sidebar-457.AC5.1 Success:** Initial render of 190 cards completes with <5ms server-side blocking (prop serialisation only)
- **vue-annotation-sidebar-457.AC5.2 Success:** CRDT mutation triggers prop update delivered to all clients within one event loop tick

### vue-annotation-sidebar-457.AC6: CRDT Sync
- **vue-annotation-sidebar-457.AC6.1 Success:** Remote CRDT change (from another client) updates cards via prop push
- **vue-annotation-sidebar-457.AC6.2 Success:** `cards_epoch` increments after each items prop update (E2E sync contract)

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/document.py:415-422` — where `refresh_annotations` and `_refresh_annotation_cards` are called
- `src/promptgrimoire/pages/annotation/document.py:288-289` — where `setupCardPositioning()` JS is called
- `src/promptgrimoire/pages/annotation/broadcast.py:333-358` — `_handle_remote_update()` with per-tab dispatch
- `src/promptgrimoire/pages/annotation/tab_bar.py:314-333` — `_refresh_source_tab()` tab switch handler
- `src/promptgrimoire/pages/annotation/tab_bar.py:530-539` — `_save_previous_source_tab()` state save
- `src/promptgrimoire/pages/annotation/__init__.py:240-253` — PageState card-related fields
- `src/promptgrimoire/pages/annotation/cards.py` — entire file (to be deleted)
- `src/promptgrimoire/static/annotation-card-sync.js:29-145` — `setupCardPositioning()` (to be removed)
- `src/promptgrimoire/pages/annotation/highlights.py:89-90, 321-322` — callers of `refresh_annotations`
- `src/promptgrimoire/pages/annotation/tag_management_save.py:93-94` — caller of `refresh_annotations`
- `src/promptgrimoire/pages/annotation/tag_quick_create.py:228-229` — caller of `refresh_annotations`
- `src/promptgrimoire/pages/annotation/header.py:155-186` — `_wrap_export_stale_clear()` wrapping refresh_annotations
- CLAUDE.md — fire-and-forget JS, project conventions

## Impact Analysis

**NOT affected (verified independently rendered):**
- Organise tab (`organise.py`) — own `_build_highlight_card()`, no cards.py dependency
- Respond tab (`respond.py`) — own `_build_reference_card()`, no cards.py dependency
- Both share `card_shared.py` utilities which are preserved

**Affected:**
- Source (Annotate) tab only — card rendering switches from Python `cards.py` to Vue `annotation-sidebar.js`

---

<!-- START_TASK_1 -->
### Task 1: Wire AnnotationSidebar into document.py

**Verifies:** vue-annotation-sidebar-457.AC5.1, vue-annotation-sidebar-457.AC6.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document.py`
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

**Replace card building with Vue sidebar creation:**

In `document.py`, where `_refresh_annotation_cards(state, trigger="initial_load")` is currently called (line 422):

1. Remove: `from .cards import _refresh_annotation_cards`
2. Import: `from .sidebar import AnnotationSidebar`
3. Create `AnnotationSidebar` instance inside the annotations container
4. Call `sidebar.refresh_items(state)` to push initial items prop
5. Set `state.refresh_annotations` to a new function that calls `sidebar.refresh_items(state)`

**`refresh_items()` on AnnotationSidebar** should:
1. Call `serialise_items()` with current CRDT state, tag info, permissions
2. Push `items` prop
3. Push `expanded_ids` prop
4. Push `tag_options` prop
5. Push `permissions` prop
6. Call `self.update()`
7. Increment `state.cards_epoch` and push epoch via fire-and-forget `ui.run_javascript()` — must set BOTH `window.__annotationCardsEpoch` AND `window.__cardEpochs[docId]` where `docId` is the `doc_container_id` prop (added in Phase 5 Task 4). The per-doc epoch is what E2E tests wait on for multi-document workspaces.

**Remove `setupCardPositioning()` JS call** (line 288-289) — positioning is now inside the Vue component.

**Tab state save/restore simplification:**
- `_save_previous_source_tab()` no longer needs to save `annotation_cards` or `card_snapshots` (Vue re-renders from props)
- `_restore_source_tab_state()` no longer needs to restore these
- Keep saving/restoring `expanded_cards` (user's expand state persists across tab switches)

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/document.py`
Expected: No type errors

**Commit:** `feat(annotation): wire AnnotationSidebar into document.py, replace card building (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update broadcast handler for Vue prop push

**Verifies:** vue-annotation-sidebar-457.AC6.1, vue-annotation-sidebar-457.AC6.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py`

**Implementation:**

In `_handle_remote_update()` (line 333-358):

The existing code at line 350-351:
```python
state.refresh_annotations(trigger="crdt_broadcast")
```

This already works — Phase 9 Task 1 changes what `refresh_annotations` does (Vue prop push instead of card rebuild). No change needed to broadcast.py itself.

**Critical invariant — do NOT add an `active_tab` guard:** The Source tab `refresh_annotations` call at line 350 fires on **every** broadcast, regardless of which tab is active. This is intentional — it keeps the Vue sidebar's props current even when the panel is hidden (NiceGUI tab panels hide/show, they don't destroy). When the user switches back to the Source tab, cards are already up-to-date. Do NOT add `if state.active_tab == source_tab:` — that would cause stale cards on tab switch.

Organise and Respond already have their own active-tab guards (lines 352, 357) and their own independent refresh callbacks.

**However, verify these callers of `refresh_annotations` also work correctly:**
- `highlights.py:89-90` — after highlight creation
- `highlights.py:321-322` — after tag application
- `tag_management_save.py:93-94` — after tag metadata save
- `tag_quick_create.py:228-229` — after quick tag creation
- `header.py:155-186` — `_wrap_export_stale_clear()` wrapper

All callers use `state.refresh_annotations(trigger=...)` which now pushes Vue props. The `trigger` parameter is used for logging/debugging only. Verify none assume the callback rebuilds NiceGUI elements (e.g., none access `state.annotation_cards` after calling it).

**Epoch contract:** The new `refresh_items()` must increment `state.cards_epoch` and push it to `window.__annotationCardsEpoch` (and `window.__cardEpochs[docId]`) after each items update. This is what E2E tests wait on.

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/broadcast.py`
Expected: No type errors

**Commit:** No commit if no code changes needed. If callers need modification: `refactor(annotation): update broadcast callers for Vue prop push (#457)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update remaining refresh_annotations callers

**Files:**
- Verify: `src/promptgrimoire/pages/annotation/highlights.py` (lines 89-90, 321-322)
- Verify: `src/promptgrimoire/pages/annotation/tag_management_save.py` (line 93-94)
- Verify: `src/promptgrimoire/pages/annotation/tag_quick_create.py` (line 228-229)
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (lines 314-333)

**Implementation:**

Most callers don't need changes — they call `state.refresh_annotations()` which now pushes Vue props.

**Tab bar changes** (`_refresh_source_tab` at line 314-333):
- Keep: `_push_highlights_to_client(state)` (line 316)
- Keep: `state.refresh_annotations(trigger="tab_switch_annotate")` (line 317-318) — now pushes Vue props
- Keep: `_update_highlight_css(state)` (line 319)
- **Remove:** Lines 325-332 — restoring per-document card positioning function (`window._positionCardsMap`). Vue component handles its own positioning.

**Tab state save** (`_save_previous_source_tab` at lines 530-539):
- Remove saves of `annotation_cards` and `card_snapshots` to per-document cache
- Keep saving `expanded_cards`

**PageState cleanup** (`__init__.py`):
- Remove or deprecate `annotation_cards` field (line 240)
- Remove `card_snapshots` field (line 243)
- Remove `detail_built_cards` field (line 251) — Vue tracks this client-side
- Keep `expanded_cards` (line 248) — server-authoritative expand state
- Keep `cards_epoch` (line 254) — E2E sync contract
- Update `invalidate_card_cache()` (line 343) — instead of `annotation_cards = None`, call `refresh_annotations`

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/`
Expected: No type errors in any annotation module

**Commit:** `refactor(annotation): update tab bar and PageState for Vue sidebar (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Delete dead code

**Files:**
- Delete: `src/promptgrimoire/pages/annotation/cards.py` (entire file — 19 dead functions)
- Modify: `src/promptgrimoire/static/annotation-card-sync.js` — remove `setupCardPositioning()` and related code

**Implementation:**

**Delete `cards.py`:** All 19 functions are dead code after Vue replacement. The file has no public API except `_refresh_annotation_cards` which is replaced.

**Modify `annotation-card-sync.js`:** Remove:
- `setupCardPositioning()` function (lines 29-145) — positioning absorbed into Vue component
- `onScroll` handler and scroll event listener
- MutationObserver setup
- Card hover event delegation (lines 127-144) — hover handled in Vue
- `window._positionCardsMap`, `window._positionCards`, `window._activeDocContainerId` globals

Keep:
- `initToolbarObserver()` (lines 147-177) — toolbar height tracking, not card-specific
- Any other non-card utilities

**Verify no imports reference deleted code:**
- Search for `from.*cards import` in `src/promptgrimoire/pages/annotation/`
- Search for `setupCardPositioning` in `src/promptgrimoire/`
- Search for imports in test files: `tests/integration/test_annotation_cards_charac.py` and `tests/unit/test_card_header_html.py` both import from `cards.py` — they will cause import errors after deletion

**Important:** `test_annotation_cards_charac.py` and `test_card_header_html.py` will fail with ImportError after `cards.py` is deleted. This is expected — Phase 10 Task 1 replaces these test files. To avoid broken tests between Phase 9 and Phase 10, either:
- (Preferred) Delete the test files that import from `cards.py` in this task AND create placeholder replacements in Phase 10
- Or accept that `uv run grimoire test all` will have import errors until Phase 10 Task 1 runs

**Verification:**
Run: `uv run grimoire test all` (unit + integration lanes)
Expected: No import errors in production code. Test import errors from `test_annotation_cards_charac.py` and `test_card_header_html.py` are expected (Phase 10 replaces them).

**Commit:** `refactor(annotation): delete cards.py and setupCardPositioning dead code (#457)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Performance and CRDT sync verification

**Verifies:** vue-annotation-sidebar-457.AC5.1, AC5.2, AC6.1, AC6.2

**Files:**
- No new files — verification of existing implementation

**Testing:**

**AC5.1 (server-side blocking <5ms):**
- Add timing instrumentation to `refresh_items()`: `time.monotonic()` around items serialisation + prop push
- With Pabai fixture (190 highlights), verify total time < 5ms
- Log the timing for review

**AC5.2 (prop update within one event loop tick):**
- After CRDT mutation, the `refresh_items()` call and `sidebar.update()` should complete synchronously within the handler (no `await` between mutation and prop push)

**AC6.1 (remote CRDT change updates cards):**
- Verify by running two NiceGUI user fixtures viewing the same workspace
- Client A adds a comment → Client B sees the new comment via prop update

**AC6.2 (epoch increment):**
- After each `refresh_items()`, `window.__annotationCardsEpoch` must increment
- Verify the Vue component's `watch` on items triggers epoch update

**Verification:**
Run: `uv run grimoire test run tests/integration/test_event_loop_render_lag.py` (should pass more easily with Vue)
Expected: Timing assertions pass with improved thresholds

**Commit:** `perf(annotation): verify <5ms server-side blocking with Vue sidebar (#457)`
<!-- END_TASK_5 -->
