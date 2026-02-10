# 134-lua-highlight Test Requirements

Maps each acceptance criterion to automated tests or documented human verification.

---

## AC1: Pre-Pandoc region computation

### 134-lua-highlight.AC1.1

**Criterion:** Given overlapping highlights spanning a block boundary (`<h1>` into `<p>`), the HTML span insertion produces non-overlapping `<span>` elements pre-split at the block boundary, each with `data-hl` listing active highlight indices and `data-colors` listing active colours.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_highlight_spans.py`
- **What it verifies:** Calls `compute_highlight_spans()` with HTML containing `<h1>Title</h1><p>Body text</p>` and a highlight spanning from the heading into the paragraph. Asserts the output contains two separate `<span>` elements -- one inside the `<h1>` and one inside the `<p>` -- each with correct `data-hl` and `data-colors` attributes. Parses the output HTML with selectolax and asserts no single `<span>` straddles the block boundary.

---

### 134-lua-highlight.AC1.2

**Criterion:** Given 3+ overlapping highlights on the same text, the span carries `data-hl="0,1,2"` and `data-colors="blue,orange,green"` (comma-separated, matching input order).

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_highlight_spans.py`
- **What it verifies:** Calls `compute_highlight_spans()` with HTML `<p>overlapping text here</p>` and three highlights covering overlapping ranges. Asserts the overlap region's `<span>` has `data-hl="0,1,2"` and `data-colors` listing all three colour names in comma-separated order matching input order.

---

### 134-lua-highlight.AC1.3

**Criterion:** Given a highlight that doesn't cross any block boundary, a single `<span>` is emitted wrapping the full range.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_highlight_spans.py`
- **What it verifies:** Calls `compute_highlight_spans()` with HTML `<p>simple highlight</p>` and one highlight covering a substring entirely within the `<p>`. Asserts exactly one `<span>` with `data-hl` is present in the output.

---

### 134-lua-highlight.AC1.4

**Criterion:** Given text with no highlights, no `<span>` elements are inserted.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_highlight_spans.py`
- **What it verifies:** Calls `compute_highlight_spans()` with HTML `<p>no highlights</p>` and an empty highlight list. Asserts the output is identical to the input (no `<span>` elements with `data-hl` added).

---

### 134-lua-highlight.AC1.5

**Criterion (failure mode):** Given a cross-block highlight, the span is NOT left crossing the block boundary (Pandoc would silently destroy it).

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_highlight_spans.py`
- **What it verifies:** Calls `compute_highlight_spans()` with HTML `<h2>Heading</h2><p>Body</p>` and a highlight spanning across both. Parses the output and asserts that no single `<span>` crosses the `</h2><p>` boundary. Each block element gets its own `<span>`. This is the inverse assertion of AC1.1 -- specifically tests the failure mode where a naive implementation would emit a cross-block span.

---

## AC2: Pandoc Lua filter rendering

### 134-lua-highlight.AC2.1

**Criterion:** Given a span with `hl="0"` and `colors="blue"`, the Lua filter emits `\highLight[tag-jurisdiction-light]{\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{text}}` (single highlight tier).

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc as a subprocess with HTML `<p><span data-hl="0" data-colors="tag-jurisdiction-light">highlighted text</span></p>` and the `highlight.lua` filter. Asserts the LaTeX output contains `\highLight[tag-jurisdiction-light]{` and `\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{`. Tests actual Pandoc behaviour, not a simulated Lua environment.

---

### 134-lua-highlight.AC2.2

**Criterion:** Given a span with `hl="0,1"` and `colors="blue,orange"`, the filter emits nested `\highLight` with stacked `\underLine` (2-highlight tier: 2pt outer, 1pt inner).

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc with HTML containing `data-hl="0,1" data-colors="tag-jurisdiction-light,tag-evidence-light"`. Asserts the LaTeX output contains two nested `\highLight` wrappers and stacked `\underLine` commands with outer 2pt/-5pt and inner 1pt/-3pt using the corresponding dark colour variants.

---

### 134-lua-highlight.AC2.3

**Criterion:** Given a span with `hl="0,1,2"` and 3+ colours, the filter emits nested `\highLight` with single thick `\underLine[color=many-dark, height=4pt, bottom=-5pt]` (many tier).

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc with HTML containing `data-hl="0,1,2" data-colors="tag-jurisdiction-light,tag-evidence-light,tag-ratio-light"`. Asserts three nested `\highLight` wrappers and a single `\underLine[color=many-dark, height=4pt, bottom=-5pt]`.

---

### 134-lua-highlight.AC2.4

**Criterion:** Given a span with `annot` attribute, the filter emits `\annot{tag-name}{\textbf{Tag Name}\par{\scriptsize Author}}` as `RawInline` after the highlighted content.

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc with HTML containing a span with `data-hl`, `data-colors`, and `data-annots` (pre-formatted LaTeX annotation string). Asserts the `\annot{...}` string appears in the LaTeX output AFTER the closing braces of the highlight/underline wrapping.

---

### 134-lua-highlight.AC2.5

