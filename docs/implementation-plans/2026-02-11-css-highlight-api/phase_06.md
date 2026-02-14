# CSS Custom Highlight API — Phase 6: Cleanup and Verification

**Goal:** Remove ALL remaining char-span references from the codebase. Verify PDF export still works. Update documentation. Rewrite E2E test helpers.

**Architecture:** Systematic deletion of dead code (functions, CSS selectors, JS constants, tests) with verification that nothing breaks. E2E test helpers switch from `[data-char-index]` locators to mouse-event-based selection with JS coordinate lookup via the text walker.

**Tech Stack:** Python, Playwright (for E2E helper rewrite)

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-02-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### css-highlight-api.AC6: PDF export unchanged
- **css-highlight-api.AC6.1 Success:** Highlights created via CSS Custom Highlight API with char offsets produce identical PDF output when fed to `export_annotation_pdf()` as highlights created via the old char-span system
- **css-highlight-api.AC6.2 Success:** Existing PDF export tests pass without modification (char offset data shape is unchanged)

### css-highlight-api.AC8: Scroll-sync and card interaction without char-span DOM queries
- **css-highlight-api.AC8.4 Success:** No `querySelector('[data-char-index]')` calls exist in the annotation page JS

---

<!-- START_SUBCOMPONENT_A (task 1) -->
## Subcomponent A: Delete Remaining Char-Span Dead Code

<!-- START_TASK_1 -->
### Task 1: Delete remaining char-span dead code from annotation.py

**Verifies:** None (cleanup — AC5 is fully handled by Phase 3 Task 5)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Implementation:**

Phase 3 Task 5 deletes the char-span functions from `html_input.py` and `__init__.py`. This task catches the one remaining piece of dead code in `annotation.py`:

1. Delete `_process_text_to_char_spans(text: str)` (L459-501) — comment says "Remains for backward compatibility but will be removed". After Phase 3, nothing calls this function.

2. Clean up any unused imports that result from the deletion.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Expected: Passes.

**Commit:** `refactor: delete _process_text_to_char_spans dead code`
<!-- END_TASK_1 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 2-3) -->
## Subcomponent B: Remove Char-Span CSS and JS from annotation.py

<!-- START_TASK_2 -->
### Task 2: Delete char-span CSS selectors from _PAGE_CSS

**Verifies:** css-highlight-api.AC8.4 (partial)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Implementation:**

Remove these CSS rules from the `_PAGE_CSS` string constant:

1. `.doc-container .char { display: inline; ... }` block (L254-262) — styling for char span elements
2. `.char { cursor: text; }` rule (L307) — cursor style for char spans
3. `.char.card-hover-highlight { ... }` rule (L308-310) — hover effect when annotation card is hovered

These selectors target elements that no longer exist in the DOM after Phase 3.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Expected: Passes.

**Commit:** `refactor: remove char-span CSS selectors from annotation page`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify and remove any remaining char-span JS references

**Verifies:** css-highlight-api.AC8.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Implementation:**

**Note:** This task is primarily a verification sweep. Phases 3 and 4 perform the main deletions; this task catches anything those phases missed and ensures zero char-span references remain.

Phase 3 deletes the main JS constants (`_CHAR_SPANS_JS`, `_HIGHLIGHT_CSS_JS`, etc.). This task catches any REMAINING references:

1. Delete the `window._injectCharSpans` JS function definition (L1318-1385) — the 67-line JS string that wraps text in char spans. This should have been deleted in Phase 3 but verify it's gone.

2. Delete ALL calls to `window._injectCharSpans`:
   - L404: `ui.run_javascript("if (window._injectCharSpans) window._injectCharSpans();")`
   - L2941: `ui.run_javascript("if (window._injectCharSpans) window._injectCharSpans();")`

3. In `_warp_to_highlight()` (L383-436): delete JS code that queries `[data-char-index="..."]` (L414-436). Replace with Range-based scrolling using the text walker (this should be done in Phase 4, but verify).

4. **Verification sweep:** Run this grep to confirm zero remaining references:
   ```
   grep -rn "data-char-index\|_injectCharSpans\|inject_char_spans\|strip_char_spans\|extract_chars_from_spans" src/
   ```
   Expected: zero matches in `src/` (only matches in `tests/` for the AC5 verification tests).

