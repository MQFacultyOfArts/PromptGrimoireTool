# Unicode Robustness Design

## Summary

This design adds robust unicode handling to PromptGrimoire's text handling pipeline—from PostgreSQL storage through pycrdt CRDTs to browser rendering and PDF export. Currently, LaTeX export only handles ASCII special characters; documents containing CJK text (Chinese, Japanese, Korean) or emoji fail to compile or render incorrectly. The primary approach is detect-and-wrap: text is scanned for unicode ranges, then wrapped in LaTeX commands with explicit font switches. This is more reliable than fontspec fallback chains, which have proven tedious to configure across environments.

The implementation includes a comprehensive test corpus: Big List of Naughty Strings (BLNS) parsed by category for targeted testing, plus CJK conversation fixtures for full pipeline integration tests. Pytest markers separate fast smoke tests from slow full-corpus validation (`pytest -m blns`). Round-trip tests verify unicode survives each pipeline stage; injection tests verify BLNS doesn't break security boundaries. A visual validation demo route (`/demo/blns-validation`) enables manual comparison of browser and PDF rendering.

## Definition of Done

- [ ] Core unicode tests (CJK + common emoji) run on every `pytest` invocation
- [ ] BLNS corpus tests available via `pytest -m blns`
- [ ] `uv run test-all-fixtures` runs full corpus including BLNS and slow LaTeX tests
- [ ] `uv run test-debug` excludes BLNS and slow tests
- [ ] LaTeX export renders CJK text correctly (Japanese, Chinese, Korean)
- [ ] LaTeX export renders emoji correctly (including ZWJ sequences)
- [ ] All text storage/retrieval paths pass unicode round-trip tests
- [ ] `/demo/blns-validation` route provides visual inspection of BLNS/CJK rendering

## Glossary

- **BLNS (Big List of Naughty Strings)**: A corpus of pathological input strings (unicode edge cases, control characters, RTL text, etc.) used to stress-test string handling in applications
- **CJK**: Chinese, Japanese, and Korean writing systems; use unified ideographic characters from Unicode ranges U+4E00–U+9FFF
- **CRDT (Conflict-free Replicated Data Type)**: Data structure that allows concurrent edits from multiple users without conflicts; PromptGrimoire uses pycrdt for collaborative annotation
- **Emoji ZWJ sequences**: Multi-codepoint emoji formed by joining base emoji with Zero-Width Joiner (U+200D), e.g. family emoji, profession emoji with skin tones
- **Hiragana/Katakana**: Japanese syllabic writing systems (U+3040–U+309F, U+30A0–U+30FF)
- **Hangul**: Korean alphabet characters (U+AC00–U+D7AF)
- **LaTeX**: Document preparation system using plain-text markup; PromptGrimoire uses it for PDF generation
- **LuaLaTeX**: Modern LaTeX engine with native Unicode support and Lua scripting; required for advanced font handling
- **Noto fonts**: Google's open-source font family with comprehensive Unicode coverage, including CJK
- **Parameterized tests**: pytest feature to run the same test logic against multiple input values
- **pytest markers**: Tags (`@pytest.mark.blns`) to categorise tests and control which run via command-line filters
- **Round-trip test**: Test that stores data, retrieves it, and verifies it's unchanged; validates encoding/decoding correctness
- **TinyTeX**: Minimal LaTeX distribution; PromptGrimoire uses it for portable, consistent PDF generation
- **Unicode range detection**: Scanning text to identify character blocks (CJK, emoji, ASCII) for targeted handling

## Architecture

**Primary approach:** Detect-and-wrap. Text is scanned for unicode ranges (CJK ideographs, emoji), then wrapped in appropriate LaTeX commands with explicit font switches. This approach is more reliable than fontspec fallback chains, which have proven tedious to configure correctly across environments.

Phase 1 briefly investigates whether fontspec-only could work, but the expectation is detect-and-wrap will be needed.

**Components:**

1. **Unicode LaTeX Handler** (`src/promptgrimoire/export/unicode_latex.py`)
   - Range detection for CJK and emoji codepoints
   - Explicit font-switch wrapping for non-ASCII text
   - Entry point: `escape_unicode_latex()` replacing `_escape_latex()`

