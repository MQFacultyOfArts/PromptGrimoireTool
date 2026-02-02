# Ralph Loop: Visual QA of PDF Exports

## One-liner invocation

```bash
/ralph-loop --max-iterations 30 --completion-promise 'ALL FIXTURES PASS' Execute visual QA task from docs/wip/ralph-loop-visual-qa.md
```

## Task

Visual QA of PDF exports - page-by-page inspection

## Setup

1. Generate all PDFs: `uv run pytest tests/integration/test_chatbot_fixtures.py::TestChatbotFixturesToPdf -v`
2. PDFs are in `output/test_output/chatbot_*/`

## For Each Fixture

Excluding approved: austlii, claude_cooking, claude_maths

1. Open the PDF with playwright browser
2. Screenshot EVERY page
3. For each page, verify:
   - **LEGIBLE**: Text is readable, no garbled/corrupted characters, CJK renders correctly
   - **SENSIBLE**: Speaker turns are distinct, content flows logically, no jumbled sections
   - **WELL-FORMED**: Margins correct, no text overflow, no orphaned headers, images sized appropriately

4. If issues found:
   - Document: fixture name, page number, issue type, description
   - Identify root cause in preprocessing/filter code
   - Fix
   - Re-generate that fixture's PDF
   - Re-inspect

5. If no issues: mark fixture as PASS and move to next

## Fixture Order

- [ ] openai_biblatex.html
- [ ] openai_dh_dr.html
- [ ] openai_dprk_denmark.html
- [ ] openai_software_long_dr.html
- [ ] google_aistudio_image.html
- [ ] google_aistudio_ux_discussion.html
- [ ] google_gemini_debug.html
- [ ] google_gemini_deep_research.html
- [ ] scienceos_loc.html
- [ ] scienceos_philsci.html
- [ ] chinese_wikipedia.html
- [ ] translation_japanese_sample.html
- [ ] translation_korean_sample.html
- [ ] translation_spanish_sample.html

## Progress Tracking

| Fixture | Status | Issues | Notes |
|---------|--------|--------|-------|
| openai_biblatex | PENDING | | |
| openai_dh_dr | PENDING | | |
| openai_dprk_denmark | PENDING | | |
| openai_software_long_dr | PENDING | | |
| google_aistudio_image | PENDING | | |
| google_aistudio_ux_discussion | PENDING | | |
| google_gemini_debug | PENDING | | |
| google_gemini_deep_research | PENDING | | |
| scienceos_loc | PENDING | | |
| scienceos_philsci | PENDING | | |
| chinese_wikipedia | PENDING | | |
| translation_japanese_sample | PENDING | | |
| translation_korean_sample | PENDING | | |
| translation_spanish_sample | PENDING | | |

## Completion Criteria

All 14 fixtures must PASS visual inspection before outputting `<promise>ALL FIXTURES PASS</promise>`
