# LaTeX Test Optimisation — Phase 5: File Splits and Cleanup

**Goal:** Split monolith files along natural concern boundaries revealed by previous phases. No source file in `export/` exceeds 550 lines, test fixtures live in the right conftest.

**Architecture:** Three splits: (1) `format_annot_latex()` moves from `highlight_spans.py` to new `export/latex_format.py`, (2) boundary detection functions + constants move from `highlight_spans.py` to new `export/span_boundaries.py`, (3) `pdf_exporter` fixture moves from root `tests/conftest.py` to `tests/integration/conftest.py` and BLNS helpers to `tests/unit/conftest.py`.

**Tech Stack:** Python 3.14

**Scope:** 5 phases from original design (phase 5 of 5)

**Codebase verified:** 2026-02-13

**Key files to read before implementing:**
- `src/promptgrimoire/export/highlight_spans.py` — 752 lines, primary split target
- `tests/conftest.py` — 692 lines, fixture split target
- `tests/integration/conftest.py` — 41 lines, receives `pdf_exporter`
- `tests/unit/conftest.py` — 65 lines, receives BLNS helpers

---

## Acceptance Criteria Coverage

This phase implements and tests:

### latex-test-optimization.AC5: File splits (DoD item 8)

- **latex-test-optimization.AC5.1 Success:** No source file in `src/promptgrimoire/export/` exceeds 550 lines
- **latex-test-optimization.AC5.2 Success:** `format_annot_latex()` lives in `export/latex_format.py`, separate from HTML region computation in `highlight_spans.py`
- **latex-test-optimization.AC5.3 Success:** `pdf_exporter` fixture lives in `tests/integration/conftest.py`, not root `tests/conftest.py`
- **latex-test-optimization.AC5.4 Success:** All imports across the codebase resolve correctly after moves

---

## Existing Code Reference

Before implementing, the executor should read these files for context:

| File | Purpose | Lines |
|------|---------|-------|
| `src/promptgrimoire/export/highlight_spans.py` | Region computation + annotation formatting + boundary detection | 752 |
| `tests/conftest.py` | Root fixtures: `pdf_exporter`, BLNS helpers, `requires_latexmk`, E2E fixtures | 692 |
| `tests/integration/conftest.py` | Integration fixtures (currently just DB reset) | 41 |
| `tests/unit/conftest.py` | Unit fixtures | 65 |

---

## Line count budget

After all Phase 5 splits, the files should be:

| File | Before | After | Change |
|------|--------|-------|--------|
| `highlight_spans.py` | 752 | ~520 | -232 (format_annot + boundary functions + constants) |
| `latex_format.py` | new | ~90 | format_annot_latex + imports |
| `span_boundaries.py` | new | ~180 | 3 boundary functions + 2 constants + imports |
| `tests/conftest.py` | 692 | ~490 | -202 (pdf_exporter + BLNS helpers) |
| `tests/integration/conftest.py` | 41 | ~130 | +88 (pdf_exporter + PdfExportResult) |
| `tests/unit/conftest.py` | 65 | ~185 | +117 (BLNS helpers) |

All under 550.

**Note:** All "Before" and "After" line counts are approximate and based on codebase state at time of writing. Phases 1-4 modify these files, so actual counts will vary. The acceptance criterion (AC5.1: no file exceeds 550 lines) is what matters, not the exact estimates.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
## Subcomponent A: Export Module Splits

<!-- START_TASK_1 -->
### Task 1: Create export/latex_format.py from format_annot_latex()

**Verifies:** latex-test-optimization.AC5.2

**Files:**
- Create: `src/promptgrimoire/export/latex_format.py`
- Modify: `src/promptgrimoire/export/highlight_spans.py` (remove function)
- Modify: `src/promptgrimoire/export/__init__.py` (add export)
- Modify: any files importing `format_annot_latex` from `highlight_spans`

**Implementation:**

**Step 1: Create `latex_format.py`.** Move from `highlight_spans.py`:
- The section comment (lines 97-99)
- `format_annot_latex()` function (lines 102-168)

The new file needs these imports:
```python
from __future__ import annotations

from typing import Any

from promptgrimoire.export.latex_render import NoEscape, latex_cmd
from promptgrimoire.export.preamble import _format_timestamp, _strip_test_uuid
from promptgrimoire.export.unicode_latex import escape_unicode_latex
```

(Exact imports depend on the state after Phase 4 migration. If Phase 4 has already run, `format_annot_latex` uses `latex_cmd`/`render_latex`. If not, it still uses f-strings and `escape_unicode_latex` directly.)

**Step 2: Update `highlight_spans.py`.** Remove:
- Lines 97-168 (format_annot_latex section)
- Any imports only used by format_annot_latex (e.g., `_format_timestamp`, `_strip_test_uuid`, possibly `escape_unicode_latex` if no other function uses it)

Add import at top:
```python
from promptgrimoire.export.latex_format import format_annot_latex
```

