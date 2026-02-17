# 134-lua-highlight Implementation Plan — Phase 4: Wire new pipeline and delete old code

**Goal:** Rewire `convert_html_with_annotations` to use the new pipeline (Phase 2's `compute_highlight_spans` + Phase 3's `highlight.lua`), delete all Process 4 code (~900 lines), delete `latex.py` entirely, and remove the `pylatexenc` and `lark` dependencies.

**Architecture:** This is the cutover phase. Update `convert_html_with_annotations` (in `pandoc.py` after Phase 1) to call `compute_highlight_spans()` instead of `insert_markers_into_dom()`, pass `highlight.lua` to Pandoc, and remove the post-Pandoc marker replacement calls. Then systematically delete all P4 functions, classes, constants, the Lark grammar, and P2 legacy code. Delete `latex.py` (now empty). Delete Process 4 test files. Remove `pylatexenc` and `lark` from `pyproject.toml`.

**Tech Stack:** Python 3.14, no new dependencies (removing two)

**Scope:** Phase 4 of 4 from original design

**Codebase verified:** 2026-02-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 134-lua-highlight.AC4: Deletion and cleanup (DoD items 3, 4)
- **134-lua-highlight.AC4.1 Success:** `pylatexenc` is removed from `pyproject.toml` dependencies.
- **134-lua-highlight.AC4.2 Success:** All Process 4 functions are deleted: `tokenize_markers`, `build_regions`, `walk_and_wrap`, `_wrap_region_ast`, `_classify_node`, `_classify_macro`, `_walk_nodes`, `_split_text_at_boundaries`, `generate_highlighted_latex`, `generate_underline_wrapper`, `generate_highlight_wrapper`, `_wrap_content_with_nested_highlights`, `_wrap_content_with_highlight`, `_replace_markers_with_annots`, `_move_annots_outside_restricted`, `_brace_depth_at`, `_find_closing_brace_at_depth`, `_find_matching_brace`, `_extract_env_boundaries`, `_extract_annot_command`, `_strip_texorpdfstring`.
- **134-lua-highlight.AC4.3 Success:** Process 4 test files are deleted: `test_region_builder.py`, `test_latex_generator.py`, `test_walk_and_wrap.py`, `test_marker_lexer.py`, `test_overlapping_highlights.py`.
- **134-lua-highlight.AC4.4 Success:** `MarkerToken`, `MarkerTokenType`, `Region` classes are deleted.
- **134-lua-highlight.AC4.5 Success:** The Lark grammar (`_MARKER_GRAMMAR`) and marker constants (`HLSTART_TEMPLATE`, `HLEND_TEMPLATE`, etc.) are deleted.
- **134-lua-highlight.AC4.6 Success:** `_format_annot` is deleted from Python (annotation formatting moves to Lua filter).

### 134-lua-highlight.AC5: Visual equivalence (DoD item 5)
- **134-lua-highlight.AC5.1 Success:** The Lawlis v R fixture produces a PDF with identical highlight rectangles (verified via `mutool draw -F trace` colour rectangle count).
- **134-lua-highlight.AC5.2 Success:** The E7 perverse overlap test case (4 overlapping highlights, heading boundary) produces equivalent output through the new pipeline.
- **134-lua-highlight.AC5.3 Success:** All integration tests in `test_highlight_latex_elements.py` pass with the new pipeline.

---

## Design Decisions

1. **`latex.py` is deleted entirely** — after Phase 1 moves P5+P3 and Phase 4 deletes P2+P4, the file is empty. All references updated in earlier phases.
2. **`convert_html_to_latex()` signature changes** from `filter_path: Path | None` to `filter_paths: list[Path]` to support passing both `highlight.lua` and platform-specific filters.
3. **Annotation formatting logic adapted from `_format_annot`** into a helper in `highlight_spans.py` that produces pre-formatted `\annot{...}{...}` LaTeX strings for the `data-annots` attribute. The original `_format_annot` is then deleted.
4. **Both `lark` and `pylatexenc`** removed from `pyproject.toml` — both are only used in `latex.py`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add annotation formatting to `highlight_spans.py`

**Verifies:** 134-lua-highlight.AC4.6

