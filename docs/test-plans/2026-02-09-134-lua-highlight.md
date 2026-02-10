# Human Test Plan: 134-lua-highlight

Generated: 2026-02-10
Coverage validation: PASS (20/20 automated ACs, 91 tests)

## Prerequisites

- TinyTeX installed (`uv run python scripts/setup_latex.py`)
- `mutool` available on PATH (part of MuPDF tools package)
- Working Pandoc installation with Lua filter support
- All automated tests passing:
  ```bash
  uv run pytest tests/unit/export/test_highlight_spans.py \
    tests/unit/export/test_module_split.py \
    tests/unit/export/test_pipeline_cleanup.py \
    tests/integration/test_highlight_lua_filter.py \
    tests/integration/test_highlight_latex_elements.py -v
  ```
- The annotation UI is functional (currently blocked by a regression on `main` -- verify before proceeding with AC5.1/AC5.2)

## Phase 1: PDF Compilation Smoke Test

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | Run `uv run pytest tests/integration/test_pdf_export.py -v` | All tests pass. At least one test generates a PDF file. |
| 1.2 | Verify TinyTeX is used for compilation by checking that latexmk resolves to `~/.TinyTeX/bin/*/latexmk` | Path does NOT fall back to system PATH. |

## Phase 2: AC5.1 -- Lawlis v R Fixture Visual Equivalence

Purpose: Confirm the Lawlis v R fixture produces a PDF with highlight rectangles matching the pre-refactor baseline.

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Run the annotation PDF export with the Lawlis v R fixture data through the UI or via `export_annotation_pdf()`. | A PDF file is produced without compilation errors. |
| 2.2 | Open the generated PDF. Visually inspect for coloured highlight rectangles. | Highlight rectangles are visible, coloured appropriately, and positioned over the correct text ranges. |
| 2.3 | Run `mutool draw -F trace <path-to-pdf> 1` on the first page. Count coloured rectangle operations (`fill_path` with non-black/non-white fill colours). | Count matches the pre-refactor baseline. |
| 2.4 | Compare colour values in trace output against expected tag colours (jurisdiction blue, evidence orange, etc.). | Colours match tag colour definitions in `preamble.py`. |

## Phase 3: AC5.2 -- E7 Perverse Overlap Visual Equivalence

Purpose: Confirm the E7 experiment (4 overlapping highlights crossing a heading boundary) produces equivalent output.

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | Construct HTML with `<h2>Heading text</h2><p>Body paragraph text</p>` and 4 overlapping highlights covering various ranges across the heading/paragraph boundary. | Source HTML and highlight definitions are available. |
| 3.2 | Run through the new pipeline: `compute_highlight_spans()` + Pandoc with `highlight.lua` + LuaLaTeX compilation. | A PDF file is produced without errors. |
| 3.3 | Run `mutool draw -F trace <path-to-pdf> 1` on the output PDF. | Trace output is produced successfully. |
| 3.4 | Count coloured rectangles. The E7 baseline established 18 coloured rectangles across 9 regions. | Rectangle count matches 18 (or established baseline). |
| 3.5 | Visually inspect for "one, two, many" stacking tiers: single=thin 1pt underline, double=stacked 2pt+1pt underlines, triple+=single thick 4pt many-dark underline. | All three stacking tiers render correctly with distinct visual appearance. |
| 3.6 | Verify highlights in heading and paragraph are visually separate (not crossing block boundary). | Heading and body each have distinct highlight rectangles. |

## Phase 4: End-to-End Annotation Export

Purpose: Verify the full user-facing workflow.

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | Start app with `uv run python -m promptgrimoire`. Navigate to `/annotation`. | Annotation page loads without errors. |
| 4.2 | Paste an HTML conversation fixture (e.g., `tests/fixtures/conversations/claude_cooking.html`). | HTML renders with character-level selection available. |
| 4.3 | Create 3 overlapping highlights across different text ranges with different tags. Ensure at least one crosses a block boundary. | Highlights created with coloured indicators in UI. |
| 4.4 | Add an annotation comment to one highlight. | Comment saved and visible. |
| 4.5 | Export to PDF. | PDF generated/downloaded. |
| 4.6 | Open PDF. Verify: (a) all 3 highlights visible with correct colours, (b) cross-block highlight split at boundary, (c) annotation margin note appears, (d) no literal `\annot` text in PDF. | All elements render correctly. |

## Human Verification Required

| Criterion | Why Manual | Steps |
|-----------|-----------|-------|
| AC5.1 Lawlis v R visual equivalence | Requires TinyTeX + mutool, multi-second compilation, brittle rectangle-count parsing | Phase 2 (2.1--2.4) |
| AC5.2 E7 perverse overlap equivalence | Same infrastructure + visual inspection of stacking model | Phase 3 (3.1--3.6) |

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|---------------------|---------------|-------------|
| AC1.1 Cross-block split | `test_highlight_spans.py::TestAC1_1_CrossBlockSplit` | -- |
| AC1.2 3+ overlapping | `test_highlight_spans.py::TestAC1_2_OverlappingHighlights` | -- |
| AC1.3 Single-block span | `test_highlight_spans.py::TestAC1_3_SingleBlockHighlight` | -- |
| AC1.4 No highlights | `test_highlight_spans.py::TestAC1_4_NoHighlights` | -- |
| AC1.5 No cross-block | `test_highlight_spans.py::TestAC1_5_NoCrossBlockSpan` | -- |
| AC2.1 Single tier | `test_highlight_lua_filter.py::TestSingleHighlight` | -- |
| AC2.2 Two-tier stacking | `test_highlight_lua_filter.py::TestTwoHighlights` | -- |
| AC2.3 Many-tier | `test_highlight_lua_filter.py::TestManyHighlights` | -- |
| AC2.4 Annotation emission | `test_highlight_lua_filter.py::TestAnnotation` | -- |
| AC2.5 Heading texorpdfstring | `test_highlight_lua_filter.py::TestHeading` | -- |
| AC2.6 No-hl pass-through | `test_highlight_lua_filter.py::TestNoHlAttribute` | -- |
| AC3.1 Module line counts | `test_module_split.py::TestAC3_1_LineCounts` | -- |
| AC3.2 Symbol placement | `test_module_split.py::TestAC3_2_SymbolPlacement` | -- |
| AC3.3 Public API imports | `test_module_split.py::TestAC3_3_PublicAPI` | -- |
| AC4.1 pylatexenc removed | `test_pipeline_cleanup.py::TestAC4_1_PylatexencRemoved` | -- |
| AC4.2 latex.py deleted | `test_pipeline_cleanup.py::TestAC4_2_LatexPyDeleted` | -- |
| AC4.3 P4 test files deleted | `test_pipeline_cleanup.py::TestAC4_3_P4TestFilesDeleted` | -- |
| AC4.4 P4 classes removed | `test_pipeline_cleanup.py::TestAC4_4_P4ClassesRemoved` | -- |
| AC4.5 Lark removed | `test_pipeline_cleanup.py::TestAC4_5_LarkRemoved` | -- |
| AC4.6 _format_annot removed | `test_pipeline_cleanup.py::TestAC4_6_FormatAnnotRemoved` | -- |
| AC5.1 Lawlis visual equiv | -- | Phase 2 (2.1--2.4) |
| AC5.2 E7 perverse overlap | -- | Phase 3 (3.1--3.6) |
| AC5.3 Integration tests pass | `test_pipeline_cleanup.py::TestAC5_3` + `test_highlight_latex_elements.py` (18 tests) | -- |
