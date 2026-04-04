# Critical Peer Review: Phase 3-4 Vue Annotation Sidebar Implementation

Reviewer: Claude Opus 4.6 (1M context)
Date: 2026-04-03
Documents reviewed: phase_03.md, phase_04.md, phase-3-results.md, test-requirements.md, sidebar.py, annotationsidebar.js, items_serialise.py, test_vue_sidebar_spike.py, test_vue_sidebar_dom_contract.py, test_items_serialise.py, test_vue_sidebar_spike_e2e.py, _server_script.py (spike section), _lanes.py, testing.py

## Hidden Assumptions

### Load-Bearing

1. **NiceGUI `_props` dict is the faithful transport to Vue props.** The entire integration test strategy depends on the assumption that if `el._props["items"]` contains the correct data, Vue will receive it as `props.items`. No evidence is provided that this is the case for custom `ui.element` subclasses with complex nested dicts. The E2E test validates this empirically for the spike page, but only for the specific data shapes tested. **Status: Partially validated by E2E tests.**

2. **`anonymise_author()` returns the raw author name when `anonymous_sharing=False`.** The unit tests assert `display_author == "Alice Smith"` when `anonymous_sharing=False`, but none of the tests independently verify the `anonymise_author` function's contract -- they rely on the existing function behaving as expected. **Status: Dependency assumption, reasonable -- the function has its own tests elsewhere.**

3. **Vue 3's `watch` with `{ deep: true }` fires on NiceGUI prop pushes.** The epoch synchronisation mechanism depends on Vue's deep watcher detecting when NiceGUI replaces the `items` array via websocket prop update. The E2E test for GO4 (prop update re-render) validates that card count changes, but does not directly test epoch increment. **Status: Partially validated. Epoch increment not tested until Phase 9.**

4. **NiceGUI serves custom Vue component JS files from `component=Path(...)` in production.** Validated only in the test server (`_server_script.py`). The production annotation page does not yet use `AnnotationSidebar`. **Status: Unverified on production code path.**

5. **Comment `created_at` values are always comparable strings.** The sorting `sorted(comments, key=lambda c: c["created_at"])` assumes ISO-format string comparison produces chronological order. This works for ISO 8601 but would break with timezone-naive vs timezone-aware mixing. **Status: Implicit assumption, not tested with edge-case timestamps.**

### Non-Critical

6. **`_TEXT_PREVIEW_LIMIT = 80` is a reasonable truncation length.** Aesthetic choice, no correctness impact.

7. **`_RECOVERED_TAG_LABEL = "\u26a0 recovered"` matches existing UI convention.** Not verified against the current NiceGUI card implementation, but low risk.

## ACH Matrix

The central question: **Did the spike validate what it claimed?**

| Evidence | H1: Spike validates go/no-go | H2: Spike validates only Python wiring, not Vue | H3: Spike is insufficient for any go/no-go decision |
|---|---|---|---|
| Integration tests pass (all 6) | + | + | + |
| Integration tests inspect `_props`, not DOM | ? | + | + |
| E2E tests pass (all 7) | + | - | - |
| E2E validates card rendering, $emit, prop update | + | - | - |
| phase-3-results.md marks criteria 2,3,4 as "PARTIAL" | - | + | ? |
| E2E was added after human flagged the gap | ? | + (initially) | ? |
| Three bugs found only in E2E (hyphen, position, auth) | - | + | ? |

**Decision:** H1 survives only because the E2E tests were added retroactively. The original spike (integration tests alone) would have been H2 -- Python wiring validated, Vue rendering unvalidated. The phase-3-results.md is honest about this after revision, marking criteria 2/3/4 as PARTIAL. The key question is whether the results document was always this honest or was revised after the E2E failures.

The three bugs found only by E2E testing (JS filename hyphens, position:absolute zero-size, authentication for websocket) demonstrate that H2 was the initial state. The spike was insufficient to catch real integration failures until the human demanded browser tests.

## Findings

### High (count: 2)

