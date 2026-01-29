# Resume Notes: Issue #76 CSS Fidelity

**Date:** 2026-01-29
**Branch:** `nested-highlight-marker-parser`

## Where We Left Off

Completed brainstorming and design for Issue #76 (CSS fidelity for PDF export). Design document is at `docs/design-plans/2026-01-29-css-fidelity-pdf-export.md`.

## Next Steps (in order)

### Phase 1: Unit handling
Update `src/promptgrimoire/export/filters/libreoffice.lua` to handle `em`, `rem`, `px` units. The `parse_margin_left()` function currently only handles `in` and `cm`.

### Phase 2: Speaker pre-processing
New Python code in `latex.py` (or new module) to:
- Detect platform from HTML (Claude/Gemini/OpenAI/ScienceOS/AustLII)
- Inject "User:"/"Assistant:" labels
- Preserve visual styling (background color)

### Phase 3: UI chrome removal
BeautifulSoup pre-processor to strip avatars, icons, buttons before Pandoc.

### Phase 4: Fixture validation
Run all 11 fixtures through pipeline, manual visual review.

## Key Files

- `src/promptgrimoire/export/filters/libreoffice.lua` - Lua filter (unit handling)
- `src/promptgrimoire/export/latex.py` - Python pipeline (speaker/chrome pre-processing)
- `tests/unit/export/test_css_fidelity.py` - Add tests for new functionality
- `tests/fixtures/conversations/` - The 11 test fixtures

## Issues Updated

- #76 - Has acceptance criteria and design doc link
- #100 (Seam H) - Has dependency note on #76
- #93 (Seam A) - Has note about conversation turn segmentation consideration

## Waiting On

Vanessa's translation work fixtures (instructions provided for her Claude to help capture them on Windows via manual copy-paste).
