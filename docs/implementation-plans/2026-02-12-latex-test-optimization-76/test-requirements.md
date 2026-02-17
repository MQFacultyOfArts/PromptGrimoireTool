# LaTeX Test Optimisation -- Test Requirements

**Design plan:** `docs/design-plans/2026-02-12-latex-test-optimization-76.md`
**Implementation plans:** `docs/implementation-plans/2026-02-12-latex-test-optimization-76/phase_01.md` through `phase_05.md`

This document maps every acceptance criterion (AC1.1 through AC5.4) to specific automated tests or human verification steps. Every AC is covered.

---

## Automated Test Coverage Required

Tests in this table must exist and pass before the implementation is considered complete. The "Test File" column gives the expected location after all phases are implemented. The "Verifies" column describes what specific behaviour the test must assert.

| Criterion | Test File | Verifies |
|-----------|-----------|----------|
| AC1.1 Compile count <= 12 | `tests/integration/test_mega_doc_infrastructure.py` + Phase 1 Task 16 verification | Count `compile_latex()` invocations across full `pytest -m latex` run. Expect ~12 total (2 workspace variants + 2 mega-docs + 1 error path + 1 simple compile + 1 rich markdown + 2 isolation + 1 infrastructure + 1 preamble smoke + 1 string function). Note: original AC said <=6 but AC1.8 isolation tests and standalone tests raise this to ~12 (82% reduction from 68). |
| AC1.2 All original assertions preserved | `tests/integration/test_english_mega_doc.py`, `tests/integration/test_i18n_mega_doc.py`, `tests/integration/test_workspace_fixture_export.py` | Every assertion from the original 68-compile test suite has a corresponding subtest in mega-doc or module-scoped fixture tests. Verified by cross-referencing the codepath coverage table in `docs/wip/2026-02-12-latexmk-test-optimization.md`. |
| AC1.3 No test exceeds 5s wall clock | `pytest -m latex --durations=0` output | No individual LaTeX test exceeds 5s. After Phase 3, Latin-only mega-doc tests complete in under 2s each. |
| AC1.4 `generate_tex_only()` returns .tex without compiling | `tests/integration/test_pdf_export.py::TestGenerateTexOnly` | Call `generate_tex_only()` with HTML + highlight. Assert returns `Path` to `.tex` that exists, contains `\documentclass`, `\begin{document}`, highlight commands. Assert NO `.pdf` in parent directory. Also test with `general_notes` and `notes_latex` parameters. |
| AC1.5 Subfiles independently compilable | `tests/integration/test_mega_doc_infrastructure.py` | Build mega-document with 2 segments. Assert main `.tex` compiles to PDF. Extract each subfile path and call `compile_latex()` on each independently -- assert each produces a PDF. |
| AC1.6 Subtest failure does not block remaining subtests | `tests/integration/test_mega_doc_infrastructure.py`, `tests/integration/test_workspace_fixture_export.py` | Use `subtests.test()` context manager for each segment/highlight assertion. One failing subtest must not prevent others from executing. Verified by pytest-subtests plugin behaviour (independent assertion execution). |
| AC1.7 Duplicate tests deleted without coverage loss | Phase 1 Task 15 (deletion) + `uv run test-all -m latex` | Delete `test_interleaved_highlights_compile`, `test_export_cjk_with_highlight`, `test_output_dir_defaults_to_tex_parent`. Verify all remaining tests pass and every codepath from the audit table still has at least one covering test. |
| AC1.8 Critical path isolation tests | `tests/integration/test_pdf_export.py::TestCriticalPathIsolation` | Two fast standalone compile tests: (1) margin note alignment -- short document with 1 highlight + comment, assert PDF exists and `.tex` contains `\annot`; (2) highlight boundary precision -- short document with 1 highlight spanning exactly 2 words, assert `.tex` has `\highLight` wrapping those words. Each completes in <2s. |
| AC2.1 `.sty` compiles standalone | `tests/integration/test_pdf_export.py::test_sty_compiles_standalone` | Write minimal `.tex` (`\documentclass{article}\usepackage{promptgrimoire-export}\begin{document}Test\end{document}`), copy `.sty` to same dir, call `compile_latex()`, assert PDF created. |
| AC2.2 Production output parity | Phase 1 mega-doc tests as regression guard + Phase 2 Task 6 verification | All mega-doc tests pass after `.sty` extraction. Preamble content is identical in semantics (just different packaging). |
| AC2.3 `.sty` contains all static content | `tests/integration/test_pdf_export.py::test_sty_compiles_standalone` + Phase 2 Task 1 implementation | The `.sty` file contains: package declarations (`\RequirePackage`), fixed commands (`\tightlist`, `\emojifallbackchar`, `\includegraphics` stub, `\cjktext`), environments (`userturn`, `assistantturn`), `\annot` macro, paragraph formatting, `otherlanguage` no-op, speaker colours. Verified indirectly by compilation (AC2.1) and by all mega-doc tests passing (AC2.2). |
| AC2.4 Missing `.sty` causes clear failure | `tests/integration/test_pdf_export.py::test_missing_sty_raises_error` | Write `.tex` with `\usepackage{promptgrimoire-export}` but do NOT copy `.sty`. Call `compile_latex()`. Assert raises `LaTeXCompilationError`. |
| AC3.1 `detect_scripts("Hello")` returns empty | `tests/unit/export/test_font_detection.py` | `detect_scripts("Hello world")` returns `frozenset()`. Also test Hebrew (`"shlom"` -> `{"hebr"}`), Arabic -> `{"arab"}`, CJK -> `{"cjk"}`, Devanagari -> `{"deva"}`, Greek -> `{"grek"}`, mixed -> `{"cjk", "hebr"}`, empty string -> `frozenset()`. Uses subtests for per-script iteration. |
| AC3.2 `detect_scripts()` covers all required scripts | `tests/unit/export/test_font_detection.py` (Guard 2) | For each `tag` in `_REQUIRED_SCRIPTS`, take first code point from `SCRIPT_TAG_RANGES[tag][0][0]`, construct `chr(cp)`, call `detect_scripts()`, assert `tag` in result. Proves every registered font CAN be activated. |
| AC3.3 Latin-only preamble output | `tests/unit/export/test_font_preamble.py` | `build_font_preamble(frozenset())` output contains Gentium Plus, Charis SIL, Noto Serif, `\setmainfont{TeX Gyre Termes}`. Does NOT contain `luatexja-fontspec`, `\setmainjfont`, `\renewcommand` with `cjktext`, or any non-base font names. |
| AC3.4 CJK preamble output | `tests/unit/export/test_font_preamble.py` | `build_font_preamble(frozenset({"cjk"}))` output contains `\usepackage{luatexja-fontspec}`, `\ltjsetparameter`, `\setmainjfont{Noto Serif CJK SC}`, `\setsansjfont{Noto Sans CJK SC}`, `\newjfontfamily\notocjk`, `\renewcommand` with `cjktext`/`notocjk`, `\setmainfont{TeX Gyre Termes}`, plus base fonts. |
| AC3.5 English-only compile < 2s | `tests/integration/test_pdf_export.py` (Phase 3 Task 9) | Compile English-only document through production pipeline. Time only the `compile_latex()` step with `time.monotonic()`. Assert < 2 seconds. Uses `@requires_latexmk`. |
| AC3.6 Full Unicode renders without U+FFFD | `tests/unit/test_latex_packages.py::test_unicode_preamble_compiles_without_tofu` + i18n mega-doc | Existing test compiles document with BLNS strings using production pipeline. i18n mega-doc (Phase 1 Task 12) compiles CJK/multilingual content and verifies no replacement characters in PDF text. |
| AC3.7 Guard 4: registry/detection consistency | `tests/unit/export/test_font_detection.py` (Guard 4) | Assert `_REQUIRED_SCRIPTS` is subset of `SCRIPT_TAG_RANGES.keys()`. Assert every non-`"latn"` `script_tag` in `FONT_REGISTRY` appears in `SCRIPT_TAG_RANGES`. Construct text with one character from every script in `_REQUIRED_SCRIPTS`, call `detect_scripts()`, assert result equals `_REQUIRED_SCRIPTS`. |
| AC3.8 `\cjktext` pass-through without CJK | `tests/integration/test_pdf_export.py` (Phase 3 Task 9) | Compile Latin-only document containing `\cjktext{hello}` in body. `.sty` provides `\providecommand{\cjktext}[1]{#1}` and `build_font_preamble(frozenset())` does NOT emit `\renewcommand`. Assert compiles without error. Assert PDF contains "hello". |
| AC4.1 `generate_tag_colour_definitions()` uses `latex_cmd()` | `tests/unit/export/test_latex_migration_snapshots.py` (Snapshot 1) + source code verification | Snapshot test calls function with known input including `"C#_notes"` tag, asserts output matches pre-migration baseline. Source inspection verifies `latex_cmd()` calls replace f-string `{{` patterns. |
| AC4.2 `format_annot_latex()` uses `render_latex()`/`latex_cmd()` | `tests/unit/export/test_latex_migration_snapshots.py` (Snapshots 2-3) + source code verification | Snapshot tests call function with known highlights (including LaTeX special chars in author/comment), assert output matches pre-migration baseline. Source inspection verifies migration. |
| AC4.3 `escape_latex()` escapes all 10 specials | `tests/unit/export/test_latex_render.py::TestEscapeLatex` | Test each of 10 LaTeX specials (`#$%&_{}~^\`) with subtests. Test passthrough for normal text, combined specials (`"Cost: $30 & 50%"`), and `NoEscape` passthrough. |
| AC4.4 Output identity pre/post migration | `tests/unit/export/test_latex_migration_snapshots.py` | Three snapshot tests captured BEFORE migration, verified AFTER: (1) `generate_tag_colour_definitions()` with known tags, (2) `format_annot_latex()` with known highlight, (3) `format_annot_latex()` with LaTeX specials in author/comments. Must be byte-identical. |
| AC4.5 Tag names with LaTeX specials | `tests/unit/export/test_latex_render.py::TestEscapeLatex` + `tests/unit/export/test_latex_migration_snapshots.py` | `escape_latex("C#_notes")` returns `"C\\#\\_notes"`. Snapshot test with `"C#_notes"` tag verifies colour definitions handle the name correctly. |
| AC5.1 No export source file > 550 lines | Phase 5 Task 3 verification | `wc -l src/promptgrimoire/export/*.py \| sort -rn` -- every file under 550 lines. |
| AC5.2 `format_annot_latex()` in `latex_format.py` | Phase 5 Task 1 implementation + `uv run test-all` | `grep -l "def format_annot_latex" src/promptgrimoire/export/` shows `latex_format.py` only. `highlight_spans.py` re-exports for backward compatibility. All tests pass. |
| AC5.3 `pdf_exporter` in `tests/integration/conftest.py` | Phase 5 Task 4 implementation + `uv run test-all` | `grep -l "def pdf_exporter" tests/` shows `tests/integration/conftest.py` only. No unit or E2E tests use it. All integration tests pass with fixture discovery. |
| AC5.4 All imports resolve after moves | Phase 5 Task 6 verification | `uvx ty check` passes. `uv run ruff check .` passes. Manual import verification of all moved modules succeeds. `uv run test-all` passes with zero import errors. |

---

## Human Verification Required

Items in this table require manual inspection or judgement that automated tests cannot fully capture.

| Criterion | Why Manual | Steps |
|-----------|------------|-------|
| AC1.1 Compile count | Exact count requires instrumented run or log analysis; not a simple assertion | See "End-to-End: Compile Count Audit" below |
| AC1.2 Assertion coverage completeness | Requires cross-referencing audit document with final test suite | See "End-to-End: Assertion Coverage Audit" below |
| AC1.3 Wall clock timing | Timing varies by machine; needs human judgement on acceptable variance | See "End-to-End: Performance Verification" below |
| AC2.2 Production output parity | Byte-identical PDF comparison is fragile (timestamps, font hinting); functional equivalence is the real criterion | See "Phase 2: Output Parity Spot-check" below |
| AC2.3 Static content completeness | Must visually confirm `.sty` includes all 8 content categories listed in Phase 2 Task 1 | See "Phase 2: .sty Content Inspection" below |
| AC4.1 No f-string `{{` patterns in migrated functions | Source code structure requires human review (grep may miss edge cases) | See "Phase 4: Source Inspection" below |
| AC4.2 No f-string `{{` patterns in migrated functions | Same as AC4.1 | See "Phase 4: Source Inspection" below |
| AC5.1 Line count verification | `wc -l` is definitive but needs human to run and check | See "Phase 5: File Size Verification" below |

---

## Human Test Plan

### Prerequisites

- TinyTeX installed (`uv run python scripts/setup_latex.py` -- includes `subfiles` package from Phase 1 Task 1)
- All dev dependencies installed (`uv sync`)
- `uv run test-all` passing (non-LaTeX tests green, confirming no regressions from file moves)
- `uv run test-all -m latex` passing (all LaTeX tests green)

### Phase 1: Mega-document Infrastructure

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | Run `uv run pytest tests/integration/test_pdf_export.py::TestGenerateTexOnly -v` | All tests pass. `generate_tex_only()` returns `.tex` path, file contains `\documentclass` and `\begin{document}`, no `.pdf` in output directory. |
| 1.2 | Run `uv run pytest tests/integration/test_mega_doc_infrastructure.py -v` | Infrastructure test passes: mega-doc compiles, subfiles compile independently, `MegaDocResult` has correct segment data. |
| 1.3 | Run `uv run pytest tests/integration/test_workspace_fixture_export.py -v` | All workspace export tests pass using module-scoped cached fixtures (2 compiles, not 30). |
| 1.4 | Run `uv run pytest tests/integration/test_english_mega_doc.py -v` | All English mega-doc subtests pass (chatbot fixtures, pipeline highlights, basic pipeline). 1 compile for entire module. |
| 1.5 | Run `uv run pytest tests/integration/test_i18n_mega_doc.py -v` | All i18n mega-doc subtests pass (CJK fixtures, character presence checks). 1 compile for entire module. |
| 1.6 | Verify duplicate tests deleted: `grep -rn "test_interleaved_highlights_compile\|test_export_cjk_with_highlight\|test_output_dir_defaults_to_tex_parent" tests/` | No results (tests removed). |
| 1.7 | Run `uv run pytest tests/integration/test_pdf_export.py::TestCriticalPathIsolation -v` | Isolation tests pass (margin note, highlight boundary), each <2s. |

### Phase 2: .sty Extraction

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Open `src/promptgrimoire/export/promptgrimoire-export.sty` in a text editor | File exists, is valid LaTeX, begins with `\NeedsTeXFormat{LaTeX2e}` and `\ProvidesPackage{promptgrimoire-export}`. |
| 2.2 | Run `uv run pytest tests/integration/test_pdf_export.py -k test_sty_compiles -v` | Guard test passes: minimal document with `\usepackage{promptgrimoire-export}` compiles to PDF. |
| 2.3 | Run `uv run pytest tests/integration/test_pdf_export.py -k test_missing_sty -v` | Failure test passes: compilation raises `LaTeXCompilationError` when `.sty` missing. |
| 2.4 | Verify `ANNOTATION_PREAMBLE_BASE` is gone: `grep -rn "ANNOTATION_PREAMBLE_BASE" src/promptgrimoire/export/preamble.py` | No results. |
| 2.5 | Verify `UNICODE_PREAMBLE` is gone: `grep -rn "UNICODE_PREAMBLE" src/promptgrimoire/export/unicode_latex.py` | No results (constant deleted; other functions remain). |
| 2.6 | Verify `build_annotation_preamble()` emits package load: `grep -n "usepackage.*promptgrimoire-export" src/promptgrimoire/export/preamble.py` | Shows `\usepackage{promptgrimoire-export}` in function body. |

### Phase 3: Dynamic Font Loading

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | Run `uv run pytest tests/unit/export/test_font_detection.py -v` | All detection tests and guard tests pass (AC3.1, AC3.2, AC3.7). |
| 3.2 | Run `uv run pytest tests/unit/export/test_font_preamble.py -v` | All preamble output tests pass (AC3.3, AC3.4, mixed scripts, full chain). |
| 3.3 | Run `uv run python -c "from promptgrimoire.export.unicode_latex import build_font_preamble; print(build_font_preamble(frozenset()))"` | Prints fallback chain with only 3 base fonts (Gentium Plus, Charis SIL, Noto Serif), `\setmainfont{TeX Gyre Termes}`, no `luatexja-fontspec`. |
| 3.4 | Run `uv run python -c "from promptgrimoire.export.unicode_latex import build_font_preamble; print(build_font_preamble(frozenset({'cjk'})))"` | Prints CJK setup with `luatexja-fontspec`, `\setmainjfont{Noto Serif CJK SC}`, `\renewcommand{\cjktext}`. |
| 3.5 | Verify `.sty` uses `fontspec` not `luatexja-fontspec`: `grep -n "RequirePackage.*fontspec" src/promptgrimoire/export/promptgrimoire-export.sty` | Shows `\RequirePackage{fontspec}` (NOT `luatexja-fontspec`). |
| 3.6 | Verify `.sty` has `\providecommand{\cjktext}`: `grep -n "providecommand.*cjktext" src/promptgrimoire/export/promptgrimoire-export.sty` | Shows `\providecommand{\cjktext}[1]{#1}`. |
| 3.7 | Verify `build_annotation_preamble()` has `body_text` parameter: `grep -n "def build_annotation_preamble" src/promptgrimoire/export/preamble.py` | Function signature includes `body_text: str = ""`. |

### Phase 4: t-string Migration

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | Run `uv run pytest tests/unit/export/test_latex_render.py -v` | All tests pass: `escape_latex()`, `NoEscape`, `latex_cmd()`, `render_latex()`. |
| 4.2 | Run `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v` | All snapshot tests pass (output identical to pre-migration baselines). |
| 4.3 | Run `uv run python -c "from promptgrimoire.export.latex_render import latex_cmd; print(latex_cmd('definecolor', 'mycolor', 'HTML', 'FF0000'))"` | Prints `\definecolor{mycolor}{HTML}{FF0000}`. |
| 4.4 | Run `uv run python -c "from promptgrimoire.export.latex_render import escape_latex; print(escape_latex('C#_notes'))"` | Prints `C\#\_notes`. |
| 4.5 | Verify `generate_tag_colour_definitions()` uses `latex_cmd()`: `grep -n "latex_cmd" src/promptgrimoire/export/preamble.py` | Shows `latex_cmd()` calls in the function body. |
| 4.6 | Verify `format_annot_latex()` uses `render_latex()` or `latex_cmd()`: `grep -n "latex_cmd\|render_latex" src/promptgrimoire/export/highlight_spans.py` (or `latex_format.py` if Phase 5 already ran) | Shows calls to `latex_cmd()` and/or `render_latex()`. |

### Phase 5: File Splits

| Step | Action | Expected |
|------|--------|----------|
| 5.1 | Run `wc -l src/promptgrimoire/export/*.py \| sort -rn` | No file exceeds 550 lines. |
| 5.2 | Verify `format_annot_latex()` location: `grep -rn "def format_annot_latex" src/promptgrimoire/export/` | Shows `latex_format.py` only (not `highlight_spans.py`). |
| 5.3 | Verify `pdf_exporter` fixture location: `grep -rn "def pdf_exporter" tests/` | Shows `tests/integration/conftest.py` only (not root `tests/conftest.py`). |
| 5.4 | Run `uvx ty check` | Type checking passes with zero errors. |
| 5.5 | Run `uv run ruff check .` | Linting passes. |
| 5.6 | Run `uv run python -c "from promptgrimoire.export.highlight_spans import compute_highlight_spans; from promptgrimoire.export.latex_format import format_annot_latex; from promptgrimoire.export.span_boundaries import PANDOC_BLOCK_ELEMENTS; from promptgrimoire.export.latex_render import render_latex, NoEscape, latex_cmd; from promptgrimoire.export.unicode_latex import escape_unicode_latex, detect_scripts; from promptgrimoire.export.preamble import build_annotation_preamble; from promptgrimoire.export.pdf_export import export_annotation_pdf; from promptgrimoire.export.pdf import compile_latex; print('All imports OK')"` | Prints "All imports OK" with no errors. |

### End-to-End: Compile Count Audit

**Purpose:** Verify AC1.1 -- total `compile_latex()` invocations across the full LaTeX test suite is ~12 (down from 68).

**Steps:**
1. Temporarily add `import logging; logger = logging.getLogger(__name__)` and `logger.warning("COMPILE_LATEX_CALLED")` at the top of `compile_latex()` in `src/promptgrimoire/export/pdf.py` (line ~65).
2. Run: `uv run test-all -m latex -v 2>&1 | grep -c "COMPILE_LATEX_CALLED"`
3. Expected: ~12 (exact breakdown: 2 workspace variants + 1 English mega-doc + 1 i18n mega-doc + 1 error path + 1 simple compile + 1 rich markdown + 2 isolation tests + 1 infrastructure + 1 preamble smoke + 1 string function = 12).
4. Remove the temporary logging.
5. If count exceeds 12 significantly, investigate which tests are calling `compile_latex()` unexpectedly.

### End-to-End: Assertion Coverage Audit

**Purpose:** Verify AC1.2 -- every assertion from the original 68-compile suite is preserved.

**Steps:**
1. Open `docs/wip/2026-02-12-latexmk-test-optimization.md` (the per-test compile audit).
2. For each test listed in the audit, verify one of: (a) it exists as a subtest in a mega-doc test, (b) it uses a module-scoped fixture, (c) it was deleted as redundant (AC1.7) with documented coverage explanation, (d) it remains as a standalone test.
3. Expected: every original test is accounted for.

### End-to-End: Performance Verification

**Purpose:** Verify AC1.3 and AC3.5 -- timing improvements are real.

**Steps:**
1. Run: `uv run pytest -m latex --durations=0 2>&1 | head -40`
2. Verify: no individual test exceeds 5s wall clock (AC1.3).
3. Verify: English mega-doc and Latin-only tests complete in <2s each (AC3.5 -- only after Phase 3).
4. Verify: i18n mega-doc completes in ~5s (full font chain, expected).
5. Compare total LaTeX test time against the 74.33s baseline (should be dramatically lower).

### End-to-End: Subfile Fallback Debugging

**Purpose:** Verify the mega-document subfile fallback produces useful error reports when a segment fails.

**Steps:**
1. In a test environment, temporarily modify one chatbot fixture's Pandoc output to include `\undefinedcommand` (e.g., add it to `tests/fixtures/claude_cooking.html` or modify the mega-document builder).
2. Run: `uv run pytest tests/integration/test_english_mega_doc.py -v`
3. Expected: test fails with a `LaTeXCompilationError` whose message includes a subfile isolation report identifying the failing segment (e.g., `segment_claude_cooking: FAILED - Undefined control sequence`).
4. Revert the modification.

### Phase 2: Output Parity Spot-check

**Purpose:** Verify AC2.2 -- `.sty` extraction does not change compiled output.

**Steps:**
1. After Phase 2 implementation, run `uv run pytest tests/integration/test_workspace_fixture_export.py -v`.
2. Verify all workspace tests pass (these compile real documents through the production pipeline).
3. Optionally: use `generate_tex_only()` to produce a `.tex` file, inspect the preamble section. It should contain `\usepackage{promptgrimoire-export}` plus per-document tag colour definitions -- no inline LaTeX package declarations.

### Phase 2: .sty Content Inspection

**Purpose:** Verify AC2.3 -- all 8 content categories are present.

**Steps:**
1. Open `src/promptgrimoire/export/promptgrimoire-export.sty`.
2. Verify these sections exist:
   - Package dependencies (`\RequirePackage{...}`)
   - Fixed commands (`\renewcommand{\includegraphics}`, `\providecommand{\tightlist}`, `\newcommand{\emojifallbackchar}`)
   - Environment definitions (`userturn`, `assistantturn`)
   - Paragraph formatting (`\setlength{\parindent}`, `\setlength{\parskip}`, `\setlength{\emergencystretch}`, `\setcounter{secnumdepth}`)
   - Static colour definitions (`usercolor`, `assistantcolor`, `many-dark`)
   - Annotation macro (`\newcounter{annotnum}`, `\newcommand{\annot}`)
   - Font-related (after Phase 3: `\RequirePackage{fontspec}`, `\RequirePackage{emoji}`, `\setemojifont`, `\providecommand{\cjktext}`)
   - `otherlanguage` no-op environment

### Phase 4: Source Inspection

**Purpose:** Verify AC4.1 and AC4.2 -- f-string `{{` patterns eliminated from migrated functions.

**Steps:**
1. Run: `grep -n 'f"\\\\' src/promptgrimoire/export/preamble.py src/promptgrimoire/export/highlight_spans.py src/promptgrimoire/export/unicode_latex.py`
2. Expected: no results in `generate_tag_colour_definitions()`, `format_annot_latex()`, or `_format_emoji_for_latex()`.
3. Allowed exceptions: `build_annotation_preamble()` (preamble assembly, not command construction), `build_font_preamble()` (complex multi-line LaTeX from Phase 3), `_DOCUMENT_TEMPLATE` in `pdf_export.py` (deliberately kept as `.format()`).

### Phase 5: File Size Verification

**Purpose:** Verify AC5.1 -- no export source file exceeds 550 lines.

**Steps:**
1. Run: `wc -l src/promptgrimoire/export/*.py | sort -rn`
2. Verify every file is under 550 lines.
3. Expected approximate sizes: `highlight_spans.py` ~520, `unicode_latex.py` ~450, `pandoc.py` ~360, `pdf_export.py` ~350, `html_normaliser.py` ~218, `span_boundaries.py` ~180, `preamble.py` ~100, `latex_format.py` ~90, `latex_render.py` ~80, `pdf.py` ~128.

---

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 Compile count <= 12 | Mega-doc infrastructure test (2 segments compile) | End-to-End: Compile Count Audit (instrumented run) |
| AC1.2 Assertions preserved | English mega-doc subtests, i18n mega-doc subtests, workspace fixture tests | End-to-End: Assertion Coverage Audit (cross-reference audit doc) |
| AC1.3 No test > 5s | `pytest --durations=0` | End-to-End: Performance Verification |
| AC1.4 `generate_tex_only()` | `TestGenerateTexOnly` (3 tests: basic, general_notes, notes_latex) | Phase 1 step 1.1 |
| AC1.5 Subfiles compilable | `test_mega_doc_infrastructure.py` (subfile independence) | Phase 1 step 1.2 |
| AC1.6 Subtest isolation | pytest-subtests in mega-doc and workspace tests | Phase 1 steps 1.3-1.5 |
| AC1.7 Duplicates deleted | `uv run test-all -m latex` passes after deletion | Phase 1 step 1.6 |
| AC1.8 Isolation tests | `TestCriticalPathIsolation` (margin note, highlight boundary) | Phase 1 step 1.7 |
| AC2.1 `.sty` compiles | `test_sty_compiles_standalone` | Phase 2 step 2.2 |
| AC2.2 Output parity | All mega-doc tests pass post-extraction | Phase 2: Output Parity Spot-check |
| AC2.3 `.sty` content | Guard test (compilation proves content works) | Phase 2: .sty Content Inspection |
| AC2.4 Missing `.sty` fails | `test_missing_sty_raises_error` | Phase 2 step 2.3 |
| AC3.1 `detect_scripts` basic | `test_font_detection.py` per-script subtests | Phase 3 step 3.1 |
| AC3.2 Detection covers all scripts | `test_font_detection.py` Guard 2 | Phase 3 step 3.1 |
| AC3.3 Latin-only preamble | `test_font_preamble.py` Latin-only assertions | Phase 3 step 3.3 |
| AC3.4 CJK preamble | `test_font_preamble.py` CJK assertions | Phase 3 step 3.4 |
| AC3.5 English compile < 2s | `test_pdf_export.py` timed compile test | End-to-End: Performance Verification |
| AC3.6 No U+FFFD in Unicode | `test_unicode_preamble_compiles_without_tofu` + i18n mega-doc | Phase 3 steps 3.1-3.2 (all tests green) |
| AC3.7 Guard 4 consistency | `test_font_detection.py` Guard 4 (registry vs detection) | Phase 3 step 3.1 |
| AC3.8 `\cjktext` pass-through | `test_pdf_export.py` cjktext passthrough compile | Phase 3 step 3.6 |
| AC4.1 `generate_tag_colour_definitions` migrated | `test_latex_migration_snapshots.py` Snapshot 1 | Phase 4: Source Inspection |
| AC4.2 `format_annot_latex` migrated | `test_latex_migration_snapshots.py` Snapshots 2-3 | Phase 4: Source Inspection |
| AC4.3 `escape_latex()` 10 specials | `test_latex_render.py::TestEscapeLatex` (10 subtests + combos) | Phase 4 step 4.4 |
| AC4.4 Output identity | `test_latex_migration_snapshots.py` (3 snapshots) | Phase 4 step 4.2 |
| AC4.5 Special chars in tags | `test_latex_render.py` + `test_latex_migration_snapshots.py` | Phase 4 step 4.4 |
| AC5.1 No file > 550 lines | -- | Phase 5: File Size Verification |
| AC5.2 `format_annot_latex` in `latex_format.py` | `uv run test-all` (imports resolve) | Phase 5 step 5.2 |
| AC5.3 `pdf_exporter` in integration conftest | `uv run test-all` (fixture discovery) | Phase 5 step 5.3 |
| AC5.4 All imports resolve | `uv run test-all` + `uvx ty check` + `uv run ruff check .` | Phase 5 steps 5.4-5.6 |