**Verification:**
Run: `grep -rn "data-char-index" src/` — expect zero matches
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`

**Commit:** `refactor: remove all remaining char-span JS references`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 4-5) -->
## Subcomponent C: Delete and Rewrite Tests

<!-- START_TASK_4 -->
### Task 4: Delete obsolete char-span test code

**Files:**
- Modify: `tests/unit/input_pipeline/test_text_extraction.py` (renamed from `test_char_spans.py` in Phase 3 Task 5) — audit for any remaining char-span-dependent tests that Phase 3 may have missed
- Delete: `tests/unit/test_char_tokenization.py` — entirely char-span-dependent (all tests import `_process_text_to_char_spans()` which is deleted in Task 1)
- Modify: `tests/unit/input_pipeline/test_process_input.py` — remove any assertions that check for `data-char-index` in output

**Implementation:**

Phase 3 Task 5 already renamed `test_char_spans.py` to `test_text_extraction.py` and deleted char-span test classes, keeping `TestExtractTextFromHtml` and `TestStripHtmlToText`. This task catches anything Phase 3 missed:

1. **Audit `test_text_extraction.py`** (the renamed file) — confirm only `TestExtractTextFromHtml` and `TestStripHtmlToText` remain. Delete any stale imports or helper functions that referenced removed char-span functions.

2. **Delete `test_char_tokenization.py`** — the entire file depends on `_process_text_to_char_spans()` (deleted in Task 1). No tests in this file are worth keeping.

3. **Audit `test_process_input.py`** — find assertions checking for `data-char-index` in pipeline output. Remove those assertions (pipeline no longer produces char spans). Keep assertions about other pipeline behaviour.

**Verification:**
Run: `uv run test-all`
Expected: All remaining tests pass.

**Commit:** `test: delete obsolete char-span tests`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Rewrite E2E annotation_helpers.py to use mouse-based selection

**Files:**
- Modify: `tests/e2e/annotation_helpers.py:24-75`

**Implementation:**

Replace the `select_chars()` function which currently uses `[data-char-index]` locators:

```python
# OLD: Direct locator queries on char-span DOM
start_el = page.locator(f"[data-char-index='{start_char}']")
end_el = page.locator(f"[data-char-index='{end_char}']")
```

New implementation using JS coordinate lookup + Playwright mouse events:

```python
async def select_chars(page, start_char: int, end_char: int) -> None:
    """Select a character range using mouse events.

    Uses the text walker (annotation-highlight.js) to convert char offsets
    to screen coordinates, then performs a mouse click-drag selection.
    """
    # Get bounding rectangles for start and end positions via text walker.
    # Uses charOffsetToRect() (Phase 4) which handles StaticRange → live Range
    # conversion internally — charOffsetToRange() returns StaticRange which
    # does NOT have getBoundingClientRect().
    coords = await page.evaluate(f"""(() => {{
        const container = document.getElementById('doc-container');
        if (typeof walkTextNodes === 'undefined') return null;
        const nodes = walkTextNodes(container);
        const startRect = charOffsetToRect(nodes, {start_char});
        const endRect = charOffsetToRect(nodes, {end_char} - 1);
        return {{
            startX: startRect.left + 1,
            startY: startRect.top + startRect.height / 2,
            endX: endRect.right - 1,
            endY: endRect.top + endRect.height / 2
        }};
    }})()""")
    if coords is None:
        raise RuntimeError("Could not get char coordinates — text walker not loaded")
    # Perform mouse-based selection (real user interaction)
    await page.mouse.click(coords["startX"], coords["startY"])
    await page.mouse.down()
    await page.mouse.move(coords["endX"], coords["endY"])
    await page.mouse.up()
```

The `create_highlight()` helper may also need updating if it depends on char-span DOM. Audit and update accordingly.

**Key point:** The JS `page.evaluate()` is read-only (coordinate lookup). The actual selection is performed via Playwright's native mouse API, simulating real user behaviour. JS functions (`walkTextNodes`, `charOffsetToRange`) are in global scope per Phase 2's design — no namespace prefix needed.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_highlight.py -v -k "test_create"` (or any single E2E test)
Expected: Test passes with the new helper.

**Commit:** `refactor: rewrite E2E helpers to use mouse-based text selection`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 6-7) -->
## Subcomponent D: PDF Export Verification and Documentation