2. **Test Fixtures** (`tests/fixtures/`)
   - BLNS corpus (`blns.txt`, `blns.json`) — full corpus for opt-in runs; txt parsed at collection time for category-based parameterisation
   - BLNS injection subset (curated from categories) — ~50 strings targeting LaTeX/SQL/XSS injection, runs always
   - CJK conversation fixtures (`conversations/translation_*.html`, `conversations/chinese_wikipedia.html`) — full pipeline integration tests
   - Curated unicode samples extracted from CJK fixtures for unit tests

3. **Test Infrastructure** (`tests/unit/test_unicode_handling.py`)
   - Parameterized tests with pytest markers
   - Round-trip tests for DB, CRDT, and LaTeX layers
   - **Injection tests** for all text input paths (not just preservation)

4. **Test Runner Scripts**
   - `test-all-fixtures` script for full confidence runs

## Existing Patterns

Investigation found existing LaTeX escaping in `src/promptgrimoire/export/latex.py:572-588`. The `_escape_latex()` function handles ASCII special characters only.

This design extends that pattern:
- Keep existing ASCII escape logic
- Add unicode range detection before escaping
- Wrap non-ASCII in appropriate LaTeX commands

The existing pattern of a single escape function is preserved—`escape_unicode_latex()` becomes the new entry point, calling the existing ASCII logic internally.

Test runner scripts follow existing pattern in `scripts/test_debug.py`.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Investigation and Test Infrastructure

**Goal:** Determine viable LaTeX approach; set up test corpus and pytest markers

**Components:**
- **Fontspec investigation** — Test if TeX Gyre Termes + Noto CJK + Noto Color Emoji fallback chain works in LuaLaTeX
- `tests/fixtures/blns.txt` — Big List of Naughty Strings corpus with category comments (parsed at collection time)
- `tests/fixtures/blns.json` — BLNS as flat JSON array (alternative format)
- `tests/conftest.py` — BLNS parser: extracts categories from `#\t` headers, provides `BLNS_BY_CATEGORY` dict
- `tests/conftest.py` — Injection subset: curated ~50 strings from injection-related categories
- `pyproject.toml` — Add `blns` and `slow` pytest markers, configure default exclusion
- `scripts/test_all_fixtures.py` — Script to run full corpus

**Dependencies:** None

**Done when:**
- Decision documented: fontspec fallback OR detect-and-wrap
- `pytest --collect-only` shows markers registered
- `uv run pytest` excludes `blns` and `slow` by default (but runs `blns_injection` always)
- `uv run test-all-fixtures` runs without marker filtering
- `uv run test-debug` continues to work (excludes slow tests)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Unicode Detection Module

**Goal:** Create unicode range detection utilities

**Components:**
- `src/promptgrimoire/export/unicode_latex.py` — Unicode detection and LaTeX wrapping
  - `is_cjk(char)` — Detect CJK unified ideographs, hiragana, katakana, hangul
  - `is_emoji(char)` — Detect emoji ranges (may use `emoji` library or regex)
  - `escape_unicode_latex(text)` — Main entry point

**Dependencies:** Phase 1 (test fixtures)

**Done when:**
- Detection correctly identifies CJK ranges (U+4E00–U+9FFF, U+3040–U+30FF, U+AC00–U+D7AF)
- Detection correctly identifies emoji (including multi-codepoint sequences)
- Unit tests pass for detection functions
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: LaTeX Wrapping Implementation

**Goal:** Wrap detected unicode in appropriate LaTeX commands

**Components:**
- `src/promptgrimoire/export/unicode_latex.py` — Extend with wrapping logic
  - CJK text wrapped for font switching
  - Emoji wrapped with `\emoji{}` command or font switch
  - Preserve existing ASCII escape logic from `_escape_latex()`

**Dependencies:** Phase 2 (detection module)

**Done when:**
- `escape_unicode_latex("Hello 世界")` produces valid LaTeX with CJK handling
- `escape_unicode_latex("Test 🎉")` produces valid LaTeX with emoji handling
- Mixed content handled correctly
- Unit tests pass
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: TinyTeX Package Setup

**Goal:** Add required LaTeX packages for CJK and emoji

**Components:**
- `scripts/setup_latex.py` — Add package installation
  - `emoji` package
  - `luatexja` bundle
  - `noto` fonts (or configure system font usage)

