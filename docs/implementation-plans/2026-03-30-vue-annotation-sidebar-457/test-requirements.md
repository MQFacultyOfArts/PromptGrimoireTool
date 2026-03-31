# Test Requirements: Vue Annotation Sidebar (#457)

**Generated:** 2026-03-31 (updated for 10-phase plan)
**Source:** Implementation phases 1-10 from `docs/implementation-plans/2026-03-30-vue-annotation-sidebar-457/`
**Criteria count:** 5 Spike GO criteria + 6 AC8/AC9 criteria + 12 AC1 criteria + 2 AC2 + 2 AC3 + 4 AC4 + 2 AC5 + 2 AC6 + 1 AC7 = 36 numbered criteria, plus 1 cross-tab integration scenario (not an AC)

## Summary Table

| Criterion ID | Description | Test Type | Test File | Phase |
|---|---|---|---|---|
| AC8.1 | Respond panel renders 190 highlights <50ms blocking | unit + e2e | `tests/unit/test_respond_reference_card_html.py`, `tests/e2e/test_organise_respond_flow.py`, `tests/e2e/test_law_student.py` | 1 |
| AC8.2 | Respond search/filter works | e2e | `tests/e2e/test_organise_respond_flow.py`, `tests/e2e/test_law_student.py` | 1 |
| AC8.3 | Respond locate button switches tab + scrolls | unit + e2e | `tests/unit/test_respond_reference_card_html.py` (onclick assert), `tests/e2e/test_organise_respond_flow.py` | 1 |
| AC9.1 | Organise renders 190 highlights <50ms blocking | unit + e2e | `tests/unit/test_organise_card_html.py`, `tests/e2e/test_organise_perf.py`, `tests/e2e/test_annotation_drag.py` | 2 |
| AC9.2 | SortableJS drag-and-drop works | e2e | `tests/e2e/test_annotation_drag.py`, `tests/e2e/test_organise_respond_flow.py` | 2 |
| AC9.3 | Organise locate button switches tab + scrolls | unit + e2e | `tests/unit/test_organise_card_html.py` (onclick assert), `tests/e2e/test_organise_respond_flow.py` | 2 |
| Spike.GO1 | Component registration works | integration | `tests/integration/test_vue_sidebar_spike.py` | 3 |
| Spike.GO2 | Python props arrive in Vue | integration | `tests/integration/test_vue_sidebar_spike.py` | 3 |
| Spike.GO3 | Vue emits reach Python | integration | `tests/integration/test_vue_sidebar_spike.py` | 3 |
| Spike.GO4 | Prop updates re-render correctly | integration | `tests/integration/test_vue_sidebar_spike.py` | 3 |
| Spike.GO5 | DOM exposes data-testid/data-* attributes | integration | `tests/integration/test_vue_sidebar_spike.py` | 3 |
| AC2.1 | Cards have data-testid, data-highlight-id, data-start-char, data-end-char | integration + unit | `tests/integration/test_vue_sidebar_dom_contract.py`, `tests/unit/test_items_serialise.py` | 4 |
| AC2.2 | Detail section has data-testid for card-detail, tag-select, comment-input, post-comment-btn, comment-count | integration | `tests/integration/test_vue_sidebar_dom_contract.py` | 4 |
| AC3.1 | Cards positioned absolutely aligned to highlight vertical position | e2e | `tests/e2e/test_card_layout.py` | 5 |
| AC3.2 | Scroll, expand/collapse, and item changes trigger repositioning | e2e | `tests/e2e/test_card_layout.py` | 5 |
| AC1.1 | Clicking header row expands card | integration | `tests/integration/test_vue_sidebar_expand.py` | 6 |
| AC1.2 | Clicking expanded header collapses card | integration | `tests/integration/test_vue_sidebar_expand.py` | 6 |
| AC1.3 | Pre-expanded cards render detail on load | integration | `tests/integration/test_vue_sidebar_expand.py` | 6 |
| AC1.4 | Tag dropdown change updates colour and CRDT | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC1.5 | Comment submit adds comment, clears input, increments badge | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC1.6 | Comment delete removes comment, decrements badge | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC1.7 | Highlight delete removes card from sidebar and CRDT | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC1.8 | Para_ref click enters edit mode, blur/enter saves to CRDT | integration | `tests/integration/test_vue_sidebar_interactions.py` | 8 |
| AC1.9 | Locate button scrolls document to highlight with throb | integration + human | `tests/integration/test_vue_sidebar_interactions.py` | 8 |
| AC1.10 | Hover over card highlights text range in document | integration + human | `tests/integration/test_vue_sidebar_interactions.py` | 8 |
| AC1.11 | Empty/whitespace comment rejected | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC1.12 | Tag dropdown shows recovery entry for deleted tag | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC4.1 | Users with can_annotate see tag dropdown, comment input, post button | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC4.2 | Viewers without can_annotate do not see edit controls | integration + e2e | `tests/integration/test_vue_sidebar_mutations.py`, `tests/e2e/test_card_layout.py` | 7 |
| AC4.3 | Delete buttons shown only for content owner or privileged user | integration | `tests/integration/test_vue_sidebar_mutations.py` | 7 |
| AC4.4 | Unauthorized mutation event rejected server-side (no CRDT change) | integration | `tests/integration/test_vue_sidebar_mutations.py` (negative test: emit `delete_highlight` as viewer, assert CRDT unchanged) | 7 |
| AC5.1 | Initial render <5ms server-side blocking | integration | `tests/integration/test_event_loop_render_lag.py` | 9 |
| AC5.2 | CRDT mutation prop update within one event loop tick | code review + integration (proxy) | Code review verifies no `await` in mutation-to-push path; `tests/integration/test_event_loop_render_lag.py` timing is a proxy | 9 |
| AC6.1 | Remote CRDT change updates cards via prop push | integration | `tests/integration/test_vue_sidebar_broadcast.py` | 9 |
| AC6.2 | cards_epoch increments after each items prop update | integration | `tests/integration/test_vue_sidebar_broadcast.py` (dedicated epoch assertion); `tests/e2e/test_card_layout.py` provides implicit coverage via epoch wait but does not assert epoch increment directly | 9 |
| Cross-tab | All 3 tabs work with 190 highlights, performance under load | e2e | `tests/e2e/test_vue_sidebar_cross_tab.py` | 10 |
| AC7.1 | All 8 test lanes pass with no test deletions without replacement | all lanes | Full suite: `uv run grimoire e2e all` | 10 |

