# Test Requirements: Paragraph Numbering (#191)

## Automated Test Coverage

| AC ID | Criterion | Test Type | Test File | Phase |
|-------|-----------|-----------|-----------|-------|
| AC1.1 | Plain prose `<p>` elements get sequential numbers starting at 1 | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.2 | Mixed block elements (`<p>`, `<blockquote>`, `<li>`) numbered sequentially | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.3 | `<br><br>+` sequences within a block create new paragraph numbers | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.4 | Single `<br>` does NOT create a new paragraph number | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.5 | Headers (`<h1>`-`<h6>`) are skipped, not numbered | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.6 | Empty/whitespace-only blocks are skipped, not numbered | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC1.7 | Pasted markdown (`<br>`-heavy HTML) produces sensible numbering | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs` | 2 |
| AC2.1 | AustLII `<li value="1">` through `<li value="42">` shows those numbers | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs` | 2 |
| AC2.2 | Gaps in source numbering preserved (e.g. 1, 2, 5, 6) | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs` | 2 |
| AC2.3 | Non-numbered blocks between `<li>` items have no paragraph number | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs` | 2 |
| AC3.1 | HTML with 2+ `<li value>` elements detected as source-numbered | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestDetectSourceNumbering` | 2 |
| AC3.2 | HTML with 0-1 `<li value>` elements detected as auto-numbered | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestDetectSourceNumbering` | 2 |
| AC3.1 | Paste-in with 2+ `<li value>` sets `auto_number_paragraphs = False` in DB | Integration | `tests/integration/test_paragraph_numbering.py::TestAddDocumentWithParagraphFields` | 3 |
| AC3.2 | Paste-in with 0-1 `<li value>` sets `auto_number_paragraphs = True` in DB | Integration | `tests/integration/test_paragraph_numbering.py::TestAddDocumentWithParagraphFields` | 3 |
| AC3.3 | Upload dialog shows detected state with override switch | Integration | `tests/integration/test_paragraph_numbering.py::TestUploadDialogAutoDetect` | 7 |
| AC4.1 | Auto-numbered document: `data-para` attributes injected on correct block elements | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes` | 4 |
| AC4.2 | Source-numbered document: `data-para` attributes use source numbers | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes` | 4 |
| AC4.3 | Margin numbers don't overlap with document content | Human | N/A (visual/CSS layout) | 4 |
| AC5.1 | Highlight on paragraph 3 shows `[3]` on annotation card | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef` | 5 |
| AC5.1 | Highlight on paragraph 3 — end-to-end wiring through `_add_highlight()` | Integration | `tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring` | 5 |
| AC5.2 | Highlight spanning paragraphs 3-5 shows `[3]-[5]` | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef` | 5 |
| AC5.2 | Multi-paragraph highlight — end-to-end wiring | Integration | `tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring` | 5 |
| AC5.3 | User can edit `para_ref` on existing annotation card | Unit | `tests/unit/test_annotation_doc.py::test_update_highlight_para_ref` | 7 |
| AC5.4 | Highlight on unnumbered block shows no `para_ref` | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef` | 5 |
| AC5.4 | Highlight on unnumbered block — end-to-end wiring | Integration | `tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring` | 5 |
| AC6.1 | PDF margin notes show `[N]` for annotations on numbered paragraphs | Unit | `tests/unit/export/test_highlight_spans.py` (new tests with `word_to_legal_para`) | 6 |
| AC6.1 | String-to-int key conversion at export call site | Unit | `tests/unit/export/test_pdf_export_para_map.py` | 6 |
| AC6.2 | Both auto-numbered and source-numbered docs produce correct PDF output | Unit | `tests/unit/export/test_highlight_spans.py` (parameterized: sequential + gapped maps) | 6 |
| AC7.1 | Toggle visible in workspace header area | Human | N/A (visual/layout) | 7 |
| AC7.2 | Toggling rebuilds `paragraph_map` and updates margin numbers | Integration | `tests/integration/test_paragraph_numbering.py::TestToggleParagraphNumbering` | 7 |
| AC7.3 | Toggling does NOT modify existing `para_ref` values on highlights | Integration | `tests/integration/test_paragraph_numbering.py::TestToggleParagraphNumbering` | 7 |
| AC8.1 | Mapping builder char offsets match `extract_text_from_html()` positions exactly | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestCharOffsetAlignment` | 2 |

