# PDF Export Character Alignment — Test Requirements

Maps every acceptance criterion from `docs/design-plans/2026-02-08-pdf-export-char-alignment.md` to either an automated test or a documented human verification step.

**Notation:** Each entry uses the scoped identifier `pdf-export-char-alignment.AC{N}.{M}`.

---

## AC1: PDF includes source document with annotations

### pdf-export-char-alignment.AC1.1 — Export from Tab 1 produces PDF with source body, highlights, and comments

| Field | Value |
|-------|-------|
| **Type** | Integration |
| **Test file** | `tests/integration/test_pdf_export.py` |
| **Description** | Existing test `test_export_basic_html` (adapted in Phase 2 Task 4) calls `export_annotation_pdf` with HTML content and highlights, then asserts the output PDF exists and the intermediate `.tex` file contains HLSTART/HLEND markers replaced by `\highLight` LaTeX commands. Phase 2 Task 1 changes the production caller (`_handle_pdf_export`) to use `doc.content` — this wiring is verified by end-to-end UAT (see human verification below). |
| **Phase** | 2 (Task 1, Task 4) |
| **Rationale** | The automated test verifies the export pipeline produces correct LaTeX from HTML input. The Tab 1 vs Tab 3 distinction is a UI-layer concern (which data is read from the page state), not testable at unit/integration level without a running NiceGUI app. |

**Human verification (supplement):**

| Field | Value |
|-------|-------|
| **Criterion** | pdf-export-char-alignment.AC1.1 |
| **Justification** | The "from Tab 1" aspect requires a running NiceGUI app with database, CRDT state, and browser interaction to confirm the correct data flows from the Annotate tab through to the export function. |
| **Approach** | Phase 2 UAT step 3-5: Start the app, navigate to `/annotation`, paste a document, add highlights, click Export PDF from Tab 1. Verify PDF opens with source body, highlights at correct positions, and annotation comments in margins. |

---

### pdf-export-char-alignment.AC1.2 — Export from Tab 3 produces same source body with highlights and comments

| Field | Value |
|-------|-------|
| **Type** | Human verification only |
| **Justification** | This criterion verifies that Tab 3 (Respond) uses the same underlying `doc.content` and highlights as Tab 1. The export pipeline itself is tab-agnostic — `_handle_pdf_export` reads `doc.content` regardless of active tab. The distinction is purely a UI-layer concern requiring a running app and tab switching. |
| **Approach** | Phase 2 UAT: Start the app, add highlights on Tab 1, switch to Tab 3, click Export PDF. Verify the output PDF is identical to AC1.1 (same source body, same highlight positions, same comments). |
| **Phase** | 2 |

---

### pdf-export-char-alignment.AC1.3 — Highlights at correct character positions (marker text matches extract_text_from_html char slice)

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Round-trip property test: for each test case, call `extract_text_from_html(html)` to get the character array, then call `insert_markers_into_dom(html, highlights)` with a highlight at `[start:end]`. Extract the text between HLSTART and HLEND markers in the output, strip tags, decode entities, collapse whitespace, and assert it equals `"".join(chars[start:end])`. Covers test cases 1-4, 9-13, 17 from Phase 1 Task 3 (simple paragraph, multi-paragraph, formatted spans, cross-tag boundary, table, heading+paragraph, HTML entities, multiple entities, entity at boundary, ANNMARKER presence). |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC1.4 — CJK/Unicode highlights at correct positions

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Test case 6 from Phase 1 Task 3: `<p>你好世界</p>` with highlight on `[0:2]` ("你好"). Verifies characters are indexed individually by Unicode codepoint, not by UTF-8 byte offset. Round-trip property applies: `extract_text_from_html` char slice matches marker-bounded text. |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC1.5 — No document content shows user-facing error, not blank PDF

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/export/test_empty_content_guard.py` |
| **Description** | Test that `export_annotation_pdf` with empty `html_content` and non-empty `highlights` raises `ValueError` with message containing "empty content". The user-facing `ui.notify` call in `_handle_pdf_export` (which catches this and shows a warning) is a UI concern verified by UAT. |
| **Phase** | 2 (Task 4) |

**Human verification (supplement):**

| Field | Value |
|-------|-------|
| **Criterion** | pdf-export-char-alignment.AC1.5 |
| **Justification** | The user-facing notification ("No document content to export") is rendered by NiceGUI's `ui.notify`, which requires a running browser session. |
| **Approach** | Phase 2 UAT: Start app, navigate to `/annotation` on a workspace with no pasted content, click Export PDF. Verify a warning notification appears (not a blank PDF or a crash). |

---

### pdf-export-char-alignment.AC1.6 — export_annotation_pdf raises ValueError for highlights with empty content

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/export/test_empty_content_guard.py` |
| **Description** | Direct assertion: `export_annotation_pdf(html_content="", highlights=[{"start_char": 0, "end_char": 5, ...}], ...)` raises `ValueError`. Second test case: `html_content="   "` (whitespace only) with highlights also raises. Third test case: `html_content=""` with empty highlights list does NOT raise (graceful no-op). |
| **Phase** | 2 (Task 3, Task 4) |

