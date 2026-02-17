# LaTeX Test Optimisation — Phase 1: Mega-document Test Infrastructure

**Goal:** Reduce 68 `compile_latex()` invocations to ~12 compiles while preserving all existing test assertions.

**Architecture:** Three mechanisms: (1) `generate_tex_only()` for tests that only need `.tex` content (no compilation), (2) module-scoped async fixtures that compile once per test module and cache results, (3) mega-document compilation combining multiple test bodies into a single LaTeX document using the `subfiles` package, with automatic per-subfile fallback debugging on compilation failure. The pytest-subtests plugin enables independent assertions per segment.

**Tech Stack:** Python 3.14, pytest 9.0.2, pytest-subtests plugin, LaTeX subfiles package, pytest_asyncio

**Scope:** 5 phases from original design (phase 1 of 5)

**Codebase verified:** 2026-02-12

**Key testing references:**
- `docs/testing.md` — project testing guidelines, E2E patterns, database isolation
- `CLAUDE.md` lines 40-52 — TDD mandate, async fixture rule, E2E isolation
- `.ed3d/implementation-plan-guidance.md` — UAT requirements, command conventions

---

## Acceptance Criteria Coverage

This phase implements and tests:

### latex-test-optimization.AC1: Compile reduction (DoD items 1, 5, 7)

- **latex-test-optimization.AC1.1 Success:** Total `compile_latex()` invocations across the full test suite is <= 6 (5 mega-docs + 1 error path standalone)
- **latex-test-optimization.AC1.2 Success:** Every assertion from the original 68-compile test suite has a corresponding subtest in the mega-doc tests
- **latex-test-optimization.AC1.3 Success:** No individual LaTeX test exceeds 5s wall clock (down from 13-16s per test in baseline of 74.33s / 2290 tests). After Phase 3 (dynamic fonts), Latin-only mega-doc tests complete in under 2s each
- **latex-test-optimization.AC1.4 Success:** `generate_tex_only()` returns a `.tex` file path without invoking `compile_latex()`
- **latex-test-optimization.AC1.5 Success:** Each mega-document body segment is independently compilable via `subfiles` package
- **latex-test-optimization.AC1.6 Failure:** A subtest failure in mega-doc does not prevent remaining subtests from executing
- **latex-test-optimization.AC1.7 Edge:** Duplicate tests (`test_interleaved_highlights_compile`, `test_export_cjk_with_highlight`, `test_output_dir_defaults_to_tex_parent`) are deleted without coverage loss -- their assertions are covered by remaining tests
- **latex-test-optimization.AC1.8 Success:** Critical paths (margin note alignment, Unicode rendering, highlight boundaries) retain fast standalone isolation tests alongside mega-doc subtests -- margin notes are sensitive to page context and must be verified in short documents, not just mega-doc sections

**Note on AC1.1 vs AC1.8:** The <=6 target (5 mega-docs + 1 error) does not account for AC1.8's standalone isolation tests, infrastructure tests, or standalone tests that don't fit mega-document structure (error paths, preamble smoke tests, rich markdown compilation). Actual target is ~12 compiles — see Task 16 for the full breakdown. This is still an 82% reduction from 68.

---

## Existing Code Reference

Before implementing, the executor should read these files for context:

| File | Purpose | Lines |
|------|---------|-------|
| `src/promptgrimoire/export/pdf_export.py` | Production export pipeline to refactor | 349 |
| `src/promptgrimoire/export/pdf.py` | `compile_latex()` and `LaTeXCompilationError` | 128 |
| `src/promptgrimoire/export/preamble.py` | `build_annotation_preamble()` | 183 |
| `tests/conftest.py` | `pdf_exporter` fixture (lines 301-379), `TAG_COLOURS`, `requires_latexmk` | 692 |
| `tests/integration/conftest.py` | Integration fixtures | 42 |
| `docs/wip/2026-02-12-latexmk-test-optimization.md` | Detailed per-test compile audit (68 compiles) | 582 |
| `tests/unit/test_latex_packages.py` | Preamble smoke tests (`test_unicode_preamble_compiles_without_tofu`) — standalone compile, not migrated to mega-doc | — |
| `tests/unit/export/test_latex_string_functions.py` | String function compilation test — standalone compile, not migrated to mega-doc | — |
| `docs/lualatex/subfiles-reference.md` | subfiles package API reference | 88 |

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
## Subcomponent A: Dependencies

<!-- START_TASK_1 -->
### Task 1: Add subfiles to TinyTeX REQUIRED_PACKAGES

