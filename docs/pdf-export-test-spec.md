# PDF Export E2E Test Specification

## Source
From conversation on 2026-01-26 (session d12a5cb0-6c3f-41e5-88a9-84cda7c41bce)

## Requirements

The E2E test must demonstrate all 10 tags with specific annotations at designated locations.

## Tag Specifications

| # | Tag | Location | User | Notes |
|---|-----|----------|------|-------|
| 1 | `jurisdiction` | (existing) | Alice | Para number was off, word boundaries wrong at "(S" |
| 2 | `procedural_history` | Case name | Bob | Bob comments on case name |
| 3 | `legally_relevant_facts` | Grounds section | Alice | Highlight from header to "." |
| 4 | `legal_issues` | (not specified) | - | Need to find appropriate location |
| 5 | `reasons` | Paragraphs 7 and 15 | - | Two separate highlights |
| 6 | `courts_reasoning` | Paragraph 16 | - | With lipsum multi-paragraph comments |
| 7 | `decision` | Paragraph 48 | - | Highlight all of 48 and its subsequent lists |
| 8 | `order` | Paragraphs 5-7 | - | Multi-paragraph span |
| 9 | `domestic_sources` | Paragraph 23 | - | - |
| 10 | `reflection` | Paragraph 23 | - | Same passage as domestic sources |

## Fixes Needed

1. **Paragraph number display** - jurisdiction was showing [48] instead of correct number
2. **Newline after date** - margin note needs newline after date line
3. **Word boundaries** - highlight was ending after "(S" due to mid-word font splits in RTF

## Technical Fixes Applied (in crashed session)

- `fix_midword_font_splits()` in `html_normaliser.py` - merges "(S</font><font><i>entencing"
- Moved ANNMARKER outside HLEND so `\annot{}` is outside `\highLight{}`
- Split multi-paragraph highlights: `\highLight{para1}\par\highLight{para2}`
- Switched to LuaLaTeX with fontspec, lua-ul, luacolor

## Test Structure

Two users with rotating UUIDs per test run:
- Alice Jones (`alice.jones.{uuid}@test.example.edu.au`)
- Bob Smith (`bob.smith.{uuid}@test.example.edu.au`)

Shared document via `?doc={shared_doc_id}` query parameter.
