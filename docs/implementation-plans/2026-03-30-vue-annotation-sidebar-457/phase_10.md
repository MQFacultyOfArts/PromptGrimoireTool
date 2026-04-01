# Vue Annotation Sidebar Implementation Plan — Phase 10

**Goal:** All existing tests pass or are adapted to equivalent assertions on the Vue component. No test deletions without equivalent replacement.

**Architecture:** NiceGUI element inspection tests (28 charac + lazy detail) replaced with serialisation unit tests + prop/event integration tests. E2E tests unchanged (DOM contract preserved). Performance test threshold updated after measurement.

**Tech Stack:** pytest, NiceGUI user simulation, Playwright, vitest

**Scope:** Phase 10 of 10 from original design

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

This phase implements and tests:

### vue-annotation-sidebar-457.AC7: Test Coverage
- **vue-annotation-sidebar-457.AC7.1 Success:** All 8 test lanes pass with no test deletions without equivalent replacement

---

## Reference Files

**Read before starting:**
- `tests/integration/test_annotation_cards_charac.py` — 28 tests, NiceGUI element inspection (to be replaced)
- `tests/integration/test_lazy_card_detail.py` — lazy detail tests, element inspection (to be replaced)
- `tests/e2e/test_card_layout.py` — 8 Playwright tests (should work unchanged)
- `tests/integration/test_event_loop_render_lag.py` — performance test with xfail (threshold update)
- `tests/unit/test_card_header_html.py` — HTML generation tests (to be replaced with serialisation tests)
- `tests/unit/test_items_serialise.py` — from Phase 4 (already covers some serialisation)
- `tests/integration/test_vue_sidebar_spike.py` — from Phase 3
- `tests/integration/test_vue_sidebar_dom_contract.py` — from Phase 4
- `tests/integration/test_vue_sidebar_expand.py` — from Phase 6
- `tests/integration/test_vue_sidebar_mutations.py` — from Phase 7
- `tests/integration/test_vue_sidebar_interactions.py` — from Phase 8
- `docs/testing.md` — testing guidelines
- CLAUDE.md — test lane model, data-testid conventions

---

<!-- START_TASK_1 -->
### Task 1: Replace test_annotation_cards_charac.py

**Verifies:** vue-annotation-sidebar-457.AC7.1

**Files:**
- Delete: `tests/integration/test_annotation_cards_charac.py`
- Create: `tests/integration/test_vue_sidebar_charac.py`

**Implementation:**

The existing 28 tests fall into three categories. Each must have an equivalent replacement:

**Card rendering tests (11 tests):**
Current: inspect NiceGUI element trees (`card.descendants()`, `card.props`)
Replacement: verify `serialise_items()` output shape and content, then verify Vue sidebar receives correct `items` prop via NiceGUI integration test.

Equivalent test patterns:
- "Cards render in start_char order" → assert `serialise_items()` returns items sorted by `start_char`
- "Comment badge shows count" → assert item dict has `comments` list with correct length
- "Tag colour on card" → assert item dict has correct `color` from tag lookup
- "Initials computed" → assert item dict has correct `initials` from `author_initials()`
- "Delete button shown for own content" → assert item dict has `can_delete: True` when user_id matches

**Diff/snapshot tests (14 tests):**
Current: test `_snapshot_highlight()`, `_diff_annotation_cards()`, `_compute_card_diff()`
Replacement: test `serialise_items()` produces correct output when CRDT state changes. The diff algorithm is eliminated — Vue handles DOM diffing. Equivalent tests:
- "Adding highlight produces new item in serialised list"
- "Removing highlight removes item from serialised list"
- "Changing tag produces updated item with new tag_display and color"
- "Adding comment increments comment count in item"
- "Rapid mutations produce consistent final state"

**Permission and edge case tests (3 tests):**
Current: test permission gating and edge cases on rendered cards
Replacement: verify `serialise_items()` correctly computes `can_delete`, `can_annotate` flag gating, and edge cases (empty highlights, missing tags). These overlap with Phase 7 integration tests (`test_vue_sidebar_mutations.py` covers AC4.1-AC4.3) — verify coverage and add any missing cases.

**Note:** Many of the current tests are implicitly testing the diff algorithm's correctness. With Vue, there's no diff algorithm — `serialise_items()` always produces a complete list. The equivalent tests verify that the serialisation is correct for each state change.

**Audit all 28 tests individually:** Read the full file before writing replacements. Map each test function to its replacement location (this file, Phase 4 unit tests, or Phase 7 integration tests). No test may be deleted without a documented equivalent.

