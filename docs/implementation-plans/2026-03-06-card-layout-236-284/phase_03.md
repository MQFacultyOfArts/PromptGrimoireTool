# Annotation Card Layout — Phase 3: E2E Test Refactoring — Expand Before Interact

**Goal:** Update all card-touching E2E tests to expand cards before interacting with inner elements. Add `@pytest.mark.cards` marker to all card-touching test files.

**Architecture:** Three-pronged approach: (1) auto-expand in shared helpers (`get_comment_authors`, `count_comment_delete_buttons`) so call sites don't need explicit expand, (2) explicit `expand_card()` calls before direct card inner-element interactions in test bodies, (3) `@pytest.mark.cards` marker on all card-touching test files for the `e2e cards` runner.

**Tech Stack:** Playwright, pytest markers

**Scope:** Phase 3 of 4 from original design (phases 1-4)

**Codebase verified:** 2026-03-07

**Scope note:** Codebase investigation found two files not in the original design plan that also touch card inner elements: `test_instructor_workflow.py` (tag-select at lines 602-603, 615-616) and `test_anonymous_sharing.py` (calls `get_comment_authors()` and `count_comment_delete_buttons()`). Both are included here to prevent breakage when collapsed cards ship.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### card-layout-236-284.AC1: Bug fixes — race condition and solitaire collapse
- **card-layout-236-284.AC1.1 Success:** Cards render at correct vertical positions on initial page load (SPA navigation) without requiring user scroll
- **card-layout-236-284.AC1.3 Success:** Scrolling past all cards then scrolling back restores cards at correct positions (no solitaire collapse)
- **card-layout-236-284.AC1.4 Success:** Hidden cards (`display: none`) use cached height from `data-cached-height` instead of 0 in the push-down algorithm

### card-layout-236-284.AC2: Collapsed annotation cards
- **card-layout-236-284.AC2.1 Success:** Cards default to compact view (~28px) showing coloured dot, tag name, author initials, para_ref, comment count badge, chevron, locate button, delete button
- **card-layout-236-284.AC2.2 Success:** Clicking expand chevron reveals detail section (tag select, full author, text preview, comments)
- **card-layout-236-284.AC2.3 Success:** Clicking collapse chevron hides detail section, returning card to compact state
- **card-layout-236-284.AC2.4 Success:** Author initials derived correctly — "Brian Ballsun-Stanton" → "B.B.S.", single name → "B."
- **card-layout-236-284.AC2.5 Success:** Cards below an expanding card push down smoothly via `positionCards()` re-run
- **card-layout-236-284.AC2.6 Success:** View-only users see static tag label (not dropdown) in both compact and expanded states
- **card-layout-236-284.AC2.7 Success:** Comment input only visible in expanded state when `can_annotate` is true
- **card-layout-236-284.AC2.8 Edge:** Anonymous author renders as "A." initials without error

### card-layout-236-284.AC3: E2E card helpers and test updates
- **card-layout-236-284.AC3.3 Success:** All card-touching E2E tests pass after inserting `expand_card()` before inner-element interactions
- **card-layout-236-284.AC3.4 Failure:** Interacting with tag-select or comment-input without expanding first fails (element not visible)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Auto-expand in `get_comment_authors` and `count_comment_delete_buttons`

**Verifies:** card-layout-236-284.AC3.3 (helpers auto-expand, keeping call sites working)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py:971-999` (both functions)

**Implementation:**

Update `get_comment_authors` (line 971) and `count_comment_delete_buttons` (line 987) to call `expand_card` before accessing card inner elements, following the same pattern as `add_comment_to_highlight` from Phase 2.

Replace `get_comment_authors` (lines 971-984):

```python
def get_comment_authors(page: Page, *, card_index: int = 0) -> list[str]:
    """Get author names from comments on an annotation card.

    Automatically expands the card if collapsed, since comments
    are inside the detail section.

    Args:
        page: Playwright page with an annotation workspace loaded.
        card_index: 0-based index of the annotation card.

    Returns:
        List of author display names in DOM order.
    """
    expand_card(page, card_index)

    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    labels = card.locator("[data-testid='comment-author']")
    return [labels.nth(i).inner_text() for i in range(labels.count())]
