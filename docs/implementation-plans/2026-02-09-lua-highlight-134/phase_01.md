# 134-lua-highlight Implementation Plan — Phase 1: Extract preamble and Pandoc modules

**Goal:** Split `latex.py` (1,708 lines) into focused modules aligned with the DFD, creating `preamble.py` and `pandoc.py` without any behaviour change.

**Architecture:** Pure mechanical refactor. Move P5 functions (colour defs, preamble, escape utilities) to `preamble.py`. Move P3 functions (Pandoc conversion, orchestration) to `pandoc.py`. Update all imports. P2 and P4 code stays in `latex.py` temporarily — deleted in Phase 4.

**Tech Stack:** Python 3.14, no new dependencies

**Scope:** Phase 1 of 4 from original design

**Codebase verified:** 2026-02-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 134-lua-highlight.AC3: Module split (DoD item 2)
- **134-lua-highlight.AC3.1 Success:** `latex.py` is split into modules where no single file exceeds ~400 lines.
- **134-lua-highlight.AC3.2 Success:** Module boundaries align with DFD processes (marker insertion, Pandoc conversion, preamble/document assembly).
- **134-lua-highlight.AC3.3 Success:** All imports from `pdf_export.py` and `annotation.py` continue to resolve (public API preserved via `__init__.py` re-exports or updated imports).

---

## Design Decisions

1. **`convert_html_with_annotations` moves to `pandoc.py`** despite calling P4 functions that stay in `latex.py`. Creates temporary cross-module import (`pandoc.py` → `latex.py`) that Phase 4 eliminates.
2. **`_format_annot` stays in `latex.py`** with P4 code (not moved to `preamble.py`). AC4.6 deletes it entirely in Phase 4. Moving to preamble.py would be wasted churn.
3. **`_escape_html_text_content` stays in `latex.py`** — it's P2 legacy code deleted in Phase 4.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Create `preamble.py` with P5 functions

**Verifies:** 134-lua-highlight.AC3.1, 134-lua-highlight.AC3.2

**Files:**
- Create: `src/promptgrimoire/export/preamble.py`
- Modify: `src/promptgrimoire/export/latex.py` (remove P5 functions and `ANNOTATION_PREAMBLE_BASE` constant)

**Implementation:**

Create `src/promptgrimoire/export/preamble.py` containing these symbols extracted from `latex.py`:

- `ANNOTATION_PREAMBLE_BASE` constant (currently lines 812–881)
- `generate_tag_colour_definitions()` (currently lines 885–915)
- `build_annotation_preamble()` (currently lines 918–937)
- `_escape_latex()` (currently lines 940–956)
- `_format_timestamp()` (currently lines 959–965)
- `_strip_test_uuid()` (currently lines 968–974)

The new module needs these imports (check actual usage in each function):
- `from __future__ import annotations`
- `import re` (used by `_strip_test_uuid`)
- `from promptgrimoire.export.unicode_latex import UNICODE_PREAMBLE` (used by `build_annotation_preamble`)

`build_annotation_preamble` defines `speaker_colours` inline — this stays with the function.

Remove all moved symbols from `latex.py`. No cross-import back to `preamble.py` is needed — `_format_annot` (P4, staying in `latex.py`) calls `escape_unicode_latex` (from `unicode_latex.py`, already imported), NOT `_escape_latex`. The `_escape_latex` function has no production callers; it is only tested directly in `test_latex_string_functions.py`.

**Testing:**

Existing tests in `tests/unit/export/test_latex_string_functions.py` import `ANNOTATION_PREAMBLE_BASE`, `_escape_latex`, `_format_annot`, `_format_timestamp`, `generate_tag_colour_definitions` from `latex.py`. Update imports for the moved functions to import from `preamble` instead. `_format_annot` import stays pointing at `latex.py`.

Run: `uv run pytest tests/unit/export/test_latex_string_functions.py -v`
Expected: All tests pass with updated imports.

