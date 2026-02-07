# LaTeX/PDF Test Audit

What each test claims to verify vs what it actually validates.

---

## tests/unit/test_latex_export.py

**Module docstring:** "Unit tests for LaTeX export with annotations."

### TestEscapeLatex

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_escape_ampersand` | Ampersand should be escaped | `_escape_latex("A & B") == r"A \& B"` |
| `test_escape_percent` | Percent should be escaped | `_escape_latex("100%") == r"100\%"` |
| `test_escape_dollar` | Dollar sign should be escaped | `_escape_latex("$100") == r"\$100"` |
| `test_escape_underscore` | Underscore should be escaped | `_escape_latex("foo_bar") == r"foo\_bar"` |
| `test_escape_hash` | Hash should be escaped | `_escape_latex("#1") == r"\#1"` |
| `test_escape_curly_braces` | Curly braces should be escaped | `_escape_latex("{x}") == r"\{x\}"` |

**Assessment:** These are pure function tests with hardcoded input→output. Valid unit tests but don't prove the escaped output compiles in LaTeX.

### TestFormatTimestamp

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_valid_iso_timestamp` | Valid ISO timestamp should be formatted | Checks result contains "26", "Jan", "2026", "14:30" |
| `test_invalid_timestamp_returns_empty` | Invalid timestamp should return empty | `_format_timestamp("not-a-date") == ""` |
| `test_empty_timestamp_returns_empty` | Empty timestamp should return empty | `_format_timestamp("") == ""` |

**Assessment:** Valid function tests. Uses hardcoded timestamp input.

### TestGenerateTagColourDefinitions

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_single_tag` | Single tag should produce one definecolor | Asserts string contains `\definecolor{tag-jurisdiction}{HTML}{1f77b4}` |
| `test_multiple_tags` | Multiple tags should produce multiple definecolors | Asserts string contains hardcoded definecolor commands |
| `test_underscore_converted_to_dash` | Underscores should become dashes | Asserts "tag-my-tag-name" in result |
| `test_hash_stripped_from_colour` | Hash should be stripped | Asserts "{AABBCC}" in result, "##" not in result |

**Assessment:** Tests string output format only. Hardcoded colour values (`#1f77b4`, `#d62728`). Does NOT verify these `\definecolor` commands compile in LaTeX.

### TestBuildAnnotationPreamble

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_includes_xcolor` | Preamble should include xcolor package | `r"\usepackage{xcolor}" in result` |
| `test_includes_marginalia` | Preamble should include marginalia package | `r"\usepackage{marginalia}" in result` |
| `test_includes_geometry` | Preamble should include geometry with wide margin | `r"\usepackage[" in result` and `"right=6cm" in result` |
| `test_includes_annot_command` | Preamble should define annot command | `r"\newcommand{\annot}" in result` |
| `test_includes_colour_definitions` | Preamble should include colour definitions | `r"\definecolor{tag-jurisdiction}" in result` |

**Assessment:** ⚠️ **PROBLEM AREA** - Tests verify strings exist in preamble. Does NOT verify:
- Packages are installed
- Packages work with LuaLaTeX
- Preamble compiles without errors
- `\annot` command works when used

### TestFormatAnnot

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_basic_annotation` | Basic annotation should produce valid annot command | Asserts `\annot{tag-jurisdiction}`, "Jurisdiction", "Alice" in result |
| `test_with_paragraph_reference` | Annotation with para ref should include it | Asserts "[45]" in result |
| `test_with_comments` | Annotation with comments should include them | Asserts author names and comment text in result |
| `test_escapes_special_characters_in_author` | Special chars in author should be escaped | Asserts `\&` in result |
| `test_escapes_special_characters_in_comments` | Special chars in comments should be escaped | Asserts `\%` and `\&` in result |

**Assessment:** Tests string output format. Uses hardcoded highlight dicts. Does NOT verify `\annot` command compiles.

### TestInsertMarkersIntoHtml

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_empty_highlights` | Empty highlights should return unchanged HTML | `result == html` and `markers == []` |
| `test_single_highlight` | Single highlight should insert marker | Asserts "ANNMARKER0ENDMARKER" in result |
| `test_multiple_highlights` | Multiple highlights should insert multiple markers | Asserts both markers present |
| `test_preserves_html_tags` | HTML tags should be preserved | Asserts `<strong>` tags still present |

**Assessment:** Valid function tests for marker insertion logic.

### TestReplaceMarkersWithAnnots

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_replaces_marker` | Marker should be replaced with annot command | "ANNMARKER" not in result, `\annot{tag-jurisdiction}` in result |
| `test_with_word_to_legal_para` | Should include para ref when mapping provided | "[10]" in result |
| `test_multiple_markers` | Multiple markers should all be replaced | Both `\annot` commands present |

**Assessment:** Tests string transformation only. Does NOT compile the LaTeX.

---

## tests/unit/test_latex_cross_env.py

**Module docstring:** "Tests for LaTeX highlight behavior across environment boundaries."

