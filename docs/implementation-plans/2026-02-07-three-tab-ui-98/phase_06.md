# Three-Tab Annotation Interface — Phase 6: Warp Navigation and Cross-Tab Reactivity

**Goal:** Wire up warp-to-Tab-1 from Tabs 2 and 3, and ensure all tabs react to changes from other tabs.

**Architecture:** Add a "locate" button to highlight cards in Tab 2 (`annotation_organise.py`) and Tab 3 (`annotation_respond.py`) that programmatically switches to Tab 1 via `tab_panels.set_value("Annotate")` and scrolls to the highlight's position using the existing `scrollIntoView` pattern (`annotation.py:816`). Cross-tab reactivity is wired by extending the broadcast callback in `_setup_client_sync()` to call refresh functions for Tab 2 columns and Tab 3 reference panel whenever CRDT state changes. The `PageState` dataclass gains new callable fields for these refresh hooks.

**Tech Stack:** NiceGUI `ui.tab_panels.set_value()`, JavaScript `scrollIntoView()`, existing CRDT broadcast callback pattern

**Scope:** 7 phases from original design (phase 6 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC5: Cross-tab navigation and reactivity
- **three-tab-ui.AC5.1 Success:** "Locate" button on a highlight card in Tab 2 or Tab 3 switches to Tab 1 and scrolls the viewport to the highlighted phrase in the document
- **three-tab-ui.AC5.2 Success:** Creating a highlight in Tab 1 appears in Tab 2 columns and Tab 3 reference panel without manual refresh
- **three-tab-ui.AC5.3 Success:** Changing a highlight's tag via Tab 2 drag updates the tag colour in Tab 1's sidebar card
- **three-tab-ui.AC5.4 Failure:** Warp-to-Tab-1 does not affect other users' active tab
- **three-tab-ui.AC5.5 Success:** After warping to Tab 1 from a highlight card, user can return to their previous tab and scroll position

---

## Codebase Verification Findings

- ✓ NiceGUI `ui.tab_panels()` supports `set_value()` — documented in `docs/nicegui/ui-patterns.md:411-415`; per-client, does not affect other users
- ✓ Existing scroll-to-highlight code at `annotation.py:816` — `scrollIntoView({behavior:'smooth',block:'center'})` on char span elements
- ✓ Char spans: `data-char-index` attributes injected client-side at `annotation.py:1212-1266`; query via `document.querySelector('[data-char-index="N"]')`
- ✓ Highlight card data: `_build_annotation_card` at `annotation.py:718-850` — has `highlight_id`, `start_char`, `end_char`, `tag`, `text`, `author`
- ✓ Card stores position data as HTML attributes at `annotation.py:750-758` — `data-start-char`, `data-end-char`
- ✓ Broadcast pattern at `annotation.py:1464-1553` — `_setup_client_sync()` creates `broadcast_update()` callable, iterates `_connected_clients` dict, calls per-client `cstate.callback()`
- ✓ `PageState` dataclass at `annotation.py:296-326` — has `refresh_annotations`, `broadcast_update` callables; extensible for new tab refresh callbacks
- ✓ Client callback at `annotation.py:1519-1525` — `handle_update_from_other()` calls `_update_highlight_css()`, `_update_cursor_css()`, and `state.refresh_annotations()`
- ✓ `PageState` already has `tab_panels` field from Phase 1 Task 1 — Phase 6 adds `refresh_organise_tab` and `refresh_respond_tab` fields
- ✗ No "locate" buttons on cards yet — Phase 6 adds them to Tab 2 and Tab 3 cards

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Add warp navigation infrastructure to PageState and annotation.py

**Verifies:** three-tab-ui.AC5.1 (partially — provides the infrastructure), three-tab-ui.AC5.4, three-tab-ui.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (`PageState` dataclass, `_setup_client_sync`)

**Implementation:**

1. Extend `PageState` with new fields (note: `tab_panels` was already added in Phase 1 Task 1):
   - `refresh_organise_tab: Any | None = None` — callable to refresh Tab 2 columns from CRDT state
   - `refresh_respond_tab: Any | None = None` — callable to refresh Tab 3 reference panel from CRDT state

2. The `tab_panels` reference on `PageState` was already stored in Phase 1 Task 1 when the tab container was created. No additional work needed here — Phase 6 uses the existing `state.tab_panels` reference.

3. Create a helper function `_warp_to_highlight(state: PageState, start_char: int) -> None` that:
   - Calls `state.tab_panels.set_value("Annotate")` to switch the current client's tab to Tab 1
   - Uses `ui.run_javascript()` to execute the existing scroll pattern:
     ```javascript
     const el = document.querySelector('[data-char-index="<start_char>"]');
     if (el) el.scrollIntoView({behavior:'smooth',block:'center'});
     ```
   - This is a per-client operation — `set_value()` only affects the calling client's tab state, not other users (AC5.4)

4. Extend the broadcast callback in `_setup_client_sync()` at `handle_update_from_other()`:
   - After calling `state.refresh_annotations()` (Tab 1), also call:
     - `state.refresh_organise_tab()` if not None (Tab 2 — re-renders columns from CRDT)
     - `state.refresh_respond_tab()` if not None (Tab 3 — re-renders reference panel from CRDT)
   - This ensures highlight changes from any tab propagate to all other tabs

**Key design decision:** The warp function is per-client — `set_value()` only affects the NiceGUI client that called it. Other connected clients stay on their current tab (AC5.4). After warping, the user can click any tab header to return to their previous tab; NiceGUI preserves tab panel DOM state so scroll position within Tab 2/Tab 3 is preserved (AC5.5).

**Testing:**
Tests in Task 4 verify AC5.1, AC5.4, AC5.5.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: add warp navigation infrastructure and cross-tab broadcast callbacks`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add "locate" button to Tab 2 and Tab 3 highlight cards

**Verifies:** three-tab-ui.AC5.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation_organise.py` (Tab 2 cards)
- Modify: `src/promptgrimoire/pages/annotation_respond.py` (Tab 3 reference panel cards)

**Implementation:**

1. In `annotation_organise.py`, update `render_organise_tab()` to add a "locate" icon button to each highlight card:
   - Add a small button (e.g., `ui.button(icon="location_on")` or `ui.icon("my_location")`) to the card footer/header
   - The button's click handler calls `_warp_to_highlight(state, highlight["start_char"])` imported from `annotation.py`
   - The button should be styled as a subtle icon button (not a full-size button) to avoid visual clutter in the column layout

2. In `annotation_respond.py`, update `render_respond_tab()` to add the same "locate" button to each reference panel highlight card:
   - Same pattern as Tab 2 — small icon button, calls `_warp_to_highlight()` on click
   - Reference panel cards are read-only, so the locate button is the primary interaction point

3. Both modules need access to `PageState` (for the `_warp_to_highlight` call) and highlight `start_char` data. Both already receive `state: PageState` as a parameter and build cards from CRDT highlight data that includes `start_char`.

**Testing:**
Tests in Task 4 verify AC5.1.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation_organise.py src/promptgrimoire/pages/annotation_respond.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: add locate buttons to Tab 2 and Tab 3 highlight cards`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire cross-tab refresh callbacks

**Verifies:** three-tab-ui.AC5.2, three-tab-ui.AC5.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation_organise.py` (register refresh callback)
- Modify: `src/promptgrimoire/pages/annotation_respond.py` (register refresh callback)
- Modify: `src/promptgrimoire/pages/annotation.py` (connect callbacks in `_on_tab_change`)

**Implementation:**

1. In `annotation_organise.py`, `render_organise_tab()` returns or registers a `refresh_organise()` callable that:
   - Clears the Tab 2 column container
   - Re-reads highlights from `crdt_doc.get_all_highlights()` grouped by tag
   - Re-reads tag order from `crdt_doc.get_tag_order(tag_name)` per tag
   - Rebuilds the tag columns with current data
   - This is called whenever a CRDT broadcast occurs while the client has Tab 2 initialised

2. In `annotation_respond.py`, `render_respond_tab()` returns or registers a `refresh_respond_reference()` callable that:
   - Clears the right-side reference panel
   - Re-reads highlights from `crdt_doc.get_all_highlights()` grouped by tag
   - Rebuilds the reference panel cards
   - Does NOT re-initialise the Milkdown editor (it has its own Yjs sync channel)

3. In `annotation.py`, in the `_on_tab_change` handler:
   - When Tab 2 is first rendered: store the refresh callable on `state.refresh_organise_tab`
   - When Tab 3 is first rendered: store the refresh callable on `state.refresh_respond_tab`
   - These are then called by the broadcast callback registered in Task 1

4. Cross-tab reactivity flows:
   - **Tab 1 → Tab 2 (AC5.2):** Creating a highlight in Tab 1 triggers `broadcast_update()` → other clients' `handle_update_from_other()` calls `state.refresh_organise_tab()` → Tab 2 columns rebuild with new highlight in correct column
   - **Tab 1 → Tab 3 (AC5.2):** Same flow, calls `state.refresh_respond_tab()` → Tab 3 reference panel rebuilds with new highlight
   - **Tab 2 → Tab 1 (AC5.3):** Dragging a card to change its tag triggers `broadcast_update()` → other clients' `handle_update_from_other()` calls `state.refresh_annotations()` → Tab 1 sidebar card updates tag colour/label (already handled by existing broadcast, but verify it works)

**Testing:**
Tests in Task 4 verify AC5.2, AC5.3.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation_organise.py src/promptgrimoire/pages/annotation_respond.py src/promptgrimoire/pages/annotation.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: wire cross-tab refresh callbacks for highlight reactivity`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E tests for warp navigation and cross-tab reactivity

**Verifies:** three-tab-ui.AC5.1, three-tab-ui.AC5.2, three-tab-ui.AC5.3, three-tab-ui.AC5.4, three-tab-ui.AC5.5

**Files:**
- Create or modify: `tests/e2e/test_annotation_tabs.py` (add warp navigation and cross-tab tests)

**Implementation:**

No code changes — this task adds E2E tests verifying warp navigation and cross-tab reactivity.

**Testing:**
Tests must verify each AC listed above:
- three-tab-ui.AC5.1: "Locate" button switches to Tab 1 and scrolls to highlight
- three-tab-ui.AC5.2: Creating a highlight in Tab 1 appears in Tab 2 and Tab 3
- three-tab-ui.AC5.3: Tag change via Tab 2 drag updates Tab 1 sidebar card
- three-tab-ui.AC5.4: Warp does not affect other users' active tab
- three-tab-ui.AC5.5: After warping, user can return to previous tab

Write E2E tests in `tests/e2e/test_annotation_tabs.py`:

- `test_locate_button_warps_to_tab1_and_scrolls` — Create a highlight, switch to Organise tab, click the "locate" button on the highlight card. Verify: the active tab changes to "Annotate", and the highlight's position is visible in the viewport (the char span with `data-char-index` matching the highlight's `start_char` is in the visible area). Use Playwright's `is_visible()` or bounding box check.

- `test_locate_button_from_tab3_warps_to_tab1` — Create a highlight, switch to Respond tab, click locate on the reference panel card. Verify same as above — tab switches to Annotate and highlight is scrolled into view.

- `test_new_highlight_appears_in_tab2` — Open two browser contexts. Context 1 stays on Tab 2 (Organise). Context 2 creates a highlight on Tab 1 (Annotate). Verify: Context 1 sees the new highlight appear in the correct tag column on Tab 2 without manual refresh (AC5.2).

- `test_new_highlight_appears_in_tab3_reference` — Same setup but Context 1 is on Tab 3 (Respond). Verify the reference panel updates with the new highlight.

- `test_tab2_tag_change_updates_tab1_sidebar` — Open two browser contexts. Context 1 on Tab 1, Context 2 on Tab 2. Context 2 drags a highlight card from tag A column to tag B column. Verify Context 1's sidebar annotation card shows tag B (colour and label updated) (AC5.3).

- `test_warp_does_not_affect_other_user` — Open two browser contexts. Context 1 on Tab 2, Context 2 on Tab 2. Context 1 clicks "locate" on a card. Verify: Context 1 switches to Annotate tab. Context 2 remains on Organise tab (AC5.4).

- `test_return_to_previous_tab_after_warp` — Create a highlight, switch to Organise tab, scroll down in the Tab 2 panel. Click "locate" on a card (warps to Tab 1). Click the "Organise" tab header to return. Verify: Tab 2 content is still rendered (not re-initialised) and the user is back in Tab 2 (AC5.5).

Follow existing E2E patterns from `tests/e2e/test_annotation_basics.py` — use `authenticated_page` fixture, `setup_workspace_with_content` helper.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_locate or test_warp or test_new_highlight or test_tab2_tag`
Expected: All tests pass

**Commit:** `test: add E2E tests for warp navigation and cross-tab reactivity`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run E2E tests: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_locate or test_warp or test_new_highlight or test_tab2_tag"`
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Navigate to `/annotation`, create a workspace, add content
4. [ ] Create several highlights with different tags
5. [ ] Switch to "Organise" tab — verify highlight cards have a "locate" icon button
6. [ ] Click the "locate" button on a highlight card
7. [ ] Verify: Tab switches to "Annotate" and the document scrolls to show the highlighted text
8. [ ] Switch to "Respond" tab — verify reference panel cards also have "locate" buttons
9. [ ] Click "locate" on a reference panel card — verify same warp + scroll behaviour
10. [ ] Open a second browser tab to the same workspace, stay on Organise tab
11. [ ] In the first browser tab (on Annotate), create a new highlight
12. [ ] Verify: Second browser's Organise tab shows the new highlight in the correct column (no refresh needed)
13. [ ] Switch second browser to Respond tab — verify reference panel also shows the new highlight
14. [ ] In Organise tab, drag a highlight card to a different tag column
15. [ ] Verify: In the other browser (on Annotate tab), the sidebar card for that highlight now shows the new tag colour
16. [ ] Click "locate" in one browser — verify the OTHER browser's tab does NOT change (per-client only)
17. [ ] Warp to Tab 1 from Organise, then click Organise tab header — verify Tab 2 is still there (not re-initialised)

## Evidence Required
- [ ] Test output showing green for warp navigation and cross-tab E2E tests
- [ ] Screenshot showing "locate" button on a Tab 2 highlight card
- [ ] Screenshot showing Tab 1 after warp — scrolled to the correct highlight
- [ ] Screenshot or confirmation of cross-tab reactivity (highlight appears in Tab 2 after creation in Tab 1)
