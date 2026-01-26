# PDF Export E2E Test - Implementation Notes

## Session: 2026-01-26

### Objective
Implement E2E test that exercises all 10 annotation tags at specific document locations, demonstrating multi-user collaboration and PDF export.

---

## Work Completed

### 1. Test Structure Created (`tests/e2e/test_pdf_export.py`)

**Functions created:**
- `_select_words(page, start_word, end_word)` - Drag selection for word ranges
- `_scroll_to_word_and_find_card(page, word_idx, card_text)` - Find annotation card by content
- `_add_comment_to_visible_card(page, card, text)` - Add comment with force clicks for overlapping cards
- `_alice_creates_annotations(page)` - Creates 10 annotations (all tags)
- `_bob_creates_annotation_and_replies(page, expected_count)` - Bob adds procedural_history
- `_alice_replies_back(page)` - Alice's reply in comment thread
- `_alice_adds_lipsum_comments(page)` - Multi-paragraph comments on courts_reasoning
- `_alice_writes_general_notes(page)` - General notes section
- `_alice_exports_pdf(page)` - Trigger export and verify success

**Test scenario:**
1. Alice creates 10 annotations covering all BriefTag types
2. Bob joins, adds procedural_history on case name, replies to Alice's jurisdiction comment
3. Alice replies back, adds lipsum comments to courts_reasoning, writes general notes
4. Alice exports PDF

### 2. LaTeX Export Bug Fixed (`src/promptgrimoire/export/latex.py`)

**Problem:** `\highLight{}` commands were crossing table cell boundaries, causing LaTeX errors:
```
! Extra }, or forgotten \endgroup.
```

**Root cause:** The `highlight_wrapper()` function only split on `\par` to handle multi-paragraph highlights, but didn't handle table structure delimiters.

**Fix:** Added split on table delimiters in addition to `\par`:
```python
split_pattern = r"(\\par\b|\\\\|\\tabularnewline\b|(?<!\\)&)"
```

This ensures highlights don't span across:
- `\\` (table row end)
- `&` (table column separator)
- `\tabularnewline` (explicit row end)

---

## Issues Discovered

### Issue 1: Overlapping Highlight Selection (UNRESOLVED)

**Symptoms:**
- When annotation 5 ends at word 1640, creating annotation 6 starting at word 1640 fails
- Card count stays at 5 instead of increasing to 6
- Same pattern with adjacent annotations at words 2480

**What we know:**
1. The CRDT supports overlapping highlights - no deduplication or rejection
2. `end_word` in CRDT is EXCLUSIVE (stores end+1 from selection)
3. Selection bounds in test are INCLUSIVE (what you click on)
4. The `_select_words` function successfully finds and scrolls to both words
5. Both words pass visibility assertions
6. Drag selection appears to execute without error
7. But the highlight is not created

**Investigation performed:**
- Tried shift-click selection → same failure
- Tried drag selection → same failure
- Added assertions for both start and end word visibility → both pass
- Added debugging to check background color and selection text

**Hypotheses to test:**
1. The JavaScript `getWordRangeFromSelection()` might not detect selection starting on highlighted text
2. CSS styling might interfere with browser text selection behavior
3. The selection event might fire but with incorrect word indices
4. There might be timing/race condition in event handling

**User clarification:** User confirmed overlapping highlights SHOULD work via UI - this is a bug to fix, not a limitation to work around.

### Issue 2: Card Overlap Z-Index

**Symptoms:**
- Multiple cards at similar document positions overlap visually
- jurisdiction card (4346-4360) and decision card (4335-4400) both show "[48]"
- Clicking on overlapped card fails due to pointer interception

**Workaround applied:**
- Use `card.click(force=True)` to bypass interception check
- Find cards by tag name ("Jurisdiction") or comment text ("it's excessive") instead of just paragraph number

---

## Key Learnings

### Selection Semantics

The UI selection → CRDT storage flow:
1. User selects words 1575-1640 (inclusive both ends)
2. JavaScript emits `{start: 1575, end: 1640}`
3. Python handler calls `add_highlight(..., end_word=end+1)` → stores 1641
4. CSS uses `range(start, end)` → styles words 1575-1640

This means if you want words 1575-1639 highlighted, you select 1575-1639 (not 1575-1640).

### Word Index Sources

The word indices in the plan came from HTML rendering of the RTF document. The raw RTF has different word counts due to RTF control sequences. Always verify indices against the actual rendered page.

### Test Data Overlap Intent

Per the spec:
- `reasons` and `order` intentionally overlap at words 893-905 (testing overlapping highlights)
- `domestic_sources` and `reflection` are on "same passage" in para 23 (testing adjacent/overlapping)
- `reasons para 15` and `courts_reasoning para 16` are adjacent at word boundary

These are deliberate edge cases, not mistakes.

---

## Next Steps

1. **Debug selection issue:**
   - Add console logging in JavaScript `getWordRangeFromSelection()`
   - Check if selection event fires with correct data
   - Verify selection works manually in headed browser mode

2. **If selection on highlighted word is broken:**
   - Check if CSS `user-select` or `pointer-events` affects text selection
   - Check if JavaScript selection API behaves differently for styled text
   - Consider alternative selection approaches

3. **Once all annotations create successfully:**
   - Verify PDF export completes
   - Check PDF contains all 10 tags with correct colors
   - Verify margin notes have correct content (comments, usernames, timestamps)

---

## Files Modified This Session

- `tests/e2e/test_pdf_export.py` - New comprehensive E2E test
- `src/promptgrimoire/export/latex.py` - Table boundary fix in highlight_wrapper()
- `docs/pdf-export-test-spec.md` - Test specification from user

## Files NOT Committed (existing modifications)

- `src/promptgrimoire/crdt/annotation_doc.py` - Unrelated changes
- `src/promptgrimoire/db/annotation_state.py` - Unrelated changes
- `src/promptgrimoire/pages/live_annotation_demo.py` - Unrelated changes
