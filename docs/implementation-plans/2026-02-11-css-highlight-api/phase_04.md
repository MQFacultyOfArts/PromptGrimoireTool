# CSS Custom Highlight API — Phase 4: Scroll-Sync and Card Interaction

**Goal:** Restore annotation card positioning and card-hover highlighting without char-span DOM queries.

**Architecture:** `charOffsetToRect()` convenience wrapper converts char offsets to viewport-relative rectangles via `Range.getBoundingClientRect()`. Scroll-sync uses this for card positioning. Card hover creates/destroys temporary `CSS.highlights` entries. Go-to-highlight uses `Range.scrollIntoView()` with timed bright-flash via temporary highlight entry.

**Tech Stack:** CSS Custom Highlight API, Range.getBoundingClientRect(), NiceGUI `ui.run_javascript()`.

**Scope:** Phase 4 of 6 from original design.

**Codebase verified:** 2026-02-12

**Note on E2E tests:** Old E2E tests in `test_annotation_highlights.py` are deeply tied to char-span DOM structure. They will be completely rewritten for the new CSS Highlight API, not patched. The existing E2E test audit (currently at `docs/implementation-plans/2026-02-04-html-input-pipeline/e2e-test-audit.md`, moved to `docs/e2e-test-audit.md` in this phase) documents all E2E coverage — update it to reflect the CSS Highlight API migration changes.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### css-highlight-api.AC8: Scroll-sync and card interaction without char-span DOM queries
- **css-highlight-api.AC8.1 Success:** Annotation cards in the sidebar track the vertical position of their corresponding highlight text on scroll
- **css-highlight-api.AC8.2 Success:** Hovering an annotation card paints a temporary highlight on the corresponding text via `CSS.highlights`
- **css-highlight-api.AC8.3 Success:** Clicking an annotation card's target button scrolls the document to the highlight position and pulses/throbs the highlight (visual feedback confirming which text is targeted)
- **css-highlight-api.AC8.4 Success:** No `querySelector('[data-char-index]')` calls exist in the annotation page JS
- **css-highlight-api.AC8.5 Success:** The throb animation uses only CSS properties available in `::highlight()` (background-color opacity transition) or a brief temporary CSS class on the container

---

<!-- START_TASK_1 -->
### Task 1: Add charOffsetToRect() to annotation-highlight.js

**Verifies:** None (infrastructure — provides function used by scroll-sync and go-to)

**Files:**
- Modify: `src/promptgrimoire/static/annotation-highlight.js`

**Implementation:**

Add `charOffsetToRect(textNodes, charIdx)` function that:
1. Calls `charOffsetToRange(textNodes, charIdx, charIdx + 1)` to get a Range covering a single character
2. Note: `charOffsetToRange()` returns a `StaticRange` (required by `CSS.highlights`). Create a temporary live `Range` from the StaticRange's start/end containers and offsets (`document.createRange()` + `setStart/setEnd`), since `StaticRange` does not support `getBoundingClientRect()`
3. Calls `range.getBoundingClientRect()` on the live `Range` to get a DOMRect
4. Returns the DOMRect (has `top`, `left`, `width`, `height`, `bottom`, `right`)

Also add `scrollToCharOffset(textNodes, startChar, endChar)` convenience function that:
1. Creates a live `Range` spanning the char range (same StaticRange → live Range conversion as `charOffsetToRect`: call `charOffsetToRange()` for the StaticRange, then `document.createRange()` + `setStart/setEnd` from its containers/offsets)
2. Calls `range.getBoundingClientRect()` on the live Range to check if visible
3. Creates a temporary element at the range position and scrolls to it, or uses `element.scrollIntoView()` on the range's start node

Also add hover/throb highlight functions:
- `showHoverHighlight(textNodes, startChar, endChar)` — creates `CSS.highlights.set('hl-hover', new Highlight(range))`
- `clearHoverHighlight()` — `CSS.highlights.delete('hl-hover')`
- `throbHighlight(textNodes, startChar, endChar, durationMs)` — creates `CSS.highlights.set('hl-throb', new Highlight(range))`, removes after `durationMs` via `setTimeout()`

**Verification:**
Run: `uv run pytest tests/integration/test_text_walker_parity.py -v` (no regressions)

**Commit:** `feat: add charOffsetToRect, hover, and throb highlight functions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add ::highlight(hl-hover) and ::highlight(hl-throb) CSS

**Verifies:** None (infrastructure — CSS for hover and throb effects)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` — add `::highlight(hl-hover)` and `::highlight(hl-throb)` rules to CSS

**Implementation:**

Add to the annotation page CSS (in `_PAGE_CSS` or in the dynamic `::highlight()` CSS generation):

```css
::highlight(hl-hover) {
    background-color: rgba(255, 215, 0, 0.3);
}
::highlight(hl-throb) {
    background-color: rgba(255, 215, 0, 0.6);
}
```

The `hl-hover` provides a subtle golden highlight when hovering a card. The `hl-throb` provides a brighter flash for the go-to action. Both use `background-color` only (the one reliable property in `::highlight()`).

Also remove the `.char.card-hover-highlight` CSS rule from `_PAGE_CSS` (L313-314) — this class is no longer used.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`

**Commit:** `feat: add ::highlight() CSS rules for hover and throb effects`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Rewrite scroll-sync JS to use charOffsetToRect()

**Verifies:** css-highlight-api.AC8.1, css-highlight-api.AC8.4 (partial — eliminates scroll-sync data-char-index queries)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:1412-1499` (the `scroll_sync_js` variable)

**Implementation:**