```

Replace `count_comment_delete_buttons` (lines 987-999):

```python
def count_comment_delete_buttons(page: Page, *, card_index: int = 0) -> int:
    """Count visible delete buttons on an annotation card.

    Automatically expands the card if collapsed, since delete
    buttons are inside the detail section.

    Args:
        page: Playwright page with an annotation workspace loaded.
        card_index: 0-based index of the annotation card.

    Returns:
        Number of delete buttons visible.
    """
    expand_card(page, card_index)

    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    return card.locator("[data-testid='comment-delete']").count()
```

**Verification:**
Run: `uv run grimoire test changed`
Expected: No test breakage from helper changes.

**Commit:** `feat(e2e): auto-expand card in comment helper functions`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `_post_comment_on_first_card` in `test_translation_student.py`

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_translation_student.py:74-82` (local helper)

**Implementation:**

The local helper `_post_comment_on_first_card()` at line 74 manually does `card.click()` to expand the card before filling the comment input. Replace with `expand_card()` for deterministic expand behaviour.

Replace the helper (lines 74-82) with:

```python
def _post_comment_on_first_card(page: Page, comment_uuid: str) -> None:
    """Post a comment on the first annotation card."""
    from tests.e2e.annotation_helpers import expand_card

    expand_card(page, 0)

    card = page.locator("[data-testid='annotation-card']").first
    card.get_by_test_id("comment-input").fill(comment_uuid)
    card.get_by_test_id("post-comment-btn").click()
```

Also check if line ~294 has a similar manual `card.click()` pattern in `test_mixed_script_annotation` and replace with `expand_card()`. Ensure the post button there also uses `get_by_test_id("post-comment-btn")` not `get_by_text("Post")`.

**Verification:**
Run: `uv run grimoire test changed`
Expected: No test breakage.

**Commit:** `refactor(e2e): use expand_card in translation student helper`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-7) -->

<!-- START_TASK_3 -->
### Task 3: Add `@pytest.mark.cards` and `expand_card` to `test_annotation_canvas.py`

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_annotation_canvas.py`

**Implementation:**

1. Add `import pytest` if not present
2. Add `from tests.e2e.annotation_helpers import expand_card` to imports
3. Add `@pytest.mark.cards` to class `TestAnnotationCanvas`
4. Insert `expand_card(page, 0)` before line 139 (first `tag-select` interaction on first card)
5. Insert `expand_card(page, 1)` before line 150 (tag-select on second card)

Note: Lines 207-208 and 216-217 call `add_comment_to_highlight()` which auto-expands — no explicit expand needed there.

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: `test_annotation_canvas.py` tests pass.

**Commit:** `refactor(e2e): expand cards before tag-select in annotation canvas tests`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add `@pytest.mark.cards` and `expand_card` to `test_happy_path_workflow.py`

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_happy_path_workflow.py`

**Implementation:**

1. Add `import pytest` if not present
2. Add `from tests.e2e.annotation_helpers import expand_card` to imports
3. Add `@pytest.mark.cards` to class `TestHappyPathWorkflow`
4. Insert `expand_card(student_page, 0)` before line 106 (tag-select visibility check on first card)

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: `test_happy_path_workflow.py` tests pass.

