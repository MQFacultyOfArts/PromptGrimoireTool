# Execution Status: PDF Export Character Alignment

**Last updated:** 2026-02-09
**Branch:** milkdown-crdt-spike
**Base SHA (before work):** e1a3e85

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: `insert_markers_into_dom` + Tests | **COMPLETE** | UAT confirmed 2026-02-09. 2152 tests pass, 80 Phase 1 tests pass. |
| Phase 2: Wire into Export Pipeline | **IN PROGRESS** | `walk_and_wrap` implemented, detection tests written. 12 known failures remain. |
| Phase 3: Rename general_notes to response_draft | Not started | |
| Phase 4: Delete Dead Code | Not started | |

## Phase 2 — Current State

### What's Done

6 commits, 30 integration tests written:

1. `a73ba76` — `fix: use doc.content instead of deleted doc.raw_content for PDF export`
2. `effc106` — `feat: wire insert_markers_into_dom into convert_html_with_annotations`
3. `1b97886` — `fix: simplify export_annotation_pdf, add ValueError for empty content`
4. `a82b538` — `test: add ValueError guard and fixture regression tests for export pipeline`
5. `f51940b` — `fix: move \annot outside LaTeX sectioning commands (Issue #132)`
6. `5cb966a` — `feat: walk_and_wrap AST splitting, workspace fixture, PDF detection tests`

### Known Failures (12 tests) — RED phase

**Highlight boundary drift (2 failures):**
- `hl5_jurisdiction`: "Mr Lawlis sought leave to rely on three grounds" — body text after "Grounds of Appeal" heading is NOT inside `\highLight{}`. Only heading is wrapped.
- `hl9_legal_issues`: "21 years old at the time" — continuation text after "Subjective factors" heading is NOT inside `\highLight{}`.

Root cause: `_insert_markers_into_html` character counting diverges from `extract_text_from_html`. Markers drift from expected positions on long documents. This is the Phase 1 alignment issue — the DOM-based `insert_markers_into_dom` should fix it once wired in properly.

**Unicode/tofu (10 failures):**
- U+FFFD replacement characters in PDF output
- 9 scripts fail to render: Armenian, Arabic, Bulgarian, Georgian, Greek, Hebrew, Hindi, Thai, Ukrainian
- Chinese Simplified and Vietnamese render correctly

Root cause: The General Notes section goes through `markdown_to_latex_notes()` (pandoc markdown→LaTeX) which produces raw Unicode inside `\href{}{}` commands. The `UNICODE_PREAMBLE` font fallback chain should handle this but does NOT activate for all scripts. The text IS in the .tex source — the fonts fail at render time. Needs investigation: possibly `\href` context bypasses main font fallback, or luatexja-fontspec fallback chain has gaps.

### Response Draft Persistence (DONE)

Added `mark_dirty_workspace()` call to `_setup_yjs_event_handler` in `annotation_respond.py` so Milkdown editor changes in Tab 3 are persisted to the database via the CRDT persistence manager.

### Workspace Fixture

Created `tests/fixtures/workspace_lawlis_v_r.json` with:
- 11 highlights (jurisdiction, procedural_history, reasons, legally_relevant_facts, legal_issues, reflection)
- Comments on each highlight
- Response draft markdown with multilingual lorem ipsum (Armenian, Arabic, Chinese, Korean, Georgian, Hindi, Hebrew, Thai, etc.)

HTML fixture: `tests/fixtures/conversations/lawlis_v_r_austlii.html` (Lawlis v R [2025] NSWCCA 183)

### Detection Test Suite

`tests/integration/test_workspace_fixture_export.py` — 30 tests:

| Test Class | Tests | Pass | Fail |
|---|---|---|---|
| `TestPdfBasicIntegrity` | 1 | 1 | 0 |
| `TestHighlightBoundariesInPdf` | 13 | 13 | 0 |
| `TestHighlightWrappingInTex` | 3 | 1 | 2 |
| `TestUnicodeRendering` | 13 | 3 | 10 |

Tests use `pymupdf` (dev dependency) and `pdftotext` (system) for PDF text extraction.

### Design Decision: AST-Walk Approach (Issue #132)

Instead of patching the delimiter list, replace the splitting infrastructure with a **single AST walk**:

1. Parse full LaTeX (from Pandoc) with pylatexenc (already a dependency, already used in `_extract_env_boundaries()` and `_strip_texorpdfstring()`)
2. Walk AST depth-first, maintaining a **stack of active highlights**
3. At **text nodes** (LatexCharsNode): scan for HLSTART/HLEND/ANNMARKER markers (Lark tokenizer stays), push/pop highlight stack, emit text wrapped in current stack
4. At **structural boundary nodes** (environments, sections, paragraph breaks): close active highlights, emit boundary, reopen highlights
5. At **inline nodes** (`\textbf`, `\emph`): pass through inside current wrapping
6. ANNMARKER: emit `\annot` at current (post-boundary) level — inherently the most normal context