**Files:**
- Modify: `src/promptgrimoire/export/highlight_spans.py`

**Implementation:**

Add a `format_annot_latex()` function to `highlight_spans.py` that produces a pre-formatted `\annot{colour}{content}` LaTeX string. This adapts the logic from `_format_annot()` (latex.py:978-1045) for use by `compute_highlight_spans()` when populating the `data-annots` attribute.

The function takes a highlight dict and optional para_ref string, and returns a LaTeX string. It must:

1. Extract `tag`, `author`, `comments`, `created_at` from the highlight dict
2. Sanitise the tag slug: `tag.replace("_", "-")` for the colour name
3. Format the tag display name: `tag.replace("_", " ").title()`
4. Build margin content:
   - Line 1: `\textbf{Tag Display}` (with optional para_ref)
   - Line 2: `\par{\scriptsize Author}` (with optional timestamp via `_format_timestamp`)
   - Comments section: `\par\hrulefill` separator, then each comment formatted
5. Use `escape_unicode_latex()` from `unicode_latex.py` for all text content
6. Return `\annot{tag-slug}{margin_content}`

Import `_format_timestamp` and `_strip_test_uuid` from `preamble.py` (moved there in Phase 1). Import `escape_unicode_latex` from `unicode_latex.py`.

Update `compute_highlight_spans()` to call `format_annot_latex()` when populating the `data-annots` attribute on the last span of each highlight.

**Testing:**

Add a test to `tests/unit/export/test_highlight_spans.py` verifying that a highlight with tag, author, and comments produces the expected `\annot{...}{...}` LaTeX string in the `data-annots` attribute.

Run: `uv run pytest tests/unit/export/test_highlight_spans.py -v`
Expected: All tests pass.

**Commit:** `feat: add format_annot_latex to highlight_spans.py for pre-formatted annotations`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Rewire `convert_html_with_annotations` to use new pipeline

**Verifies:** 134-lua-highlight.AC5.3

**Files:**
- Modify: `src/promptgrimoire/export/pandoc.py` (where `convert_html_with_annotations` lives after Phase 1)

**Implementation:**

Update `convert_html_with_annotations()` in `pandoc.py`:

1. **Change signature:** Replace `filter_path: Path | None = None` with `filter_paths: list[Path] | None = None` (default None, treated as empty list). **Keep `word_to_legal_para` parameter** — it is passed through to `compute_highlight_spans()`. **Remove `# noqa: ARG001`** from the `tag_colours` parameter — it is no longer unused since it's now passed to `compute_highlight_spans()`.

2. **Replace marker insertion with span insertion:**
   - Remove: `marked_html, marker_highlights = insert_markers_into_dom(html, highlights)`
   - Add: `span_html = compute_highlight_spans(html, highlights, tag_colours, word_to_legal_para=word_to_legal_para)`
   - Import `compute_highlight_spans` from `highlight_spans.py`
   - **Note:** `word_to_legal_para` (maps char index → legal paragraph number) was previously consumed by `_replace_markers_with_annots()` to resolve `para_ref` for annotation margin notes. In the new pipeline, `compute_highlight_spans()` resolves `para_ref` during span insertion by looking up each highlight's `start_char` in the mapping, then passes the resolved `para_ref` to `format_annot_latex()` when building the `data-annots` attribute. The `compute_highlight_spans()` signature must accept `word_to_legal_para: dict[int, int | None] | None = None`.

3. **Always include `highlight.lua`:**
   - Compute highlight filter path: `_HIGHLIGHT_FILTER = Path(__file__).parent / "filters" / "highlight.lua"`
   - Build combined filter list: start with `[_HIGHLIGHT_FILTER]`, extend with caller's `filter_paths` if provided

4. **Remove post-Pandoc marker processing:**
   - Remove: `result = _replace_markers_with_annots(latex, marker_highlights, word_to_legal_para)`
   - Remove: `return _move_annots_outside_restricted(result)`
   - Replace with: `return latex` (Pandoc + Lua filter handles everything)

5. **Remove `_strip_control_chars` call** — control char stripping can happen in `compute_highlight_spans` if needed, or during HTML normalisation.