**Mark:** `@pytest.mark.nicegui_ui` for integration tests that create an AnnotationSidebar.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_charac.py`
Expected: All replacement tests pass

**Commit:** `test(annotation): replace charac tests with Vue sidebar equivalents (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace test_lazy_card_detail.py

**Verifies:** vue-annotation-sidebar-457.AC7.1

**Files:**
- Delete: `tests/integration/test_lazy_card_detail.py`
- Verify: `tests/integration/test_vue_sidebar_expand.py` (from Phase 6) covers the same ACs

**Implementation:**

The existing lazy detail tests verify AC1.1-AC1.3 plus a diff/rebuild invariant. Phase 6 already created `test_vue_sidebar_expand.py` which covers these ACs. Verify coverage:

- **AC1.1 (collapsed cards have no detail DOM):** Covered in Phase 6 test — `v-if="detailBuiltIds.has(item.id)"` prevents detail creation
- **AC1.2 (detail built on first expand):** Covered in Phase 6 test — expand click adds to `detailBuiltIds`
- **AC1.3 (pre-expanded cards build detail):** Covered in Phase 6 test — `expanded_ids` prop
- **Diff/rebuild invariant:** With Vue, "rebuild" is a full items prop push — detail state survives because `detailBuiltIds` is independent of items prop. Not a numbered AC — it's a structural guarantee of the Vue reactive model.

If Phase 6's tests don't cover all cases, add missing cases to `test_vue_sidebar_expand.py` rather than creating a new file.

**Key change:** The current tests inspect `state.detail_built_cards` (Python set on PageState). With Vue, `detailBuiltIds` lives client-side. Integration tests should verify:
- `expanded_ids` prop is pushed correctly
- `toggle_expand` events produce correct state updates
- The Vue component's DOM shows/hides detail sections (via NiceGUI user simulation HTML output)

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_expand.py`
Expected: All AC1.1-AC1.3 cases plus diff/rebuild invariant covered and passing

**Commit:** `test(annotation): replace lazy detail tests, verify Phase 6 test coverage (#457)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify E2E test_card_layout.py passes unchanged

**Verifies:** vue-annotation-sidebar-457.AC7.1

**Files:**
- Verify: `tests/e2e/test_card_layout.py` — run without modification

**Implementation:**

The 8 E2E tests use Playwright locators on `data-testid` attributes. The Vue sidebar preserves the exact DOM contract. Run the tests and verify they pass.

**Expected results per test:**
1. `test_initial_positioning_non_zero_no_overlap` — passes (cards positioned absolutely with `style.top`)
2. `test_scroll_recovery_no_solitaire_collapse` — passes (scroll repositioning via rAF)
3. `test_race_condition_highlights_ready` — passes (Vue watches items + highlights-ready)
4. `test_default_collapsed_with_compact_header` — passes (default collapsed, compact header visible)
5. `test_expand_collapse_toggle` — passes (chevron click toggles detail visibility)
6. `test_author_initials_in_compact_header` — passes (initials from serialised data)
7. `test_push_down_on_expand` — passes (positionCards fires after expand)
8. `test_viewer_sees_no_tag_select_or_comment_input` — passes (permissions gating)

**If any test fails:** Investigate whether the DOM contract was broken. Common issues:
- Missing `data-testid` attribute on Vue template element
- Different CSS class or style (e.g. `position: absolute` not set)
- Epoch timing difference (`window.__annotationCardsEpoch` not incrementing correctly)
- Missing `window._highlightsReady` flag

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: All 8 tests pass

**Commit:** No commit if tests pass unchanged. If adaptation needed: `test(annotation): adapt card layout E2E tests for Vue sidebar (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update test_event_loop_render_lag.py thresholds

**Verifies:** vue-annotation-sidebar-457.AC7.1

**Files:**
- Modify: `tests/integration/test_event_loop_render_lag.py`

**Implementation:**

**Step 1: Measure Vue baseline**
Run the performance test and capture actual timing:
- With Vue sidebar, server-side cost is `serialise_items()` + prop push (no NiceGUI element creation)
- Expected: < 5ms total for 190 highlights (vs current ~100ms)
- The structlog event to capture may need updating (currently `card_diff_add` — may change to a new event name for prop serialisation)

**Step 2: Update thresholds**
- Set per-card threshold to 2× measured value (safety margin)
- Remove `@pytest.mark.xfail` marker
- Update the structlog event capture if the event name changed

**Step 3: Update event instrumentation**
If `refresh_items()` doesn't emit the same `card_diff_add` structlog event:
- Add a structlog event to `refresh_items()`: `logger.info("sidebar_items_push", elapsed_ms=elapsed, item_count=len(items))`
- Update the test to capture this event instead

**Verification:**
Run: `uv run grimoire test run tests/integration/test_event_loop_render_lag.py`
Expected: Test passes (no xfail), timing well within threshold

**Commit:** `perf(annotation): update render lag test thresholds for Vue sidebar (#457)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Replace test_card_header_html.py and run full test suite

**Verifies:** vue-annotation-sidebar-457.AC7.1

**Files:**
- Delete: `tests/unit/test_card_header_html.py` (tests dead `_render_compact_header_html()` function)
- Verify: `tests/unit/test_items_serialise.py` (from Phase 4) covers equivalent assertions

**Implementation:**

`test_card_header_html.py` tests:
- Colour dot present → covered by `test_items_serialise.py` (item has `color` field)
- Tag display escaped → covered by serialisation (Vue handles rendering/escaping)
- Initials escaped → covered by serialisation
- Comment badge conditional → covered by serialisation (comments list length)
- Para ref conditional → covered by serialisation (para_ref field)

If any escaping tests are missing from `test_items_serialise.py`, add them there. The Vue component handles HTML escaping via Vue's built-in template escaping (`{{ }}` auto-escapes).

**Final verification — run all 8 lanes:**
Run: `uv run grimoire e2e all`
Expected: All 8 lanes pass: js, bats, unit, integration, playwright, nicegui, smoke, blns+extra

**AC7.1 checklist:**
- [ ] Unit tests pass (including new serialisation tests)
- [ ] Integration tests pass (Vue sidebar NiceGUI tests)
- [ ] E2E tests pass (card layout, card interactions)
- [ ] NiceGUI lane passes (Vue sidebar nicegui_ui tests)
- [ ] Performance test passes (updated thresholds)
- [ ] No test file deleted without equivalent replacement

**Commit:** `test(annotation): replace header HTML tests, verify all 8 lanes pass (#457)`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Cross-tab E2E test with Pabai fixture (all three tabs + performance)

**Verifies:** vue-annotation-sidebar-457.AC5.1, AC5.2, AC6.1, AC7.1

**Files:**
- Create: `tests/e2e/test_vue_sidebar_cross_tab.py`

**Testing:**
Playwright E2E test using the deduplicated Pabai fixture (190 highlights, realistic production data). This test validates that the Vue sidebar works correctly across all three tabs and demonstrates performance under realistic load.

**Test scenario:**

1. **Source tab initial render (performance):**
   - Load workspace with Pabai fixture (190 highlights, multiple tags, comments)
   - Wait for `window.__annotationCardsEpoch` to increment (cards rendered)
   - **Timing assertion:** Capture `performance.now()` before and after epoch change. Server-side is <5ms but client render may take longer — assert total (server + client) is < 500ms for 190 cards
   - Verify: 190 cards with `data-testid="annotation-card"` present
   - Verify: cards positioned absolutely (non-zero `style.top`)
   - Verify: no overlapping cards (collision avoidance working)

2. **Source tab interaction:**
   - Expand a card → detail section visible
   - Verify tag dropdown, comment list, para_ref visible in detail
   - Collapse → detail hidden, retained
   - Hover a card → verify no JS errors (CSS Highlight API visual verification is human UAT)

3. **Switch to Organise tab:**
   - Click Organise tab
   - Verify: tag columns rendered with highlight cards grouped correctly
   - Verify: card count across all columns equals total highlights (190)
   - Verify: "Locate" button on an Organise card works (switches back to Source tab, scrolls to highlight)

4. **Switch to Respond tab:**
   - Click Respond tab
   - Verify: reference panel shows highlights grouped by tag
   - Verify: Milkdown editor present and functional
   - Verify: "Locate" button on a reference card switches to Source tab

5. **Return to Source tab (cross-tab state preservation):**
   - Switch back to Source tab
   - Verify: all 190 cards still present (no cards lost)
   - Verify: previously expanded card's expansion state preserved
   - Verify: card positioning correct (cards didn't stack at top)
   - **Timing assertion:** Tab switch render time < 200ms (prop push, not full rebuild)

6. **Cross-tab CRDT sync (two-client):**
   - If test infrastructure supports two contexts (`two_annotation_contexts` fixture):
   - Client A on Source tab adds a comment
   - Client B on Organise tab → verify Organise rebuilds with updated comment count
   - Client B switches to Source tab → verify new comment visible in card
   - **Timing assertion:** Cross-client prop delivery < 2s

**Performance thresholds:**
- Initial 190-card render: < 500ms total (server + client)
- Tab switch (Source → Organise → Source): < 200ms for Source re-render
- Cross-client prop delivery: < 2s
- No card overlap at any point (collision avoidance)

**Marker:** `@pytest.mark.e2e` (Playwright lane). Consider `@pytest.mark.noci` if the test is too heavy for default CI — include in `e2e slow` and nightly.

**Dependencies:**
- `tests/fixtures/pabai_workspace_scrubbed.json` (deduplicated in Phase 6 Task 1)
- `tests/e2e/db_fixtures.py` — `_create_workspace_via_db()` to load fixture

**Verification:**
Run: `uv run grimoire e2e run -k test_vue_sidebar_cross_tab`
Expected: All assertions pass, timing within thresholds

**Commit:** `test(annotation): cross-tab E2E test with Pabai fixture, all 3 tabs + performance (#457)`
<!-- END_TASK_6 -->
