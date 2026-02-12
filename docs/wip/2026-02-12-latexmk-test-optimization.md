# LaTeX Test Optimization: Compile-Once Architecture

**Date:** 2026-02-12
**Context:** 68 `latexmk` invocations across the test suite, each taking ~10s wall time on lualatex. Total serial cost: ~11 minutes of pure compilation. 30 of these compile **identical** inputs.

---

## Part 1: Current Inventory — Every `compile_latex()` Call

### File: test_workspace_fixture_export.py (30 compiles)

**TestPdfBasicIntegrity.test_export_produces_pdf** — 1 compile
```
Input:  lawlis_v_r_austlii.html + 11 highlights + response_draft_markdown
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: PDF exists, >50KB, %PDF header
```

**TestHighlightBoundariesInPdf.test_all_comments_appear_in_pdf** — 1 compile
```
Input:  lawlis_v_r_austlii.html + 11 highlights (NO response draft)
Chain:  export_annotation_pdf → compile_latex
Assert: Every highlight's comment text appears in PDF (pymupdf extraction)
```

**TestHighlightBoundariesInPdf.test_highlight_N_*_boundary** × 11 — 11 compiles
```
Input:  lawlis_v_r_austlii.html + 11 highlights (NO response draft) [IDENTICAL to above]
Chain:  export_annotation_pdf → compile_latex
Assert: Per-highlight text fragments appear in PDF (pymupdf extraction)
```

**TestHighlightBoundariesInPdf.test_highlight_boundaries_in_tex** — 1 compile
```
Input:  lawlis_v_r_austlii.html + 11 highlights (NO response draft) [IDENTICAL to above]
Chain:  export_annotation_pdf → compile_latex
Assert: .tex has comments in \annot commands, annot count >= highlight count
```

**TestHighlightWrappingInTex.test_text_inside_highlight_wrapping** × 3 — 3 compiles
```
Input:  lawlis_v_r_austlii.html + 11 highlights (NO response draft) [IDENTICAL to above]
Chain:  export_annotation_pdf → compile_latex
Assert: Text fragments are INSIDE \highLight{} bodies in .tex
```

**TestUnicodeRendering.test_no_replacement_characters_in_pdf** — 1 compile
```
Input:  lawlis_v_r_austlii.html + 11 highlights + response_draft_markdown [IDENTICAL to BasicIntegrity]
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: No U+FFFD in pdftotext extraction
```

**TestUnicodeRendering.test_script_renders_in_pdf** × 11 — 11 compiles
```
Input:  lawlis_v_r_austlii.html + 11 highlights + response_draft_markdown [IDENTICAL to above]
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: Per-script text (Armenian, Arabic, ...) found in PDF via pdftotext or pymupdf
```

**TestUnicodeRendering.test_general_notes_section_exists** — 1 compile
```
Input:  lawlis_v_r_austlii.html + 11 highlights + response_draft_markdown [IDENTICAL to above]
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: "General Notes" and "Lorem Ipsum" in pymupdf extraction
```

**Summary:** 30 compiles. Only **2 distinct inputs**:
- **Variant A:** lawlis_v_r + 11 highlights (no response draft) — compiled **16 times**
- **Variant B:** lawlis_v_r + 11 highlights + response draft — compiled **14 times**

---

### File: test_chatbot_fixtures.py (17 compiles)

**TestChatbotFixturesToPdf.test_fixture_compiles_to_pdf** × 17
```
Input:  17 chatbot HTML fixtures (each unique), preprocessed via preprocess_for_export()
Chain:  preprocess_for_export → pdf_exporter → export_annotation_pdf → compile_latex
Assert: PDF exists and non-empty

Fixtures:
  claude_cooking, claude_maths,
  google_aistudio_image, google_aistudio_ux_discussion,
  google_gemini_debug, google_gemini_deep_research,
  openai_biblatex, openai_dh_dr, openai_dprk_denmark, openai_software_long_dr,
  scienceos_loc, scienceos_philsci,
  austlii,
  chinese_wikipedia, translation_japanese_sample, translation_korean_sample, translation_spanish_sample
```

**Note:** `TestChatbotFixturesToLatex` (same file) already tests all 17 fixtures convert to LaTeX via Pandoc — no compilation needed for that check. The PDF step proves the LaTeX compiles.