### Infrastructure (no AC, operational verification)

| Concern | Test Type | Test File | Phase |
|---------|-----------|-----------|-------|
| New columns round-trip through SQLModel/PostgreSQL | Integration | `tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields` | 1 |
| Default values (`True`, `{}`) applied to new documents | Integration | `tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields` | 1 |
| `paragraph_map` JSON keys survive as strings after round-trip | Integration | `tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields` | 1 |
| Alembic migration applies and downgrades cleanly | Manual (CLI) | N/A | 1 |
| Cloned documents preserve `auto_number_paragraphs` and `paragraph_map` | Integration | `tests/integration/test_paragraph_numbering.py::TestClonePreservesParagraphFields` | 3 |
| Empty map `{}` passed to `inject_paragraph_attributes()` returns HTML unchanged | Unit | `tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes` | 4 |
| `word_to_legal_para=None` preserves existing export behaviour (no para_ref) | Unit | `tests/unit/export/test_highlight_spans.py` (existing + regression test) | 6 |

## Human Verification Required

| AC ID | Criterion | Justification | Verification Approach |
|-------|-----------|---------------|----------------------|
| AC4.3 | Margin numbers don't overlap with document content | CSS layout positioning (`position: absolute`, `left: -3rem`, padding adjustments) cannot be verified without a browser rendering engine. The correctness depends on the interaction between `doc-container` padding, the `::before` pseudo-element offset, font metrics, and viewport width. | **UAT (Phase 4 step 7):** Open workspaces with auto-numbered and source-numbered documents at default and narrow viewport widths. Confirm numbers sit in the left padding area, do not overlap body text, and remain aligned for single-digit and multi-digit numbers. Verify `user-select: none` prevents numbers from appearing in clipboard when copying document text. |
| AC7.1 | Toggle visible in workspace header area | The toggle's visibility and placement in the header row is a visual/layout concern. Integration tests can verify the toggle's functional behavior (data changes) but not that it renders in the correct visual location relative to copy protection and sharing controls. | **UAT (Phase 7 step 5):** Open a workspace. Confirm the "Auto-number" toggle/switch appears in the header area between the copy protection chip and sharing controls. Verify it is visible without scrolling and its label is legible. |
| AC3.3 | Upload dialog shows detected state with override switch (visual aspect) | The integration test in Phase 7 verifies the dialog's return value contract (tuple of content type + auto-number boolean). However, the visual presentation — that the switch is pre-set to the detected value, that the amber hint text appears when source numbering is detected, and that the switch label is clear — requires browser rendering. | **UAT (Phase 7 step 8):** Upload an AustLII HTML file. Confirm the content type dialog shows the auto-number switch defaulting to OFF with the "Source paragraph numbers detected" hint in amber. Upload a plain HTML file and confirm the switch defaults to ON with no hint. Toggle the switch and confirm the override takes effect. |
| AC5.3 | User can edit `para_ref` on existing annotation card (interaction) | The CRDT update method is unit-tested. However, the click-to-edit UX (label -> input swap on click, save on blur/Enter, swap back to label) is a NiceGUI DOM interaction that requires a browser. | **UAT (Phase 7 step 9):** On an annotation card with a `para_ref` value, click the para_ref label. Confirm it becomes an editable input. Type a new value and press Enter (or click away). Confirm the label updates and the value persists on page reload. |
| N/A | PDF export produces visually correct margin notes | Unit tests verify that `compute_highlight_spans()` receives correct `word_to_legal_para` data and that the LaTeX output contains `[N]` references. However, the final visual appearance in the compiled PDF (margin note positioning, font, alignment with highlight text) requires LaTeX compilation and visual inspection. | **UAT (Phase 6 steps 6-7):** Export a workspace with highlights on numbered paragraphs as PDF. Open the PDF and confirm `[N]` margin notes appear adjacent to the correct annotations. Repeat with both an auto-numbered and a source-numbered document. |
| N/A | Backfill script processes existing documents correctly | The script is run manually against a live database. Testing it requires a populated database with pre-existing documents. A dry-run mode provides a safety check, but the actual backfill modifies production-like data. | **UAT (Phase 3 steps 5-6):** Run `uv run backfill-paragraph-maps --dry-run` and confirm it reports the correct count of documents that would be updated. Run `uv run backfill-paragraph-maps` and confirm it completes without errors. Spot-check a few documents in the DB to verify their `paragraph_map` is populated and `auto_number_paragraphs` is set correctly (especially for any AustLII documents). |

