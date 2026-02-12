# LaTeX Test Suite Optimisation: Compile Reduction, Dynamic Fonts, and Preamble Extraction

## Summary

This design optimizes PromptGrimoire's LaTeX test suite by reducing 68 slow compilation invocations (totalling ~11 minutes) to 5 mega-document compiles (~13 seconds). The approach combines three architectural changes: (1) extracting static LaTeX preamble code into a proper `.sty` package file shared by production and tests, (2) implementing dynamic font loading that detects which Unicode scripts are actually present in a document and loads only the necessary fonts (reducing English-only compile time from ~5s to ~1s), and (3) consolidating tests that share the same input variant into mega-documents separated by page breaks, where each compile validates multiple assertions using pytest-subtests.

The work also includes two code quality improvements: migrating LaTeX generation from f-strings with heavy `{{` escaping to Python 3.14 t-strings with auto-escaping, and splitting oversized files along natural concern boundaries (separating HTML region computation from LaTeX formatting, moving test fixtures to module-specific conftest files). All changes preserve existing test coverage through regression guards ensuring production/test parity. Phase 1 (mega-document infrastructure) provides the test safety net for subsequent refactoring phases.

## Definition of Done

1. LaTeX test suite reduced from 68 `compile_latex()` invocations to ~5 mega-document compiles
2. Shared `promptgrimoire-export.sty` extracted from Python preamble code, used by both production and tests
3. Dynamic font loading based on Unicode range detection -- only load fallback fonts needed for the document's actual content
4. LaTeX generation functions migrated to Python 3.14 t-strings with a `render_latex()` renderer for auto-escaping
5. `pytest-subtests` used for multiple assertions per compile
6. Regression guards ensuring production/test preamble parity (`.sty` validity, font registry coverage, snapshot comparison)
7. All existing test assertions preserved -- no coverage regression
8. Monolith files split along natural concern boundaries (highlight_spans.py, conftest.py, unicode_latex.py)

## Acceptance Criteria

### latex-test-optimization.AC1: Compile reduction (DoD items 1, 5, 7)

- **latex-test-optimization.AC1.1 Success:** Total `compile_latex()` invocations across the full test suite is <= 6 (5 mega-docs + 1 error path standalone)
- **latex-test-optimization.AC1.2 Success:** Every assertion from the original 68-compile test suite has a corresponding subtest in the mega-doc tests
- **latex-test-optimization.AC1.3 Success:** No individual LaTeX test exceeds 5s wall clock (down from 13-16s per test in baseline of 74.33s / 2290 tests). After Phase 3 (dynamic fonts), Latin-only mega-doc tests complete in under 2s each
- **latex-test-optimization.AC1.4 Success:** `generate_tex_only()` returns a `.tex` file path without invoking `compile_latex()`
- **latex-test-optimization.AC1.5 Success:** Each mega-document body segment is independently compilable via `subfiles` package
- **latex-test-optimization.AC1.6 Failure:** A subtest failure in mega-doc does not prevent remaining subtests from executing
- **latex-test-optimization.AC1.7 Edge:** Duplicate tests (`test_interleaved_highlights_compile`, `test_export_cjk_with_highlight`, `test_output_dir_defaults_to_tex_parent`) are deleted without coverage loss -- their assertions are covered by remaining tests
- **latex-test-optimization.AC1.8 Success:** Critical paths (margin note alignment, Unicode rendering, highlight boundaries) retain fast standalone isolation tests alongside mega-doc subtests -- margin notes are sensitive to page context and must be verified in short documents, not just mega-doc sections

### latex-test-optimization.AC2: `.sty` extraction (DoD items 2, 6)

- **latex-test-optimization.AC2.1 Success:** `promptgrimoire-export.sty` compiles in a minimal `\documentclass{article}\usepackage{promptgrimoire-export}\begin{document}Test\end{document}` without errors
- **latex-test-optimization.AC2.2 Success:** Production `export_annotation_pdf()` output is byte-identical to pre-extraction output for a reference document (same preamble content, just different packaging)
- **latex-test-optimization.AC2.3 Success:** The `.sty` file contains all static preamble content: package declarations, fixed commands, environments, and macros
- **latex-test-optimization.AC2.4 Failure:** Removing the `.sty` from the output directory causes `compile_latex()` to fail with a clear error (not a silent fallback)