**Commit:** `refactor(e2e): expand card before tag-select in happy path test`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add `@pytest.mark.cards` and `expand_card` to `test_history_tutorial.py`

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_history_tutorial.py`

**Implementation:**

1. Add `from tests.e2e.annotation_helpers import expand_card` to imports
2. Add `@pytest.mark.cards` to class `TestHistoryTutorial`
3. Insert `expand_card(page1, 0)` before line 95 (where `page1.locator(ANNOTATION_CARD).first.click()` opens the card — replace `.click()` with `expand_card`)
4. Replace the manual comment posting block (lines 95-99):
   - Remove `page1.locator(ANNOTATION_CARD).first.click()` (line 95)
   - Insert `expand_card(page1, 0)` instead
   - Keep comment fill and post lines (98-99)
5. Insert `expand_card(page1, 0)` before line 113 (tag-select interaction after page2 sync)

Note: The manual comment posting (lines 98-99) fills `comment-input` directly — this is inside the detail section, so expand must come first. The `add_comment_to_highlight` helper isn't used here.

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: `test_history_tutorial.py` tests pass.

**Commit:** `refactor(e2e): expand cards before interactions in history tutorial test`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Add `@pytest.mark.cards` and `expand_card` to `test_law_student.py`

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_law_student.py`

**Implementation:**

1. Add `from tests.e2e.annotation_helpers import expand_card` to imports
2. Add `@pytest.mark.cards` to class `TestLawStudent`
3. Replace manual card expand patterns with `expand_card()`:
   - Replace `page.locator("[data-testid='annotation-card']").first.click()` at line 133 with `expand_card(page, 0)`
   - Replace `page.locator("[data-testid='annotation-card']").nth(1).click()` at line 161 with `expand_card(page, 1)`
4. Insert `expand_card(page, 0)` before line 182 (tag-select interaction on first card)
5. Insert `expand_card(page, 2)` before line 234-236 (comment input on third card)

Note: Lines 133 and 161 use `.click()` to expand the card before filling comment input. Replace with `expand_card()` which uses the dedicated expand button and waits for the detail section.

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: `test_law_student.py` tests pass.

**Commit:** `refactor(e2e): expand cards before interactions in law student test`

<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Add `@pytest.mark.cards` to remaining files and `expand_card` where needed

**Verifies:** card-layout-236-284.AC3.3

**Files:**
- Modify: `tests/e2e/test_empty_tag_ux.py` — marker only
- Modify: `tests/e2e/test_organise_perf.py` — marker only
- Modify: `tests/e2e/test_translation_student.py` — marker + expand (Task 2 handles the helper, this adds the marker and handles line ~294)
- Modify: `tests/e2e/test_annotation_drag.py` — marker + expand before sidebar tag-select (~line 307)
- Modify: `tests/e2e/test_instructor_workflow.py` — marker + expand before tag-select (~lines 602, 615)
- Modify: `tests/e2e/test_anonymous_sharing.py` — marker only (calls auto-expanding helpers)

**Implementation:**

For each file:

1. **`test_empty_tag_ux.py`:** Add `@pytest.mark.cards` to each test class. No `expand_card()` needed — tests only check card presence/count, not inner elements.

2. **`test_organise_perf.py`:** Add `@pytest.mark.cards` to `TestOrganiseTabPerformance`. No `expand_card()` needed — only checks card count.

3. **`test_translation_student.py`:** Add `@pytest.mark.cards` to `TestTranslationStudent`. For line ~294 (`card.click()` followed by comment fill in `test_mixed_script_annotation`), replace with `expand_card(page, 0)`. Import `expand_card` (may already be imported from Task 2).

4. **`test_annotation_drag.py`:** Add `@pytest.mark.cards` to classes that touch annotation cards (not just organise cards). Insert `expand_card(page, 0)` before line ~307 where test checks sidebar `tag-select` after drag operation.

5. **`test_instructor_workflow.py`:** Add `@pytest.mark.cards` to `TestFullCourseSetup`. Insert `expand_card(student_page, 0)` before line ~602 and `expand_card(student_page, 1)` before line ~615 (tag-select interactions).

6. **`test_anonymous_sharing.py`:** Add `@pytest.mark.cards` to test classes. No explicit `expand_card()` needed — all card interactions go through `add_comment_to_highlight`, `get_comment_authors`, and `count_comment_delete_buttons`, which auto-expand.

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: All card-touching tests discovered and passing.

**Commit:** `refactor(e2e): add cards marker and expand calls to remaining test files`

<!-- END_TASK_7 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_8 -->
### Task 8: Verify AC3.4 — interaction without expand fails