This replaces:
- `_wrap_content_with_nested_highlights()` (hardcoded delimiter splitting)
- `_move_annots_outside_sections()` (regex post-processor)
- The hardcoded delimiter list

### Popperian Risky Test

**Falsifiable claim:** A single function `walk_and_wrap(latex: str, marker_highlights: list[dict], ...) -> str` that parses the full Pandoc LaTeX with pylatexenc and walks the AST tracking a highlight stack will:

1. Never produce `\highLight` or `\underLine` containing a blank line or `\par`
2. Never produce `\annot` inside `\section{}` or any restricted argument
3. Pass all 2192 existing tests without modification
4. Handle the currently-crashing export (highlight spanning heading + list) without LaTeX compilation errors

If ANY of these fail, the AST-walk approach is wrong and needs a different design.

## Phase 1 Commits

1. `b1ed015` — `feat: add shared marker constants module`
2. `4c5d033` — `feat: implement insert_markers_into_dom with two-pass approach`
3. `93be344` — `test: add tests for insert_markers_into_dom`
4. `2d5d5a1` — `test: add fixture-based tests for insert_markers_into_dom`
5. `49cbf0d` — `fix: handle boundary conditions in insert_markers_into_dom`
6. `07449bb` — `fix: add type: ignore justification comment per project standard`

## Phase 1 Review History

- **Review 1:** APPROVED, zero issues
- **Proleptic challenge:** 3 counterarguments raised
  - #1 (DOM walk duplication): Filed as Issue #131, deferred
  - #2 (Phase 2 dependency assumption): Assessed as addressed by design
  - #3 (No fixture-based tests): **Addressed** — added 53 fixture tests
- **Boundary bugs found during fixture testing:** Fixed (HLEND at doc end, HLSTART at char 0, marker ordering)
- **Review 2:** Important: 1 (type:ignore comment), Minor: 1 (walk dupe = Issue #131)
- **Review 3:** APPROVED, zero issues

## Phase 1 UAT Checklist (CONFIRMED 2026-02-09)

- [x] Shared marker constants module at `src/promptgrimoire/export/marker_constants.py`
- [x] `insert_markers_into_dom` in `src/promptgrimoire/input_pipeline/html_input.py`
- [x] Round-trip property holds for all test cases
- [x] 27 unit tests pass (including 6 boundary condition tests)
- [x] 53 fixture-based integration tests pass across 17 real platform HTML fixtures
- [x] Boundary bugs fixed
- [x] ACs covered: AC3.1-AC3.5, AC1.3, AC1.4

## Files Changed in Phase 1

- **Created:** `src/promptgrimoire/export/marker_constants.py`
- **Modified:** `src/promptgrimoire/input_pipeline/html_input.py` (~280 lines added)
- **Modified:** `src/promptgrimoire/input_pipeline/__init__.py` (export added)
- **Created:** `tests/unit/input_pipeline/test_insert_markers.py` (27 tests)
- **Created:** `tests/unit/input_pipeline/test_insert_markers_fixtures.py` (53 tests)

## Implementation Guidance

- `.ed3d/implementation-plan-guidance.md` exists — pass to code reviewers
- `test-requirements.md` exists in plan directory — use at final review

## Issues Filed

- #131: refactor: extract shared DOM walk from extract_text_from_html and _walk_and_map
- #132: generalize LaTeX annotation splitting using AST (pylatexenc)

## Key Files

- `src/promptgrimoire/export/latex.py` — pipeline, walk_and_wrap, pylatexenc AST walk
- `src/promptgrimoire/export/unicode_latex.py` — UNICODE_PREAMBLE, escape_unicode_latex
- `src/promptgrimoire/export/pdf_export.py` — markdown_to_latex_notes, export orchestration
- `tests/integration/test_workspace_fixture_export.py` — 30 PDF-level detection tests
- `tests/unit/export/test_walk_and_wrap.py` — 21 walk_and_wrap unit tests
- `tests/integration/test_highlight_latex_elements.py` — 18 structural tests

## Resume Instructions

1. Start a new conversation on branch `milkdown-crdt-spike`
2. Read this file for full context
3. **Next tasks (in order):**
   a. Fix tofu: investigate why UNICODE_PREAMBLE font fallback doesn't activate for text inside `\href{}{}` in the General Notes section
   b. Fix highlight boundary drift: wire `insert_markers_into_dom` (Phase 1) to replace `_insert_markers_into_html` so character counting aligns with `extract_text_from_html`
4. All 12 detection test failures should turn GREEN as fixes land
5. Phases 3 and 4 of the original plan remain after this