**Files:**
- Modify: `scripts/setup_latex.py:48-73` (add to REQUIRED_PACKAGES list)

**Implementation:**
Add `"subfiles"` to the `REQUIRED_PACKAGES` list in `scripts/setup_latex.py` with a comment explaining its purpose. Place it in the "Build tools" section alongside `latexmk`.

**Verification:**
Run: `uv run python scripts/setup_latex.py`
Expected: Script installs subfiles package without errors. Verify with: `~/.TinyTeX/bin/x86_64-linux/tlmgr list --only-installed | grep subfiles`

**Commit:** `chore: add subfiles LaTeX package to TinyTeX setup`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify pytest-subtests dependency

**Verifies:** None (infrastructure verification)

**Files:**
- No file changes (verification only)

**Implementation:**
The `subtests` fixture comes from the `pytest-subtests` package (already in dev dependencies as `"pytest-subtests>=0.15.0"`). Verify it works correctly, as all mega-document tests depend on it.

**Verification:**
Create a quick throwaway test:
```python
def test_subtests_work(subtests):
    for i in range(3):
        with subtests.test(msg=f"case-{i}"):
            assert i >= 0
```
Run it, verify it passes, then delete the throwaway test.

Run: `uv run python -c "import pytest_subtests; print(pytest_subtests.__version__)"` — should print a version

**Note:** `pytest-subtests` is an EXTERNAL package, not built into pytest. Do NOT remove it — all mega-document tests use the `subtests` fixture.
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
## Subcomponent B: generate_tex_only()

<!-- START_TASK_3 -->
### Task 3: Write failing test for generate_tex_only()

**Verifies:** latex-test-optimization.AC1.4

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (add new test class at end of file)