**Overlap:** The 4 i18n fixtures (chinese_wikipedia, translation_japanese/korean/spanish_sample) are also compiled in `test_pdf_export.py::TestI18nPdfExport` with additional .tex and log assertions. The chatbot test only asserts "PDF exists" — strictly weaker.

---

### File: test_pdf_export.py (15 compiles)

**TestPdfCompilation.test_compile_simple_document** — 1 compile
```
Input:  Bare \documentclass{article} + "Hello, world!"
Chain:  compile_latex (direct)
Assert: PDF exists, %PDF header
```

**TestPdfCompilation.test_compile_failure_raises** — 1 compile (expected failure)
```
Input:  Invalid LaTeX with \undefined command
Chain:  compile_latex (direct)
Assert: Raises LaTeXCompilationError
```

**TestPdfCompilation.test_output_dir_defaults_to_tex_parent** — 1 compile
```
Input:  Bare \documentclass{article} + "Test."
Chain:  compile_latex (direct, no output_dir)
Assert: PDF created in tex file's parent directory
OVERLAP: Same codepath as test_compile_simple_document — only differs in output_dir handling
```

**TestMarginnoteExportPipeline.test_export_annotation_pdf_basic** — 1 compile
```
Input:  "<p>This is a test document with highlighted text.</p>" + 1 highlight (jurisdiction)
Chain:  export_annotation_pdf → compile_latex
Assert: PDF exists, %PDF header
UNIQUE CODEPATH: Minimal pipeline-through-compilation test
```

**TestMarginnoteExportPipeline.test_export_with_general_notes** — 1 compile
```
Input:  "<p>Document text here.</p>" + no highlights + general_notes HTML
Chain:  export_annotation_pdf → compile_latex
Assert: PDF exists, .tex contains "General Notes"
NOTE: The meaningful assertion is .tex content — PDF compilation adds no information
```

**TestMarginnoteExportPipeline.test_export_with_comments** — 1 compile
```
Input:  "<p>The court held...</p>" + 1 highlight with 2 comments
Chain:  export_annotation_pdf → compile_latex
Assert: PDF exists, .tex contains author names + comment text
NOTE: Again, meaningful assertions are .tex-level
```

**TestI18nPdfExport.test_export_i18n_fixture** × 4 — 4 compiles
```
Input:  4 clean i18n fixture HTMLs (chinese_wikipedia, japanese, korean, spanish), no highlights
Chain:  export_annotation_pdf → compile_latex
Assert: PDF valid + .tex has i18n chars + no font errors in log
UNIQUE CODEPATH: Font fallback chain per script family
OVERLAP: Same 4 fixtures also compiled in test_chatbot_fixtures.py with weaker assertions
```

**TestI18nPdfExport.test_export_cjk_with_highlight** — 1 compile
```
Input:  Mixed CJK plain text + 1 highlight on first 2 chars
Chain:  export_annotation_pdf → compile_latex
Assert: PDF exists, non-empty
UNIQUE CODEPATH: CJK characters inside \highLight{} wrapper
```

**TestResponseDraftExport.test_export_with_markdown_notes_ac6_1** — 1 compile
```
Input:  "<p>Document text for annotation.</p>" + markdown notes ("# My Response\n\n...")
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: PDF exists, .tex contains "General Notes", "My Response", "analysis"
NOTE: Meaningful assertions are .tex-level
```

**TestResponseDraftExport.test_export_empty_draft_no_section_ac6_2** — 1 compile
```
Input:  "<p>Document text for annotation.</p>" + notes_latex=""
Chain:  export_annotation_pdf → compile_latex
Assert: PDF exists, .tex does NOT contain "General Notes"
NOTE: Meaningful assertion is .tex-level (absence of a section)
```

**TestResponseDraftExport.test_export_with_rich_markdown_ac6_1** — 1 compile
```
Input:  "<p>Source document.</p>" + rich markdown (headers, lists, bold, italic)
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: PDF exists, .tex contains headers, itemize, text
NOTE: Meaningful assertions are .tex-level
```

**TestResponseDraftExport.test_notes_latex_takes_precedence_over_general_notes** — 1 compile
```
Input:  "<p>Document text.</p>" + both general_notes HTML AND notes_latex markdown
Chain:  markdown_to_latex_notes → export_annotation_pdf → compile_latex
Assert: PDF exists, .tex contains markdown content (not HTML notes)
NOTE: Meaningful assertion is .tex-level (precedence logic)
```