6. **Update `convert_html_to_latex`** to accept `filter_paths: list[Path]` instead of `filter_path: Path | None`:
   - Change signature
   - Replace single `--lua-filter` extension with a loop: `for fp in filter_paths: cmd.extend(["--lua-filter", str(fp)])`

7. **Remove `_strip_texorpdfstring` call** from `convert_html_to_latex()` — no longer needed (see issue #136).

8. **Update imports:** Remove imports of `insert_markers_into_dom`, `_replace_markers_with_annots`, `_move_annots_outside_restricted` from `latex.py`. Add import of `compute_highlight_spans`.

**Also update `pdf_export.py`:**
- Change `filter_path=_LIBREOFFICE_FILTER` to `filter_paths=[_LIBREOFFICE_FILTER]` at the call site (line ~311).

**Testing:**

Run: `uv run pytest tests/integration/test_highlight_latex_elements.py -v`
Expected: All integration tests pass with the new pipeline.

Run: `uv run test-all`
Expected: Full suite passes.

**Commit:** `feat: rewire convert_html_with_annotations to use highlight spans + Lua filter`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Delete all Process 4 code and `latex.py`

**Verifies:** 134-lua-highlight.AC4.1, 134-lua-highlight.AC4.2, 134-lua-highlight.AC4.3, 134-lua-highlight.AC4.4, 134-lua-highlight.AC4.5, 134-lua-highlight.AC4.6

**Files:**
- Delete: `src/promptgrimoire/export/latex.py`
- Modify: `pyproject.toml` (remove `pylatexenc` and `lark` dependencies)

**Implementation:**

1. **Delete `src/promptgrimoire/export/latex.py` entirely.** After Phase 1 moved P5 functions to `preamble.py` and P3 functions to `pandoc.py`, and Task 2 above rewired the pipeline, `latex.py` contains only dead P4 code. Deleting the file removes:
   - All 22 P4 functions (AC4.2)
   - `MarkerTokenType`, `MarkerToken`, `Region` classes (AC4.4)
   - `_MARKER_GRAMMAR`, `_HLSTART_TEMPLATE`, `_HLEND_TEMPLATE`, and marker constants local to `latex.py` (AC4.5). **Note:** `src/promptgrimoire/export/marker_constants.py` is NOT deleted — it is still used by `insert_markers_into_dom` in `html_input.py`, which remains a public export of the `input_pipeline` module.
   - `_format_annot` (AC4.6 — its logic was adapted into `highlight_spans.py` in Task 1)
   - `_insert_markers_into_html` (P2 legacy)
   - `_escape_html_text_content` (P2 legacy, unused in production)
   - `_strip_texorpdfstring` (no longer needed)

2. **Remove `pylatexenc` from main dependencies only:**
   - Delete line 30: `"pylatexenc>=2.10",` (main dependencies)
   - **Keep** line 138: `"pylatexenc>=2.10",` (dev dependencies) — still needed by `tests/helpers/latex_parse.py` which is used by `test_latex_string_functions.py` for structural LaTeX assertions

3. **Remove `lark` from `pyproject.toml`:**
   - Delete line 31: `"lark>=1.1.0",` (main dependencies)

4. **Delete Process 4 test files (AC4.3):**
   - Delete: `tests/unit/export/test_region_builder.py`
   - Delete: `tests/unit/export/test_latex_generator.py`
   - Delete: `tests/unit/export/test_walk_and_wrap.py`
   - Delete: `tests/unit/export/test_marker_lexer.py`
   - Delete: `tests/unit/test_overlapping_highlights.py`

5. **Migrate `tests/unit/export/test_latex_string_functions.py`:**
   - After Phase 1, this file imports `ANNOTATION_PREAMBLE_BASE`, `_escape_latex`, `_format_timestamp`, `generate_tag_colour_definitions` from `preamble.py` and `_format_annot` from `latex.py`.
   - When `latex.py` is deleted, `_format_annot` is no longer importable. Three test classes use it: `TestFormatAnnot` (line 139), `TestCompilationValidation` (line 224), `TestUnicodeAnnotationEscaping` (line 385).
   - **Migrate these three classes** to import `format_annot_latex` from `highlight_spans.py` instead of `_format_annot` from `latex.py`. Update call sites from `_format_annot(highlight_dict)` to `format_annot_latex(highlight_dict)`. Adjust assertions if the new function's output format differs slightly (e.g., the `para_ref` parameter may need to be passed explicitly rather than being embedded in the highlight dict).
   - Update the file's import block: remove `_format_annot` from `latex.py` import, add `from promptgrimoire.export.highlight_spans import format_annot_latex`.
   - `_escape_latex` is only tested directly (no production callers). Keep `TestEscapeLaTeX` class but update its import to `from promptgrimoire.export.preamble import _escape_latex` (it was moved in Phase 1).
   - `TestFormatTimestamp` and `TestGenerateTagColourDefinitions` are unaffected — they import from `preamble.py` after Phase 1.

6. **Delete additional test files that only test deleted functions:**
   - Delete: `tests/unit/export/test_marker_insertion.py` (tests `_insert_markers_into_html`)
   - Modify: `tests/unit/export/test_plain_text_conversion.py` — delete only the `TestEscapeHtmlTextContent` class (line 59+) which tests `_escape_html_text_content` from `latex.py`. **Keep** `TestPlainTextToHtml` (lines 6-56) which tests `_plain_text_to_html` from `pdf_export.py` — that function is NOT being deleted. Update the import line to remove the `latex.py` import (only `pdf_export` import remains).
   - Delete: `tests/unit/export/test_crlf_char_index_bug.py` (tests `_insert_markers_into_html`; CRLF edge case rewritten in Phase 2 Task 3's `test_highlight_spans.py`)

7. **Run `uv sync`** to update the lock file after dependency removal.

8. **Verify no remaining references:**
   - `grep -rn "from promptgrimoire.export.latex" src/ tests/` should return zero results
   - `grep -rn "from pylatexenc" src/` should return zero results
   - `grep -rn "from lark" src/` should return zero results

**Testing:**

Run: `uv run test-all`
Expected: All tests pass. No import errors.

**Commit:** `refactor: delete latex.py, P4 test files, and remove pylatexenc + lark dependencies`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Write AC4 + AC5 validation tests

**Verifies:** 134-lua-highlight.AC4.1, 134-lua-highlight.AC4.2, 134-lua-highlight.AC4.3, 134-lua-highlight.AC4.4, 134-lua-highlight.AC4.5, 134-lua-highlight.AC5.1, 134-lua-highlight.AC5.2, 134-lua-highlight.AC5.3

**Files:**
- Create: `tests/unit/export/test_pipeline_cleanup.py`

**Implementation:**

Write a validation test file that asserts the cleanup is complete:

**AC4 validation tests:**
- AC4.1: Assert `pylatexenc` is NOT in `pyproject.toml` **main** dependencies. Read the file, extract the `[project] dependencies` section (between `dependencies = [` and the closing `]`), and assert `pylatexenc` does not appear in that section. Note: `pylatexenc` is intentionally kept in `[dependency-groups] dev` for `tests/helpers/latex_parse.py`.
- AC4.2: Assert `latex.py` does not exist: `not Path("src/promptgrimoire/export/latex.py").exists()`
- AC4.3: Assert each deleted test file does not exist.
- AC4.4: Assert that importing `MarkerToken`, `MarkerTokenType`, `Region` from `promptgrimoire.export` raises `ImportError`.
- AC4.5: Assert that `lark` is NOT in `pyproject.toml` dependencies.
- AC4.6: Assert that `_format_annot` is not importable from any `promptgrimoire.export` module.

**AC5 validation tests:**
- AC5.3: Assert that `tests/integration/test_highlight_latex_elements.py` exists and imports resolve correctly (the integration tests themselves run as part of `test-all`).

**Note on AC5.1 and AC5.2:** These require PDF compilation and `mutool` analysis, which are visual/integration verification steps. They should be verified during UAT, not in automated unit tests. Document this in the test file with a comment.

Run: `uv run pytest tests/unit/export/test_pipeline_cleanup.py -v`
Expected: All assertions pass.

Run: `uv run test-all`
Expected: Full suite passes — no regressions.

**Commit:** `test: add pipeline cleanup validation tests for AC4 + AC5`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->