This re-export maintains backwards compatibility for any code importing `format_annot_latex` from `highlight_spans`.

**Step 3: Find all importers.** Search the codebase for files that import `format_annot_latex` from `highlight_spans`:
```bash
grep -rn "from.*highlight_spans.*import.*format_annot_latex" src/ tests/
```
Update these imports to use `latex_format` directly. The re-export in `highlight_spans.py` is a safety net, not the primary import path.

**Step 4: Add `format_annot_latex` to `export/__init__.py`** if it's part of the public API.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass, no import errors

Run: `wc -l src/promptgrimoire/export/highlight_spans.py`
Expected: ~680 lines (still needs boundary extraction in Task 2)

**Commit:** `refactor: move format_annot_latex() to export/latex_format.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create export/span_boundaries.py from boundary detection functions

**Verifies:** latex-test-optimization.AC5.1 (highlight_spans.py under 550)

**Files:**
- Create: `src/promptgrimoire/export/span_boundaries.py`
- Modify: `src/promptgrimoire/export/highlight_spans.py` (remove functions + constants)

**Implementation:**

**Step 1: Create `span_boundaries.py`.** Move from `highlight_spans.py`:

Constants:
- `PANDOC_BLOCK_ELEMENTS` (lines 32-66)
- `INLINE_FORMATTING_ELEMENTS` (lines 68-94)

Functions:
- `_detect_block_boundaries()` (lines 272-347)
- `_inline_context_at()` (lines 348-396)
- `_detect_inline_boundaries()` (lines 397-431)

The new file needs these imports:
```python
from __future__ import annotations

from promptgrimoire.input_pipeline.html_input import TextNodeInfo
```

(Check exact imports — the boundary functions use `TextNodeInfo` and possibly other types from `html_input`.)

**Step 2: Update `highlight_spans.py`.** Remove the moved constants and functions. Add imports:
```python
from promptgrimoire.export.span_boundaries import (
    INLINE_FORMATTING_ELEMENTS,
    PANDOC_BLOCK_ELEMENTS,
    _detect_block_boundaries,
    _detect_inline_boundaries,
)
```

Note: `_inline_context_at` is only called by `_detect_inline_boundaries`, so it doesn't need to be imported by `highlight_spans.py`.

**Step 3: Verify remaining functions in `highlight_spans.py` still have access to the constants and boundary functions they need.** The main consumers are:
- `_split_regions_at_boundaries()` — calls `_detect_block_boundaries` and `_detect_inline_boundaries`
- `_build_span_tag()` — may reference constants

**Verification:**
Run: `uv run test-all`
Expected: All tests pass

Run: `wc -l src/promptgrimoire/export/highlight_spans.py`
Expected: ~520 lines (under 550)

**Commit:** `refactor: move boundary detection to export/span_boundaries.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify all export files under 550 lines

**Verifies:** latex-test-optimization.AC5.1

**Files:**
- No file changes (verification only)

**Implementation:**

Run: `wc -l src/promptgrimoire/export/*.py | sort -rn`

Verify ALL files are under 550 lines. Expected after all phases:

| File | Expected lines |
|------|---------------|
| `highlight_spans.py` | ~520 |
| `unicode_latex.py` | ~450 (grew in Phase 3 with FONT_REGISTRY + detect_scripts) |
| `pandoc.py` | ~360 (unchanged) |
| `pdf_export.py` | ~350 (grew slightly with generate_tex_only in Phase 1) |
| `html_normaliser.py` | ~218 (unchanged) |
| `span_boundaries.py` | ~180 (new) |
| `preamble.py` | ~100 (shrank in Phase 2, ANNOTATION_PREAMBLE_BASE → .sty) |
| `latex_format.py` | ~90 (new) |
| `latex_render.py` | ~80 (new, Phase 4) |
| `pdf.py` | ~128 (unchanged) |
| `list_normalizer.py` | ~63 (unchanged) |
| `__init__.py` | ~25 |

If any file exceeds 550, investigate and split further.

**Verification:**
Run: `wc -l src/promptgrimoire/export/*.py | sort -rn`
Expected: no file exceeds 550 lines
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
## Subcomponent B: Test Fixture Splits

<!-- START_TASK_4 -->
### Task 4: Move pdf_exporter fixture to tests/integration/conftest.py

**Verifies:** latex-test-optimization.AC5.3

**Files:**
- Modify: `tests/conftest.py` (remove `PdfExportResult` and `pdf_exporter`)
- Modify: `tests/integration/conftest.py` (add them)

**Implementation:**

**Step 1: Move from `tests/conftest.py` to `tests/integration/conftest.py`:**
- `PdfExportResult` dataclass (lines 292-300)
- `pdf_exporter` fixture (lines 301-379)
- Any imports they need that aren't already in `tests/integration/conftest.py`

