# E2E Test Migration Implementation Plan — Phase 2

**Goal:** Replace `data-char-index` locators in active test files with text-walker-based equivalents.

**Architecture:** Use `_textNodes` readiness checks for waits, `#doc-container` queries for DOM navigation, and `textContent` for content verification. `test_dom_performance.py` is deferred to Phase 8 for deletion (benchmark designed for old char-span architecture — Lakatos degenerating).

**Tech Stack:** Playwright, pytest

**Scope:** Phase 2 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC1: No data-char-index references (DoD 1, 7)
- **156-e2e-test-migration.AC1.3 Success:** `test_annotation_tabs.py` contains zero `data-char-index` locators

### 156-e2e-test-migration.AC2: All active E2E tests pass (DoD 2)
- **156-e2e-test-migration.AC2.1 Success:** `uv run test-e2e` completes with zero failures and zero timeouts

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Fix test_annotation_tabs.py (5 references)

**Verifies:** 156-e2e-test-migration.AC1.3

**Files:**
- Modify: `tests/e2e/test_annotation_tabs.py:103, 142, 155, 482, 522`

**Implementation:**

Five references need replacing. All are content-presence checks after tab navigation or workspace setup:

**Lines 103** — visibility check ("Tab 1 should have document content"):
Replace `expect(page.locator("[data-char-index]").first).to_be_visible()` with a `#doc-container` text content check. The test is verifying the Annotate tab has document content visible. Use `expect(page.locator("#doc-container")).to_contain_text()` or check `_textNodes` length.

**Lines 142-143** — element count ("Expected char spans in Tab 1"):
Replace `page.locator("[data-char-index]").count()` with a function that checks `_textNodes.length` or `textContent.length`. The test is counting content elements before tab switch, then verifying the same count after return. Since char spans no longer exist, verify content presence via `textContent.length > 0` or `_textNodes.length > 0`.

**Lines 155-156** — visibility check + count assertion after tab round-trip:
Same pattern as 142. Replace locator with `#doc-container` text content check. The count comparison (`char_spans_after.count() == initial_count`) should compare `_textNodes.length` before and after, or simply verify `textContent` hasn't changed.

**Lines 482 and 522** — readiness checks (`expect(page.locator("[data-char-index='0']")).to_be_visible(timeout=3000)`):
Replace with `page.wait_for_function("() => window._textNodes && window._textNodes.length > 0", timeout=3000)`. These are waiting for content to render after warp navigation.

**Testing:**
- 156-e2e-test-migration.AC1.3: `grep "data-char-index" tests/e2e/test_annotation_tabs.py` returns no matches

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -x --timeout=60 -m e2e` (requires test DB configured)
Expected: All tests pass without char-index timeouts

**Commit:** `fix(e2e): replace data-char-index locators in test_annotation_tabs with text walker checks`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Fix test_html_paste_whitespace.py (11 references)

**Verifies:** 156-e2e-test-migration.AC2.1

**Files:**
- Modify: `tests/e2e/test_html_paste_whitespace.py:148, 154, 164, 246, 250, 258, 328, 335, 336, 435, 493`

**Implementation:**

Eleven references across four categories:

**Readiness waits (lines 148, 246, 328, 435, 493):**
All five are `page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)`. These wait for document rendering after HTML paste + submit + dialog confirm. Replace with:
```python
page.wait_for_function(
    "() => window._textNodes && window._textNodes.length > 0",
    timeout=15000,
)
```
Note: `test_html_paste_whitespace.py` has its own `simulate_html_paste()` helper. After paste, there's a "Click Add" step, then a content type confirm dialog, then rendering. The _textNodes check works here because `annotation.py:1216` initialises the walker on every content load.

**Element scroll (lines 154, 250):**
Both are `page.locator("[data-char-index='100']").scroll_into_view_if_needed()`. These scroll to a position in the document for screenshot verification. Replace with scrolling `#doc-container` or using `page.evaluate()` to scroll the container element to a percentage position.

**DOM navigation (line 164):**
`page.locator("[data-char-index]").first.locator("..")` — finds container via char span parent. Replace with `page.locator("#doc-container")` directly.

**JavaScript DOM queries (lines 258, 335-336):**
Lines 258 and 336 use `document.querySelectorAll('[data-char-index]')` inside `page.evaluate()` to iterate through text content. Line 335 is a JS comment referencing the same selector within the page.evaluate() block at line 336. Replace all three with text walker queries: use `document.getElementById('doc-container').textContent` to find text positions, or use `walkTextNodes()` + `charOffsetToRect()` for coordinate-based lookups. Remove the JS comment on line 335 as it describes the old architecture.

**Testing:**
- 156-e2e-test-migration.AC2.1: Tests pass without char-index references

**Verification:**
Run: `uv run pytest tests/e2e/test_html_paste_whitespace.py -v -x --timeout=60 -m e2e`
Expected: All paste/whitespace tests pass

**Commit:** `fix(e2e): replace data-char-index locators in test_html_paste_whitespace with text walker checks`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Fix test_fixture_screenshots.py (1 reference)

**Verifies:** 156-e2e-test-migration.AC2.1

**Files:**
- Modify: `tests/e2e/test_fixture_screenshots.py:206`

**Implementation:**

Single reference at line 206:
```python
page.locator("[data-char-index]").first.wait_for(state="attached", timeout=30000)
```

Replace with:
```python
page.wait_for_function(
    "() => window._textNodes && window._textNodes.length > 0",
    timeout=30000,
)
```

The 30-second timeout is intentional — fixture screenshots load large HTML fixtures that take time to process.

**Testing:**
- 156-e2e-test-migration.AC2.1: Test passes without timeout

**Verification:**
Run: `uv run pytest tests/e2e/test_fixture_screenshots.py -v -x --timeout=120 -m e2e -k "austlii"`
Expected: AustLII fixture renders and screenshot is captured

**Commit:** `fix(e2e): replace data-char-index wait in test_fixture_screenshots with _textNodes readiness`
<!-- END_TASK_3 -->