**Verifies:** card-layout-236-284.AC3.4

**Files:**
- No file changes — verification only

**Implementation:**

Manually verify that interacting with a card inner element without expanding first fails. This is a negative test to confirm the collapsed card design is working:

1. In any card-touching test, temporarily remove an `expand_card()` call before a `tag-select` or `comment-input` interaction
2. Run the test
3. Confirm it fails because the element is not visible (Playwright timeout waiting for visibility)
4. Restore the `expand_card()` call

This is a manual verification step, not a permanent test. The assertion is: "without expand, inner elements are hidden and interactions fail."

**Verification:**
Run one test with expand removed, confirm failure. Restore.

**Commit:** No commit — verification only.

<!-- END_TASK_8 -->

<!-- START_SUBCOMPONENT_C (tasks 9-10) -->

<!-- START_TASK_9 -->
### Task 9: Add E2E regression test for AC1 — card positioning and solitaire collapse

**Verifies:** card-layout-236-284.AC1.1, card-layout-236-284.AC1.2, card-layout-236-284.AC1.3, card-layout-236-284.AC1.4, card-layout-236-284.AC1.5

**Files:**
- Create: `tests/e2e/test_card_layout.py` (e2e)

**Implementation:**

Create a new E2E test file with `@pytest.mark.cards` for the card positioning bug fixes. The test should:

1. **AC1.1 — initial positioning:** Create a workspace with content, create 2-3 highlights, verify each annotation card has a non-zero `top` style value and cards don't overlap (each card's `top` > previous card's `top` + previous card's height).

2. **AC1.2 — race condition (highlights-ready):** After SPA navigation to an annotation workspace with existing highlights, verify that `window._highlightsReady` is `true` and that cards are positioned correctly without requiring any user scroll. Use `page.wait_for_function("() => window._highlightsReady === true", timeout=10000)` to confirm the ready flag is set. Then verify cards have non-zero `top` values — this proves `setupCardPositioning()` caught the `highlights-ready` event even if it fired before listener registration.

3. **AC1.3 — scroll recovery (no solitaire collapse):** After creating highlights, scroll the document container past all cards so they become hidden, then scroll back. Verify cards are restored at their original positions (within a small tolerance). Use `page.wait_for_function()` to check card `top` values rather than sleeps.

4. **AC1.4 — height cache:** After scrolling past cards, verify hidden cards have a `data-cached-height` attribute with a positive value. Use Playwright's native `locator.get_attribute("data-cached-height")` to read the attribute — no `page.evaluate()` needed.

5. **AC1.5 — fallback default height:** Create a **new highlight** on content that has never been scrolled past (so the card has never had its height cached). Immediately scroll past and back before any `positionCards()` cycle caches the height. Verify the card still positions correctly (uses the 80px fallback) — the card should have a reasonable `top` value rather than collapsing to 0. This avoids `page.evaluate()` DOM mutation.

**Testing:**
- AC1.1: Create 3 highlights, check each card has `style` containing `top:` with a positive px value. Cards at indices 0, 1, 2 should have increasing `top` values.
- AC1.2: Navigate to workspace with existing highlights, `page.wait_for_function("() => window._highlightsReady === true")`, verify cards have non-zero `top` values immediately (no scroll needed).
- AC1.3: Record card `top` values, scroll down past all cards, scroll back up, verify `top` values restored (within 5px tolerance).
- AC1.4: While cards are hidden (after scrolling past), use `card_locator.get_attribute("data-cached-height")` and assert it is not `None` and `int(value) > 0`.
- AC1.5: Create a fresh highlight, immediately scroll past and back before height is cached, verify card `top` is still positive (fallback to 80px default).

**Verification:**
Run: `uv run grimoire e2e cards -k "test_card_layout"`
Expected: All tests pass.

**Commit:** `test(e2e): add regression tests for card positioning and solitaire collapse fixes`

<!-- END_TASK_9 -->

<!-- START_TASK_10 -->
### Task 10: Add E2E test for AC2 — collapsed card feature