### latex-test-optimization.AC3: Dynamic font loading (DoD items 3, 6)

- **latex-test-optimization.AC3.1 Success:** `detect_scripts("Hello World")` returns `frozenset()` (no non-Latin scripts detected; Latin is implicit)
- **latex-test-optimization.AC3.2 Success:** `detect_scripts(text_with_all_required_scripts)` returns script tags covering Armenian, Arabic, Cyrillic, CJK, Georgian, Greek, Hebrew, Devanagari, Thai
- **latex-test-optimization.AC3.3 Success:** `build_font_preamble(frozenset())` emits a fallback chain with only Latin base fonts (Gentium Plus, Charis SIL, Noto Serif) and no `luatexja-fontspec` loading
- **latex-test-optimization.AC3.4 Success:** `build_font_preamble(frozenset({"cjk"}))` emits `luatexja-fontspec`, CJK font setup (`\setmainjfont{Noto Serif CJK SC}`), and CJK entries in fallback chain
- **latex-test-optimization.AC3.5 Success:** An English-only document compiles in under 2 seconds (vs ~5s with full Unicode preamble)
- **latex-test-optimization.AC3.6 Success:** A document containing all `_REQUIRED_SCRIPTS` text renders without U+FFFD replacement characters
- **latex-test-optimization.AC3.7 Failure:** Adding a font to `FONT_REGISTRY` without a corresponding `detect_scripts()` range causes Guard 4 test to fail
- **latex-test-optimization.AC3.8 Edge:** `\cjktext{}` command works as pass-through when `luatexja-fontspec` is not loaded (no undefined command error)

### latex-test-optimization.AC4: t-string migration (DoD item 4)