---

### File: test_pdf_pipeline.py (4 compiles)

**TestPdfPipeline.test_issue_85_regression_no_literal_markers** — 1 compile
```
Input:  "<p>The quick brown fox jumps over the lazy dog.</p>" + 2 interleaved highlights
Chain:  pdf_exporter → export_annotation_pdf → compile_latex
Assert: .tex has NO literal HLSTART/HLEND/ANNMARKER, HAS \highLight, PDF exists
UNIQUE CODEPATH: Regression guard for marker processing
```

**TestPdfPipeline.test_interleaved_highlights_compile** — 1 compile
```
Input:  "<p>One two three four five six seven eight</p>" + 2 interleaved highlights
Chain:  pdf_exporter → export_annotation_pdf → compile_latex
Assert: PDF exists
OVERLAP: Same highlight topology as issue_85 (2 interleaved), just different text
```

**TestPdfPipeline.test_three_overlapping_compile** — 1 compile
```
Input:  "<p>Word one word two word three word four</p>" + 3 nested highlights
Chain:  pdf_exporter → export_annotation_pdf → compile_latex
Assert: PDF exists
UNIQUE CODEPATH: 3-highlight overlap triggers "many-dark" underline rendering
```

**TestPdfPipeline.test_overlapping_highlights_crossing_list_boundary** — 1 compile
```
Input:  HTML with <p> + <ol> + <p> + 2 highlights crossing list boundary
Chain:  pdf_exporter → export_annotation_pdf → compile_latex
Assert: PDF exists
UNIQUE CODEPATH: Highlights crossing LaTeX environment boundaries (enumerate)
```

---

### File: test_latex_string_functions.py (1 compile)

**TestCompilationValidation.test_all_outputs_compile_with_lualatex** — 1 compile
```
Input:  Synthetic document combining escape sequences + 3 annotations + colour defs + preamble
Chain:  generate_tag_colour_definitions + escape_unicode_latex + format_annot_latex → compile_latex
Assert: PDF valid, no fatal LaTeX errors in log
UNIQUE CODEPATH: Source-of-truth compilation of all string generation functions
```

---

### File: test_latex_packages.py (1 compile)

**TestLaTeXPackages.test_unicode_preamble_compiles_without_tofu** — 1 compile
```
Input:  Minimal doc with UNICODE_PREAMBLE + \cjktext{日本語} + \emoji{party-popper}
Chain:  compile_latex
Assert: PDF valid, pdftotext has no U+FFFD, CJK text found
UNIQUE CODEPATH: Preamble smoke test for font packages
```

---

## Part 2: Duplication Analysis

### Exact-Input Duplicates (compile identical .tex)

| Input | Compiled in | Times | Needed |
|-------|-----------|-------|--------|
| lawlis_v_r + 11 highlights (no response draft) | test_workspace_fixture_export: highlight boundary ×11, all_comments, tex_boundaries, wrapping ×3 | **16** | **1** |
| lawlis_v_r + 11 highlights + response draft | test_workspace_fixture_export: basic_integrity, no_replacement, script_renders ×11, general_notes | **14** | **1** |

**Waste: 28 redundant compiles** (~5 minutes wall time)

### Near-Duplicate Codepaths

| Test A | Test B | Relationship |
|--------|--------|-------------|
| test_compile_simple_document | test_output_dir_defaults_to_tex_parent | Same .tex, different output_dir param |
| test_interleaved_highlights_compile | test_issue_85_regression_no_literal_markers | Same topology (2 interleaved), different text; issue_85 has strictly more assertions |
| chatbot × 4 i18n fixtures (exists-only) | test_export_i18n_fixture × 4 (chars + log) | Same inputs; i18n tests are strictly stronger |

### .tex-Only Assertions (compile not needed for the assertion itself)

These tests call `export_annotation_pdf()` (which compiles) but only inspect `.tex`:

| Test | What it actually checks |
|------|------------------------|
| test_export_with_general_notes | .tex contains "General Notes" |
| test_export_with_comments | .tex contains author + comment text |
| test_highlight_boundaries_in_tex | .tex has \annot commands + comment text |
| test_text_inside_highlight_wrapping ×3 | Text inside \highLight{} bodies in .tex |
| test_export_with_markdown_notes_ac6_1 | .tex contains "General Notes", "My Response" |
| test_export_empty_draft_no_section_ac6_2 | .tex does NOT contain "General Notes" |
| test_export_with_rich_markdown_ac6_1 | .tex has headers, itemize, text |
| test_notes_latex_takes_precedence_over_general_notes | .tex has markdown content, not HTML |