**Testing:**
Create `TestGenerateTexOnly` class with these test cases:
- AC1.4: Call `generate_tex_only()` with simple HTML + 1 highlight. Assert it returns a `Path` to a `.tex` file that exists, and the file contains expected LaTeX content (`\documentclass`, `\begin{document}`, highlight commands). Assert `compile_latex` was NOT called (the `.tex` file's parent should contain NO `.pdf` file).
- Test with `general_notes` parameter: Assert `.tex` contains "General Notes" section.
- Test with `notes_latex` parameter: Assert `.tex` contains the LaTeX notes content.

Import `generate_tex_only` from `promptgrimoire.export.pdf_export` (this import will fail until Task 4).

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py::TestGenerateTexOnly -v`
Expected: ImportError or AttributeError (function doesn't exist yet)

Do NOT commit yet — test is expected to fail.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement generate_tex_only()

**Verifies:** latex-test-optimization.AC1.4

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py` (extract function, refactor `export_annotation_pdf`)
- Modify: `src/promptgrimoire/export/__init__.py` (add `generate_tex_only` to `__all__`)

**Implementation:**
Extract steps 1-7 from `export_annotation_pdf()` (lines 302-344) into a new `generate_tex_only()` function. The new function handles everything up to writing the `.tex` file but does NOT call `compile_latex()`. Then refactor `export_annotation_pdf()` to call `generate_tex_only()` + `compile_latex()`.

`generate_tex_only()` signature should match `export_annotation_pdf()` except:
- Returns `Path` to the `.tex` file (not PDF)
- No `user_id` parameter (test utility, not production user-facing)
- `output_dir` is required (not optional) — tests always provide an explicit directory

Key constraint: `export_annotation_pdf()` MUST produce identical output to before. The refactoring is purely structural — same code, different call chain.

Add `"generate_tex_only"` to the `__all__` list in `src/promptgrimoire/export/__init__.py`.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py::TestGenerateTexOnly -v`
Expected: All new tests pass

Run: `uv run test-all -m latex`
Expected: All existing tests still pass (export_annotation_pdf behaviour unchanged)

**Commit:** `feat: extract generate_tex_only() from export pipeline for tex-only testing`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
## Subcomponent C: Mega-document Infrastructure

<!-- START_TASK_5 -->
### Task 5: Create mega-document builder and result types

**Verifies:** latex-test-optimization.AC1.5

**Files:**
- Modify: `tests/integration/conftest.py` (add mega-document helpers)

**Implementation:**
Add mega-document infrastructure to `tests/integration/conftest.py`. This includes:

1. **`MegaDocSegment`** — frozen dataclass defining one segment of a mega-document:
   - `name: str` — identifier for subtests and subfile naming
   - `html: str` — HTML content (raw)
   - `highlights: list[dict]` — highlight annotations (empty list for no highlights)
   - `tag_colours: dict[str, str]` — tag colour mapping
   - `general_notes: str = ""` — HTML notes
   - `notes_latex: str = ""` — pre-converted LaTeX notes
   - `preprocess: bool = True` — whether to run `preprocess_for_export()`

2. **`MegaDocResult`** — dataclass holding compilation results:
   - `pdf_path: Path` — compiled PDF
   - `tex_path: Path` — main document `.tex`
   - `output_dir: Path` — directory containing all files
   - `segment_tex: dict[str, str]` — mapping of segment name to its LaTeX body content
   - `pdf_text: str` — full PDF text extraction (via pymupdf or pdftotext)
   - `subfile_paths: dict[str, Path]` — mapping of segment name to subfile `.tex` path

3. **`compile_mega_document()`** — async function that:
   - Takes `segments: list[MegaDocSegment]` and `output_dir: Path`
   - For each segment: processes HTML through the export pipeline (preprocess → convert_html_with_annotations → build body), writes a subfile `.tex` with `\documentclass[mega_test.tex]{subfiles}` header
   - Builds the main document `.tex` with shared preamble, `\usepackage{subfiles}`, and `\subfile{segment_name}` includes separated by `\clearpage\section*{segment\_name}`
   - Calls `compile_latex()` on the main document
   - Extracts PDF text
   - Returns `MegaDocResult`

The preamble for the mega-document should use `build_annotation_preamble()` with the union of all segments' `tag_colours`. This ensures all colour definitions are available.

**Key details for subfile structure:**

Main document (`mega_test.tex`):
```latex
\documentclass[a4paper,12pt]{article}
\usepackage{subfiles}
% ... preamble from build_annotation_preamble() ...
\begin{document}
\subfile{segment_name_1}
\clearpage
\subfile{segment_name_2}
% ...
\end{document}
```

Each subfile (`segment_name_1.tex`):
```latex
\documentclass[mega_test.tex]{subfiles}
\begin{document}
\section*{segment\_name\_1}
% ... LaTeX body for this segment ...
\end{document}
```

When compiled as part of the mega-document, subfiles contribute only their body. When compiled standalone (for debugging), they load the main document's preamble.

**Verification:**
No direct test yet — verified by Task 6.
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Subfile fallback debugging and infrastructure verification

**Verifies:** latex-test-optimization.AC1.5, latex-test-optimization.AC1.6

**Files:**
- Modify: `tests/integration/conftest.py` (add fallback to `compile_mega_document`)
- Create: `tests/integration/test_mega_doc_infrastructure.py` (infrastructure verification)

**Implementation:**

**Part A: Subfile fallback in `compile_mega_document()`**

Wrap the `compile_latex()` call in `compile_mega_document()` with error handling. When `LaTeXCompilationError` is raised:

1. Iterate through each subfile in `subfile_paths`
2. Attempt to compile each subfile independently via `compile_latex()`
3. Collect per-subfile results: `{name: "ok"}` or `{name: "FAILED: error message"}`
4. Re-raise `LaTeXCompilationError` with enhanced message that includes the per-subfile isolation report

Example enhanced error output:
```
LaTeX compilation failed (exit 1): PDF not created
Subfile isolation results:
  segment_claude_cooking: ok
  segment_google_aistudio: ok
  segment_openai_biblatex: FAILED - Undefined control sequence \badcommand
  segment_scienceos_loc: ok
```

**Part B: Infrastructure verification test**

Create a test that verifies the mega-document infrastructure works:
- Build a mega-document with 2 simple segments (minimal HTML, no highlights)
- Assert: main `.tex` compiles to PDF
- Assert: each subfile `.tex` exists and is independently compilable
- Assert: `MegaDocResult.segment_tex` has entries for both segments
- Assert: `MegaDocResult.pdf_text` contains text from both segments

Use `@requires_latexmk` decorator. Mark with `@pytest.mark.latex`.

**Testing:**
- AC1.5: Verify each subfile compiles independently — test extracts subfile paths and calls `compile_latex()` on each.
- AC1.6: Verify subtests work with the infrastructure — use `subtests.test()` for each segment assertion. One subtest failure should not prevent others.

**Verification:**
Run: `uv run pytest tests/integration/test_mega_doc_infrastructure.py -v`
Expected: All tests pass, mega-doc compiles, subfiles compile independently

**Commit:** `feat: add mega-document builder with subfile fallback debugging`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 7-8) -->
## Subcomponent D: Workspace Test Migration

**Context:** `tests/integration/test_workspace_fixture_export.py` (692 lines) currently compiles the same workspace fixture 30 times with only 2 distinct inputs:
- **Variant A:** lawlis_v_r_austlii.html + 11 highlights, NO response draft (compiled 16 times)
- **Variant B:** lawlis_v_r_austlii.html + 11 highlights + response_draft_markdown (compiled 14 times)

The audit at `docs/wip/2026-02-12-latexmk-test-optimization.md` (lines 10-71) has the complete per-test breakdown.

<!-- START_TASK_7 -->
### Task 7: Create workspace module-scoped fixtures

**Verifies:** latex-test-optimization.AC1.1 (partial), latex-test-optimization.AC1.2 (partial)

**Files:**
- Modify: `tests/integration/test_workspace_fixture_export.py` (add module-scoped fixtures)

**Implementation:**
Add two `@pytest_asyncio.fixture(scope="module")` fixtures at the top of the file:

1. **`lawlis_no_draft_result`** — compiles variant A once:
   - Loads `lawlis_v_r_austlii.html` fixture and 11 highlights (same loading as existing `workspace_fixture` and `html_content` fixtures)
   - Calls `export_annotation_pdf()` with highlights, tag colours, NO general notes or draft
   - Extracts PDF text via pymupdf
   - Returns a frozen dataclass/namedtuple with: `pdf_path`, `tex_path`, `tex_content`, `pdf_text`, `output_dir`

2. **`lawlis_with_draft_result`** — compiles variant B once:
   - Same as above PLUS `response_draft_markdown` and `general_notes`
   - Calls `markdown_to_latex_notes()` for the draft conversion
   - Returns same structure with additional fields for draft content

Use `tmp_path_factory.mktemp()` for output directories (compatible with module scope, unlike `tmp_path` which is function-scoped).

**CRITICAL:** Use `@pytest_asyncio.fixture` NOT `@pytest.fixture` for async fixtures. See CLAUDE.md async fixture rule.

**Verification:**
No direct test — verified by Task 8 when existing assertions pass against cached results.
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Convert workspace tests to use cached fixtures

**Verifies:** latex-test-optimization.AC1.1 (partial), latex-test-optimization.AC1.2 (partial), latex-test-optimization.AC1.6

**Files:**
- Modify: `tests/integration/test_workspace_fixture_export.py` (convert all test classes)

**Implementation:**
Convert all test classes to receive the module-scoped fixtures instead of calling `export_annotation_pdf()`:

**TestPdfBasicIntegrity** (uses variant B):
- `test_export_produces_pdf` → assert `lawlis_with_draft_result.pdf_path.exists()`, size >50KB, `%PDF` header

**TestHighlightBoundariesInPdf** (uses variant A):
- `test_all_comments_appear_in_pdf` → search `lawlis_no_draft_result.pdf_text` for each comment
- `test_highlight_N_*_boundary` × 11 → use `subtests.test(msg=f"highlight-{n}")` for each highlight, search cached `pdf_text` for boundary text fragments
- `test_highlight_boundaries_in_tex` → search `lawlis_no_draft_result.tex_content` for `\annot` commands

**TestHighlightWrappingInTex** (uses variant A):
- `test_text_inside_highlight_wrapping` × 3 → use subtests, search cached `tex_content`

**TestUnicodeRendering** (uses variant B):
- `test_no_replacement_characters_in_pdf` → check cached `pdf_text` for U+FFFD
- `test_script_renders_in_pdf` × 11 → use `subtests.test(msg=script_name)` for each script, search cached `pdf_text`
- `test_general_notes_section_exists` → search cached `pdf_text` for "General Notes"

**Key pattern:** Tests that were previously `@pytest.mark.parametrize` with per-highlight/per-script iteration should become loops with `subtests.test()` context managers. This preserves independent assertion execution (AC1.6).

Remove any direct calls to `export_annotation_pdf()` or `compile_latex()` from test methods. All compilation now happens in the module-scoped fixtures.

**Verification:**
Run: `uv run pytest tests/integration/test_workspace_fixture_export.py -v`
Expected: All existing assertions pass. Only 2 compile_latex() invocations for this file (check by adding temporary logging or counting output).

**Commit:** `refactor: workspace tests use module-scoped compiled fixtures (30 -> 2 compiles)`
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_D -->

<!-- START_SUBCOMPONENT_E (tasks 9-10) -->
## Subcomponent E: English Mega-document

**Context:** The English mega-document combines all English-only compile tests into a single compilation. This includes:
- 13 English chatbot fixtures from `test_chatbot_fixtures.py` (claude_cooking, claude_maths, google_aistudio_image, google_aistudio_ux_discussion, google_gemini_debug, google_gemini_deep_research, openai_biblatex, openai_dh_dr, openai_dprk_denmark, openai_software_long_dr, scienceos_loc, scienceos_philsci, austlii)
- Pipeline highlight tests from `test_pdf_pipeline.py` (issue_85 regression, 3-overlap, cross-boundary)
- Cross-env highlights from `test_cross_env_highlights.py`
- Standalone export tests from `test_pdf_export.py` (basic pipeline, marginnote pipeline)

The audit at `docs/wip/2026-02-12-latexmk-test-optimization.md` lines 74-94 (chatbot), 197-229 (pipeline), 98-128 (marginnote) has the per-test details.

<!-- START_TASK_9 -->
### Task 9: Create English mega-document fixture

**Verifies:** latex-test-optimization.AC1.1 (partial), latex-test-optimization.AC1.5

**Files:**
- Create: `tests/integration/test_english_mega_doc.py`

**Implementation:**
Create a new test module with a module-scoped mega-document fixture:

1. **Define segments** — one `MegaDocSegment` per test input:
   - 13 chatbot fixtures: load HTML from `tests/fixtures/`, preprocess=True, no highlights
   - Pipeline tests: inline HTML with specific highlight configurations:
     - `issue_85_regression`: `"<p>The quick brown fox jumps over the lazy dog.</p>"` + 2 interleaved highlights (copy highlight definitions from `test_pdf_pipeline.py:32-114`)
     - `three_overlapping`: `"<p>Word one word two word three word four</p>"` + 3 nested highlights
     - `cross_boundary`: HTML with `<p>` + `<ol>` + `<p>` + 2 highlights crossing list boundary
   - Cross-env highlights: HTML from `test_cross_env_highlights.py` + highlights spanning list items
   - Basic pipeline: `"<p>This is a test document with highlighted text.</p>"` + 1 highlight
   - Marginnote with comments: `"<p>The court held...</p>"` + 1 highlight with 2 comments

2. **Module-scoped fixture** using `compile_mega_document()`:
   ```python
   @pytest_asyncio.fixture(scope="module")
   async def english_mega_result(tmp_path_factory):
       output_dir = tmp_path_factory.mktemp("english_mega")
       segments = _build_english_segments()
       return await compile_mega_document(segments, output_dir)
   ```

3. Use `@requires_latexmk` on the test class (from `tests/conftest.py`).

**Verification:**
No direct test — verified by Task 10.
<!-- END_TASK_9 -->

<!-- START_TASK_10 -->
### Task 10: Migrate English tests to mega-doc subtests

**Verifies:** latex-test-optimization.AC1.2 (partial), latex-test-optimization.AC1.6

**Files:**
- Modify: `tests/integration/test_english_mega_doc.py` (add test classes)
- Modify: `tests/integration/test_chatbot_fixtures.py` (remove `TestChatbotFixturesToPdf` compile tests for English fixtures)
- Modify: `tests/integration/test_pdf_pipeline.py` (remove compile tests moved to mega-doc)
- Modify: `tests/integration/test_cross_env_highlights.py` (remove or redirect to mega-doc)
- Modify: `tests/integration/test_pdf_export.py` (remove basic pipeline compile test, keep standalone)

**Implementation:**
Add test classes to `test_english_mega_doc.py` that assert against `english_mega_result`:

**TestChatbotCompilation:**
- One loop with subtests: `for segment in chatbot_segment_names: with subtests.test(msg=segment): assert segment in result.segment_tex`
- Assert PDF exists and is non-empty (one assertion, not per-segment)

**TestPipelineHighlights:**
- `test_issue_85_regression`: subtest asserting `.tex` has NO literal `HLSTART`/`HLEND` markers, HAS `\highLight`
- `test_three_overlapping_compile`: subtest asserting PDF compiled (unique codepath: many-dark underline)
- `test_cross_boundary_compile`: subtest asserting PDF compiled (unique codepath: cross-environment)
- `test_cross_env_highlights`: subtest asserting highlights span list boundaries

**TestBasicPipeline:**
- `test_basic_pipeline_compile`: assert PDF exists, `%PDF` header

**Migrate assertions VERBATIM** from the original test files. Do NOT paraphrase or simplify assertions — the original assertion text is the specification.

**Cleanup of original files:**
- `test_chatbot_fixtures.py`: Remove English fixtures from `TestChatbotFixturesToPdf` (keep `TestChatbotFixturesToLatex` which is non-compile). Keep CJK fixtures in the file temporarily (moved in Task 12).
- `test_pdf_pipeline.py`: Remove `test_issue_85_regression_no_literal_markers`, `test_three_overlapping_compile`, `test_overlapping_highlights_crossing_list_boundary`. If file becomes empty of compile tests, keep it for any remaining non-compile tests or delete if empty.
- `test_cross_env_highlights.py`: Remove or redirect to mega-doc. If file becomes empty, delete.
- `test_pdf_export.py`: Remove `TestMarginnoteExportPipeline.test_export_annotation_pdf_basic` (moved to mega-doc). Keep other methods that use `generate_tex_only()` (migrated in Task 11).

**Verification:**
Run: `uv run pytest tests/integration/test_english_mega_doc.py -v`
Expected: All subtests pass, 1 compile_latex() invocation for this file

Run: `uv run test-all -m latex`
Expected: All tests pass across all files

**Commit:** `refactor: consolidate English LaTeX tests into mega-document (38 -> 1 compile)`
<!-- END_TASK_10 -->
<!-- END_SUBCOMPONENT_E -->

<!-- START_SUBCOMPONENT_F (tasks 11-12) -->
## Subcomponent F: i18n/CJK Mega-document

**Context:** The i18n mega-document combines all CJK and multilingual compile tests:
- 4 CJK chatbot fixtures from `test_chatbot_fixtures.py` (chinese_wikipedia, translation_japanese_sample, translation_korean_sample, translation_spanish_sample)
- 4 i18n fixtures from `test_pdf_export.py::TestI18nPdfExport` (same 4 fixtures with stronger assertions)

The audit at `docs/wip/2026-02-12-latexmk-test-optimization.md` lines 82-94 (chatbot CJK overlap) and 146-153 (i18n tests) has details.

<!-- START_TASK_11 -->
### Task 11: Create i18n mega-document fixture

**Verifies:** latex-test-optimization.AC1.1 (partial), latex-test-optimization.AC1.5

**Files:**
- Create: `tests/integration/test_i18n_mega_doc.py`

**Implementation:**
Create a new test module with a module-scoped mega-document fixture:

1. **Define segments** — one `MegaDocSegment` per i18n fixture:
   - `chinese_wikipedia` — CJK text, no highlights
   - `translation_japanese_sample` — Japanese text, no highlights
   - `translation_korean_sample` — Korean text, no highlights
   - `translation_spanish_sample` — Spanish text (with accents), no highlights
   - All 4 use `preprocess=True`, no highlights, no notes

2. **Module-scoped fixture** using `compile_mega_document()`:
   ```python
   @pytest_asyncio.fixture(scope="module")
   async def i18n_mega_result(tmp_path_factory):
       output_dir = tmp_path_factory.mktemp("i18n_mega")
       segments = _build_i18n_segments()
       return await compile_mega_document(segments, output_dir)
   ```

3. This mega-document uses the FULL Unicode preamble (all fonts loaded) because the content includes CJK, Latin, and potentially other scripts.

**Verification:**
No direct test — verified by Task 12.
<!-- END_TASK_11 -->

<!-- START_TASK_12 -->
### Task 12: Migrate i18n tests to mega-doc subtests

**Verifies:** latex-test-optimization.AC1.2 (partial), latex-test-optimization.AC1.6

**Files:**
- Modify: `tests/integration/test_i18n_mega_doc.py` (add test classes)
- Modify: `tests/integration/test_chatbot_fixtures.py` (remove CJK fixtures from compile tests)
- Modify: `tests/integration/test_pdf_export.py` (remove `TestI18nPdfExport`)

**Implementation:**
Add test classes to `test_i18n_mega_doc.py`:

**TestI18nCompilation:**
- Subtest per fixture: assert PDF compiled, segment tex exists
- For each i18n fixture: subtest asserting `.tex` contains i18n characters (copy character checks from `test_pdf_export.py::TestI18nPdfExport.test_export_i18n_fixture`)
- For each i18n fixture: subtest asserting no font errors in compilation log (check `.log` file for "Missing character" warnings)

**Cleanup of original files:**
- `test_chatbot_fixtures.py`: Remove CJK fixtures from `TestChatbotFixturesToPdf`. After this + Task 10's English removal, `TestChatbotFixturesToPdf` should be empty — delete the class. Keep `TestChatbotFixturesToLatex`.
- `test_pdf_export.py`: Remove `TestI18nPdfExport` class entirely (all assertions moved to mega-doc).

**Verification:**
Run: `uv run pytest tests/integration/test_i18n_mega_doc.py -v`
Expected: All subtests pass, 1 compile_latex() invocation for this file

Run: `uv run test-all -m latex`
Expected: All tests pass

**Commit:** `refactor: consolidate i18n LaTeX tests into mega-document (8 -> 1 compile)`
<!-- END_TASK_12 -->
<!-- END_SUBCOMPONENT_F -->

<!-- START_SUBCOMPONENT_G (tasks 13-14) -->
## Subcomponent G: tex-only Migration and Standalone Tests

<!-- START_TASK_13 -->
### Task 13: Migrate tex-only assertions to generate_tex_only()

**Verifies:** latex-test-optimization.AC1.4

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (convert tex-only tests)

**Implementation:**
Several tests in `test_pdf_export.py` call `export_annotation_pdf()` but only inspect `.tex` content — they pay the compilation cost for nothing. Convert these to use `generate_tex_only()`:

**TestMarginnoteExportPipeline** (audit lines 130-143):
- `test_export_with_general_notes` → `generate_tex_only()`, assert `.tex` has "General Notes"
- `test_export_with_comments` → `generate_tex_only()`, assert `.tex` has author names + comment text
- Keep `test_export_annotation_pdf_basic` ONLY if not already moved to English mega-doc (Task 10). If moved, remove.

**TestResponseDraftExport** (audit lines 163-193):
- `test_export_with_markdown_notes_ac6_1` → `generate_tex_only()`, assert `.tex`
- `test_export_empty_draft_no_section_ac6_2` → `generate_tex_only()`, assert `.tex`
- `test_notes_latex_takes_precedence_over_general_notes` → `generate_tex_only()`, assert `.tex`
- Keep `test_export_with_rich_markdown_ac6_1` as a compile test (most complex case, proves rich markdown actually compiles)

**Important:** Remove `@requires_latexmk` from tests that no longer compile. These tests only need Pandoc, not latexmk. They should NOT have the `latex` marker since they don't invoke `compile_latex()`.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py -v`
Expected: All tests pass. Tex-only tests should run in <1s each (Pandoc only, no latexmk).

**Commit:** `refactor: tex-only assertions use generate_tex_only() (skip compilation)`
<!-- END_TASK_13 -->

<!-- START_TASK_14 -->
### Task 14: Create standalone isolation tests

**Verifies:** latex-test-optimization.AC1.8

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (add isolation test class)

**Implementation:**
Create `TestCriticalPathIsolation` class with fast standalone tests for concerns that mega-documents might mask:

1. **Margin note alignment** — compile a short document (~1 paragraph) with 1 highlight that has a comment. Assert: PDF exists, `.tex` contains `\annot` command. Short documents test margin note placement without interference from other segments.

2. **Highlight boundary precision** — compile a short document with 1 highlight spanning exactly 2 words. Assert: `.tex` has `\highLight` wrapping exactly those words.

These are intentionally minimal documents (~1s compile each). They provide fast feedback for specific concerns without waiting for the full mega-document.

Note: Unicode rendering isolation is already covered by `test_latex_packages.py::test_unicode_preamble_compiles_without_tofu` (1 compile, kept unchanged) and by the workspace variant B fixture (which includes multilingual content).

Use `@requires_latexmk` decorator.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py::TestCriticalPathIsolation -v`
Expected: Tests pass, each completes in <2s

**Commit:** `test: add critical path isolation tests for margin notes and highlight boundaries`
<!-- END_TASK_14 -->
<!-- END_SUBCOMPONENT_G -->

<!-- START_SUBCOMPONENT_H (tasks 15-16) -->
## Subcomponent H: Cleanup and Verification

<!-- START_TASK_15 -->
### Task 15: Delete redundant tests

**Verifies:** latex-test-optimization.AC1.7

**Files:**
- Modify: `tests/integration/test_pdf_pipeline.py` (delete `test_interleaved_highlights_compile`)
- Modify: `tests/integration/test_pdf_export.py` (delete `test_export_cjk_with_highlight`, `test_output_dir_defaults_to_tex_parent`)

**Implementation:**
Delete 3 tests with redundant coverage:

1. **`test_interleaved_highlights_compile`** in `test_pdf_pipeline.py` — same 2-overlap topology as `test_issue_85_regression_no_literal_markers` (which has strictly more assertions: checks for literal markers AND `\highLight` presence). Different HTML text but identical LaTeX highlight structure.

2. **`test_export_cjk_with_highlight`** in `test_pdf_export.py` — CJK text inside `\highLight{}` is already covered by:
   - Workspace variant A fixture (real document with CJK content + highlights)
   - i18n mega-document (CJK font rendering)

3. **`test_output_dir_defaults_to_tex_parent`** in `test_pdf_export.py` — tests that `compile_latex()` defaults `output_dir` to `tex_path.parent`. This is a one-line `Path` default (pdf.py:85), not worth a 5-10s compile. Replace with a unit test (if desired) that checks the default without compiling.

For each deletion, verify the codepath coverage table at `docs/wip/2026-02-12-latexmk-test-optimization.md` (Part 5, lines 536-563) — every codepath should still have at least one covering test.

**Verification:**
Run: `uv run test-all -m latex`
Expected: All remaining tests pass

**Commit:** `test: remove 3 tests with redundant coverage`
<!-- END_TASK_15 -->

<!-- START_TASK_16 -->
### Task 16: Verify compile count and assertion coverage

**Verifies:** latex-test-optimization.AC1.1, latex-test-optimization.AC1.2, latex-test-optimization.AC1.3

**Files:**
- No file changes (verification only)

**Implementation:**
Perform final verification of all Phase 1 acceptance criteria:

**AC1.1 — Compile count:**
Run the full LaTeX test suite and count `compile_latex()` invocations. Options:
- Add temporary logging to `compile_latex()` in `pdf.py:65` (`logger.info("compile_latex called")`) and grep output
- Or count by examining which test files/fixtures invoke compilation

Expected breakdown:
| Source | Compiles |
|--------|----------|
| Workspace variant A (module-scoped) | 1 |
| Workspace variant B (module-scoped) | 1 |
| English mega-document | 1 |
| i18n mega-document | 1 |
| Error path (`test_compile_failure_raises`) | 1 |
| Standalone compile (`test_compile_simple_document`) | 1 |
| Rich markdown compile (`test_export_with_rich_markdown_ac6_1`) | 1 |
| Isolation tests (~2) | 2 |
| Infrastructure test (Task 6) | 1 |
| Preamble smoke test (`test_unicode_preamble_compiles_without_tofu`) | 1 |
| String function compilation test | 1 |
| **Total** | **~12** |

**Note:** This count exceeds AC1.1's ≤6 target. The AC was written before AC1.8 (isolation tests) and before accounting for standalone tests that are not suitable for mega-document inclusion (error paths, preamble smoke tests, string function compilation). The actual target is ~12 compiles — still an 82% reduction from 68. If the user requires ≤6, some standalone tests would need to be merged into mega-documents, which may reduce debuggability.

**AC1.2 — Assertion coverage:**
Compare the list of all test functions before and after migration. Every original assertion should have a corresponding subtest or direct test in the new structure. Use the codepath coverage table in `docs/wip/2026-02-12-latexmk-test-optimization.md` as the checklist.

**AC1.3 — Wall clock:**
Run: `uv run pytest -m latex --durations=0`
No individual test should exceed 5s. Mega-document tests should complete in 2-5s each (single compile for multiple assertions).

**Verification:**
Run: `uv run test-all -m latex -v --tb=short`
Expected: All tests pass, no regressions

Run: `uv run test-all` (full suite without latex filter)
Expected: All tests pass, no regressions in non-latex tests

**Commit:** (no commit if no changes needed; update audit doc if numbers differ from expectation)
<!-- END_TASK_16 -->
<!-- END_SUBCOMPONENT_H -->

---

## UAT Steps

1. [ ] Run `uv run test-all -m latex -v` — all LaTeX tests pass
2. [ ] Run `uv run test-all` — full suite passes (no regressions)
3. [ ] Count `compile_latex()` invocations — should be ~12 (down from 68)
4. [ ] Run `uv run pytest -m latex --durations=0` — no test exceeds 5s
5. [ ] Inspect `tests/integration/test_english_mega_doc.py` — verify subfile `.tex` files exist in test output
6. [ ] Intentionally break one segment's LaTeX (e.g., add `\undefined` to a chatbot fixture's output) and verify the subfile fallback report identifies the failing segment

## Evidence Required
- [ ] Test output showing all LaTeX tests green
- [ ] Duration output showing per-test times
- [ ] Compile count evidence (log grep or manual count)
