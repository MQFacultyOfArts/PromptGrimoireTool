# Resume Notes: Issue #76 CSS Fidelity

**Date:** 2026-01-30
**Branch:** `css-fidelity-pdf-export`

## Completed Work

### Phase 1: Unit Handling ✅
Updated `src/promptgrimoire/export/filters/libreoffice.lua` to handle additional CSS units:
- `em` units pass through to LaTeX (native support)
- `rem` units convert to `em` (1:1 ratio)
- `px` units convert to `pt` (x0.75 factor)

Tests in `tests/unit/export/test_css_fidelity.py::TestUnitConversion`

### Phase 2: Speaker Pre-processing ✅
New module `src/promptgrimoire/export/speaker_preprocessor.py`:
- Platform detection: Claude, OpenAI, Gemini, ScienceOS
- Speaker label injection: `<strong>User:</strong>` / `<strong>Assistant:</strong>`
- Works with all 11 conversation fixtures

Tests in `tests/unit/export/test_css_fidelity.py::TestSpeakerDetection` and `TestSpeakerDetectionWithFixtures`

### Phase 3: UI Chrome Removal ✅
New module `src/promptgrimoire/export/chrome_remover.py`:
- Avatar/profile-pic image removal
- Icon element removal (tabler-icon-*, icon-*)
- Action button removal (copy, share buttons)
- Small image removal (<32px dimensions)
- Hidden element removal (display:none)

Tests in `tests/unit/export/test_css_fidelity.py::TestUIChromeRemoval`

### Phase 4: Fixture Validation ✅
Integration tests in `tests/integration/test_chatbot_fixtures.py`:
- All 11 fixtures convert to LaTeX without errors
- Speaker labels injected for chatbot fixtures
- Chrome removed from fixtures

**Important:** Pre-processor order matters:
1. `inject_speaker_labels(html)` - FIRST (uses platform markers for detection)
2. `remove_ui_chrome(html)` - SECOND (removes markers after labels injected)

## Next Steps

1. **Manual Visual Review** - Run `pytest tests/integration/test_chatbot_fixtures.py::TestChatbotFixturesToPdf` to generate PDFs to `output/test_output/chatbot_*/`, visually confirm:
   - Speaker distinction visible
   - Content images present
   - No obvious layout breakage
   - Text readable

2. **Integration with Main Pipeline** - The new pre-processors (`speaker_preprocessor.py`, `chrome_remover.py`) are not yet integrated into `pdf_export.py`. They need to be added to the export workflow for production use.

## Key Files

- `src/promptgrimoire/export/filters/libreoffice.lua` - Lua filter (unit handling)
- `src/promptgrimoire/export/speaker_preprocessor.py` - Speaker label injection
- `src/promptgrimoire/export/chrome_remover.py` - UI chrome removal
- `tests/unit/export/test_css_fidelity.py` - Unit tests (32 tests)
- `tests/integration/test_chatbot_fixtures.py` - Integration tests (17 tests)
- `tests/fixtures/conversations/` - 11 test fixtures

## Test Summary

- **Unit tests:** 32 tests in `test_css_fidelity.py`
- **Integration tests:** 17 tests in `test_chatbot_fixtures.py`
- **Total:** 49 new tests, all passing
- **Full suite:** 524 tests pass
