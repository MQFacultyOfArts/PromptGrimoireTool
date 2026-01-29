# WIP: Issue #76 CSS Fidelity Testing

## Done
- Created `tests/unit/export/test_css_fidelity.py` with 9 passing tests
- Fixed Lua filter to handle `cm` units (was only `in`)
- Created `scripts/save_clipboard_fixture.py` for capturing chatbot HTML
- Created `scripts/test_pdf_export.py` for manual PDF verification
- Added conversation fixtures from Claude, Gemini, OpenAI, ScienceOS, AustLII

## TODO
Lua filter needs to handle more CSS units found in chatbot exports:
- `em` → LaTeX `em` (native)
- `rem` → convert to `em`
- `px` → convert to `pt` (1px ≈ 0.75pt)

Also need to audit all semantic CSS properties that should be preserved:
- Code blocks styling
- Font weights/styles
- Background colors for code
- etc.

## Files
- `tests/fixtures/conversations/` - chatbot HTML fixtures (gemini ones lipsum'd)
- `tests/fixtures/183-austlii.html` - native AustLII HTML for comparison

## Not committed (too large, in gitignore or need git-lfs)
- `claude_cooking.html` (1.3MB)
- `claude_maths.html` (2.2MB)
- `gemini_images.html` (6.7MB)
