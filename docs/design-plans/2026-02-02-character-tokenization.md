# Character-Based Tokenization Design

## Summary

This design replaces the current word-based tokenization in the annotation system with character-based tokenization. The existing implementation splits text on whitespace boundaries (`str.split()`), which fails for CJK languages (Chinese, Japanese, Korean) that don't use spaces between words and creates problems for selecting individual whitespace characters. The new approach iterates through every character in the text (including spaces, tabs, and non-breaking spaces), assigns each a sequential index, and wraps each in its own `<span>` element. This enables character-level selection for CJK text, preserves hard whitespace from legal documents, and properly handles RTL (right-to-left) text from the Big List of Naughty Strings test suite.

The implementation maintains consistency between UI rendering and PDF export by using identical character iteration logic in both paths. The change propagates through five core components: UI tokenization, CSS selectors, JavaScript event handlers, PDF export marker insertion, and the test suite. Existing CRDT highlight data will need re-indexing or be treated as a breaking change, which is acceptable for the pre-release codebase.

## Definition of Done

1. All text in annotation UI is tokenized by character, not word
2. Each character (including whitespace) gets its own index and selectable span
3. CJK text (Chinese, Japanese, Korean) can be selected character-by-character
4. RTL text (Arabic, Hebrew from BLNS) can be selected and rendered
5. Hard whitespace (non-breaking spaces) preserved and individually selectable
6. PDF export marker insertion uses same character-based indexing
7. All existing annotation tests pass (updated for new indexing)
8. UAT: CJK fixtures and BLNS paste-in work with character selection

## Glossary

- **CJK**: Chinese, Japanese, and Korean languages that use logographic or syllabic writing systems without word-separating spaces
- **RTL (Right-to-Left)**: Text direction for languages like Arabic and Hebrew where characters flow from right to left
- **BLNS (Big List of Naughty Strings)**: A test suite containing edge-case Unicode strings (emoji, RTL text, control characters, etc.) used to verify robust text handling
- **Code point**: A single unit in the Unicode standard; Python's string iteration handles these correctly for multi-byte characters
- **Grapheme cluster**: A user-perceived character that may consist of multiple code points (e.g., emoji with skin tone modifiers)
- **Non-breaking space (nbsp)**: A whitespace character (`\u00A0`) that prevents line breaks, used in legal citations
- **CRDT (Conflict-free Replicated Data Type)**: The data structure used for collaborative editing; stores highlight positions as numerical indices
- **UAT (User Acceptance Testing)**: Manual verification by the user that the feature works in real-world scenarios
- **AustLII**: Australian Legal Information Institute, a legal database whose citations use non-breaking spaces between case components
- **Tokenization**: The process of breaking text into discrete units (words or characters) that can be individually indexed and selected

## Architecture

Replace word-based tokenization with character-based tokenization for all text in the annotation system.

**Current flow (broken for CJK):**
```
text → str.split() → words[] → <span data-word-index="N">word</span>
```

**New flow:**
```
text → iterate chars → chars[] → <span data-char-index="N">char</span>
```

**Key changes:**
- Every character (including spaces, tabs, nbsp) gets its own index
- Newlines create paragraph breaks but don't get indices
- Multi-byte Unicode characters handled correctly (Python iterates by code point)
- Data attribute renamed: `data-word-index` → `data-char-index`
- CSS class renamed: `.word` → `.char`

**Components affected:**

| Component | File | Change |
|-----------|------|--------|
| UI tokenization | `src/promptgrimoire/pages/annotation.py` | `_process_text_to_word_spans()` → `_process_text_to_char_spans()` |
| Document state | `src/promptgrimoire/pages/annotation.py` | `state.document_words` → `state.document_chars` |
| CSS generators | `src/promptgrimoire/pages/annotation.py` | All `data-word-index` selectors |
| Export tokenization | `src/promptgrimoire/export/latex.py` | `_WORD_PATTERN` and `_insert_markers_into_html()` |
| JS selection | `src/promptgrimoire/assets/js/live-annotation.js` | `data-w` and `data-word-index` selectors |

**CRDT highlight schema:** Indices now mean characters, not words. Field names (`start_word`/`end_word`) can remain for backwards compatibility or be renamed to `start_char`/`end_char`.

## Existing Patterns

Investigation found consistent tokenization pattern across UI and export:
- UI uses `line.split()` in `_process_text_to_word_spans()`
- Export uses `\S+` regex in `latex.py` to match UI behavior
- Both maintain sequential 0-based indices

This design maintains the same consistency principle: UI and export MUST use identical tokenization logic.

**Unicode handling already exists:**
- `unicode_latex.py` handles CJK font selection and escaping
- Control character stripping happens after marker insertion
- Font fallback chain includes all CJK fonts