**Criterion:** Given a highlighted span inside a heading, Pandoc auto-wraps in `\texorpdfstring{}` (no special handling in filter). Verified by E2b experiment.

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc with HTML `<h2><span data-hl="0" data-colors="tag-jurisdiction-light">heading text</span></h2>`. Asserts the LaTeX output contains `\texorpdfstring{` wrapping the highlighted content. This validates that Pandoc's native `\texorpdfstring` behaviour works with the Lua filter and no special handling is needed in `highlight.lua`.

---

### 134-lua-highlight.AC2.6

**Criterion (failure mode):** Given a span with NO `hl` attribute, the filter passes it through unchanged.

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_lua_filter.py`
- **What it verifies:** Runs Pandoc with HTML `<p><span class="other">plain text</span></p>` and the `highlight.lua` filter. Asserts the LaTeX output contains NO `\highLight` or `\underLine` commands. The span is passed through unchanged by the filter's guard clause.

---

## AC3: Module split

### 134-lua-highlight.AC3.1

**Criterion:** `latex.py` is split into modules where no single file exceeds ~400 lines.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_module_split.py`
- **What it verifies:** Counts lines in `preamble.py` and `pandoc.py` and asserts each is under 450 lines (allowing some growth margin). After Phase 4, also asserts `latex.py` no longer exists.

---

### 134-lua-highlight.AC3.2

**Criterion:** Module boundaries align with DFD processes (marker insertion, Pandoc conversion, preamble/document assembly).

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_module_split.py`
- **What it verifies:** Asserts that `preamble.py` contains `build_annotation_preamble` and `generate_tag_colour_definitions` (P5 functions). Asserts that `pandoc.py` contains `convert_html_to_latex` and `convert_html_with_annotations` (P3 functions). Uses `hasattr` or direct import assertions to verify function location.

---

### 134-lua-highlight.AC3.3

**Criterion:** All imports from `pdf_export.py` and `annotation.py` continue to resolve (public API preserved via `__init__.py` re-exports or updated imports).

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_module_split.py`
- **What it verifies:** Asserts these imports resolve without error:
  - `from promptgrimoire.export import convert_html_to_latex`
  - `from promptgrimoire.export import export_annotation_pdf`
  - `from promptgrimoire.export.preamble import build_annotation_preamble`
  - `from promptgrimoire.export.pandoc import convert_html_with_annotations`
  - `from promptgrimoire.export.pdf_export import export_annotation_pdf`

---

## AC4: Deletion and cleanup

### 134-lua-highlight.AC4.1

**Criterion:** `pylatexenc` is removed from `pyproject.toml` dependencies.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Reads `pyproject.toml`, extracts the `[project] dependencies` section (between `dependencies = [` and the closing `]`), and asserts `pylatexenc` does not appear in that section. Note: `pylatexenc` is intentionally retained in dev dependencies for `tests/helpers/latex_parse.py`.

---

### 134-lua-highlight.AC4.2

**Criterion:** All Process 4 functions are deleted: `tokenize_markers`, `build_regions`, `walk_and_wrap`, `_wrap_region_ast`, `_classify_node`, `_classify_macro`, `_walk_nodes`, `_split_text_at_boundaries`, `generate_highlighted_latex`, `generate_underline_wrapper`, `generate_highlight_wrapper`, `_wrap_content_with_nested_highlights`, `_wrap_content_with_highlight`, `_replace_markers_with_annots`, `_move_annots_outside_restricted`, `_brace_depth_at`, `_find_closing_brace_at_depth`, `_find_matching_brace`, `_extract_env_boundaries`, `_extract_annot_command`, `_strip_texorpdfstring`.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Asserts that `src/promptgrimoire/export/latex.py` does not exist (`not Path(...).exists()`). Since all P4 functions lived exclusively in `latex.py`, deletion of the file guarantees deletion of all listed functions.

---

### 134-lua-highlight.AC4.3

**Criterion:** Process 4 test files are deleted: `test_region_builder.py`, `test_latex_generator.py`, `test_walk_and_wrap.py`, `test_marker_lexer.py`, `test_overlapping_highlights.py`.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Asserts each of the five test files does not exist:
  - `tests/unit/export/test_region_builder.py`
  - `tests/unit/export/test_latex_generator.py`
  - `tests/unit/export/test_walk_and_wrap.py`
  - `tests/unit/export/test_marker_lexer.py`
  - `tests/unit/test_overlapping_highlights.py`

---

### 134-lua-highlight.AC4.4

**Criterion:** `MarkerToken`, `MarkerTokenType`, `Region` classes are deleted.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Asserts that importing `MarkerToken`, `MarkerTokenType`, or `Region` from `promptgrimoire.export` raises `ImportError`. These classes lived in `latex.py` which is deleted.

---

### 134-lua-highlight.AC4.5

