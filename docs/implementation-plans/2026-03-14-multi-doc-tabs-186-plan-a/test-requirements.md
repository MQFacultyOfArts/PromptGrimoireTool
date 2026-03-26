# Test Requirements: Multi-Document Tabbed Workspace (Plan A)

**Scope:** Design phases 1--6 (including 3b), mapped to implementation phases 1--7.

**Convention:** Criteria marked "(partial)" are verified in Plan A without the "+" tab, which is deferred to Plan B Phase 8.

---

## Automated Tests

### multi-doc-tabs-186.AC1: Tab Bar Renders Document Tabs

| Criterion | Type | Test File | Verifies | Phase |
|-----------|------|-----------|----------|-------|
| multi-doc-tabs-186.AC1.1 | integration | `tests/integration/test_multi_doc_tabs.py` | Workspace with 3 documents shows "Source 1: Title \| Source 2: Title \| Source 3: Title \| Organise \| Respond" (partial -- "+" tab deferred to Plan B) | 7 |
| multi-doc-tabs-186.AC1.2 | integration | `tests/integration/test_multi_doc_tabs.py` | Single-document workspace shows "Source 1: Title \| Organise \| Respond" (partial -- "+" tab deferred to Plan B) | 7 |
| multi-doc-tabs-186.AC1.3 | integration | `tests/integration/test_multi_doc_tabs.py` | Tabs render in `order_index` sequence from DB; reordered documents change tab positions | 7 |
| multi-doc-tabs-186.AC1.5 | integration | `tests/integration/test_multi_doc_tabs.py` | Workspace with zero documents shows only "Organise \| Respond" (partial -- "+" tab deferred to Plan B) | 7 |
| multi-doc-tabs-186.AC1.6 | integration | `tests/integration/test_multi_doc_tabs.py` | Document with empty/null title shows "Source N" with no trailing colon or empty string | 7 |

### multi-doc-tabs-186.AC2: Per-Document Content and Annotations

| Criterion | Type | Test File | Verifies | Phase |
|-----------|------|-----------|----------|-------|
| multi-doc-tabs-186.AC2.1 | integration | `tests/integration/test_multi_doc_tabs.py` | Each source tab renders its own document HTML content; switching tabs changes visible content | 7 |
| multi-doc-tabs-186.AC2.2 | integration | `tests/integration/test_multi_doc_tabs.py` | Each source tab shows only that document's annotation cards filtered by `document_id` | 7 |
| multi-doc-tabs-186.AC2.3 | integration + e2e | `tests/integration/test_multi_doc_tabs.py`, `tests/e2e/test_multi_doc_tabs.py` | Highlights created on Source 2 do not appear in Source 1's annotation cards | 7 |
| multi-doc-tabs-186.AC2.4 | integration | `tests/integration/test_multi_doc_tabs.py` | Tab content renders on first visit (deferred) and persists in DOM on subsequent visits without re-render | 7 |
| multi-doc-tabs-186.AC2.5 | e2e | `tests/e2e/test_multi_doc_tabs.py` | Switching tabs rapidly (5 switches in 1 second) does not cause duplicate content or orphaned elements | 7 |

### multi-doc-tabs-186.AC10: Feature Flag Removal

| Criterion | Type | Test File | Verifies | Phase |
|-----------|------|-----------|----------|-------|
| multi-doc-tabs-186.AC10.1 | integration | `tests/integration/test_multi_doc_tabs.py` | App starts and renders multi-document workspace without `enable_multi_document` in config; grep for `enable_multi_document` returns zero hits in `src/` | 7 |
| multi-doc-tabs-186.AC10.2 | integration | `tests/integration/test_multi_doc_tabs.py` | Existing single-document workspace renders correctly (Source 1: Title \| Organise \| Respond) after flag removal | 7 |

### multi-doc-tabs-186.AC11: Card Consistency

