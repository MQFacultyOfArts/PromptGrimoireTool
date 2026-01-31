# Test Suite Consolidation - Phase 2: Consolidate test_annotation_page.py with subtests

**Goal:** Reduce setup overhead by consolidating 7 edge case classes into 3 test methods using subtests

**Architecture:** Refactor existing test classes to share expensive setup (browser context, workspace creation) across related assertions

**Tech Stack:** pytest, pytest-subtests, Playwright

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-01-31

---

## Phase Overview

Current state: 26 tests across 15 test classes in test_annotation_page.py (816 lines)
Target state: Same coverage with shared setup using subtests, ~600 lines

**Classes to consolidate (7 edge case classes, 8 tests total):**
- TestDeleteHighlight (1 test)
- TestChangeTagDropdown (1 test)
- TestKeyboardShortcuts (1 test)
- TestOverlappingHighlights (1 test)
- TestGoToHighlight (1 test)
- TestCardHoverEffect (1 test)
- TestSpecialContent (2 tests)

**Consolidation groups:**
1. **TestHighlightMutations** - combines delete, change tag (share: workspace + document + highlight setup)
2. **TestHighlightInteractions** - combines go-to, hover effect (share: workspace + document + highlight + card)
3. **TestEdgeCases** - combines overlapping, special content, keyboard shortcuts (share: workspace + document setup)

---

<!-- START_TASK_1 -->
### Task 1: Create shared workspace+document setup helper

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Add a helper function for workspace+document setup**

Add this function after the existing `_create_highlight` helper (around line 49):

```python
def _setup_workspace_with_content(page: Page, app_server: str, content: str) -> None:
    """Navigate to annotation page, create workspace, and add document content.

    This is the common 5-step setup pattern shared by all annotation tests:
    1. Navigate to /annotation
    2. Click create workspace
    3. Wait for workspace URL
    4. Fill content
    5. Submit and wait for word spans

    Args:
        page: Playwright page.
        app_server: Base URL of the app server.
        content: Text content to add as document.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(
        re.compile("paste|content", re.IGNORECASE)
    )
    content_input.fill(content)
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
    page.wait_for_selector("[data-word-index]")
    page.wait_for_timeout(200)
```

**Step 2: Verify the helper compiles**

```bash
uv run python -c "import tests.e2e.test_annotation_page"
```

Expected: No import errors.

**Step 3: No commit yet** - this is a preparatory change for the consolidation tasks.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create TestHighlightMutations with subtests

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Add the consolidated test class**

Add after the existing TestSpecialContent class (end of file, before removing old classes):

```python
class TestHighlightMutations:
    """Consolidated tests for highlight mutation operations (delete, change tag).

    Uses subtests to share expensive workspace+document+highlight setup across
    related assertions. Each subtest verifies a different mutation operation.
    """

    @pytestmark_db
    def test_highlight_mutations(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test delete and tag change mutations with shared setup."""
        page = authenticated_page

        # Shared setup: workspace + document + highlight
        _setup_workspace_with_content(page, app_server, "Mutation test words here")
        _create_highlight(page, 0, 1)

        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()

        word = page.locator("[data-word-index='0']")

        # --- Subtest: change tag via dropdown ---
        with subtests.test(msg="change_tag_updates_color"):
            # Find the dropdown in the card
            tag_select = ann_card.locator("select, [role='combobox'], .q-select").first
            tag_select.click()

            # Select "Legal Issues" (red - #d62728 = rgb(214, 39, 40))
            page.get_by_role(
                "option", name=re.compile("legal.?issues", re.IGNORECASE)
            ).click()
            page.wait_for_timeout(500)

            # Verify color changed to legal issues red
            expect(word).to_have_css(
                "background-color", re.compile(r"rgba\(214,\s*39,\s*40"), timeout=5000
            )

        # --- Subtest: delete highlight removes card and styling ---
        with subtests.test(msg="delete_removes_card_and_styling"):
            # Click delete button (close icon)
            delete_btn = ann_card.locator("button").filter(
                has=page.locator("[class*='close']")
            )
            if delete_btn.count() == 0:
                delete_btn = (
                    ann_card.get_by_role("button")
                    .filter(
                        has=page.locator("i, svg, span").filter(
                            has_text=re.compile("close|delete", re.IGNORECASE)
                        )
                    )
                    .first
                )
            delete_btn.click()

            # Card should be gone
            expect(ann_card).not_to_be_visible(timeout=5000)

            # Styling should be removed
            expect(word).not_to_have_css(
                "background-color", re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"), timeout=5000
            )
```