**8 tests** that assert only against .tex content but pay the compile cost anyway.

---

## Part 3: Proposed Architecture

### Principle: Compile Once, Assert Many

For each distinct input, generate the PDF **once** via a `scope="module"` or `scope="class"` fixture. Individual test functions read from the cached `.tex` and `.pdf` files. No test function calls `compile_latex()` directly (except the ones testing `compile_latex` itself).

For tests that only need `.tex` content, introduce `generate_tex_only()` — the pipeline up to `.tex` generation, skipping `compile_latex()`. This is ~100ms (Pandoc) vs ~10s (lualatex).

### Change 1: test_workspace_fixture_export.py — 30 → 2 compiles

**Before:** Every test method calls `export_annotation_pdf()` independently.

**After:** Two `scope="module"` async fixtures:

```
@fixture(scope="module")
lawlis_pdf_no_draft:
  compile lawlis_v_r + 11 highlights (no response draft)
  → cached (pdf_path, tex_path, tex_content, pdf_text_pymupdf)

@fixture(scope="module")
lawlis_pdf_with_draft:
  compile lawlis_v_r + 11 highlights + response draft
  → cached (pdf_path, tex_path, tex_content, pdf_text_pymupdf, pdf_text_poppler)
```

Tests become pure assertions against cached data:

```
test_export_produces_pdf(lawlis_pdf_with_draft)
  → assert pdf exists, >50KB, %PDF header                          # reads cached pdf_path

test_all_comments_appear_in_pdf(lawlis_pdf_no_draft)
  → assert comments in cached pdf_text                              # reads cached extraction

test_highlight_N_boundary(lawlis_pdf_no_draft, highlight_index)
  → assert fragments in cached pdf_text                             # parametrized, reads cached

test_highlight_boundaries_in_tex(lawlis_pdf_no_draft)
  → assert \annot in cached tex_content                             # reads cached .tex

test_text_inside_highlight_wrapping(lawlis_pdf_no_draft, spec)
  → assert fragment inside \highLight{} in cached tex_content       # parametrized, reads cached

test_no_replacement_characters_in_pdf(lawlis_pdf_with_draft)
  → assert no U+FFFD in cached pdf_text_poppler                    # reads cached extraction

test_script_renders_in_pdf(lawlis_pdf_with_draft, script, expected)
  → assert text in cached pdf_text                                  # parametrized, reads cached

test_general_notes_section_exists(lawlis_pdf_with_draft)
  → assert "General Notes" in cached pdf_text                       # reads cached extraction
```

**Saves: 28 compiles (~4.5 min)**

### Change 2: test_chatbot_fixtures.py — 17 → 5 compiles

**Observation:** `TestChatbotFixturesToLatex` (same file, no compilation) already tests all 17 fixtures produce valid LaTeX. The PDF compilation step proves that LaTeX compiles — a property of the LaTeX engine + preamble, not the specific fixture content.

**Before:** 17 compiles (one per fixture), each asserting only "PDF exists".

**After:** Compile **5 representative fixtures** (one per platform family):

```
REPRESENTATIVE_FIXTURES = [
    "claude_cooking.html",                # Claude (Anthropic)
    "google_aistudio_ux_discussion.html", # Google AI Studio
    "openai_biblatex.html",               # OpenAI
    "scienceos_loc.html",                 # ScienceOS (research report, not chat)
    "austlii.html",                       # Legal document (not a chatbot at all)
]
```

Drop the 4 i18n fixtures from this class entirely — they're tested with **stronger** assertions in `test_pdf_export.py::TestI18nPdfExport`.

**Saves: 12 compiles (~2 min)**

**Risk:** A platform-specific HTML pattern might produce LaTeX that compiles for Claude but not for Google Gemini. Mitigation: the LaTeX conversion test (no compile) still runs on all 17 — it catches HTML→LaTeX regressions. The compile step is platform-agnostic.

### Change 3: test_pdf_export.py — 15 → 8 compiles

#### TestPdfCompilation: 3 → 2

Drop `test_output_dir_defaults_to_tex_parent`. It tests a one-line Path default in `compile_latex()` — not worth a 10s compile. Assert the default in a unit test by inspecting the function signature or mocking the subprocess.