---

## AC2: Response draft section

### pdf-export-char-alignment.AC2.1 — Tab 3 content produces "Response Draft" section in PDF

| Field | Value |
|-------|-------|
| **Type** | Unit + Integration |
| **Test file (unit)** | `tests/unit/export/test_markdown_to_latex.py` |
| **Test file (integration)** | `tests/integration/test_pdf_export.py` |
| **Description** | **Unit:** `TestBuildResponseDraftSection` (renamed from `TestBuildGeneralNotesSectionWithLatex` in Phase 3 Task 4) calls `_build_response_draft_section(response_draft_latex=r"\textbf{notes}")` and asserts the result contains `\section*{Response Draft}` and the LaTeX content. **Integration:** `test_export_with_response_draft` (renamed from `test_export_with_general_notes` in Phase 3 Task 4) calls `export_annotation_pdf` with `response_draft_latex` and asserts the `.tex` output contains "Response Draft". |
| **Phase** | 3 (Task 1, Task 4) |

---

### pdf-export-char-alignment.AC2.2 — Empty Tab 3 produces no Response Draft section

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/export/test_markdown_to_latex.py` |
| **Description** | `TestBuildResponseDraftSection` includes a test calling `_build_response_draft_section(response_draft_latex="")` and asserting the result is `""` (empty string, no section emitted). Additional edge case: `_build_response_draft_section(response_draft_latex="   ")` (whitespace only) also returns `""`. |
| **Phase** | 3 (Task 4) |

---

### pdf-export-char-alignment.AC2.3 — Export works without visiting Tab 3 (CRDT fallback)

| Field | Value |
|-------|-------|
| **Type** | Human verification only |
| **Justification** | This criterion tests a UI-layer fallback path: when Tab 3 has never been rendered, `_handle_pdf_export` falls back to `state.crdt_doc.get_response_draft_markdown()` (annotation.py:1717-1718). This requires a running NiceGUI app with CRDT state, browser tab interaction, and deferred tab rendering — none of which can be exercised in a headless unit or integration test. As noted in Phase 3, the criterion is structurally guaranteed by preserving the existing fallback code path during the rename. |
| **Approach** | Phase 3 UAT steps 7-9: Start app, create a new workspace, paste a document, add highlights, do NOT visit Tab 3. Click Export PDF. Verify PDF exports successfully with no "Response Draft" section (AC2.2 combined) and no errors. |
| **Phase** | 3 |

---

## AC3: Character index agreement

### pdf-export-char-alignment.AC3.1 — Round-trip property for any HTML

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Every test case in the file applies the round-trip property: `extract_text_from_html(html)[start:end]` equals the text between HLSTART/HLEND markers in the output of `insert_markers_into_dom(html, highlights)`. This is the structural correctness guarantee. Test cases 1-13 and 17 from Phase 1 Task 3 all verify this property on different HTML structures. Test case 11 (`<p>A &amp; B</p>`) and cases 12-13 specifically exercise entity handling under the round-trip. |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC3.2 — Multi-block HTML does not cause index drift

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Test case 2 (multi-paragraph: `<p>Hello</p><p>World</p>`) and test case 8 (block whitespace skipping: `<div>\n  <p>Hello</p>\n  <p>World</p>\n</div>`). Both verify that whitespace-only text nodes between block tags are skipped during character counting, and that highlights on the second block land at the correct position. Round-trip property confirms no drift. |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC3.3 — `<br>` tags counted as single newline

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Test case 7: `<p>Line one<br>Line two</p>`, with highlight on text before the `<br>`. Verifies that the `<br>` tag contributes exactly one character (newline) to the index count, matching `extract_text_from_html` behaviour. Round-trip property confirms agreement. |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC3.4 — Whitespace runs collapsed to single space

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Test case 5: `<p>Hello   world</p>` (multiple spaces), with highlight on the collapsed text. Verifies that three spaces collapse to one in the character index, and markers are placed at the correct collapsed position. `_WHITESPACE_RUN` regex (`[\s\u00a0]+` -> single space) is the shared rule. |
| **Phase** | 1 (Task 3) |

---

### pdf-export-char-alignment.AC3.5 — Formatted spans preserved, markers correct across tag boundaries

| Field | Value |
|-------|-------|
| **Type** | Unit |
| **Test file** | `tests/unit/input_pipeline/test_insert_markers.py` |
| **Description** | Test case 3 (formatted spans: `<p>Hello <strong>bold</strong> text</p>`, highlight on "bold") verifies that `<strong>` tags are preserved in the output HTML and markers are placed inside the formatted span at correct positions. Test case 4 (cross-tag boundary: highlight spanning from before `<strong>` to after it) verifies markers split correctly across tag boundaries. |
| **Phase** | 1 (Task 3) |

---

## AC4: Dead code removal

### pdf-export-char-alignment.AC4.1 — No references to deleted symbols remain in source code

| Field | Value |
|-------|-------|
| **Type** | Unit (grep-based verification) |
| **Test file** | No dedicated test file; verified by Phase 4 Task 5 grep commands and by `ruff check` / `ty check` catching undefined name errors |
| **Description** | Phase 4 Task 5 runs `grep -rn "_insert_markers_into_html\|_plain_text_to_html\|_escape_html_text_content" src/ tests/` and expects zero results. Also runs `grep -rn "general_notes" src/promptgrimoire/export/ src/promptgrimoire/pages/` and expects zero results (CRDT field in `crdt/annotation_doc.py` is expected — outside export/pages scope). Any surviving references would also cause `ruff check` (unused import) or `ty check` (undefined name) failures, which are gated by pre-commit hooks. |
| **Phase** | 3 (Task 2 for `general_notes` in export), 4 (Tasks 1-5 for remaining symbols) |

**Rationale:** A dedicated test asserting "no references exist" would be brittle and duplicate what the linter already enforces. The combination of (a) grep verification at implementation time, (b) ruff/ty in CI, and (c) the full test suite catching any import/call errors provides sufficient coverage.

---

### pdf-export-char-alignment.AC4.2 — ruff check and ty check clean after removal

| Field | Value |
|-------|-------|
| **Type** | Automated (CI / pre-commit hooks) |
| **Test file** | N/A — enforced by existing pre-commit hooks and Claude Code write hooks |
| **Description** | Every `.py` file write triggers `ruff check --fix`, `ruff format`, and `ty check` via Claude Code hooks. Git commits are rejected if `ruff check` or `ty check` fail via pre-commit hooks. Phase 4 Task 5 explicitly runs `uv run ruff check .` and `uvx ty check` as final verification. |
| **Phase** | 4 (Task 5) |

**Rationale:** This criterion is a quality gate, not a test case. It is enforced structurally by the development workflow. No additional test file is needed.

---

### pdf-export-char-alignment.AC4.3 — Full test suite passes

| Field | Value |
|-------|-------|
| **Type** | Automated (full suite run) |
| **Test file** | All test files via `uv run test-debug` / `uv run test-all` |
| **Description** | Phase 4 Task 5 runs `uv run test-debug` as final verification. This executes all unit and integration tests (excluding E2E). Any import error from a deleted module, any call to a removed function, or any assertion checking deleted behaviour would surface here. Phase 4 Task 4 explicitly deletes three test files (`test_plain_text_conversion.py`, `test_crlf_char_index_bug.py`, `test_marker_insertion.py`) that test only deleted code. |
| **Phase** | 4 (Task 4, Task 5) |

---

## AC5: Fixture regression

### pdf-export-char-alignment.AC5.1 — All HTML fixtures pass through insert_markers_into_dom without error

| Field | Value |
|-------|-------|
| **Type** | Unit (parametrised) |
| **Test file** | `tests/unit/export/test_empty_content_guard.py` |
| **Description** | Parametrised test (created in Phase 2 Task 4) that loads each HTML fixture from `tests/fixtures/*.html` and `tests/fixtures/*.html.gz`, calls `extract_text_from_html` to compute valid character positions, creates synthetic highlights at multiple positions (start, middle, end of extracted text), and passes them through `insert_markers_into_dom`. Asserts no exceptions raised and output contains expected HLSTART/HLEND markers. |
| **Phase** | 2 (Task 4) |

**Note on test file location:** The Phase 2 plan places this test in `test_empty_content_guard.py` alongside the ValueError guard tests. An alternative is a separate file `tests/unit/input_pipeline/test_fixture_regression.py` if the scope grows. The implementation should decide based on test count.

---

### pdf-export-char-alignment.AC5.2 — Visual inspection of exported PDFs confirms correct annotation positions

| Field | Value |
|-------|-------|
| **Type** | Human verification only |
| **Justification** | "Looks right" is an inherently visual judgement. Automated tests can verify markers are present and at correct character indices (AC3.1 covers this structurally), but confirming that the final rendered PDF shows highlights at the right visual position in the typeset document requires human eyes. Pandoc HTML-to-LaTeX conversion and LaTeX compilation introduce formatting transformations that could theoretically shift visual positions even when character indices are correct. |
| **Approach** | Phase 2 UAT steps 3-5: Paste fixture content into the app, add highlights at known positions, export to PDF, open the PDF and visually confirm highlights overlay the expected text. Compare against the same highlights shown in the browser UI. |
| **Phase** | 2 |

---

### pdf-export-char-alignment.AC5.3 — i18n fixtures produce PDFs with correct CJK/diacritical highlights

| Field | Value |
|-------|-------|
| **Type** | Human verification only |
| **Justification** | CJK character rendering in PDF depends on LaTeX font configuration (fontspec/LuaLaTeX), which varies by system. Automated tests can verify character indices are correct (AC1.4 covers this at the marker insertion level), but visual confirmation that CJK characters render and highlight correctly in the compiled PDF requires human inspection. Font fallback issues, missing glyphs, or incorrect line-breaking around CJK characters would only be visible in the rendered output. |
| **Approach** | Phase 2 UAT (AC5.3 addendum): Load i18n fixture content (Chinese Wikipedia, Japanese, Korean, Spanish), add highlights spanning CJK/diacritical characters, export to PDF. Verify highlights land on the correct characters and text renders without missing glyphs. |
| **Phase** | 2 |

---

## Summary Matrix

| Criterion | Automated? | Test Type | Test File | Phase |
|-----------|-----------|-----------|-----------|-------|
| AC1.1 | Partial | Integration + UAT | `tests/integration/test_pdf_export.py` | 2 |
| AC1.2 | No | UAT only | N/A | 2 |
| AC1.3 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC1.4 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC1.5 | Partial | Unit + UAT | `tests/unit/export/test_empty_content_guard.py` | 2 |
| AC1.6 | Yes | Unit | `tests/unit/export/test_empty_content_guard.py` | 2 |
| AC2.1 | Yes | Unit + Integration | `tests/unit/export/test_markdown_to_latex.py`, `tests/integration/test_pdf_export.py` | 3 |
| AC2.2 | Yes | Unit | `tests/unit/export/test_markdown_to_latex.py` | 3 |
| AC2.3 | No | UAT only | N/A | 3 |
| AC3.1 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC3.2 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC3.3 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC3.4 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC3.5 | Yes | Unit | `tests/unit/input_pipeline/test_insert_markers.py` | 1 |
| AC4.1 | Yes | Grep + lint | CI / pre-commit | 3, 4 |
| AC4.2 | Yes | Lint gate | CI / pre-commit | 4 |
| AC4.3 | Yes | Full suite | `uv run test-debug` | 4 |
| AC5.1 | Yes | Unit (parametrised) | `tests/unit/export/test_empty_content_guard.py` | 2 |
| AC5.2 | No | UAT only | N/A | 2 |
| AC5.3 | No | UAT only | N/A | 2 |

### Coverage totals

- **20** acceptance criteria total
- **14** fully automated (unit or integration test)
- **2** partially automated (automated test covers the function, UAT covers the UI layer)
- **4** human verification only (AC1.2, AC2.3, AC5.2, AC5.3)

### Human verification justifications

| Criterion | Reason |
|-----------|--------|
| AC1.2 | Tab-switching context requires running NiceGUI app + browser |
| AC2.3 | CRDT fallback when Tab 3 never visited requires running app + deferred rendering |
| AC5.2 | "Looks right" is a visual judgement on rendered PDF, not a character-index check |
| AC5.3 | CJK rendering depends on system fonts + LaTeX font config; requires visual confirmation |

---

## Test Files Created or Modified

### New test files (created during implementation)

| File | Phase | Contents |
|------|-------|----------|
| `tests/unit/input_pipeline/test_insert_markers.py` | 1 (Task 3) | 17 test cases for `insert_markers_into_dom`: round-trip property, whitespace collapsing, block skipping, `<br>` handling, CJK, entities, cross-tag boundaries, backward compat, ANNMARKER presence, empty-input guards |
| `tests/unit/export/test_empty_content_guard.py` | 2 (Task 4) | ValueError guard for empty content + highlights, plus parametrised fixture regression test (AC5.1) |

### Modified test files

| File | Phase | Changes |
|------|-------|---------|
| `tests/unit/export/test_markdown_to_latex.py` | 3 (Task 4) | Rename `TestBuildGeneralNotesSectionWithLatex` to `TestBuildResponseDraftSection`, update imports and assertions from "General Notes" to "Response Draft", remove HTML-path tests |
| `tests/integration/test_pdf_export.py` | 2 (Task 4), 3 (Task 4) | Remove `escape_text` parameter from calls; rename `test_export_with_general_notes` to `test_export_with_response_draft`; update to use `response_draft_latex` parameter |
| `tests/conftest.py` | 3 (Task 4) | Update `pdf_exporter` fixture: rename `general_notes` to `response_draft_latex`, remove HTML composition logic |
| `tests/unit/test_annotation_doc.py` | 3 (Task 3) | Remove `TestGeneralNotes` class and all `get_general_notes`/`set_general_notes` references |

### Deleted test files

| File | Phase | Reason |
|------|-------|--------|
| `tests/unit/export/test_plain_text_conversion.py` | 4 (Task 4) | Tests only `_plain_text_to_html` and `_escape_html_text_content`, both deleted |
| `tests/unit/export/test_crlf_char_index_bug.py` | 4 (Task 4) | Tests the plain-text CRLF flow with `_insert_markers_into_html`; bug class structurally eliminated by DOM-based approach |
| `tests/unit/export/test_marker_insertion.py` | 4 (Task 4) | All 8 tests call `_insert_markers_into_html` directly; scenarios migrated to `tests/unit/input_pipeline/test_insert_markers.py` in Phase 1 |
