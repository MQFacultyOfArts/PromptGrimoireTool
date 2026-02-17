# Execution Status: PDF Export Character Alignment

**Last updated:** 2026-02-09
**Branch:** milkdown-crdt-spike
**Base SHA (before work):** e1a3e85

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: `insert_markers_into_dom` + Tests | **COMPLETE** | UAT confirmed 2026-02-09. 2152 tests pass, 80 Phase 1 tests pass. |
| Phase 2: Wire into Export Pipeline | **BLOCKED** | 28 pass, 2 xfail. Tofu fixed. Cross-heading highlights need #134 (LuaLaTeX node-level). |
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

### Test Results: 28 pass, 2 xfail

**Unicode/tofu: FIXED** (`fde4b68`) — all 13 `TestUnicodeRendering` tests pass. Font fallback for `\href{}` context resolved.

**Highlight boundary drift (2 xfail):**
- `hl5_jurisdiction` and `hl9_legal_issues` — cross-heading highlights not wrapped correctly
- Root cause: Python-side LaTeX string manipulation fundamentally cannot handle escaped braces inside `\highLight{}`
- Tracked in #134 (LuaLaTeX node-level highlighting)
- Full-AST rewrite with pylatexenc attempted and reverted — see `WIP-walker-architectural-dead-end.md`

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
| `TestHighlightWrappingInTex` | 3 | 1 | 2 (xfail, #134) |
| `TestUnicodeRendering` | 13 | 13 | 0 |

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

1. **Tofu: DONE.** All 13 unicode tests pass after `fde4b68`.
2. **Cross-heading highlights: BLOCKED on #134.** pylatexenc approach dead-ended. See `WIP-walker-architectural-dead-end.md`.
3. **Next steps for this branch:**
   - Merge to main (28 pass, 2 xfail is clean)
   - Branch #134 from main for LuaLaTeX node-level highlighting
   - Phases 3 and 4 of the original plan can proceed independently