- **Issue: Phase 3 results claim "GO" based on partial criteria, but three showstopper bugs were only caught by E2E tests added after human intervention.**
  **Evidence:** phase-3-results.md says "Verdict: GO" and "No blockers to proceeding." The plan's original scope (phase_03.md Task 3) specified NiceGUI `user_simulation` tests using `_find_all_by_testid` and `_should_see_testid` to verify Vue-rendered DOM elements. These helpers cannot find Vue-rendered children, as the deviation notes acknowledge. The E2E test (`test_vue_sidebar_spike_e2e.py`) was added after the human pointed out the gap. The E2E tests discovered: (1) JS files with hyphens in the name break NiceGUI's `import()` -- the original file would have been `annotation-sidebar.js` per Task 2 but had to be renamed to `annotationsidebar.js`, (2) `position: absolute` without top/left produces invisible zero-size cards -- the implementer first tried `position: relative` instead of removing the style, requiring two rounds of pushback, (3) NiceGUI websocket requires authentication -- blank page without it.
  **GRADE factors:** Indirectness (integration tests used as proxy for browser validation), Reporting bias (results document now reads as though limitations were always known, but the timeline shows they were discovered reactively).
  **Ripple:** The "GO" verdict in phase-3-results.md was used to justify proceeding to Phase 4. Phase 4's DOM contract tests also use the integration-test-only approach (deviation note 3: "Integration tests validate prop data contract, not rendered DOM"). If the Phase 3 spike had been taken at face value without the human-forced E2E addition, Phase 4 would have proceeded with zero browser validation.
  **Corrected language:** Phase-3-results.md should state: "Initial spike tests validated Python-side wiring only. Browser-based E2E tests, added after the human identified the gap, discovered three showstopper integration bugs (JS filename, CSS positioning, websocket auth). All three were fixed. Criteria 1-5 now pass at the E2E level. The spike's original test design was inadequate for the stated go/no-go purpose."
  **Location:** `docs/implementation-plans/2026-03-30-vue-annotation-sidebar-457/phase-3-results.md`, Decision section

- **Issue: Plan specifies `style="position: absolute"` on card wrappers (phase_04.md line 187), but this was the source of a zero-size invisible card bug caught only in E2E testing.**
  **Evidence:** phase_04.md Task 4 says: `style="position: absolute"` (positioning in Phase 5). The current `annotationsidebar.js` does NOT have `position: absolute` on the card wrapper divs (lines 56-62), meaning this was removed after the bug was found. However, the plan still specifies it. The plan-to-implementation inconsistency means anyone following the plan for a subsequent component would reproduce the bug.
  **GRADE factors:** Internal inconsistency between plan and implementation.
  **Ripple:** Phase 5 plan presumably expects to add absolute positioning with actual top/left values. If Phase 5 references Phase 4's "already has position: absolute" as a baseline, the discrepancy will cause confusion.
  **Corrected language:** phase_04.md should add a deviation note: "position: absolute removed from card wrappers. It produced zero-size invisible elements because top/left were not set. Phase 5 must add position: absolute together with computed top values."
  **Location:** `docs/implementation-plans/2026-03-30-vue-annotation-sidebar-457/phase_04.md`, Task 4

### Medium (count: 4)

- **Issue: `can_annotate` field added to each item dict but not in Phase 4 plan's output spec.**
  **Evidence:** phase_04.md Task 1 (lines 81-100) defines the item dict schema. `can_annotate` is not listed. But `items_serialise.py` line 114 includes `"can_annotate": can_annotate` in every item. The integration test `test_vue_sidebar_dom_contract.py` line 163 asserts `hl1["can_annotate"] is True`. This is not a bug per se -- the Vue template may need it for Phase 7 (show/hide edit controls) -- but it is an undocumented plan deviation.
  **Corrected language:** Add to Phase 4 deviation notes: "Each item dict includes `can_annotate` (per-item copy of the viewer permission) for future use by Phase 7 edit control visibility."
  **Location:** `phase_04.md` deviations section; `items_serialise.py` line 114

- **Issue: Comment dict in plan spec (phase_04.md line 99) does not include `display_author`, but implementation adds it and Vue template uses it.**
  **Evidence:** Plan specifies `{"id": str, "author": str, "text": str, "created_at": str, "can_delete": bool}`. Implementation (`items_serialise.py` line 158) adds `"display_author": c_display_author`. Vue template (`annotationsidebar.js` line 95) renders `comment.display_author`. Unit test covers this (`test_items_serialise.py` line 184). This is correct behaviour (anonymised display name) but undocumented deviation.
  **Corrected language:** Add to Phase 4 deviations: "Comment dicts include `display_author` (anonymised name) in addition to raw `author`. Required for correct rendering under anonymisation."
  **Location:** `phase_04.md` deviations section