Rewrite `scroll_sync_js` to replace `querySelector('[data-char-index="'+sc+'"]').getBoundingClientRect()` with `charOffsetToRect(textNodes, sc)`. The algorithm stays the same — same debouncing, same viewport culling, same collision avoidance.

The JS now assumes `textNodes` is available in scope (set up during Phase 3's initialisation in `_render_document_with_highlights()`). The scroll-sync JS should reference this shared state.

Key changes:
- Line ~1426: `const cs = docC.querySelector('[data-char-index="'+sc+'"]');` → `const cr = charOffsetToRect(window._textNodes, sc);`
- Remove the null check (`if (!cs) continue;`) — `charOffsetToRect` always returns a rect (may be zero-size for invalid offsets)
- The `cr.top` / `cr.bottom` calculations remain the same

**Testing:**

- css-highlight-api.AC8.1: E2E test — create a long document with multiple highlights, scroll through, verify cards track their highlights' vertical positions
- css-highlight-api.AC8.4 (partial): Grep the JS output for `data-char-index` — should find no occurrences in scroll-sync code

Test file: `tests/e2e/test_scroll_sync.py`

**Verification:**
Run: `uv run pytest tests/e2e/test_scroll_sync.py -v`

**Commit:** `feat: rewrite scroll-sync to use charOffsetToRect instead of char-span queries`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Rewrite card hover and go-to-highlight

**Verifies:** css-highlight-api.AC8.2, css-highlight-api.AC8.3, css-highlight-api.AC8.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:1468-1495` (hover JS in scroll_sync_js)
- Modify: `src/promptgrimoire/pages/annotation.py:900-928` (go-to-highlight handler)

**Implementation:**

**Hover rewrite** (replaces L1468-1495):
- `mouseover` handler: extract `startChar`, `endChar` from `card.dataset`, call `showHoverHighlight(window._textNodes, startChar, endChar)`
- `mouseleave` handler: call `clearHoverHighlight()`
- Removes all `querySelector('[data-char-index]')` loops — O(1) instead of O(n)

**Go-to-highlight rewrite** (replaces L900-928):
- Call `scrollToCharOffset(window._textNodes, startChar, endChar)` to scroll the document to the highlight (handles StaticRange → live Range conversion and scrolling internally)
- Call `throbHighlight(window._textNodes, startChar, endChar, 800)` for the flash effect
- Remove char-span-based scroll and individual char background manipulation

**Testing:**

- css-highlight-api.AC8.2: E2E test — hover annotation card, verify text highlight appears (check `CSS.highlights.has('hl-hover')` or visual verification)
- css-highlight-api.AC8.3: E2E test — click go-to button, verify scroll to highlight and throb effect
- css-highlight-api.AC8.5: Code review — verify hover/throb only use `background-color` in `::highlight()` rules

Test file: `tests/e2e/test_card_interaction.py`

**Verification:**
Run: `uv run pytest tests/e2e/test_card_interaction.py -v`

**Commit:** `feat: rewrite card hover and go-to-highlight to use CSS.highlights`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Delete old E2E tests and document coverage

**Verifies:** css-highlight-api.AC8.4 (no data-char-index queries remain)

**Files:**
- Delete: char-span-dependent test classes from `tests/e2e/test_annotation_highlights.py` (specifically `TestHighlightInteractionsConsolidated` with `goto_scrolls_to_highlight` and `hover_highlights_words` subtests, L269-338)
- Modify: `tests/e2e/annotation_helpers.py` — update `select_chars()` to use new text-walker-based selection (no `[data-char-index]` locators); update `setup_workspace_with_content()` to remove the "wait for char spans" step
- Move: `docs/implementation-plans/2026-02-04-html-input-pipeline/e2e-test-audit.md` → `docs/e2e-test-audit.md` (more accessible location) and update with CSS Highlight API migration changes

**Implementation:**

1. Remove `TestHighlightInteractionsConsolidated` from `test_annotation_highlights.py` — replaced by new tests in `test_scroll_sync.py` and `test_card_interaction.py` (Tasks 3-4)

2. Update `annotation_helpers.py`:
   - `select_chars()` currently finds char spans by `[data-char-index]` to get bounding boxes for mouse simulation. **Defer the full rewrite to Phase 6 Task 5** (which provides the concrete `charOffsetToRect()`-based implementation). For now, mark `select_chars()` with a `# TODO: Phase 6 Task 5 rewrites this to use charOffsetToRect()` comment and leave the existing implementation (the old E2E tests that call it are being deleted in step 1 of this task, so it won't be exercised).
   - `setup_workspace_with_content()` currently waits for `[data-char-index]` elements to appear. Replace with waiting for `annotation-highlight.js` to initialise (e.g. wait for `window._textNodes` to be defined, or wait for the document container to have content).

3. Move `docs/implementation-plans/2026-02-04-html-input-pipeline/e2e-test-audit.md` to `docs/e2e-test-audit.md` and update:
   - Add a "CSS Highlight API Migration" section documenting what changed
   - List tests deleted and their replacement tests
   - Update any char-span-specific user action descriptions
   - Flag coverage gaps (if any) for future work

4. Verify no `querySelector('[data-char-index]')` remains in the annotation page JS — search all JS strings in annotation.py.

**Testing:**

- css-highlight-api.AC8.4: Automated grep test — `tests/unit/test_no_char_span_queries.py` that reads `annotation.py` source and asserts no `data-char-index` string appears in any JS code blocks

**Verification:**
Run: `uv run test-all` (full suite, ensure no broken tests)
Run: `uv run pytest tests/e2e/ -v` (all E2E tests pass)

**Commit:** `refactor: remove char-span E2E tests, update helpers, document coverage`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_A -->
