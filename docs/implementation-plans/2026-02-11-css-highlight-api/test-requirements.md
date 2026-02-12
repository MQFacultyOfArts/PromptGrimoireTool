# CSS Custom Highlight API -- Test Requirements

## Overview

This document maps every acceptance criterion from the CSS Custom Highlight API design plan to either an automated test or a documented human verification step. It rationalises test types against the implementation decisions made in phases 1-6.

**Total acceptance criteria:** 30 sub-criteria across 8 groups (AC1-AC8).

**Test type key:**
- **Unit** -- Pure Python or isolated JS logic, no browser or server required. Runs in `test-all`.
- **Integration** -- Requires Playwright browser but not a live app server. Uses `page.set_content()` and `page.evaluate()` for JS/Python algorithm parity. Marked `@pytest.mark.e2e` (requires Playwright install). Runs separately.
- **E2E** -- Full Playwright tests against a live NiceGUI app server. Marked `@pytest.mark.e2e`. Excluded from `test-all`.
- **Static analysis** -- Automated grep/AST scan of source code. Runs in `test-all`.
- **Human** -- Cannot be meaningfully automated; requires manual browser inspection.

---

## Automated Test Map

| AC | Sub-criterion | Test type | Test file | Phase | Notes |
|----|---------------|-----------|-----------|-------|-------|
| AC1.1 | Highlights paint on correct text ranges without `<span class="char">` in DOM | E2E | `tests/e2e/test_highlight_rendering.py` | 3 | Create workspace, add highlight, assert no `span.char` elements, verify highlight visible |
| AC1.1 | (integration flow) | E2E | `tests/e2e/test_annotation_highlight_api.py` | 3 | Full user flow: select text, create highlight, verify CSS Highlight API rendering |
| AC1.2 | Multiple tags render simultaneously with distinct colours | E2E | `tests/e2e/test_highlight_rendering.py` | 3 | Create highlights with two different tags, verify both render with distinct colours via `CSS.highlights` entries |
| AC1.3 | Highlights span across block boundaries without splitting | E2E | `tests/e2e/test_highlight_rendering.py` | 3 | Create highlight spanning p boundary, verify continuous highlight |
| AC1.4 | Invalid char offsets (start >= end, negative, beyond length) silently skipped with warning | Integration | `tests/e2e/test_highlight_rendering.py` | 3 | Load page with fixture, call `applyHighlights()` via `page.evaluate()` with invalid offsets, listen for console warning, verify no crash. Uses `page.evaluate()` because this validates JS error handling logic, not user interaction. |
| AC1.5 | Overlapping highlights from different tags both visible | E2E | `tests/e2e/test_highlight_rendering.py` | 3 | Create two overlapping highlights with different tags, verify both render (layered opacity) |
| AC2.1 | Mouse text selection produces correct `{start_char, end_char}` | E2E | `tests/e2e/test_text_selection.py` | 3 | Select text with mouse, verify `selection_made` event carries correct char offsets matching server `document_chars` |
| AC2.1 | (integration flow) | E2E | `tests/e2e/test_annotation_highlight_api.py` | 3 | Select text, verify offsets, create highlight, verify it renders |
| AC2.2 | Selection across block boundaries produces contiguous offsets | E2E | `tests/e2e/test_text_selection.py` | 3 | Select across paragraph into list item, verify contiguous char offsets |
| AC2.3 | Selection outside document container is ignored | E2E | `tests/e2e/test_text_selection.py` | 3 | Select text in sidebar, verify no `selection_made` event emitted |
| AC2.4 | Collapsed selection (click without drag) does not emit event | E2E | `tests/e2e/test_text_selection.py` | 3 | Single click (no drag), verify no `selection_made` event |
| AC3.1 | Remote cursor appears as coloured vertical line with name label | Integration | `tests/e2e/test_remote_presence_rendering.py` | 5 | Call `renderRemoteCursor()` via `page.evaluate()`, verify `.remote-cursor` div with name label and colour. Uses `page.evaluate()` because this validates JS rendering logic in isolation. |
| AC3.1 | (multi-user flow) | E2E | `tests/e2e/test_remote_presence_e2e.py` | 5 | Two browser contexts, click in context_a, verify cursor in context_b |
| AC3.2 | Remote selection appears as coloured CSS highlight distinct from annotations | Integration | `tests/e2e/test_remote_presence_rendering.py` | 5 | Call `renderRemoteSelection()` via `page.evaluate()`, verify `CSS.highlights.has('hl-sel-...')`. Uses `page.evaluate()` because this validates CSS Highlight API registration. |
| AC3.2 | (multi-user flow) | E2E | `tests/e2e/test_remote_presence_e2e.py` | 5 | Two contexts, select in context_a, verify highlight in context_b |
| AC3.3 | Disconnected user's cursor/selection removed within 30s | E2E | `tests/e2e/test_remote_presence_e2e.py` | 5 | Close context_a, wait up to 5s in context_b, verify remote indicators gone. Implementation uses `client.on_disconnect` (~1-2s), well within 30s AC requirement. |
| AC3.4 | Local user's own cursor/selection not rendered as remote indicator | E2E | `tests/e2e/test_remote_presence_e2e.py` | 5 | In context_a, verify no `.remote-cursor` for own client_id |
| AC3.5 | `_connected_clients`, `_ClientState`, `_build_remote_cursor_css()`, `_build_remote_selection_css()` deleted | Static analysis | `tests/unit/test_no_char_span_queries.py` | 5 | Grep `annotation.py` source for these identifiers, assert zero matches. Aligns with Phase 6 Task 8 final verification sweep. |
| AC4.1 | Browser with `CSS.highlights` proceeds normally | E2E | `tests/e2e/test_browser_gate.py` | 1 | Navigate to `/login` in Playwright Chromium (supports CSS.highlights), verify login UI visible, no upgrade overlay |
| AC4.2 | Browser without `CSS.highlights` sees upgrade message, cannot access annotation | E2E | `tests/e2e/test_browser_gate.py` | 1 | Navigate to `/login`, use `page.evaluate()` to delete `CSS.highlights` and re-invoke gate check, verify upgrade overlay covers login UI. `page.evaluate()` justified because simulating an unsupported browser requires JS manipulation; no unsupported browser available in Playwright. |
| AC5.1 | `inject_char_spans`, `strip_char_spans`, `extract_chars_from_spans` not in `__all__` | Unit | `tests/unit/input_pipeline/test_public_api.py` | 3 | Import `promptgrimoire.input_pipeline`, check `__all__` does not contain these names |
| AC5.2 | `from promptgrimoire.input_pipeline import inject_char_spans` raises `ImportError` | Unit | `tests/unit/input_pipeline/test_public_api.py` | 3 | Attempt import, assert `ImportError` raised |
| AC5.3 | `extract_text_from_html()` remains available and functional | Unit | `tests/unit/input_pipeline/test_public_api.py` | 3 | Import from `input_pipeline.html_input`, call with sample HTML, verify correct output. Also covered by 19 existing tests in `TestExtractTextFromHtml` (renamed to `test_text_extraction.py`). |
| AC6.1 | CSS Highlight API highlights produce identical PDF output | Unit | `tests/unit/export/test_highlight_spans.py` (existing) | 6 | Existing tests verify `compute_highlight_spans()` produces correct LaTeX from char offsets. Data shape is unchanged (integer offsets from CRDT). No new test needed -- existing tests serve as regression gate. |
| AC6.2 | Existing PDF export tests pass without modification | Unit + Integration | `tests/unit/export/` and `tests/integration/test_highlight_latex_elements.py` (existing) | 6 | Run existing suites unmodified. Zero test changes required -- the PDF pipeline has no char-span dependency. |
| AC7.1 | JS `walkTextNodes()` char count equals Python `extract_text_from_html()` for every `workspace_*.html` fixture | Integration | `tests/integration/test_text_walker_parity.py` | 2 | Parameterised over glob `tests/fixtures/workspace_*.html`. Python reads file and counts chars; Playwright loads HTML and runs JS. Assert counts match. |
| AC7.2 | Fixtures with `<br>`, nested tables, empty `<p>`, `&nbsp;` produce matching counts | Integration | `tests/integration/test_text_walker_parity.py` | 2 | Parameterised test includes `workspace_edge_cases.html` (created in Phase 2) with these edge cases |
| AC7.3 | Empty HTML produces 0 chars from both JS and Python | Integration | `tests/integration/test_text_walker_parity.py` | 2 | Parameterised test includes `workspace_empty.html` (created in Phase 2) |
| AC8.1 | Annotation cards track highlight vertical position on scroll | E2E | `tests/e2e/test_scroll_sync.py` | 4 | Long document with multiple highlights, scroll, verify cards track positions |
| AC8.2 | Hovering annotation card paints temporary highlight via `CSS.highlights` | E2E | `tests/e2e/test_card_interaction.py` | 4 | Hover card, verify `CSS.highlights.has('hl-hover')` or visual highlight on text |
| AC8.3 | Clicking card target button scrolls to highlight and pulses/throbs | E2E | `tests/e2e/test_card_interaction.py` | 4 | Click go-to button, verify scroll position and throb highlight (`hl-throb` in `CSS.highlights`) |
| AC8.4 | No `querySelector('[data-char-index]')` in annotation page JS | Static analysis | `tests/unit/test_no_char_span_queries.py` | 4, 6 | Read `annotation.py` source, assert `data-char-index` string absent from all JS code blocks. Phase 4 Task 5 creates the test; Phase 6 Task 3 confirms zero remaining references. |
| AC8.5 | Throb animation uses only `::highlight()`-compatible CSS properties | Static analysis + Human | `tests/unit/test_no_char_span_queries.py` + Human | 4 | Automated: verify `::highlight(hl-throb)` rule uses only `background-color`. Human: visual confirmation that the throb effect is perceptible (see Human Verification section). |