**Step 2: Run the new test to verify it works**

```bash
uv run pytest tests/e2e/test_annotation_page.py::TestHighlightMutations -v
```

Expected: Test passes with 2 subtests shown.

**Step 3: No commit yet** - wait until all consolidations are complete.

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create TestHighlightInteractions with subtests

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Add the consolidated test class**

Add after TestHighlightMutations:

```python
class TestHighlightInteractions:
    """Consolidated tests for highlight interaction features (goto, hover).

    Uses subtests to share expensive workspace+document+highlight setup across
    related assertions. Each subtest verifies a different interaction feature.
    """

    @pytestmark_db
    def test_highlight_interactions(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test goto and hover interactions with shared setup."""
        page = authenticated_page

        # Need long content for scroll testing
        long_content = " ".join([f"word{i}" for i in range(100)])
        _setup_workspace_with_content(page, app_server, long_content)

        # Scroll to end and create highlight there (for scroll testing)
        word_90 = page.locator("[data-word-index='90']")
        word_90.scroll_into_view_if_needed()
        _select_words(page, 90, 92)
        page.get_by_role(
            "button", name=re.compile("jurisdiction", re.IGNORECASE)
        ).click()
        page.wait_for_timeout(300)

        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()

        # --- Subtest: goto button scrolls to highlight ---
        with subtests.test(msg="goto_scrolls_to_highlight"):
            # Scroll back to top first
            page.locator("[data-word-index='0']").scroll_into_view_if_needed()
            page.wait_for_timeout(200)

            # Click go-to button (icon has text "my_location")
            goto_btn = ann_card.locator("button").filter(has_text="my_location").first
            goto_btn.click()
            page.wait_for_timeout(500)

            # Word 90 should now be visible
            expect(word_90).to_be_in_viewport()

        # --- Subtest: hovering card highlights words ---
        with subtests.test(msg="hover_highlights_words"):
            # Ensure card is visible (may need to scroll)
            ann_card.scroll_into_view_if_needed()

            # Hover over card
            ann_card.hover()
            page.wait_for_timeout(100)

            # Words should have hover highlight class
            expect(word_90).to_have_class(re.compile("card-hover-highlight"), timeout=2000)
```

**Step 2: Run the new test to verify it works**

```bash
uv run pytest tests/e2e/test_annotation_page.py::TestHighlightInteractions -v
```

Expected: Test passes with 2 subtests shown.

**Step 3: No commit yet** - wait until all consolidations are complete.

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create TestEdgeCases with subtests

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Add the consolidated test class**

Add after TestHighlightInteractions:

