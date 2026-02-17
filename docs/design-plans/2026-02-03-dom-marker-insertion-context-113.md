# DOM-Based Marker Insertion - Design Context

**Date:** 2026-02-03
**Status:** Phase 1 Context Gathering Complete
**Related Issues:** #113, #111, #101

## Problem Statement

PDF export fails on BLNS content because marker insertion operates on `raw_content` (plain text) but treats it as HTML. When text contains literal `<script>` or `&#x0A;` strings, the marker insertion:

1. Misinterprets `<script>` as an HTML tag and skips it
2. Breaks HTML entity-like strings when inserting markers mid-string
3. Results in malformed LaTeX that fails to compile

**Example failure:**
```
Original: jav&#x0A;ascript
After marker: jav&#x0HLSTART{0}ENDHL;A;ascript
LaTeX error: "File ended while scanning use of \highLight"
```

## Current Architecture (Broken)

```
raw_content (plain text with literal <, &, etc.)
    ↓
_insert_markers_into_html() tries to "skip HTML tags"
    ↓
Treats <script> in text as actual tag → index mismatch
    ↓
Pandoc converts to LaTeX
    ↓
Broken markers cause compilation failure
```

**Key code:** `src/promptgrimoire/export/latex.py:789-796`
```python
if html[i] == "<":
    # Skip HTML tags - BUT raw_content isn't HTML!
    tag_end = html.find(">", i)
```

## Proposed Architecture (DOM-Based)

```
doc.content (pre-escaped HTML with <span data-char-index="N">)
    ↓
DOM parse with BeautifulSoup/lxml
    ↓
Find spans by data-char-index attribute
    ↓
Insert markers at span boundaries (not mid-string)
    ↓
Serialize back to HTML
    ↓
Pandoc converts to LaTeX (markers survive as text)
```

**Why this works:**
- `doc.content` has `<script>` → `&lt;script&gt;` (pre-escaped)
- DOM parsing handles actual HTML structure correctly
- `data-char-index` attributes match UI indices exactly
- Markers inserted at element boundaries, never mid-entity

## Prerequisites (Already Complete)

The character-based tokenization design (2026-02-02) is fully implemented:

| Phase | Status | Evidence |
|-------|--------|----------|
| Phase 1: Core tokenization | ✅ Done | `_process_text_to_char_spans()` exists |
| Phase 2: CSS generators | ✅ Done | commit `a3e2353` |
| Phase 3: JS selection | ✅ Done | commit `5f54bd8` |
| Phase 4: Export markers | ✅ Done | commit `52ed59f` |
| Phase 5: Test suite | ✅ Done | commit `1897eaf` |

**Key artifacts available:**
- `doc.content` = HTML with `<span class="char" data-char-index="N">char</span>` per character
- `doc.raw_content` = plain text (for text extraction, not for export)
- UI highlights use `start_char`/`end_char` indices matching `data-char-index`

## Issues This Would Fix

| Issue | Title | Root Cause | Fixed |
|-------|-------|-----------|-------|
| #113 | LaTeX fails on HTML entities | Markers break `&#x0A;` strings | ✅ |
| #111 | Character index mismatch | raw_content counting differs from UI | ✅ |
| #101 | CJK/BLNS support | Export fragility with special chars | ✅ |

## Dependencies

**None.** All prerequisites from character-tokenization are merged.

## Test Workspace

- Workspace: `f4270318-ca98-47fc-8527-9b772699a755`
- Document: `afd9a0c7-d307-4a1a-8016-e666c23ca4a3`
- Content: 183.rtf pasted 3x via LibreOffice, then BLNS

## Files to Modify

| File | Change |
|------|--------|
| `src/promptgrimoire/pages/annotation.py:1367` | `html_content=raw_content` → `html_content=doc.content` |
| `src/promptgrimoire/export/latex.py` | Rewrite `_insert_markers_into_html()` to use DOM parsing |

## Open Questions for Clarification

1. **DOM parser choice:** BeautifulSoup (already a dependency?) vs lxml vs html.parser?
2. **Marker format:** Keep current `HLSTART{n}ENDHL` or simplify?
3. **Edge case:** What if `doc.content` is None/empty but `raw_content` exists?
4. **Performance:** DOM parsing overhead acceptable for large documents?

## Next Steps

- [ ] Phase 2: Clarify requirements (answer open questions)
- [ ] Phase 3: Confirm Definition of Done
- [ ] Phase 4: Brainstorm implementation approach
- [ ] Phase 5: Write full design document
- [ ] Phase 6: Hand off to implementation planning
