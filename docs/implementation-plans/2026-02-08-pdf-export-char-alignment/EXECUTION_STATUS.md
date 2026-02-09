# Execution Status: PDF Export Character Alignment

**Last updated:** 2026-02-09
**Branch:** milkdown-crdt-spike
**Base SHA (before work):** e1a3e85

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: `insert_markers_into_dom` + Tests | **COMPLETE** | UAT confirmed 2026-02-09. 2152 tests pass, 80 Phase 1 tests pass. |
| Phase 2: Wire into Export Pipeline | **BLOCKED** | 4 tasks done, code review APPROVED. Manual test revealed LaTeX bugs → design pivot to Issue #132 (AST-based splitting). |
| Phase 3: Rename general_notes to response_draft | Not started | |
| Phase 4: Delete Dead Code | Not started | |

## Phase 2 — Current State

### What's Done

4 implementation tasks complete, code review APPROVED (2192 tests pass):

1. `a73ba76` — `fix: use doc.content instead of deleted doc.raw_content for PDF export`
2. `effc106` — `feat: wire insert_markers_into_dom into convert_html_with_annotations`
3. `1b97886` — `fix: simplify export_annotation_pdf, add ValueError for empty content`
4. `a82b538` — `test: add ValueError guard and fixture regression tests for export pipeline`
5. `f51940b` — `fix: move \annot outside LaTeX sectioning commands (Issue #132)`

### What's Broken

PDF export crashes when highlights span block boundaries. Two bugs found:

**Bug 1 (FIXED):** `\annot` (contains `\par` via `\marginalia`/`\parbox`) placed inside `\section{}` (moving argument). Fixed with `_move_annots_outside_sections()` post-processor in f51940b.

**Bug 2 (BLOCKING):** Blank lines (= `\par` in LaTeX) inside `\highLight`/`\underLine` (lua-ul). Error: `Paragraph ended before \text@command was complete`. The `_wrap_content_with_nested_highlights()` splits at a hardcoded delimiter list (`\par`, `\\`, `\tabularnewline`, `&`, `\begin{}`/`\end{}`), but misses blank lines. Adding blank lines would fix this case, but the hardcoded-list approach is whack-a-mole — every new restricted context requires another delimiter.

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

Brainstormed and validated in conversation 2026-02-09. Proleptic challenges run against three alternative approaches (A: targeted AST splitter, B: unified post-processor, C: pre-split regions). The AST-walk-with-highlight-stack emerged from dialogue as the correct approach.

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

- `src/promptgrimoire/export/latex.py` — pipeline, existing pylatexenc usage in `_extract_env_boundaries()` and `_strip_texorpdfstring()`
- `tests/integration/test_highlight_latex_elements.py` — 18 structural tests (headings, inline, block, cross-boundary)
- `tests/unit/export/test_empty_content_guard.py` — 22 pipeline tests

## Resume Instructions

1. Start a new conversation on branch `milkdown-crdt-spike`
2. Read this file for full context
3. The next task is: implement the AST-walk approach described above using TDD
4. Write tests for the Popperian risky claims FIRST
5. Phases 3 and 4 of the original plan remain after this is resolved