| Criterion | Type | Test File | Verifies | Phase |
|-----------|------|-----------|----------|-------|
| multi-doc-tabs-186.AC11.1 | integration | `tests/integration/test_organise_charac.py` | Organise cards use `build_expandable_text()` -- 80-char truncate with expand/collapse toggle replaces old 100-char static truncation | 2 |
| multi-doc-tabs-186.AC11.2 | integration | `tests/integration/test_respond_charac.py` | Respond cards use `build_expandable_text()` -- 80-char truncate with expand/collapse toggle replaces old 100-char static truncation | 2 |
| multi-doc-tabs-186.AC11.3 | integration | `tests/integration/test_respond_charac.py` | Respond cards use `anonymise_author()` for highlight and comment authors; raw author string no longer displayed | 2 |
| multi-doc-tabs-186.AC11.4 | integration | `tests/integration/test_organise_charac.py`, `tests/integration/test_respond_charac.py`, `tests/integration/test_annotation_cards_charac.py` | All three tabs use identical expandable text behaviour (80-char threshold, same toggle UX) | 2 |

### multi-doc-tabs-186.AC12: Diff-Based Card Updates

| Criterion | Type | Test File | Verifies | Phase |
|-----------|------|-----------|----------|-------|
| multi-doc-tabs-186.AC12.1 | integration | `tests/integration/test_annotation_cards_charac.py` | Adding a highlight inserts one card without destroying or rebuilding other cards; card count increases by 1; existing expanded cards preserved | 5 |
| multi-doc-tabs-186.AC12.2 | integration | `tests/integration/test_annotation_cards_charac.py` | Removing a highlight deletes one card element without full container rebuild; card count decreases by 1; other cards intact | 5 |
| multi-doc-tabs-186.AC12.3 | integration | `tests/integration/test_annotation_cards_charac.py` | New card inserted at correct position sorted by `start_char` when highlight has a `start_char` between two existing highlights | 5 |
| multi-doc-tabs-186.AC12.4 | integration | `tests/integration/test_annotation_cards_charac.py` | Tag or comment change on a highlight updates only that card; other cards unaffected; expansion state preserved | 5 |
| multi-doc-tabs-186.AC12.5 | integration | `tests/integration/test_annotation_cards_charac.py` | Rapid successive CRDT updates (3 highlights added without awaiting between adds, rapid add+remove, rapid tag changes) produce correct final card state with no duplicates or missing cards | 5 |

---

## Human Verification

### multi-doc-tabs-186.AC1.4: Tab Overflow Scroll Arrows

- **Criterion:** multi-doc-tabs-186.AC1.4
- **Phase:** 7
- **Why not fully automated:** Quasar scroll arrows are a native QTabs CSS/JS behaviour triggered by viewport width. Verifying their visual appearance and interactivity requires a real browser at a constrained viewport width. An E2E test can check for the presence of arrow DOM elements, but cannot reliably verify they are visually correct or usable across browsers.
- **Automated partial coverage:** `tests/e2e/test_multi_doc_tabs.py` creates a workspace with 8+ documents and checks that Quasar scroll arrow elements exist in the DOM when the viewport is narrow.
- **Human verification approach:** Open a workspace with 8+ documents in Chromium and Firefox. Verify that left/right scroll arrows appear when tabs overflow. Click the arrows to confirm they scroll the tab bar. Resize the browser window to confirm arrows appear/disappear at the overflow threshold.

### Visual consistency of expandable text across tabs (AC11.4 supplement)

- **Criterion:** multi-doc-tabs-186.AC11.4 (supplement)
- **Phase:** 2
- **Why not fully automated:** Integration tests verify the 80-char threshold and toggle functionality, but cannot verify visual consistency (font size, spacing, chevron icon alignment) across Annotate, Organise, and Respond tabs.
- **Human verification approach:** Open a workspace with highlights containing >80 character text. Visit all three tabs. Confirm the truncated text, expand chevron, and expanded text look identical across tabs. No visual regression from the old 100-char static truncation in Organise/Respond.

### Deferred rendering performance (AC2.4 supplement)

- **Criterion:** multi-doc-tabs-186.AC2.4 (supplement)
- **Phase:** 7
- **Why not fully automated:** Tests verify that deferred rendering works correctly (content appears on first visit, persists on revisit), but cannot measure whether the all-in-DOM pattern causes performance degradation with multiple large documents.
- **Human verification approach:** Create a workspace with 5 documents including at least one 100+ page document. Visit all tabs. Monitor browser memory usage and tab-switch latency. Confirm no perceptible lag or memory warnings. This is explicitly a measurement gate per the design's "measure after Phase 6" guidance.