- **latex-test-optimization.AC4.1 Success:** `generate_tag_colour_definitions()` uses t-strings -- no `{{` escape sequences in source
- **latex-test-optimization.AC4.2 Success:** `format_annot_latex()` uses t-strings -- no `{{` escape sequences in source
- **latex-test-optimization.AC4.3 Success:** `render_latex()` escapes LaTeX special characters (`#`, `$`, `%`, `&`, `_`, `{`, `}`, `~`, `^`, `\`) in interpolated values
- **latex-test-optimization.AC4.4 Success:** Output of t-string-rendered functions is identical to pre-migration f-string output for the same inputs
- **latex-test-optimization.AC4.5 Edge:** Tag names containing LaTeX special characters (e.g., `C#_notes`) are escaped correctly in colour definitions

### latex-test-optimization.AC5: File splits (DoD item 8)

- **latex-test-optimization.AC5.1 Success:** No source file in `src/promptgrimoire/export/` exceeds 550 lines
- **latex-test-optimization.AC5.2 Success:** `format_annot_latex()` lives in `export/latex_format.py`, separate from HTML region computation in `highlight_spans.py`
- **latex-test-optimization.AC5.3 Success:** `pdf_exporter` fixture lives in `tests/integration/conftest.py`, not root `tests/conftest.py`
- **latex-test-optimization.AC5.4 Success:** All imports across the codebase resolve correctly after moves

## Glossary

- **LuaLaTeX**: A LaTeX engine that executes Lua scripts during compilation, enabling advanced typesetting features like custom font fallback chains and Unicode handling
- **latexmk**: Build automation tool for LaTeX that handles multiple compilation passes and dependency tracking
- **luaotfload**: LuaTeX module that loads OpenType/TrueType fonts; eagerly loads font metadata on startup (~4.4s overhead)
- **luatexja-fontspec**: LaTeX package for Japanese typesetting with LuaTeX; also handles Chinese and Korean (CJK) text
- **OpenType script tag**: Four-character identifier (e.g., `hebr`, `arab`, `deva`) standardising writing system support in fonts; maps to Unicode blocks
- **Pandoc**: Document converter that transforms HTML to LaTeX in PromptGrimoire's export pipeline
- **pytest-subtests**: pytest plugin enabling multiple independent assertions per test function (like unittest.TestCase.subTest)
- **subfiles**: LaTeX package allowing document fragments to be compiled independently while sharing a main document's preamble
- **t-string**: Python 3.14 template string format (PEP 750) that separates interpolation from formatting, enabling custom renderers like `render_latex()`
- **TinyTeX**: Minimal, portable TeX Live distribution used by PromptGrimoire for consistent LaTeX compilation
- **Unicode block**: Contiguous range of Unicode code points assigned to a script or symbol set (e.g., U+0370--U+03FF for Greek)
- **xdist**: pytest plugin for parallel test execution across multiple worker processes

## Architecture

### Current state

The PDF export pipeline generates LaTeX from annotated HTML, assembles a preamble with font configuration, and compiles via `latexmk --lualatex`. The preamble is built entirely in Python: `ANNOTATION_PREAMBLE_BASE` (~85 lines of static LaTeX in `preamble.py`), `UNICODE_PREAMBLE` (~100 lines including a 30-font fallback chain in `unicode_latex.py`), and dynamic per-document tag colour definitions using f-strings with heavy `{{` escaping.

The test suite invokes `compile_latex()` 68 times across 6 test files. 30 of those compile identical inputs (same workspace fixture, same highlights, same tag colours). Each compile takes ~5-10 seconds, totalling ~11 minutes for the full suite. Font loading accounts for ~4.4 seconds per compile regardless of content (fonts are eager-loaded by luaotfload).

### Target state

Three architectural changes:

1. **Static LaTeX as a `.sty` package.** All package declarations, fixed commands, environments, and macros move to `promptgrimoire-export.sty`. Python emits `\usepackage{promptgrimoire-export}` instead of inline LaTeX. The `.sty` is the single source of truth for static preamble content, shared by production and tests.

2. **Dynamic font loading.** A `FONT_REGISTRY` in `unicode_latex.py` maps each fallback font to its OpenType script tag and corresponding Unicode ranges. `detect_scripts(text)` scans document content and returns the set of scripts present. `build_font_preamble(scripts)` emits only the font entries needed. For English-only documents (the common case), this reduces per-compile overhead from ~4.8s to ~0.4s. CJK package loading (`luatexja-fontspec`, `\setmainjfont`) is conditional on CJK ranges being detected.

3. **Mega-document testing.** Tests that share the same input variant are combined into mega-documents separated by `\clearpage` + `\section*{}`. Each mega-document compiles once; `pytest-subtests` asserts many things against the single compiled output. The `subfiles` LaTeX package makes each body segment independently compilable for debugging.

### Data flow

```
HTML content
    |
    v
detect_scripts(body_text) -> frozenset[str]
    |
    v
build_font_preamble(scripts) -> str  (conditional font chain)
    |
    v
generate_tag_colour_definitions(tag_colours) -> str  (t-string rendered)
    |
    v
build_annotation_preamble(tag_colours, body_text) -> str
    = xcolor + tag colours + \usepackage{promptgrimoire-export} + font preamble
    |
    v
_DOCUMENT_TEMPLATE.format(preamble=..., body=..., notes=...)
    |
    v
compile_latex(tex_path) -> pdf_path
```

### Compile budget

| Mega-document | Content | Fonts | Est. time |
|---------------|---------|-------|-----------|
| Workspace variant A | English legal doc, highlights, no draft | Latin only | ~1s |
| Workspace variant B | English doc + multilingual response draft | Full Unicode | ~5s |
| English chatbots + pipeline + misc | 13 English fixtures + highlight mechanics | Latin only | ~1s |
| CJK/i18n fixtures | 4 CJK chatbots + 4 i18n fixtures | Full Unicode | ~5s |
| Error path (standalone) | Trivial | Latin only | ~1s |

**Total: ~13s** (down from 68 compiles where the slowest 10 are 13-16s each; full suite 74.33s / 2290 tests with xdist). 3 Latin-only compiles + 2 full Unicode compiles. 80-90% reduction on the per-test wall clock for LaTeX tests after Phase 3.

## Existing Patterns

### Preamble assembly

`build_annotation_preamble()` in `preamble.py:146-165` already concatenates preamble sections from multiple sources. This design extends that pattern -- the `.sty` replaces inline LaTeX, and the font preamble becomes another concatenated section.

### Test markers and decorators

`@requires_latexmk` decorator in `conftest.py:192-230` applies `@pytest.mark.latex` and skips tests when TinyTeX is unavailable. All compile tests use this decorator. The mega-doc tests will continue using it.

### Module-scoped data fixtures

`tests/integration/test_workspace_fixture_export.py` already uses `@pytest.fixture(scope="module")` for `workspace_fixture()` and `html_content()` -- pure data loaders. The mega-doc pattern extends this with module-scoped compiled outputs.

### Export pipeline separation

The export module already separates concerns: `pdf.py` (compilation), `pandoc.py` (conversion), `preamble.py` (assembly), `unicode_latex.py` (Unicode handling), `highlight_spans.py` (annotation markup). This design preserves that separation and makes it cleaner by extracting static LaTeX to a `.sty` file.

### Sub-conftest files

`tests/integration/conftest.py`, `tests/e2e/conftest.py`, and `tests/unit/conftest.py` already exist. Moving fixtures from the root `conftest.py` to these files follows the established directory structure.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Mega-document Test Infrastructure

**Goal:** Reduce 68 compiles to ~5 while preserving all existing assertions. Establish the test safety net that protects subsequent refactoring phases.

**Components:**

- `generate_tex_only()` in `src/promptgrimoire/export/pdf_export.py` -- new function that runs the full pipeline up to but not including `compile_latex()`, returning the `.tex` file path
- `subfiles` package added to `scripts/setup_latex.py` TinyTeX installation
- `pytest-subtests` added to `pyproject.toml` dev dependencies
- Mega-document test helpers (fixture builders, subtest assertion utilities) in `tests/integration/conftest.py`
- Refactored test files: `test_workspace_fixture_export.py`, `test_chatbot_fixtures.py`, `test_pdf_export.py`, `test_pdf_pipeline.py`, `test_latex_string_functions.py`, `test_latex_packages.py`
- Duplicate tests deleted: `test_interleaved_highlights_compile` (same topology as `test_three_overlapping_highlights_compile`), `test_export_cjk_with_highlight` (duplicate of i18n tests), `test_output_dir_defaults_to_tex_parent` (redundant with output_dir parameter test)

**Dependencies:** None (first phase)

**Done when:** All existing assertions pass, total compile count is ~5, test suite runs in under 30 seconds for LaTeX tests (down from ~11 minutes)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Extract `.sty` Package

**Goal:** Move static LaTeX from Python string constants into a proper LaTeX package file, shared between production and tests.

**Components:**

- `promptgrimoire-export.sty` -- new file containing all static preamble content: package declarations, fixed commands (`\tightlist`, `\emojifallbackchar`, `\includegraphics` stub, `\cjktext` conditional), environments (`userturn`, `assistantturn`), `\annot` macro, paragraph formatting, `otherlanguage` no-op, speaker colours
- `src/promptgrimoire/export/preamble.py` -- `ANNOTATION_PREAMBLE_BASE` replaced with `\usepackage{promptgrimoire-export}` emission. `build_annotation_preamble()` signature unchanged externally
- Guard 1 test: `.sty` compiles in a minimal `\documentclass{article}` document

**Dependencies:** Phase 1 (mega-doc tests as safety net)

**Done when:** All mega-doc tests pass, `.sty` guard test passes, production exports produce identical PDFs
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Dynamic Font Loading

**Goal:** Load only the fonts needed for each document's actual Unicode content. Speeds up production exports for the common English-only case (12x faster) and enables Latin-only test compiles.

**Components:**

- `FallbackFont` dataclass and `FONT_REGISTRY` in `src/promptgrimoire/export/unicode_latex.py` -- structured font catalogue with OpenType script tags and Unicode range mappings
- `SCRIPT_TAG_RANGES` dict in `unicode_latex.py` -- standardised OpenType script tag to Unicode block mapping
- `detect_scripts(text) -> frozenset[str]` in `unicode_latex.py` -- scans text for Unicode code points, returns needed script tags
- `build_font_preamble(scripts) -> str` in `unicode_latex.py` -- emits minimal `\directlua{}` fallback chain + conditional CJK block
- `build_annotation_preamble()` in `preamble.py` -- gains `body_text` parameter to pass detected scripts to font builder
- `UNICODE_PREAMBLE` string constant deleted, replaced by dynamic builder output
- `\cjktext` command -- conditional definition: wraps `\notocjk` when CJK loaded, pass-through when not (defined in `.sty` with conditional logic, or emitted by Python)
- Guard 2 test: `detect_scripts()` covers all `_REQUIRED_SCRIPTS` entries
- Guard 3 test: preamble output snapshot for known multilingual input
- Guard 4 test: full-Unicode text produces full fallback chain (registry and detection are consistent)

**Dependencies:** Phase 2 (`.sty` extraction)

**Done when:** All mega-doc tests pass (Unicode mega-doc gets full chain, Latin-only mega-docs get minimal chain), guard tests pass, English-only exports compile in ~1s
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: t-string Migration

**Goal:** Replace f-string LaTeX generation (with fragile `{{` escaping) with Python 3.14 t-strings and a `render_latex()` renderer that auto-escapes interpolated values.

**Components:**

- `render_latex()` function -- t-string renderer that escapes LaTeX special characters in interpolated values
- `generate_tag_colour_definitions()` in `preamble.py` -- migrated from f-strings to t-strings
- `format_annot_latex()` in `highlight_spans.py` (or new `export/latex_format.py`) -- migrated from f-strings to t-strings
- `_DOCUMENT_TEMPLATE` in `pdf_export.py` -- migrated to t-string

**Dependencies:** Phase 2 (`.sty` extraction separates static from dynamic LaTeX)

**Done when:** All mega-doc tests pass, no f-string `{{` escaping patterns remain in export module LaTeX generation
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: File Splits and Cleanup

**Goal:** Split monolith files along natural concern boundaries revealed by previous phases.

**Components:**

- `src/promptgrimoire/export/latex_format.py` -- new module receiving `format_annot_latex()` and related LaTeX rendering functions from `highlight_spans.py` (~200 lines)
- `highlight_spans.py` shrinks to ~550 lines (HTML region computation only)
- `tests/conftest.py` -- `pdf_exporter` fixture and BLNS helpers moved to `tests/integration/conftest.py` and `tests/unit/conftest.py` respectively
- `tests/conftest.py` shrinks from 692 lines to ~300 lines (config, markers, shared helpers)

**Dependencies:** Phase 4 (t-string migration determines final shape of `format_annot_latex()`)

**Done when:** No source file exceeds ~550 lines, all tests pass, imports resolve correctly
<!-- END_PHASE_5 -->

## Additional Considerations

**`\cjktext` conditional definition.** When `luatexja-fontspec` is not loaded, the `\cjktext{...}` command must still be defined (as a pass-through) because `escape_unicode_latex()` wraps CJK characters in `\cjktext{}` regardless of font configuration. The conditional definition can live in the `.sty` using `\@ifpackageloaded{luatexja-fontspec}` or be emitted by Python alongside the font preamble.

**Font registry maintenance.** When a new font is added to the system (via `setup_latex.py`), it must also be added to `FONT_REGISTRY` with its script tag and Unicode ranges. Guard 4 catches missing entries. The `setup_latex.py` font list and `FONT_REGISTRY` should ideally share a single source of truth.

**subfiles package path resolution.** All test `.tex` files and the `.sty` must be in the same directory (or the `.sty` must be on the TeX search path). The simplest approach: write the `.sty` alongside the `.tex` in the temp directory during compilation. Production copies the `.sty` to the output directory; tests do the same.

**Critical path isolation tests.** Margin note alignment, Unicode rendering, and highlight boundaries each get a small, fast standalone test alongside their mega-doc subtests. These isolation tests compile a minimal document (~1s) targeting one specific concern. This catches state leakage that mega-doc subtests might miss (e.g. `\cjktext` redefinition affecting margin note placement, or `\clearpage` not fully flushing floating margin notes). Isolation tests are not redundant with mega-docs — they test the same concerns with a shorter feedback loop and without cross-section interference.

**Implementation scoping.** Phase 1 is the largest phase (test rewriting). Phases 2-5 are each smaller refactors protected by the Phase 1 test suite. Phase 4 (t-strings) can run in parallel with Phase 3 (dynamic fonts) since they touch different concerns, but sequential execution is safer.