Keep:
- `test_compile_simple_document` (success path)
- `test_compile_failure_raises` (error path)

**Saves: 1 compile**

#### TestMarginnoteExportPipeline: 3 → 1

`test_export_with_general_notes` and `test_export_with_comments` only check `.tex` content. They don't need PDF compilation.

**Before:**
```
test_export_annotation_pdf_basic    → compile, assert PDF header
test_export_with_general_notes      → compile, assert .tex has "General Notes"
test_export_with_comments           → compile, assert .tex has author + comment text
```

**After:**
```
test_export_annotation_pdf_basic    → compile (keep — proves minimal pipeline works)
test_export_with_general_notes      → generate_tex_only, assert .tex has "General Notes"
test_export_with_comments           → generate_tex_only, assert .tex has author + comment text
```

**Saves: 2 compiles**

#### TestI18nPdfExport: 5 → 4

Drop `test_export_cjk_with_highlight`. CJK-inside-highlight is already covered by:
- `test_workspace_fixture_export::TestHighlightWrappingInTex` (highlights on real doc)
- The CJK font rendering is proven by the 4 i18n fixture tests

The 4 fixture tests are each unique (different scripts, different font fallback chains). Keep all 4.

**Saves: 1 compile**

#### TestResponseDraftExport: 4 → 1

All 4 tests assert `.tex` content. Only 1 needs to prove it compiles.

**Before:**
```
test_export_with_markdown_notes_ac6_1                → compile, assert .tex
test_export_empty_draft_no_section_ac6_2             → compile, assert .tex
test_export_with_rich_markdown_ac6_1                 → compile, assert .tex
test_notes_latex_takes_precedence_over_general_notes → compile, assert .tex
```

**After:**
```
test_export_with_rich_markdown_ac6_1                 → compile (keep — most complex case)
test_export_with_markdown_notes_ac6_1                → generate_tex_only, assert .tex
test_export_empty_draft_no_section_ac6_2             → generate_tex_only, assert .tex
test_notes_latex_takes_precedence_over_general_notes → generate_tex_only, assert .tex
```

**Saves: 3 compiles**

### Change 4: test_pdf_pipeline.py — 4 → 3 compiles

Drop `test_interleaved_highlights_compile`. Same highlight topology (2 interleaved) as `test_issue_85_regression_no_literal_markers`, which has strictly more assertions. Different HTML text, but the LaTeX structure (nested \highLight commands) is identical.

Keep:
- `test_issue_85_regression_no_literal_markers` (regression guard + 2-overlap)
- `test_three_overlapping_compile` (3-overlap triggers "many-dark" — unique codepath)
- `test_overlapping_highlights_crossing_list_boundary` (cross-environment — unique codepath)

**Saves: 1 compile**

### No changes to:

- **test_latex_string_functions.py** (1 compile) — source of truth for string functions
- **test_latex_packages.py** (1 compile) — preamble smoke test

---

## Part 4: Implementation Requirements

### New Function: `generate_tex_only()`

Extract the .tex generation pipeline from `export_annotation_pdf()`, stopping before `compile_latex()`:

```python
async def generate_tex_only(
    html_content: str,
    highlights: list[dict],
    tag_colours: dict[str, str],
    *,
    general_notes: str = "",
    notes_latex: str = "",
    output_dir: Path,
    filename: str = "annotated_document",
) -> Path:
    """Run the full export pipeline but skip LaTeX compilation.

    Returns path to the generated .tex file.
    """
    # Same as export_annotation_pdf minus the compile_latex() call
```

This is not a new codepath — it's the existing pipeline with the last step removed. All assertions that currently check `.tex` content would use this instead.

### Module-Scoped Async Fixtures

For `test_workspace_fixture_export.py`, use `pytest_asyncio.fixture(scope="module")`:

```python
@pytest_asyncio.fixture(scope="module")
async def lawlis_pdf_no_draft(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("lawlis_no_draft")
    fixture = _load_workspace_fixture()
    html = _load_html()

    pdf_path = await export_annotation_pdf(
        html_content=html,
        highlights=fixture["highlights"],
        tag_colours=_TAG_COLOURS,
        output_dir=tmp_dir,
    )

    tex_content = (tmp_dir / "annotated_document.tex").read_text()
    pdf_text_pymupdf = _extract_pdf_text_pymupdf(pdf_path)

    return LawlisPdfResult(
        pdf_path=pdf_path,
        tex_content=tex_content,
        pdf_text=_normalize_pdf_text(pdf_text_pymupdf),
        pdf_text_raw=pdf_text_pymupdf,
    )
```