---

## ACs Partially Verified in Plan A

The following criteria are verified in Plan A but without the "+" add-document tab, which is added in Plan B Phase 8. Tests assert the tab bar structure without "+" and will be extended in Plan B.

| Criterion | Plan A Verifies | Deferred to Plan B |
|-----------|----------------|-------------------|
| multi-doc-tabs-186.AC1.1 | Tab bar shows source tabs + Organise + Respond | "+" tab between last source tab and Organise |
| multi-doc-tabs-186.AC1.2 | Single-doc shows Source 1 + Organise + Respond | "+" tab between Source 1 and Organise |
| multi-doc-tabs-186.AC1.5 | Zero-doc shows Organise + Respond only | "+" tab before Organise |

---

## ACs NOT Covered by Plan A

The following acceptance criteria from the full design are entirely deferred to Plan B (design phases 7--13). They are listed here for completeness but have no test requirements in Plan A.

| AC Group | Criteria | Plan B Phase |
|----------|----------|-------------|
| AC3: Source Labelling | AC3.1, AC3.2, AC3.3, AC3.4 | Phase 10 |
| AC4: Cross-Tab Locate | AC4.1, AC4.2, AC4.3, AC4.4 | Phase 10 |
| AC5: Add Document | AC5.1--AC5.7 | Phase 8 |
| AC6: Document Rename | AC6.1--AC6.4 | Phase 7 |
| AC7: Workspace Rename | AC7.1--AC7.3 | Phase 9 |
| AC8: Document Management Dialog | AC8.1--AC8.3 | Phase 8 |
| AC9: Delete with CRDT Purge | AC9.1--AC9.6 | Phase 8 |
| AC13: Cross-Client Sync | AC13.1--AC13.4 | Phase 12 |
| AC14: Instructor Controls | AC14.1--AC14.4 | Phase 11 |

**Note:** `remove_highlights_for_document()` (prerequisite for AC9) is implemented in Plan A Phase 5 with unit tests, but the full delete-document-with-CRDT-purge flow is Plan B.

---

## Characterisation Tests (Phase 1)

Phase 1 creates characterisation tests that lock down existing behaviour before refactoring. These tests do not verify any acceptance criteria directly but serve as the regression safety net for Phases 2--7.

| Test File | Type | What It Locks Down |
|-----------|------|--------------------|
| `tests/unit/test_card_functions.py` | unit | Pure card data functions: `_author_initials()`, `group_highlights_by_tag()`, `anonymise_author()` |
| `tests/unit/test_annotation_doc.py` (extended) | unit | CRDT `get_highlights_for_document()` filtering by `document_id`, ordering by `start_char`, cross-document isolation |
| `tests/integration/test_annotation_cards_charac.py` | integration | Annotate tab card rendering: creation, ordering, expandable text, tags, comments, author initials, locate button, `cards_epoch` |
| `tests/integration/test_organise_charac.py` | integration | Organise tab rendering: cards, snippet truncation (100-char pre-fix, 80-char post-fix), locate button, author display, comments, tag grouping |
| `tests/integration/test_respond_charac.py` | integration | Respond tab rendering: reference cards, snippet truncation, locate button, comments, raw author display (pre-fix), anonymised author (post-fix) |
| `tests/e2e/test_organise_respond_flow.py` | e2e | Cross-tab flow: highlight creation visible in Organise and Respond, comment propagation, expandable text toggle |

---

## Refactoring Phases (No Direct AC Coverage)

Phases 3, 4, and 6 are pure refactoring. They implement no new acceptance criteria. All existing tests (characterisation + any added in prior phases) serve as the regression safety net.

| Phase | What Changes | Regression Safety |
|-------|-------------|-------------------|
| Phase 3: Extract from cards.py | `card_shared.py` created; `cards.py` and `organise.py` import from it | All Phase 1--2 tests + complexipy |
| Phase 4: Extract from respond.py | `respond.py` imports from `card_shared.py`; `anonymise_display_author()` consolidated | All Phase 1--2 tests + complexipy |
| Phase 6: Extract tab management | `tab_bar.py` and `tab_state.py` created; `workspace.py` reduced | All prior tests + E2E card tests + complexipy |