**Step 2: Verify scope.** The `pdf_exporter` fixture has function scope (no explicit scope = default). It's used by integration tests only. Confirm no unit tests or E2E tests use it:
```bash
grep -rn "pdf_exporter" tests/unit/ tests/e2e/
```
If any unit tests use it, they should be reclassified as integration tests (they compile PDFs = slow).

**Step 3: Verify imports.** The `pdf_exporter` fixture imports from `promptgrimoire.export.pdf_export` and uses `compile_latex`, `export_annotation_pdf`, etc. These imports must be added to `tests/integration/conftest.py`.

**Verification:**
Run: `uv run pytest tests/integration/ -v --co` (collect only, verify fixture discovery)
Run: `uv run test-all -m latex`
Expected: All tests pass, no fixture-not-found errors

**Commit:** `refactor: move pdf_exporter fixture to tests/integration/conftest.py`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Move BLNS helpers to tests/unit/conftest.py

**Verifies:** latex-test-optimization.AC5.1 (root conftest under 550, though it's a test file)

**Files:**
- Modify: `tests/conftest.py` (remove BLNS helpers)
- Modify: `tests/unit/conftest.py` (add BLNS helpers)

**Implementation:**

**Step 1: Move from `tests/conftest.py` to `tests/unit/conftest.py`:**
- `_parse_blns_by_category()` (lines 52-116)
- `_is_cjk_codepoint()` (lines 117-132)
- `_extract_cjk_chars_from_blns()` (lines 133-145)
- `_extract_emoji_from_blns()` (lines 146-168)

These are all private helper functions used by BLNS-related test fixtures.

**Step 2: Check consumers.** Search for which tests use BLNS fixtures:
```bash
grep -rn "blns\|BLNS\|_parse_blns\|_extract_cjk\|_extract_emoji" tests/
```

If used by integration tests too, the helpers should go in root conftest or a shared utility. But BLNS tests are typically unit tests (string processing, not compilation).

**Step 3: Move any BLNS fixtures** that depend on these helpers.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass

Run: `wc -l tests/conftest.py`
Expected: ~490 lines (still large due to E2E fixtures, but under 550)

**Commit:** `refactor: move BLNS helpers to tests/unit/conftest.py`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
## Subcomponent C: Import Resolution and Verification

<!-- START_TASK_6 -->
### Task 6: Verify all imports resolve correctly

**Verifies:** latex-test-optimization.AC5.4

**Files:**
- Modify: any files with broken imports (fix as needed)

**Implementation:**

After all moves, verify that every import in the codebase resolves:

```bash
# Type check (catches import errors)
uvx ty check

# Lint check
uv run ruff check .

# Try importing all export modules
uv run python -c "
from promptgrimoire.export.highlight_spans import compute_highlight_spans
from promptgrimoire.export.latex_format import format_annot_latex
from promptgrimoire.export.span_boundaries import PANDOC_BLOCK_ELEMENTS
from promptgrimoire.export.latex_render import render_latex, NoEscape, latex_cmd
from promptgrimoire.export.unicode_latex import escape_unicode_latex, detect_scripts
from promptgrimoire.export.preamble import build_annotation_preamble
from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.export.pdf import compile_latex
print('All imports OK')
"
```

Fix any broken imports. Common issues:
- Circular imports after moves (resolve by importing at function level or restructuring)
- Tests importing from old locations (update to new module paths)
- `__init__.py` exports that reference moved functions

**Verification:**
Run: `uvx ty check`
Run: `uv run ruff check .`
Run: `uv run test-all`
Expected: All pass, no import errors

**Commit:** `fix: resolve import paths after file splits` (only if fixes needed)
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Full regression verification

**Verifies:** All AC5 criteria

**Files:**
- No file changes (verification only)

**Implementation:**

Final verification of all Phase 5 acceptance criteria:

1. **AC5.1:** `wc -l src/promptgrimoire/export/*.py | sort -rn` — no file exceeds 550
2. **AC5.2:** `grep -l "def format_annot_latex" src/promptgrimoire/export/` — shows `latex_format.py` only
3. **AC5.3:** `grep -l "def pdf_exporter" tests/` — shows `tests/integration/conftest.py` only
4. **AC5.4:** `uv run test-all` — all tests pass
5. Full suite: `uv run test-all` — zero regressions

**Verification:**
Run: `uv run test-all`
Expected: All tests pass, zero regressions
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

1. [ ] Run `wc -l src/promptgrimoire/export/*.py | sort -rn` — no file exceeds 550 lines
2. [ ] Verify `format_annot_latex()` is in `export/latex_format.py`
3. [ ] Verify `pdf_exporter` fixture is in `tests/integration/conftest.py`
4. [ ] Run `uv run test-all` — full suite passes
5. [ ] Run `uvx ty check` — type checking passes
6. [ ] Run `uv run ruff check .` — linting passes

## Evidence Required
- [ ] `wc -l` output showing all export files under 550 lines
- [ ] Test output showing all tests green
- [ ] Type checking output (clean)