<!-- START_TASK_6 -->
### Task 6: Verify PDF export pipeline unchanged

**Verifies:** css-highlight-api.AC6.1, css-highlight-api.AC6.2

**Files:**
- No changes — verification only

**Implementation:**

The PDF export pipeline uses integer character offsets from the CRDT, not char-span DOM. This task confirms nothing broke:

1. Run existing PDF export unit tests:
   ```
   uv run pytest tests/unit/export/ -v
   ```

2. Run existing integration tests for highlight LaTeX elements:
   ```
   uv run pytest tests/integration/test_highlight_latex_elements.py -v
   ```

3. Verify the data flow is intact:
   - `export/highlight_spans.py` imports `extract_text_from_html` from `input_pipeline.html_input` (not deleted)
   - `export/highlight_spans.py` imports `walk_and_map`, `TextNodeInfo`, `collapsed_to_html_offset`, `find_text_node_offsets` (not deleted)
   - `export/pdf_export.py` receives integer offsets (`start_char`, `end_char`) — no char-span dependency

4. Update stale comment in `export/pdf_export.py` (L57-59) if it references `_process_text_to_char_spans()`.

**Testing:**
- css-highlight-api.AC6.1: PDF output from CSS Highlight API highlights matches old system (same char offsets → same LaTeX)
- css-highlight-api.AC6.2: Existing tests pass without modification

**Verification:**
Run: `uv run pytest tests/unit/export/ tests/integration/test_highlight_latex_elements.py -v`
Expected: All pass without modification.

**Commit:** `test: verify PDF export unchanged after char-span removal` (only if comment update needed; skip commit if zero changes)
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md` (root)

**Implementation:**

Update these sections:

1. **Project Structure** (line ~181): Change `input_pipeline/      # HTML input processing (detection, conversion, char spans)` to `input_pipeline/      # HTML input processing (detection, conversion, text extraction)`

2. **HTML Input Pipeline section** — Pipeline Steps:
   - Remove step 7 ("Client-side char span injection")
   - The pipeline now ends at step 6 (empty element removal)

3. **Key Design Decision: Client-Side Span Injection** paragraph (lines ~302-312):
   - Replace entirely with a note about CSS Custom Highlight API:
   - "Char-level annotation highlighting uses the CSS Custom Highlight API. The server sends clean HTML; JavaScript text walkers map character offsets to DOM text node positions; highlights render via `CSS.highlights` without DOM modification."

4. **Public API** section for input_pipeline:
   - Remove `inject_char_spans` and `strip_char_spans` entries
   - Keep `extract_text_from_html()`, `detect_content_type()`, `process_input()`, `ContentType`, `CONTENT_TYPES`

5. **Highlight Pipeline** section — verify it accurately describes the current pipeline (pre-Pandoc span injection for LaTeX export is unchanged).

Do NOT update historical implementation plan docs in `docs/implementation-plans/` — they document what was built at the time.

**Verification:**
Run: `grep -n "inject_char_spans\|strip_char_spans\|char span" CLAUDE.md` — expect zero matches

**Commit:** `docs: update CLAUDE.md to reflect CSS Highlight API migration`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_D -->

<!-- START_TASK_8 -->
### Task 8: Final verification sweep

**Files:**
- No changes — verification only

**Implementation:**

Run a comprehensive sweep to confirm all char-span references are gone:

1. **Source code sweep:**
   ```
   grep -rn "data-char-index\|inject_char_spans\|strip_char_spans\|extract_chars_from_spans\|_connected_clients\|_ClientState\|_build_remote_cursor_css\|_build_remote_selection_css" src/
   ```
   Expected: zero matches.

2. **Test code sweep:**
   ```
   grep -rn "data-char-index\|inject_char_spans\|strip_char_spans" tests/
   ```
   Expected: only matches in `test_public_api.py` (the AC5 verification tests from Phase 3 that intentionally test import failures).

3. **Full test suite:**
   ```
   uv run test-all
   ```
   Expected: all pass.

4. **Type checking:**
   ```
   uvx ty check
   ```
   Expected: passes.

**Verification:**
All commands above produce expected results.

**Commit:** No commit — verification only.
<!-- END_TASK_8 -->
