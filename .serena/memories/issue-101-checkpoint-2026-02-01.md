# Issue #101 Unicode Robustness - Checkpoint 2026-02-01

## Current State

**Branch:** `101-cjk-blns`
**Last commit:** `61ed61b` - fix(latex): remove non-existent notocjksc package, add tofu detection test

## Completed Phases

### Phase 3: escape_unicode_latex + UNICODE_PREAMBLE ✅
- Commits: 4b560ab, c46023f
- `escape_unicode_latex()` wraps CJK in `\cjktext{}`, emoji in `\emoji{}`
- `UNICODE_PREAMBLE` defines luatexja-fontspec and emoji package setup
- 198 tests passing

### Phase 4: TinyTeX packages ✅
- Commits: 684ce1c, 745b9d1
- Added emoji, luatexja packages to setup_latex.py
- Removed notocjksc (doesn't exist - system fonts used instead)
- Added preamble compilation test with tofu detection

### Phase 5: latex.py integration ✅
- Commits: d4eb6c0, fa77866, 91d10bf, 6049820
- Replaced 8 `_escape_latex()` calls with `escape_unicode_latex()`
- Added `UNICODE_PREAMBLE` to `build_annotation_preamble()`
- Added _format_annot integration tests

## Current Problem

**RESOLVED** - PDF export integration tests now passing.

**Fix:** Added `haranoaji` package to `scripts/setup_latex.py`. This provides the default Japanese fonts required by `luatexja-fontspec`.

**Cleanup:**
- Deleted deprecated `tests/e2e/test_pdf_export.py` (used removed fixture) → Issue #107 for replacement
- Skipped `tests/unit/test_rtf_parser.py` (LibreOffice dependency) → Issue #108

## Remaining Phases

- Phase 6: DB/CRDT/PDF roundtrip tests (pending)
- Phase 7: Demo validation page (pending)

## User's UAT

Paste BLNS content → add annotations → export to PDF → see unicode rendered correctly

## Key Files

- `src/promptgrimoire/export/unicode_latex.py` - escape functions and UNICODE_PREAMBLE
- `src/promptgrimoire/export/latex.py` - integration point (line 41 import, line 572 preamble, lines 646-667 escape calls)
- `tests/unit/test_latex_packages.py` - preamble compilation + tofu detection test
- `tests/integration/test_pdf_export.py` - failing tests

## Commands to Resume

```bash
# Check test failure
uv run pytest tests/integration/test_pdf_export.py::TestMarginnoteExportPipeline::test_export_annotation_pdf_basic -v --tb=short

# View generated LaTeX
cat /tmp/pytest-of-brian/pytest-*/test_export_annotation_pdf_basic*/annotated_document.tex

# View compilation log
cat /tmp/pytest-of-brian/pytest-*/test_export_annotation_pdf_basic*/annotated_document.log
```