### TestCrossEnvironmentHighlights

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_cross_env_highlight_compiles_to_pdf` | Verify cross-environment highlights compile to PDF | ✅ Calls `pdf_exporter()` which runs full production pipeline. Asserts PDF exists. |

**Assessment:** ✅ **GOOD** - Uses production pipeline (`export_annotation_pdf`), real RTF fixture, actual LaTeX compilation.

---

## tests/integration/test_pdf_export.py

**Module docstring:** "Integration tests for PDF export pipeline."

### TestHtmlToLatexIntegration

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_legal_document_structure` | Convert legal document HTML with numbered paragraphs | Calls `convert_html_to_latex()` with Lua filter. Asserts "CASE NAME", `\begin{enumerate}` in result. |

**Assessment:** Tests Pandoc conversion. Does NOT compile the LaTeX output.

### TestPdfCompilation

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_compile_simple_document` | Compile a simple LaTeX document to PDF | ✅ Compiles hardcoded `\documentclass{article}` doc, checks PDF header |
| `test_compile_with_todonotes` | Compile document with todonotes package | ⚠️ Compiles hardcoded doc with `todonotes` - **PRODUCTION DOESN'T USE THIS PACKAGE** |
| `test_compile_failure_raises` | Compilation failure raises CalledProcessError | ✅ Verifies error handling works |
| `test_output_dir_defaults_to_tex_parent` | Output directory defaults to tex file's parent | ✅ Tests path logic |

**Assessment:** `test_compile_with_todonotes` tests a package (`todonotes`) that production code doesn't use. Production uses `marginalia` + `lua-ul`.

### TestMarginnoteExportPipeline

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_export_annotation_pdf_basic` | export_annotation_pdf should produce a valid PDF | ✅ Calls production `export_annotation_pdf()`, verifies PDF exists with correct header |
| `test_export_with_general_notes` | Should include general notes section | ✅ Calls production function, checks "General Notes" in tex output |
| `test_export_with_comments` | Should include comment threads | ✅ Calls production function, checks author/comment text in tex output |

**Assessment:** ✅ **GOOD** - Uses real `export_annotation_pdf()` function.

---

## tests/e2e/test_pdf_export.py

**Module docstring:** "End-to-end tests for PDF export with annotations."

### TestPdfExportWorkflow

| Test | Claimed Purpose | Actual Validation |
|------|-----------------|-------------------|
| `test_two_users_collaborate_and_export_pdf` | Full workflow: two users annotate, export PDF | ✅ Full E2E through browser. Creates annotations, comments, exports via UI button. Verifies PDF header. |

**Assessment:** ✅ **GOOD** - Full end-to-end test through actual UI.

---

## Summary

### Tests That Actually Prove Production Works

| File | Test | Method |
|------|------|--------|
| `test_latex_cross_env.py` | `test_cross_env_highlight_compiles_to_pdf` | `pdf_exporter` fixture → `export_annotation_pdf()` |
| `test_pdf_export.py` (integration) | `test_export_annotation_pdf_basic` | Direct `export_annotation_pdf()` call |
| `test_pdf_export.py` (integration) | `test_export_with_general_notes` | Direct `export_annotation_pdf()` call |
| `test_pdf_export.py` (integration) | `test_export_with_comments` | Direct `export_annotation_pdf()` call |
| `test_pdf_export.py` (e2e) | `test_two_users_collaborate_and_export_pdf` | Browser UI export |

### Tests That Only Check Strings (No Compilation)

| File | Tests | Purpose |
|------|-------|---------|
| `test_latex_export.py` | 21 tests | Test Python string transformation logic (escaping, formatting, marker insertion) - valid unit tests |

### Tests Removed (2026-01-27)

| File | Test | Reason |
|------|------|--------|
| `test_latex_export.py` | `TestEscapeLatex` (6 tests) | Just checked string transformations without proving they compile |
| `test_latex_export.py` | `TestBuildAnnotationPreamble` (5 tests) | Just checked if strings like `\usepackage{xcolor}` existed |
| `test_pdf_export.py` (integration) | `test_compile_with_todonotes` | Tested `todonotes` package; production uses `marginalia` + `lua-ul` |

### Tests Added (2026-01-27)

| File | Test | Purpose |
|------|------|---------|
| `test_latex_export.py` | `TestCompilationValidation.test_all_outputs_compile_with_lualatex` | Source of truth - compiles all edge cases, validates log for errors |

**Validation includes:**
- PDF exists and has valid header
- No fatal LaTeX errors (`! ` lines)
- No "Undefined control sequence"
- No "Missing $", "Missing {", "Missing }"

**Output for visual inspection:** `output/test_output/latex_validation/`

### Remaining Hardcoded Values in Tests

| File | Lines | Hardcoded Content | Justification |
|------|-------|-------------------|---------------|
| `test_latex_export.py` | various | Colour values `#1f77b4`, `#d62728` | Test input data for transformation logic |
| `test_latex_export.py` | 37 | Timestamp `2026-01-26T14:30:00+00:00` | Test input for timestamp formatting |