**Criterion:** The Lark grammar (`_MARKER_GRAMMAR`) and marker constants (`HLSTART_TEMPLATE`, `HLEND_TEMPLATE`, etc.) are deleted.

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Asserts `lark` does not appear in `pyproject.toml` dependencies (the grammar was the sole consumer of `lark`). Asserts `latex.py` does not exist (the grammar and constants were defined there). Note: `marker_constants.py` is intentionally NOT deleted -- it is still used by `insert_markers_into_dom` in `html_input.py`.

---

### 134-lua-highlight.AC4.6

**Criterion:** `_format_annot` is deleted from Python (annotation formatting moves to Lua filter).

**Verification:** Automated test (unit)

- **Test file:** `tests/unit/export/test_pipeline_cleanup.py`
- **What it verifies:** Asserts that `_format_annot` is not importable from any `promptgrimoire.export` module. The replacement function `format_annot_latex` in `highlight_spans.py` produces pre-formatted LaTeX strings for the `data-annots` span attribute, which the Lua filter emits as `RawInline`.

---

## AC5: Visual equivalence

### 134-lua-highlight.AC5.1

**Criterion:** The Lawlis v R fixture produces a PDF with identical highlight rectangles (verified via `mutool draw -F trace` colour rectangle count).

**Verification:** Human verification (UAT)

- **Justification:** This criterion requires end-to-end PDF compilation via LuaLaTeX and pixel-level analysis via `mutool draw -F trace`. Automating this requires TinyTeX + mutool installed in CI, PDF compilation (multi-second), and brittle rectangle-count parsing. The E7 experiment established the baseline count (18 rectangles for the perverse overlap case). During UAT, the verifier should:
  1. Run `uv run pytest tests/integration/test_pdf_export.py -v` to generate the Lawlis PDF
  2. Run `mutool draw -F trace` on the output PDF
  3. Count coloured rectangles and compare against the pre-refactor baseline
  4. Visually inspect that highlight colours and positions match

---

### 134-lua-highlight.AC5.2

**Criterion:** The E7 perverse overlap test case (4 overlapping highlights, heading boundary) produces equivalent output through the new pipeline.

**Verification:** Human verification (UAT)

- **Justification:** Same as AC5.1 -- requires PDF compilation and `mutool` analysis. The E7 experiment (in `experiments/e7-perverse-overlap/`) established a reference PDF with 9 regions, 18 coloured rectangles, and all stacking tiers exercised. During UAT, the verifier should:
  1. Run the E7 test case HTML through the new pipeline (`compute_highlight_spans` + `highlight.lua` + LuaLaTeX)
  2. Run `mutool draw -F trace` on the output PDF
  3. Compare rectangle count (should be 18) and colour distribution against the E7 baseline
  4. Visually inspect that the "one, two, many" stacking tiers render identically

---

### 134-lua-highlight.AC5.3

**Criterion:** All integration tests in `test_highlight_latex_elements.py` pass with the new pipeline.

**Verification:** Automated test (integration)

- **Test file:** `tests/integration/test_highlight_latex_elements.py` (existing file, kept and updated)
- **What it verifies:** The existing integration test suite exercises the full annotation pipeline (`convert_html_with_annotations`) with various highlight configurations. After Phase 4 rewires the pipeline to use `compute_highlight_spans` + `highlight.lua`, these tests run against the new pipeline. Passing confirms functional equivalence for all tested highlight patterns.
- **Secondary validation in:** `tests/unit/export/test_pipeline_cleanup.py` -- asserts the test file exists and its imports resolve, ensuring the integration tests were not accidentally broken or deleted during cleanup.

---

## Summary

| AC | Type | Test File | Phase |
|----|------|-----------|-------|
| AC1.1 | Unit (automated) | `tests/unit/export/test_highlight_spans.py` | 2 |
| AC1.2 | Unit (automated) | `tests/unit/export/test_highlight_spans.py` | 2 |
| AC1.3 | Unit (automated) | `tests/unit/export/test_highlight_spans.py` | 2 |
| AC1.4 | Unit (automated) | `tests/unit/export/test_highlight_spans.py` | 2 |
| AC1.5 | Unit (automated) | `tests/unit/export/test_highlight_spans.py` | 2 |
| AC2.1 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC2.2 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC2.3 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC2.4 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC2.5 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC2.6 | Integration (automated) | `tests/integration/test_highlight_lua_filter.py` | 3 |
| AC3.1 | Unit (automated) | `tests/unit/export/test_module_split.py` | 1 |
| AC3.2 | Unit (automated) | `tests/unit/export/test_module_split.py` | 1 |
| AC3.3 | Unit (automated) | `tests/unit/export/test_module_split.py` | 1 |
| AC4.1 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC4.2 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC4.3 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC4.4 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC4.5 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC4.6 | Unit (automated) | `tests/unit/export/test_pipeline_cleanup.py` | 4 |
| AC5.1 | Human verification (UAT) | N/A | 4 |
| AC5.2 | Human verification (UAT) | N/A | 4 |
| AC5.3 | Integration (automated) | `tests/integration/test_highlight_latex_elements.py` | 4 |

**Totals:** 20 automated (14 unit + 6 integration), 2 human verification (UAT)