## Rationalization Notes

### AC coverage is complete

Every sub-criterion from AC1 through AC8 maps to at least one automated test or a documented human verification entry. Several criteria have both unit and integration coverage:

- **AC3.1/AC3.2** are tested at two levels: the pure `detect_source_numbering()` function (unit, Phase 2) and the document save path that calls it (integration, Phase 3).
- **AC5.1/AC5.2/AC5.4** are tested at two levels: the pure `lookup_para_ref()` function (unit, Phase 5) and the end-to-end wiring through `_add_highlight()` (integration, Phase 5).
- **AC6.1/AC6.2** are tested at two levels: the `compute_highlight_spans()` output (unit, Phase 6 in existing test file) and the string-to-int key conversion at the `pdf_export.py` call site boundary (unit, Phase 6 in new test file).

### Phase 1 has no AC coverage by design

Phase 1 is pure infrastructure (model columns + migration). Its correctness is verified operationally by integration tests that exercise the round-trip. No acceptance criterion directly maps to "columns exist" -- they all require downstream behavior built in later phases.

### Human verification concentrates on CSS/visual and UX interaction

The five human verification items share a common characteristic: they require a browser rendering engine or interactive DOM behavior that automated unit/integration tests cannot exercise. All five could theoretically be covered by Playwright E2E tests, but the implementation plans note that E2E tests for these are lower priority than the integration tests that verify data integrity. If E2E tests are added later, they would use the `data-testid` attributes specified in the implementation plans (`paragraph-toggle`, `auto-number-switch`, `para-ref-label`, `para-ref-input`).

### AC8.1 is the critical correctness constraint

The char-offset alignment test (AC8.1) is the single most important automated test. If `build_paragraph_map()` char offsets diverge from `extract_text_from_html()`, every downstream surface (margin numbers, card `para_ref`, PDF export) will display wrong paragraph references. The Phase 2 `TestCharOffsetAlignment` class tests this with multiple HTML samples, verifying that every key in the map is a valid index into the extracted text and falls at the expected block element boundary.

### JSON key type coercion is tested at every boundary

The `dict[int, int]` -> JSON -> `dict[str, int]` round-trip is a known hazard. Tests cover:
- Phase 1 integration: keys are strings after DB round-trip
- Phase 5 unit: `lookup_para_ref()` accepts `dict[str, int]` (string keys)
- Phase 6 unit: `test_pdf_export_para_map.py` verifies string-to-int conversion at export boundary

## Test Execution Commands

```bash
# Phase 1: Model + migration integration tests
uv run pytest tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields -v

# Phase 2: Mapping builder unit tests (AC1, AC2, AC3 detection, AC8)
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py -v

# Phase 3: Document save integration tests (AC3 persistence, cloning)
uv run pytest tests/integration/test_paragraph_numbering.py::TestAddDocumentWithParagraphFields -v
uv run pytest tests/integration/test_paragraph_numbering.py::TestClonePreservesParagraphFields -v

# Phase 4: Attribute injection unit tests (AC4)
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes -v

# Phase 5: para_ref lookup unit tests + integration wiring (AC5)
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef -v
uv run pytest tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring -v

# Phase 6: PDF export unit tests (AC6)
uv run pytest tests/unit/export/test_highlight_spans.py -v -k "para"
uv run pytest tests/unit/export/test_pdf_export_para_map.py -v

# Phase 7: CRDT update + toggle + dialog tests (AC5.3, AC7, AC3.3)
uv run pytest tests/unit/test_annotation_doc.py -v -k "para_ref"
uv run pytest tests/integration/test_paragraph_numbering.py::TestToggleParagraphNumbering -v
uv run pytest tests/integration/test_paragraph_numbering.py::TestUploadDialogAutoDetect -v

# All paragraph numbering tests at once
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py tests/integration/test_paragraph_numbering.py tests/unit/export/test_pdf_export_para_map.py tests/unit/test_annotation_doc.py -v -k "para"

# All unit + integration tests (standard CI gate)
uv run test-all

# Type checking (must be clean at every phase)
uvx ty check
```