**Dependencies:** Phase 3 (wrapping implementation)

**Done when:**
- `uv run python scripts/setup_latex.py` installs required packages
- LuaLaTeX can compile documents with `\usepackage{emoji}` and `\usepackage{luatexja-fontspec}`
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Integration with Existing Export

**Goal:** Replace `_escape_latex()` with unicode-aware version

**Components:**
- `src/promptgrimoire/export/latex.py` — Update to use `escape_unicode_latex()`
- `src/promptgrimoire/export/pdf_export.py` — Update HTML-to-LaTeX conversion
- LaTeX preamble updates for emoji and CJK font setup

**Dependencies:** Phase 4 (TinyTeX packages)

**Done when:**
- Existing PDF export tests still pass
- PDF export with CJK content compiles successfully
- PDF export with emoji content compiles successfully
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Round-Trip and Injection Tests

**Goal:** Verify all text handling layers preserve unicode AND resist injection

**Components:**
- `tests/unit/test_unicode_handling.py` — Parameterized tests
  - `test_db_roundtrip` — SQLModel storage and retrieval preserves content
  - `test_crdt_roundtrip` — pycrdt Text preservation
  - `test_latex_escape_no_crash` — escape function doesn't raise
  - `test_latex_compiles` — generated LaTeX compiles (marked `slow`)
  - `test_pdf_no_tofu` — extract text from PDF via pdftotext, verify content survived rendering
  - `test_latex_no_command_injection` — BLNS injection subset doesn't execute LaTeX commands
  - `test_html_no_xss` — BLNS injection subset doesn't break HTML rendering
  - `test_sql_no_injection` — BLNS injection subset stored safely via SQLModel

**Dependencies:** Phase 5 (integration)

**Done when:**
- Core unicode samples pass all round-trip tests
- BLNS injection subset passes all injection tests (runs always)
- Full BLNS corpus passes round-trip tests (via `pytest -m blns`)
- LaTeX compilation tests pass for representative samples
- PDF tofu detection catches missing glyphs (pdftotext extraction)
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Visual Validation Demo Route

**Goal:** Manual inspection of BLNS/CJK rendering in browser and PDF

**Components:**
- `src/promptgrimoire/pages/blns_validation.py` — Demo page at `/demo/blns-validation`
  - Displays BLNS strings by category
  - Displays CJK sample content
  - Export to PDF button

**Dependencies:** Phase 6 (round-trip tests passing)

**Done when:**
- `/demo/blns-validation` route accessible (requires `ENABLE_DEMO_PAGES`)
- Can view content in browser and export to PDF for visual comparison
<!-- END_PHASE_7 -->

## Additional Considerations

**Architecture decision in Phase 1:** Detect-and-wrap is the expected approach based on prior experience with fontspec complexity. Phase 1 briefly investigates fontspec-only but will likely confirm detect-and-wrap is needed for reliable cross-environment rendering.

**Memory usage:** First compilation with Noto CJK fonts can use ~6GB RAM for font cache generation. Document this in setup instructions. CI runners may need larger instances or pre-cached fonts.

**Test performance:** BLNS has ~500 strings. LaTeX compilation is slow (~2-5s per document). Full corpus runs are for pre-release confidence, not every commit. Injection subset (~50 strings) runs always.

**Font availability:** Design assumes Noto fonts available. If not installed, LaTeX compilation will fail with clear error. Setup script handles installation.

**Missing TinyTeX packages:** LaTeX tests should skip with clear message if required packages not installed, rather than failing with cryptic LaTeX errors. Use pytest fixture that checks package availability.

**CJK fixture dual purpose:** The HTML conversation fixtures (`translation_japanese_sample.html`, etc.) serve two purposes: (1) full workspace→document→PDF pipeline integration tests, and (2) text extraction for unicode sample corpus in unit tests.

**BLNS category parsing:** The `blns.txt` file uses `#\t` prefixes for category headers. Parser distinguishes headers from explanatory comments by checking for title-case text after blank lines and filtering out lines containing "which" (explanations).

**Tofu detection:** PDF export tests verify content survived rendering by extracting text via `pdftotext` and comparing to input. Missing glyphs (rendered as `.notdef` or tofu boxes) typically disappear or become replacement characters in extraction, making this a low-cost detection method.