- **Issue: Phase 4 integration tests (`test_vue_sidebar_dom_contract.py`) validate the same thing the unit tests already validate -- prop data contract -- adding no new coverage beyond what `test_items_serialise.py` provides.**
  **Evidence:** Both `test_items_serialise.py` and `test_vue_sidebar_dom_contract.py` test that the serialised items have correct fields, correct tag recovery, correct comments, correct para_ref. The integration tests add only: (a) `refresh_items()` calls `serialise_items()` and writes to `_props["items"]`, and (b) the JS file contains certain testid strings. Item (a) is ~5 lines of glue. Item (b) is a static file read. Neither validates Vue rendering. The integration tests run in the NiceGUI serial lane (slower) for marginal additional coverage.
  **GRADE factors:** The evidence grade for "AC2.1/AC2.2 verified by integration tests" is **Low** (structural check of JS file + Python prop dict, not browser rendering).
  **Corrected language:** test-requirements.md should mark AC2.1 and AC2.2 integration coverage as "prop data contract only" rather than implying DOM validation.
  **Location:** `test-requirements.md` rows for AC2.1, AC2.2

- **Issue: The `_make_highlight` helper in `test_items_serialise.py` omits `para_ref` from the dict entirely when `para_ref=None`, but the implementation uses `hl.get("para_ref", "")` which would handle both absent key and empty string. The unit test for "missing para_ref" (line 397) passes `para_ref=None` which causes the key to be absent. This is correct for the current CRDT data shape, but the test does not cover the case where `para_ref` exists but is an empty string.**
  **Evidence:** `_make_highlight` lines 55-57: `if para_ref is not None: hl["para_ref"] = para_ref`. When `para_ref=None`, the key is absent. The `items_serialise.py` line 108: `hl.get("para_ref", "")`. The DOM contract test (`test_vue_sidebar_dom_contract.py` line 211) tests `para_ref=""` via `_HIGHLIGHTS[1]` which has `"para_ref": ""`. So the two cases (absent key and empty string) are covered across two different test files, but neither file covers both.
  **Corrected language:** Minor -- consider adding a comment in the unit test noting the empty-string case is covered in the DOM contract test.
  **Location:** `tests/unit/test_items_serialise.py`, TestEmptyParaRef class

### Low (count: 3)

- **Issue:** Phase 3 plan (line 140, Task 4) says to create `phase-1-results.md` but deviation note 3 explains it was named `phase-3-results.md`. The deviation note is accurate. No action needed.

- **Issue:** The E2E test's `spike_page` fixture navigates to `about:blank` and closes context in cleanup (lines 46-48). This is proper hygiene but duplicates the pattern from `conftest.py`'s `authenticated_page` fixture. Minor code duplication.

- **Issue:** `annotationsidebar.js` line 81 has an expand button that is `disabled`. Line 85-87 has a delete button that is `disabled`. Both are placeholders for Phase 6/7. These disabled buttons are rendered in the browser and tested by the E2E test (lines 133-141), which verifies correct disabled placeholder rendering. This is fine for now but the `disabled` attribute should be removed when interactivity is added.

## Verification

### Commands Run
- `uv run grimoire test run tests/unit/test_items_serialise.py` -- 16 passed in 0.52s
- `uv run grimoire test run tests/integration/test_vue_sidebar_spike.py` -- PASS (3.3s)
- `uv run grimoire test run tests/integration/test_vue_sidebar_dom_contract.py` -- PASS (3.6s)
- `uv run grimoire e2e run -k test_vue_sidebar_spike_e2e` -- PASS (21.4s), 50/50 files passed

### Files Verified
- `sidebar.py` `_JS_PATH` resolves to `static/annotationsidebar.js` (not `annotation-sidebar.js`) -- confirmed the hyphen-rename fix
- `annotationsidebar.js` has no `position: absolute` on card wrappers -- confirmed the CSS fix
- `items_serialise.py` calls `anonymise_author()` directly, not `anonymise_display_author()` -- confirmed plan deviation 1 is accurate
- `_server_script.py` spike page uses `refresh_items()` with `user_id="u-1"` and highlight `user_id="u-1"` for hl-1 -- `can_delete` will be True for card 1, False for card 2 -- matches E2E assertion at line 137/141
- `_NICEGUI_ALLOWLIST` and `_NICEGUI_UI_FILES` both include `test_vue_sidebar_spike.py` and `test_vue_sidebar_dom_contract.py` -- lane routing correct
- `TagInfo` dataclass has `name`, `colour`, `raw_key` fields -- matches test usage