No new patterns introduced. The character iteration approach is simpler than the current word splitting.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Core Tokenization Function + Benchmarking

**Goal:** Replace word-based tokenization with character-based tokenization in the UI, verify performance acceptable

**Components:**
- `_process_text_to_char_spans()` in `src/promptgrimoire/pages/annotation.py` — iterate characters, wrap each in span with `data-char-index`
- `state.document_chars` — list of characters for index-based extraction
- Update call site at line ~1458 where documents are processed
- Performance benchmark script — measure memory, Lighthouse score, CPU for typical document sizes

**Dependencies:** None (first phase)

**Done when:**
- Function returns HTML with character-level spans
- Unit tests verify ASCII, CJK, mixed text, whitespace handling
- `state.document_chars` populated correctly
- Benchmark results documented (memory, Lighthouse, CPU)
- Performance deemed acceptable (or design revisited before Phase 2)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CSS Generator Updates

**Goal:** Update all CSS generation to use `data-char-index`

**Components:**
- `_build_highlight_css()` in `annotation.py` — change `data-word-index` to `data-char-index`
- `_build_cursor_css()` in `annotation.py` — same change
- `_build_selection_css()` in `annotation.py` — same change
- CSS class `.word` → `.char` in inline styles

**Dependencies:** Phase 1

**Done when:**
- All CSS rules use `data-char-index` selectors
- Highlights render correctly on character spans
- Cursor and selection CSS work with new attributes
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: JavaScript Selection Handling

**Goal:** Update JS to work with character-based spans

**Components:**
- `live-annotation.js` — update all `data-w` and `data-word-index` selectors to `data-char-index`
- Inline JS in `annotation.py` (~line 893, 1077) — update selectors

**Dependencies:** Phase 2

**Done when:**
- Character selection works in browser
- Selection events emit correct character indices
- Card positioning uses character spans
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Export Marker Insertion

**Goal:** Update PDF export to use character-based indexing

**Components:**
- `_insert_markers_into_html()` in `src/promptgrimoire/export/latex.py` — iterate by character instead of `\S+` regex
- Remove or update `_WORD_PATTERN` constant
- Ensure marker insertion aligns with UI character indices

**Dependencies:** Phase 1 (must match UI tokenization)

**Done when:**
- Markers inserted at correct character positions
- Existing latex marker tests updated and passing
- PDF export produces correct highlights for character-based indices
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Test Suite Updates

**Goal:** Update all tests to work with character-based indexing

**Components:**
- `tests/e2e/annotation_helpers.py` — `select_words()` → `select_chars()` or update to work with character indices
- `tests/unit/test_latex_markers.py` — update word-based marker tests
- `tests/e2e/test_annotation_*.py` — update index assertions
- Add CJK-specific test cases using existing fixtures

**Dependencies:** Phases 1-4

**Done when:**
- All existing tests pass with updated indices
- New tests cover CJK character selection
- New tests cover BLNS edge cases (RTL, hard whitespace)
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: UAT Verification

**Goal:** Manual verification with real CJK and BLNS content

**Components:**
- Load CJK fixtures into workspace document
- Paste BLNS content
- Verify character-level selection
- Verify PDF export of CJK highlights
- Verify RTL text handling

**Dependencies:** Phase 5

**Done when:**
- User confirms CJK selection works
- User confirms BLNS paste-in works
- User confirms hard whitespace selectable (AustLII case)
<!-- END_PHASE_6 -->

## Additional Considerations

**Edge cases handled:**
- Empty strings → empty output
- Only whitespace → each space indexed
- Only newlines → empty paragraphs (current behavior preserved)
- Combining characters (e.g., `e` + combining acute) → each code point separate
- Zero-width characters (joiners, bidi marks) → get indices like any character, render as zero-width
- Non-Latin whitespace (ideographic space U+3000) → indexed as character

**Not handled (future work):**
- Grapheme cluster segmentation (proper emoji sequences)
- This means some emoji may be split into multiple spans (acceptable for MVP)

**Backwards compatibility:**
- No migration needed - not in production
- Breaking change for any existing dev workspaces is acceptable

**Why span-per-character (vs on-demand insertion):**
- Selection must work across DOM tree (paragraph boundaries, potential nested markup)
- Pre-wrapped spans provide stable `data-char-index` for mapping mouse position → index
- Highlights target span ranges via CSS selectors
- On-demand insertion would require complex offset calculation and cause reflow during selection
- Matches export pipeline which needs the same stable indices

**Performance considerations:**
- Character-based creates 5-10x more DOM elements than word-based
- Phase 1 includes benchmarking: memory, Lighthouse, CPU profiling
- If performance unacceptable, reconsider approach before proceeding to Phase 2
- Modern browsers handle 10k+ elements; monitor during UAT for edge cases