## Human Verification Required

Two criteria need human verification (CSS Highlight API not DOM-observable):

| Criterion | Reason | Approach |
|---|---|---|
| AC1.9 (Locate scroll + throb) | Scroll-to-offset depends on browser layout geometry; throb animation is visual/temporal | Manual: click locate on off-screen highlight, confirm scroll and animation in Chromium + Firefox |
| AC1.10 (Hover highlights text) | CSS Highlight API `::highlight()` pseudo-element is not DOM-observable | Manual: hover card, confirm text range highlight appears in Chromium + Firefox |

Both have automated coverage of the event plumbing. Human verification covers the visual rendering layer.

## Test File Inventory

| File | Type | Phase | Lane |
|---|---|---|---|
| `tests/unit/test_respond_reference_card_html.py` | New | 1 | unit |
| `tests/unit/test_organise_card_html.py` | New | 2 | unit |
| `tests/integration/test_vue_sidebar_spike.py` | New | 3 | nicegui |
| `tests/unit/test_items_serialise.py` | New | 4 | unit |
| `tests/integration/test_vue_sidebar_dom_contract.py` | New | 4 | nicegui |
| `tests/e2e/test_card_layout.py` | Verify unchanged | 5, 10 | playwright |
| `tests/integration/test_vue_sidebar_expand.py` | New | 6 | nicegui |
| `tests/integration/test_vue_sidebar_mutations.py` | New | 7 | nicegui |
| `tests/integration/test_vue_sidebar_interactions.py` | New | 8 | nicegui |
| `tests/integration/test_vue_sidebar_broadcast.py` | New | 9 | nicegui |
| `tests/integration/test_event_loop_render_lag.py` | Modified (thresholds) | 9, 10 | nicegui |
| `tests/integration/test_vue_sidebar_charac.py` | New (replaces deleted) | 10 | nicegui |
| `tests/e2e/test_vue_sidebar_cross_tab.py` | New | 10 | playwright |

**Deleted (with equivalents):**
- `tests/integration/test_annotation_cards_charac.py` -> `test_vue_sidebar_charac.py` + `test_items_serialise.py`
- `tests/integration/test_lazy_card_detail.py` -> `test_vue_sidebar_expand.py`
- `tests/unit/test_card_header_html.py` -> `test_items_serialise.py`

## Gaps and Risks

1. **AC6.1 test file:** Phase 9 Task 5 describes two-client verification. Implementer should create `tests/integration/test_vue_sidebar_broadcast.py`.
2. **AC2.2 deferred visibility:** Phase 4 places `data-testid` on hidden detail elements. Test must assert DOM presence, not visibility. Full visibility in Phase 6.
3. **AC5.2 structural guarantee:** "Within one tick" is a code-structure property (no `await` in mutation-to-push path). Code review verifies; timing test is a proxy.
4. **Pabai fixture path:** Phase 6 Task 1 moves fixtures. All subsequent phases depend on new path. Phase 10 full-suite run catches stale paths.
5. **SortableJS with `ui.html()`:** Phase 2 replaces `ui.card()` children with `ui.html()`. SortableJS must still detect `id="hl-{id}"` on the element. If `ui.html()` wraps content in an extra `<div>`, SortableJS event parsing may break. Phase 2 Task 4 includes fallback approaches.
