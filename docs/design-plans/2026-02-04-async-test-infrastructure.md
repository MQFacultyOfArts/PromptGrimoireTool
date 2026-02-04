# Async Test Infrastructure for LaTeX Pipeline Design

## Summary

This design converts the LaTeX export pipeline from synchronous subprocess calls to async/await patterns, enabling parallel test execution and non-blocking PDF compilation. Currently, the pipeline blocks on external processes (Pandoc for HTML→LaTeX conversion and latexmk/lualatex for compilation), which creates bottlenecks in tests and prevents concurrent execution.

The implementation follows the async subprocess pattern already established in `pdf.py:compile_latex()`, using `asyncio.create_subprocess_exec` with PIPE for stdout/stderr. This is a refactoring effort with no functional changes—the same external tools will be called, but using async I/O. Test files that directly invoke subprocess commands will be updated to use the existing async `compile_latex()` helper, and deprecated RTF parser tests will be removed to eliminate LibreOffice subprocess dependencies.

**Note:** The kpsewhich lookup (`_find_emoji_table()`) remains synchronous as it runs once at module import time, before test workers are dispatched.

## Definition of Done

The implementation is complete when:

1. **Pandoc conversion is async** - `convert_html_to_latex()` uses `asyncio.create_subprocess_exec`
2. **All callers updated** - Functions calling `convert_html_to_latex()` are async and await properly
3. **LibreOffice removed from tests** - `test_cross_env_highlights.py` loads `183-libreoffice.html` fixture directly
4. **RTF parser tests removed** - `test_rtf_parser.py` deleted (deprecated functionality that keeps erroring)
5. **Direct subprocess calls fixed** - `test_overlapping_highlights.py` and `test_latex_packages.py` use `await compile_latex()`
6. **All tests pass** - `uv run test-all` passes
7. **Pandoc subprocess is async** - `grep "subprocess.run" src/promptgrimoire/export/latex.py` returns nothing (kpsewhich in unicode_latex.py is OK - runs at import time)

## Glossary

- **asyncio**: Python's standard library for writing concurrent code using async/await syntax
- **Pandoc**: Universal document converter used to transform HTML to LaTeX in the annotation export pipeline
- **kpsewhich**: TeX utility for locating files in the TeX directory structure, used to find emoji lookup tables
- **latexmk**: Build automation tool for LaTeX that handles multiple compilation passes
- **lualatex**: LaTeX compiler with Lua scripting support, required for the marginalia package
- **RTF (Rich Text Format)**: Microsoft document format, previously used with LibreOffice conversion (now deprecated)
- **LibreOffice**: Open-source office suite previously used for RTF→HTML conversion (being removed)
- **pytest.mark.asyncio**: Pytest decorator that enables testing of async functions by running them in an event loop

## Architecture

Convert all synchronous subprocess calls in the LaTeX export pipeline to async using asyncio's async subprocess API. This enables parallel test execution without blocking on external processes.

**Components affected:**
- `src/promptgrimoire/export/latex.py` - Pandoc HTML→LaTeX conversion (make async)
- `tests/integration/test_cross_env_highlights.py` - LibreOffice fixture loading (use HTML fixture)
- `tests/unit/test_rtf_parser.py` - deprecated RTF parser tests (delete)
- `tests/unit/test_overlapping_highlights.py` - direct latexmk call (use compile_latex)
- `tests/unit/test_latex_packages.py` - direct lualatex call (use compile_latex)

**Not changed:**
- `src/promptgrimoire/export/unicode_latex.py` - kpsewhich runs at module import, before test workers dispatch

**Async subprocess pattern** (established in `pdf.py:compile_latex`): Use `asyncio.create_subprocess_exec` with PIPE for stdout/stderr, then `await proc.communicate()`.

## Existing Patterns

Investigation found the async subprocess pattern already established in `src/promptgrimoire/export/pdf.py:compile_latex()`. This design follows that exact pattern for consistency.

The `@pytest.mark.asyncio` decorator pattern is already used throughout the test suite for async tests.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Async Pandoc Conversion

**Goal:** Convert `convert_html_to_latex()` to async

**Components:**
- `src/promptgrimoire/export/latex.py` - change `subprocess.run()` at line 1230 to async subprocess
- `src/promptgrimoire/export/pdf_export.py` - update caller to await

**Dependencies:** None

**Done when:** `convert_html_to_latex()` is async, callers await it, tests pass
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Fix Test Files

**Goal:** Remove sync subprocess calls from tests, use HTML fixture for LibreOffice

**Components:**
- `tests/integration/test_cross_env_highlights.py` - load `183-libreoffice.html` fixture directly, remove `parse_rtf()` call
- `tests/unit/test_overlapping_highlights.py` - replace direct subprocess latexmk call with `await compile_latex()`
- `tests/unit/test_latex_packages.py` - replace direct subprocess lualatex call with `await compile_latex()`

**Dependencies:** Phase 1

**Done when:** No direct subprocess calls for LaTeX compilation in test files, tests pass
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Remove Deprecated RTF Parser Tests

**Goal:** Remove tests for deprecated LibreOffice RTF conversion

**Components:**
- `tests/unit/test_rtf_parser.py` - delete entire file

**Dependencies:** Phase 2

**Done when:** RTF parser tests removed, `uv run test-all` passes
<!-- END_PHASE_3 -->