**Commit:** `refactor: extract P5 preamble functions from latex.py into preamble.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `pandoc.py` with P3 functions

**Verifies:** 134-lua-highlight.AC3.1, 134-lua-highlight.AC3.2

**Files:**
- Create: `src/promptgrimoire/export/pandoc.py`
- Modify: `src/promptgrimoire/export/latex.py` (remove P3 functions)

**Implementation:**

Create `src/promptgrimoire/export/pandoc.py` containing these symbols extracted from `latex.py`:

- `_fix_invalid_newlines()` (currently lines 1476–1515)
- `convert_html_to_latex()` (currently lines 1591–1653) — async function
- `convert_html_with_annotations()` (currently lines 1656–1708) — async function

Check imports needed by these functions. `convert_html_to_latex` uses:
- `asyncio` (for subprocess)
- `subprocess` (for `CalledProcessError`)
- `pathlib.Path`
- `logging` (logger)
- `tempfile`

`convert_html_to_latex` also uses:
- `from promptgrimoire.export.list_normalizer import normalize_list_values`
- `from promptgrimoire.export.html_normaliser import normalise_styled_paragraphs` (can combine with the import below)
- `from promptgrimoire.export.latex import _strip_texorpdfstring` (P4 cross-module import — temporary until Phase 4 removes this call entirely, see issue #136)

`convert_html_with_annotations` uses:
- `from promptgrimoire.export.html_normaliser import strip_scripts_and_styles, fix_midword_font_splits`
- `from promptgrimoire.input_pipeline.html_input import insert_markers_into_dom`
- `from promptgrimoire.export.unicode_latex import _strip_control_chars`
- `from promptgrimoire.export.latex import _replace_markers_with_annots, _move_annots_outside_restricted` (P4 cross-module import — temporary until Phase 4)

Combined `html_normaliser` import: `from promptgrimoire.export.html_normaliser import fix_midword_font_splits, normalise_styled_paragraphs, strip_scripts_and_styles`

Also check `_fix_invalid_newlines` imports (likely just `re`).

The `logger` instance must be created in `pandoc.py`: `logger = logging.getLogger(__name__)`.

Remove all moved symbols from `latex.py`.

**Testing:**

Update imports in these test files:
- `tests/unit/export/test_css_fidelity.py` — imports `convert_html_to_latex` → from `pandoc`
- `tests/unit/export/test_plain_text_conversion.py` — imports `convert_html_to_latex` → from `pandoc` (keep `_escape_html_text_content` import from `latex`)
- `tests/integration/test_highlight_latex_elements.py` — imports `convert_html_with_annotations` → from `pandoc`
- `tests/integration/test_chatbot_fixtures.py` — imports `convert_html_to_latex` → from `pandoc`
- `tests/integration/test_pdf_export.py` — imports `convert_html_to_latex` → from `pandoc`

Run: `uv run test-all`
Expected: All tests pass.

**Commit:** `refactor: extract P3 Pandoc conversion functions from latex.py into pandoc.py`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Update `__init__.py` re-exports and `pdf_export.py` imports

**Verifies:** 134-lua-highlight.AC3.3

**Files:**
- Modify: `src/promptgrimoire/export/__init__.py`
- Modify: `src/promptgrimoire/export/pdf_export.py`

**Implementation:**

Update `src/promptgrimoire/export/__init__.py`:
- Change `from promptgrimoire.export.latex import convert_html_to_latex` to `from promptgrimoire.export.pandoc import convert_html_to_latex`
- Add `from promptgrimoire.export.pandoc import convert_html_with_annotations` to re-exports if not already there
- Add `from promptgrimoire.export.preamble import build_annotation_preamble` to re-exports if not already there
- Update `__all__` to include all three

Update `src/promptgrimoire/export/pdf_export.py`:
- Change `from promptgrimoire.export.latex import build_annotation_preamble, convert_html_with_annotations` to import from their new modules:
  - `from promptgrimoire.export.preamble import build_annotation_preamble`
  - `from promptgrimoire.export.pandoc import convert_html_with_annotations`

**Testing:**

Run: `uv run test-all`
Expected: All tests pass — public API preserved.

Also verify: `uv run python -c "from promptgrimoire.export import convert_html_to_latex, export_annotation_pdf"`
Expected: No import errors.

**Commit:** `refactor: update export re-exports and pdf_export imports for module split`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify module line counts and write AC3 validation test

**Verifies:** 134-lua-highlight.AC3.1, 134-lua-highlight.AC3.2, 134-lua-highlight.AC3.3

**Files:**
- Create: `tests/unit/export/test_module_split.py`

**Implementation:**

Write a test that validates the module split acceptance criteria:

- AC3.1: Assert that `preamble.py` and `pandoc.py` each have fewer than ~400 lines (use a reasonable threshold like 450 to allow some growth). Assert that `latex.py` still exists (P2+P4 code remains until Phase 4) but is smaller than its original 1,708 lines.
- AC3.2: Assert that `preamble.py` contains `build_annotation_preamble` and `generate_tag_colour_definitions`. Assert that `pandoc.py` contains `convert_html_to_latex` and `convert_html_with_annotations`.
- AC3.3: Assert that these imports work without error:
  - `from promptgrimoire.export import convert_html_to_latex`
  - `from promptgrimoire.export import export_annotation_pdf`
  - `from promptgrimoire.export.preamble import build_annotation_preamble`
  - `from promptgrimoire.export.pandoc import convert_html_with_annotations`
  - `from promptgrimoire.export.pdf_export import export_annotation_pdf`

**Testing:**

Run: `uv run pytest tests/unit/export/test_module_split.py -v`
Expected: All assertions pass.

Run: `uv run test-all`
Expected: Full suite passes — no regressions.

**Commit:** `test: add module split validation tests for AC3`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->