### Citation Checks
- phase_03.md line 89: `Path(__file__).resolve().parent.parent.parent / 'static' / 'annotation-sidebar.js'` -- STALE. Implementation uses `annotationsidebar.js` (no hyphens). Plan not updated.
- phase_04.md line 106: `anonymise_display_author()` from `card_shared.py` -- STALE. Implementation uses `anonymise_author()` from `auth/anonymise.py`. Deviation note 1 covers this but the task body still says `anonymise_display_author()`.
- phase_04.md line 187: `style="position: absolute"` -- STALE. Removed from implementation. No deviation note.

## Strongest Hypothesis

**The items serialisation pure function (`items_serialise.py`) is correct and well-tested.** It has 16 unit tests covering all documented edge cases (tag recovery, anonymisation, permissions, text truncation, comment sorting). It follows functional-core/imperative-shell correctly -- no NiceGUI imports, no side effects. The only gap is the undocumented `can_annotate` and comment `display_author` fields.

Evidence grade: **High (Demonstrated)** -- both borders tested (correct output for valid inputs, correct defaults for missing/invalid inputs), on the actual production code path (same function will be called by the real annotation page).

## Weakest Hypothesis

**"Phase 4 integration tests validate AC2.1 and AC2.2"** as claimed in test-requirements.md.

The integration tests validate the *prop data contract* -- that the Python dict contains the right fields. They do NOT validate that the Vue template renders these fields into DOM elements with the specified `data-testid` attributes. The JS file structural check (reading the file and asserting string presence) is a weak proxy for rendering correctness. The actual AC2.1/AC2.2 validation comes from the E2E test, which is categorised under Phase 3 spike validation rather than Phase 4 AC coverage.

Evidence grade: **Low (Possible)** -- structural check of JS source + Python prop dict, not browser rendering. The E2E test provides **Moderate** coverage but is not listed as the AC2 validation source.

## Pre-Mortem

If the Phase 3-4 implementation is wrong, what would the next incident reveal?

1. **Vue component fails to mount on the real annotation page (Phase 5+).** The spike test page (`_server_script.py`) creates `AnnotationSidebar` in isolation with hardcoded data. The real annotation page creates it within a complex NiceGUI element tree with CRDT data, WebSocket broadcasting, and concurrent users. If NiceGUI's component registration conflicts with other custom elements or the annotation page's existing DOM structure, the spike would have passed but production would fail. The E2E spike tests do not exercise this path.

2. **Prop updates from CRDT broadcast cause Vue reactivity failures.** The E2E test for GO4 uses a button click -> `set_items()` with a single pre-built item dict. In production, `refresh_items()` will be called from CRDT broadcast handlers with rapidly changing data. Vue's `{ deep: true }` watcher on a replaced array object should fire, but the spike does not test rapid sequential updates or concurrent prop mutations. A race between two CRDT broadcasts could produce stale renders.

3. **Performance regression with 190 highlights.** The spike tests use 2 items. The production target (from AC5.1, AC8.1, AC9.1) is 190 highlights. `serialise_items()` calls `anonymise_author()` per highlight and per comment. If `anonymise_author()` is expensive (it creates a `RandomGenerator` with SHA-256 per call for anonymous mode), 190 highlights with multiple comments could exceed the 5ms server-side blocking budget. This is untested until Phase 9.

## Fastest Next Test

**Test the Vue component on the real annotation page with a real workspace.**

Write a Playwright E2E test that:
1. Creates a workspace with 5+ highlights via the normal annotation flow
2. Loads the annotation page (when Phase 5+ wires `AnnotationSidebar` into the page)
3. Verifies card count matches highlight count
4. Verifies `data-highlight-id` attributes match actual highlight UUIDs

This would close the gap between "spike with hardcoded data" and "production with real data" -- the single biggest uncertainty remaining.

Until Phase 5 wires the component into the real page, the fastest discriminating test is: run the E2E spike with 50+ items to verify Vue rendering performance does not degrade with realistic data volumes.

## Overall Assessment

**Needs revision (minor).**

The implementation is solid. The serialisation function is correct and well-tested. The E2E tests validate the go/no-go criteria in a real browser. The code quality is high.

The documentation needs updates:

1. **[High]** phase-3-results.md should be more explicit that the E2E tests were added retroactively after human intervention, and that the original integration-only approach was insufficient. The current text reads as if the limitations were always planned for.
2. **[High]** phase_04.md needs a deviation note about `position: absolute` removal. The plan still specifies it.
3. **[Medium]** phase_04.md item dict spec should document `can_annotate` and comment `display_author` fields.
4. **[Medium]** phase_03.md Task 2 still references `annotation-sidebar.js` (with hyphens) as the filename. Should note the rename.

The implementation code is ready to proceed to Phase 5 without changes. Only the documentation needs updating.