### Marker Discipline

All tests that call `compile_latex()` keep `@pytest.mark.latex`. Tests downgraded to `generate_tex_only()` lose the marker (they only need Pandoc, not latexmk).

---

## Part 5: Summary

| File | Before | After | Saved |
|------|--------|-------|-------|
| test_workspace_fixture_export.py | 30 | 2 | **28** |
| test_chatbot_fixtures.py | 17 | 5 | **12** |
| test_pdf_export.py (Compilation) | 3 | 2 | 1 |
| test_pdf_export.py (Marginnote) | 3 | 1 | 2 |
| test_pdf_export.py (I18n) | 5 | 4 | 1 |
| test_pdf_export.py (Response) | 4 | 1 | 3 |
| test_pdf_pipeline.py | 4 | 3 | 1 |
| test_latex_string_functions.py | 1 | 1 | 0 |
| test_latex_packages.py | 1 | 1 | 0 |
| **TOTAL** | **68** | **20** | **48** |

**Wall time savings:** ~48 × 10s = **~8 minutes** per test run.

### Codepath Coverage (preserved)

Every unique codepath in the current suite is retained:

| Codepath | Covered by (after) |
|----------|--------------------|
| Bare compile_latex success | test_compile_simple_document |
| compile_latex error handling | test_compile_failure_raises |
| Minimal pipeline (1 highlight → PDF) | test_export_annotation_pdf_basic |
| General notes in .tex | test_export_with_general_notes (tex-only) |
| Comment threads in .tex | test_export_with_comments (tex-only) |
| Markdown notes → .tex | test_export_with_markdown_notes_ac6_1 (tex-only) |
| Empty draft = no section | test_export_empty_draft_no_section_ac6_2 (tex-only) |
| Rich markdown compiles | test_export_with_rich_markdown_ac6_1 |
| notes_latex precedence | test_notes_latex_takes_precedence (tex-only) |
| 4 i18n fixtures + font log | test_export_i18n_fixture ×4 |
| CJK inside \highLight | lawlis_pdf_no_draft fixture (CJK in doc) |
| 2-overlap + marker regression | test_issue_85_regression |
| 3-overlap (many-dark) | test_three_overlapping_compile |
| Cross-environment boundary | test_overlapping_highlights_crossing_list_boundary |
| Lawlis full pipeline (no draft) | lawlis_pdf_no_draft fixture |
| Lawlis full pipeline (with draft) | lawlis_pdf_with_draft fixture |
| 11 highlight boundaries in PDF | test_highlight_N_boundary ×11 (cached PDF) |
| 11 scripts render in PDF | test_script_renders_in_pdf ×11 (cached PDF) |
| Highlight wrapping in .tex | test_text_inside_highlight_wrapping ×3 (cached .tex) |
| Chatbot platform compilation | 5 representative fixtures |
| String function compilation | test_all_outputs_compile_with_lualatex |
| Preamble + CJK smoke test | test_unicode_preamble_compiles_without_tofu |

### Codepaths Removed (justified)

| Removed | Reason |
|---------|--------|
| test_output_dir_defaults_to_tex_parent | Tests Path default, not LaTeX. Unit-testable without compile. |
| test_interleaved_highlights_compile | Identical topology to issue_85 regression (which has more assertions) |
| test_export_cjk_with_highlight | CJK highlight covered by lawlis fixture; CJK font rendering by i18n tests |
| 12 chatbot fixture compiles | LaTeX conversion still tested for all 17; compilation tested for 5 representatives |

### Tests Preserved (no changes)

All test functions that currently exist continue to exist (no deletions). The only changes are:
1. **28 tests** switch from compiling their own PDF to reading from a module-scoped cached PDF/tex
2. **8 tests** switch from `export_annotation_pdf()` to `generate_tex_only()`
3. **1 test** dropped (output_dir default) — replace with unit test
4. **1 test** dropped (interleaved compile) — redundant with issue_85
5. **1 test** dropped (cjk_with_highlight) — covered by other tests
6. **12 chatbot** compiles pruned to 5 representatives (LaTeX tests kept for all 17)