**Verifies:** card-layout-236-284.AC2.1, card-layout-236-284.AC2.2, card-layout-236-284.AC2.3, card-layout-236-284.AC2.4, card-layout-236-284.AC2.5, card-layout-236-284.AC2.6, card-layout-236-284.AC2.7, card-layout-236-284.AC2.8

**Files:**
- Modify: `tests/e2e/test_card_layout.py` (add tests to file created in Task 9)

**Implementation:**

Add tests to the same file for the collapsed card feature:

1. **AC2.1 — default collapsed:** Create a highlight, verify the card is visible but `card-detail` is hidden by default. Verify the compact header contains: a coloured dot element, tag display name text, expand button (`card-expand-btn`), locate button, delete button.

2. **AC2.2 + AC2.3 — expand/collapse toggle:** Click expand button, verify `card-detail` becomes visible and contains `tag-select` and `comment-input`. Click expand button again, verify `card-detail` becomes hidden.

3. **AC2.4 — author initials:** Create a highlight as a user with a multi-part name. Verify the compact header shows correct initials format (e.g. "B.B.S." for "Brian Ballsun-Stanton"). The mock auth email is random but the display name comes from the user record — check what name the mock auth creates and verify initials match.

4. **AC2.6 + AC2.7 — view-only static label and no comment input:** Create a workspace as user1, create a highlight, grant viewer permission to user2. Navigate as user2, verify the card shows a static tag label (not a `tag-select` dropdown) in both compact and expanded states. After expanding, also verify `comment-input` count is 0 — viewers must not be able to comment (AC2.7).

5. **AC2.5 — push-down on expand:** Create 2 highlights. Record the second card's `top` CSS value. Call `expand_card(page, 0)` to expand the first card. Verify the second card's `top` value has increased (it was pushed down by the expansion). Use Playwright's `expect(second_card).not_to_have_css("top", original_top_value)` or compare parsed integer values.

6. **AC2.8 — anonymous author initials:** Create a highlight under anonymous sharing (no authenticated user / anonymous context). Verify the compact header shows "A." as the author initials, rendered without error.

**Testing:**
- AC2.1: `expect(card.get_by_test_id("card-detail")).to_be_hidden()` immediately after page load
- AC2.2: `expand_card(page, 0)` then `expect(card.get_by_test_id("card-detail")).to_be_visible()`
- AC2.3: `collapse_card(page, 0)` then `expect(card.get_by_test_id("card-detail")).to_be_hidden()`
- AC2.4: Check compact header text content for initials pattern
- AC2.5: Create 2 highlights, record second card's `top`, expand first card, assert second card's `top` increased
- AC2.6: As viewer, verify `card.get_by_test_id("tag-select")` has count 0
- AC2.7: As viewer, expand card, verify `card.get_by_test_id("comment-input")` has count 0
- AC2.8: Under anonymous sharing, verify compact header contains "A." initials text

**Verification:**
Run: `uv run grimoire e2e cards -k "test_card_layout"`
Expected: All tests pass.

**Commit:** `test(e2e): add tests for collapsed card feature (default state, toggle, initials, view-only)`

<!-- END_TASK_10 -->

<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

1. [ ] Run: `uv run grimoire e2e cards` — verify all card-touching tests are discovered and pass
2. [ ] Navigate to an annotation workspace in the browser, create a highlight
3. [ ] Verify the card appears collapsed (compact header, no detail section visible)
4. [ ] Click the expand chevron — verify detail section appears with tag select, comment input
5. [ ] Click again — verify detail section hides
6. [ ] Verify cards below push down smoothly on expand
7. [ ] Scroll past all cards, scroll back — verify no solitaire collapse (cards restore positions)
8. [ ] Temporarily remove an `expand_card()` call from a test, run it, confirm it fails (AC3.4)

## Evidence Required
- [ ] `uv run grimoire e2e cards` output showing all tests pass
- [ ] Screenshot of collapsed card with compact header
- [ ] Screenshot of expanded card showing detail section