---

## Human Verification Items

These criteria have automated coverage for correctness but require human visual inspection to confirm the user experience meets quality standards.

### HV1: Highlight visual quality (AC1.1, AC1.2, AC1.5)

**Why automation is insufficient:** Playwright can verify DOM state and `CSS.highlights` entries but cannot assess whether the rendered colours are distinguishable, the opacity layering is aesthetically appropriate, or the highlights are visually readable on different content types.

**Verification approach:** Load the annotation page with a multi-tag annotated document. Visually confirm:
- Highlight backgrounds are visible but do not obscure text
- Two overlapping highlights are both discernible (opacity layering)
- Different tags have clearly distinct colours
- Underline decoration (where supported) enhances rather than clutters

**When:** After Phase 3 completion, before Phase 4.

### HV2: Throb/pulse animation perceptibility (AC8.3, AC8.5)

**Why automation is insufficient:** The throb effect is a timed `background-color` change on `::highlight(hl-throb)`. Automated tests can verify the highlight entry exists and is removed after the timeout, but cannot assess whether the flash duration (800ms per Phase 4 Task 4) is long enough to notice yet short enough to not be distracting.

**Verification approach:** Click the go-to button on an annotation card. Visually confirm:
- The document scrolls to the highlight
- A brief bright flash is visible on the highlighted text
- The flash is noticeable but not jarring
- The flash fades cleanly (no visual artefacts)