```python
class TestEdgeCasesConsolidated:
    """Consolidated tests for edge cases (overlapping, special content, keyboard).

    Uses subtests to share browser context across related edge case assertions.
    Each subtest creates its own workspace since content requirements differ.
    """

    @pytestmark_db
    def test_edge_cases(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test various edge cases with shared browser context."""
        page = authenticated_page

        # --- Subtest: keyboard shortcut creates highlight ---
        with subtests.test(msg="keyboard_shortcut_creates_highlight"):
            _setup_workspace_with_content(page, app_server, "Keyboard shortcut test")

            # Select words
            _select_words(page, 0, 1)
            page.wait_for_timeout(300)

            # Press "1" key (Jurisdiction - blue)
            page.keyboard.press("1")
            page.wait_for_timeout(500)

            # Verify highlight created with jurisdiction color
            word = page.locator("[data-word-index='0']")
            expect(word).to_have_css(
                "background-color", re.compile(r"rgba\(31,\s*119,\s*180"), timeout=5000
            )

            # Card should appear
            ann_card = page.locator("[data-testid='annotation-card']")
            expect(ann_card).to_be_visible()

        # --- Subtest: overlapping highlights show combined styling ---
        with subtests.test(msg="overlapping_highlights_combined_styling"):
            # Navigate to fresh workspace for this test
            page.goto(f"{app_server}/annotation")
            _setup_workspace_with_content(page, app_server, "word1 word2 word3 word4 word5")

            # Create first highlight (words 1-3)
            _select_words(page, 1, 3)
            page.get_by_role(
                "button", name=re.compile("jurisdiction", re.IGNORECASE)
            ).click()

            # Wait for save
            saved_indicator = page.locator("[data-testid='save-status']")
            expect(saved_indicator).to_contain_text("Saved", timeout=10000)

            # Create second overlapping highlight (words 2-4)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            _select_words(page, 2, 4)
            page.get_by_role(
                "button", name=re.compile("legal.?issue", re.IGNORECASE)
            ).click()

            page.wait_for_timeout(500)
            expect(saved_indicator).to_contain_text("Saved", timeout=10000)

            # Middle words should have background color (overlap styling)
            word2 = page.locator("[data-word-index='2']")
            word3 = page.locator("[data-word-index='3']")
            expect(word2).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=5000
            )
            expect(word3).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=5000
            )

            # Should have two annotation cards
            cards = page.locator("[data-testid='annotation-card']")
            assert cards.count() == 2

        # --- Subtest: special characters handled correctly ---
        with subtests.test(msg="special_characters_handled"):
            page.goto(f"{app_server}/annotation")
            special_content = "Test <script> & \"quotes\" 'apostrophe' $100 @email"
            _setup_workspace_with_content(page, app_server, special_content)

            # Should have word spans (special chars escaped)
            word_spans = page.locator("[data-word-index]")
            assert word_spans.count() >= 5

            # Can create highlight
            _create_highlight(page, 0, 2)
            ann_card = page.locator("[data-testid='annotation-card']")
            expect(ann_card).to_be_visible()

        # --- Subtest: empty content shows validation error ---
        with subtests.test(msg="empty_content_shows_error"):
            page.goto(f"{app_server}/annotation")
            page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
            page.wait_for_url(re.compile(r"workspace_id="))

            # Try to submit without content
            page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

            # Should show error notification
            notification = page.locator(".q-notification, [role='alert']")
            expect(notification).to_be_visible(timeout=3000)
```

**Step 2: Run the new test to verify it works**

```bash
uv run pytest tests/e2e/test_annotation_page.py::TestEdgeCasesConsolidated -v
```

Expected: Test passes with 4 subtests shown.

**Step 3: No commit yet** - wait until cleanup is complete.

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Remove original classes and verify all tests pass

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Remove the 7 original test classes**

Delete these classes entirely (they're now covered by the consolidated tests):

1. `TestDeleteHighlight` (lines ~767-819)
2. `TestChangeTagDropdown` (lines ~822-874)
3. `TestKeyboardShortcuts` (lines ~877-918)
4. `TestOverlappingHighlights` (lines ~921-977)
5. `TestGoToHighlight` (lines ~980-1025)
6. `TestCardHoverEffect` (lines ~1028-1062)
7. `TestSpecialContent` (lines ~1065-1115)

**Step 2: Run all annotation tests to verify nothing broke**

```bash
uv run pytest tests/e2e/test_annotation_page.py -v --tb=short
```

Expected: All tests pass. Test count should be similar (consolidated tests have multiple subtests).

**Step 3: Check line count reduction**

```bash
wc -l tests/e2e/test_annotation_page.py
```

Expected: Significantly less than 816 lines (target: ~600).

**Step 4: Commit the consolidation**

```bash
git add tests/e2e/test_annotation_page.py
git commit -m "$(cat <<'EOF'
refactor(tests): consolidate 7 edge case classes into 3 using subtests

Consolidates repetitive test setup by using pytest-subtests:

- TestHighlightMutations: delete highlight + change tag (2 subtests)
- TestHighlightInteractions: goto button + hover effect (2 subtests)
- TestEdgeCasesConsolidated: keyboard shortcuts + overlapping highlights
  + special content + empty content validation (4 subtests)

Each consolidated test shares expensive workspace+document setup
across related assertions, reducing redundant browser operations.

Adds _setup_workspace_with_content() helper to extract the common
5-step workspace creation pattern.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_5 -->

---

## Phase Completion Checklist

- [ ] Helper `_setup_workspace_with_content()` added
- [ ] TestHighlightMutations created with 2 subtests
- [ ] TestHighlightInteractions created with 2 subtests
- [ ] TestEdgeCasesConsolidated created with 4 subtests
- [ ] Original 7 classes removed
- [ ] All tests pass: `uv run pytest tests/e2e/test_annotation_page.py -v`
- [ ] Line count reduced from 816 to ~600