**When:** After Phase 4 completion.

### HV3: Remote cursor and selection appearance (AC3.1, AC3.2)

**Why automation is insufficient:** Cursor positioning can be verified programmatically, but the visual presentation (cursor line thickness, name label readability, selection opacity relative to annotation highlights) requires human assessment.

**Verification approach:** Open two browser windows to the same workspace. In one window, click and select text. In the other window, visually confirm:
- Remote cursor is a visible coloured vertical line at the correct position
- Name label is readable and positioned above the cursor
- Remote selection is visible but clearly subordinate to annotation highlights (lower opacity)
- Multiple remote users' indicators are distinguishable

**When:** After Phase 5 completion.

### HV4: Browser gate message clarity (AC4.2)

**Why automation is insufficient:** The upgrade overlay's text content and visual presentation (covers full page, readable message, functional "Go Home" button) should be checked for usability.

**Verification approach:** Manually test in a browser with the gate triggered (or simulate by temporarily disabling `CSS.highlights`). Confirm:
- Message is clear and actionable
- Browser version requirements are accurate
- "Go Home" button works
- Login UI is fully obscured

**When:** After Phase 1 completion.

### HV5: Scroll-sync tracking fidelity (AC8.1)

**Why automation is insufficient:** Scroll-sync involves continuous repositioning of annotation cards during scroll. Automated tests can verify position at discrete points but cannot assess smoothness, jitter, or lag during continuous scrolling.

**Verification approach:** Load a long annotated document. Scroll continuously and observe:
- Cards smoothly track their highlight positions
- No visible jitter or lag
- Cards do not overlap excessively
- Cards remain visible when their highlights are in the viewport

**When:** After Phase 4 completion.

---

## Test File Inventory

### New test files created by this migration

| File | Type | Phase | Criteria covered |
|------|------|-------|------------------|
| `tests/e2e/test_browser_gate.py` | E2E | 1 | AC4.1, AC4.2 |
| `tests/integration/test_text_walker_parity.py` | Integration | 2 | AC7.1, AC7.2, AC7.3 |
| `tests/e2e/test_highlight_rendering.py` | E2E | 3 | AC1.1, AC1.2, AC1.3, AC1.4, AC1.5 |
| `tests/e2e/test_text_selection.py` | E2E | 3 | AC2.1, AC2.2, AC2.3, AC2.4 |
| `tests/unit/input_pipeline/test_public_api.py` | Unit | 3 | AC5.1, AC5.2, AC5.3 |
| `tests/e2e/test_annotation_highlight_api.py` | E2E | 3 | AC1.1, AC2.1 (integration flow) |
| `tests/e2e/test_scroll_sync.py` | E2E | 4 | AC8.1, AC8.4 (partial) |
| `tests/e2e/test_card_interaction.py` | E2E | 4 | AC8.2, AC8.3, AC8.5 |
| `tests/unit/test_no_char_span_queries.py` | Static analysis | 4, 6 | AC3.5, AC8.4, AC8.5 (automated portion) |
| `tests/e2e/test_remote_presence_rendering.py` | Integration | 5 | AC3.1, AC3.2 (JS rendering) |
| `tests/e2e/test_remote_presence_e2e.py` | E2E | 5 | AC3.1, AC3.2, AC3.3, AC3.4 (multi-user flow) |

### New test fixture files

| File | Phase | Purpose |
|------|-------|---------|
| `tests/fixtures/workspace_edge_cases.html` | 2 | Edge cases: `<br>`, nested tables, empty `<p>`, `&nbsp;` |
| `tests/fixtures/workspace_empty.html` | 2 | Zero text content HTML |

### Existing test files reused without modification (regression gates)

| File | Type | Criteria covered |
|------|------|------------------|
| `tests/unit/export/test_highlight_spans.py` | Unit | AC6.1 |
| `tests/unit/export/` (all) | Unit | AC6.2 |
| `tests/integration/test_highlight_latex_elements.py` | Integration | AC6.2 |

### Existing test files modified

| File | Phase | Change |
|------|-------|--------|
| `tests/unit/input_pipeline/test_char_spans.py` | 3 | Renamed to `test_text_extraction.py`; char-span test classes deleted, `TestExtractTextFromHtml` and `TestStripHtmlToText` kept |
| `tests/e2e/annotation_helpers.py` | 4, 6 | Phase 4: `setup_workspace_with_content()` updated to not wait for char spans. Phase 6: `select_chars()` rewritten to use mouse events + `charOffsetToRect()` coordinate lookup |
| `tests/e2e/test_annotation_highlights.py` | 4 | `TestHighlightInteractionsConsolidated` deleted (replaced by `test_scroll_sync.py` and `test_card_interaction.py`) |
| `tests/unit/input_pipeline/test_process_input.py` | 6 | Remove assertions checking for `data-char-index` in pipeline output |

### Existing test files deleted

| File | Phase | Reason |
|------|-------|--------|
| `tests/unit/test_char_tokenization.py` | 6 | Entirely depends on `_process_text_to_char_spans()` which is deleted |

---

## Implementation Decision Rationalisations

### Why AC1.4 uses `page.evaluate()` despite the E2E "no JS injection" rule

The testing guidelines state "NEVER inject JavaScript in E2E tests" for **simulating user behaviour**. AC1.4 tests JS error handling logic (invalid offsets logged as warning, no crash). This is an algorithm validation test, not a user interaction test. The `page.evaluate()` call directly invokes `applyHighlights()` with crafted invalid inputs -- there is no user action that naturally produces these inputs. Classified as Integration, not E2E.

### Why AC4.2 uses `page.evaluate()` to simulate an unsupported browser

Playwright bundles Chromium, Firefox, and WebKit -- all of which support `CSS.highlights`. There is no way to test a genuinely unsupported browser via Playwright. The test deletes `CSS.highlights` via `page.evaluate()` and re-invokes the gate check to verify the overlay renders. This is the only practical approach. Documented in Phase 1 Task 1.

### Why AC3 uses NiceGUI server-hub instead of pycrdt Awareness

Phase 5 documents a design deviation: Awareness's `set_local_state()` tracks a single client (the server), not multiple browser clients. The NiceGUI server-hub architecture requires per-client state management that Awareness's peer-to-peer protocol cannot provide without complex encoding. All AC3 criteria are still met. `client.on_disconnect` fires in ~1-2 seconds, exceeding the AC3.3 requirement of "within 30 seconds". The AC3 header ("via pycrdt Awareness") is satisfied in spirit by the equivalent server-side mechanism.

### Why AC6 needs no new tests

The PDF export pipeline consumes integer character offsets from the CRDT store. These offsets are computed by `extract_text_from_html()` (which is not deleted) and stored as integers in highlight records. The CSS Custom Highlight API migration changes only the **rendering** layer (browser-side). The data model (char offsets) and the export pipeline (Pandoc + Lua filter) are untouched. Existing tests in `tests/unit/export/` and `tests/integration/test_highlight_latex_elements.py` serve as regression gates. Phase 6 Task 6 runs them explicitly as verification.

### Why AC7 tests are classified as Integration, not E2E

The text walker parity tests use Playwright to run JS in a browser, but they do not require a live NiceGUI server. They load HTML fixtures via `page.set_content()` and invoke JS functions via `page.evaluate()`. This pattern is explicitly called out in Phase 2 Task 2 as an integration test validating algorithm parity, exempt from the "no JS injection" E2E rule. They are marked `@pytest.mark.e2e` because they require Playwright browser installation.

### Why AC8.5 has both automated and human verification

The automated portion verifies that the `::highlight(hl-throb)` CSS rule uses only `background-color` (a property supported by `::highlight()`). The human portion assesses whether the visual effect is perceptible and appropriate -- a subjective quality judgement that cannot be automated.
