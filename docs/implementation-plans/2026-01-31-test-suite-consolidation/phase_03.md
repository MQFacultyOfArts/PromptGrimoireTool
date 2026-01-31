# Test Suite Consolidation - Phase 3: Create test_annotation_sync.py

**Goal:** Real-time sync tests between independent browser contexts on `/annotation`

**Architecture:** New test file with two-context fixture for verifying CRDT highlight sync

**Tech Stack:** pytest, pytest-subtests, Playwright, pycrdt

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-01-31

---

## Phase Overview

Create a new test file `test_annotation_sync.py` that verifies real-time synchronization of highlights between two independent browser contexts viewing the same workspace.

**Key design decision:** Use separate browser contexts (not tabs in one context) to simulate genuinely independent clients with different cookie jars and no shared browser process state.

**Coverage target:** 10+ sync scenarios covering highlight CRUD, comment sync, and presence indicators.

---

<!-- START_TASK_1 -->
### Task 1: Add two_annotation_contexts fixture to conftest.py

**Files:**
- Modify: `tests/e2e/conftest.py`

**Step 1: Read existing conftest to understand fixture patterns**

The existing `authenticated_page` fixture pattern should be extended.

**Step 2: Add imports and helper at top of conftest.py**

Add after existing imports:

```python
from uuid import uuid4

from promptgrimoire.db.workspace import create_workspace, add_document


async def _create_test_workspace_with_content(content: str) -> str:
    """Create a workspace with document for testing.

    Returns the workspace_id as string.
    """
    workspace = await create_workspace()
    await add_document(
        workspace_id=workspace.id,
        document_type="source",
        content=content,
        raw_content=content,
    )
    return str(workspace.id)
```

**Step 3: Add the two_annotation_contexts fixture**

Add at end of conftest.py:

```python
@pytest.fixture
def two_annotation_contexts(browser, app_server, request):
    """Two separate browser contexts viewing same workspace.

    Uses separate contexts (not tabs in one context) to simulate
    genuinely independent clients - different cookie jars, no shared
    browser process state, realistic multi-user scenario.

    Yields:
        tuple: (page1, page2, workspace_id)
    """
    import asyncio

    # Create workspace with test content
    content = "Sync test word1 word2 word3 word4 word5"
    loop = asyncio.new_event_loop()
    workspace_id = loop.run_until_complete(_create_test_workspace_with_content(content))
    loop.close()

    # TWO contexts = two independent "browsers"
    context1 = browser.new_context()
    context2 = browser.new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()

    # Navigate both to the workspace
    url = f"{app_server}/annotation?workspace_id={workspace_id}"
    page1.goto(url)
    page2.goto(url)

    # Wait for both to load word spans
    page1.wait_for_selector("[data-word-index]", timeout=10000)
    page2.wait_for_selector("[data-word-index]", timeout=10000)

    yield page1, page2, workspace_id

    context1.close()
    context2.close()
```

**Step 4: Verify fixture loads without errors**

```bash
uv run pytest --co tests/e2e/ -q 2>&1 | head -20
```

Expected: Test collection succeeds without fixture errors.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create test_annotation_sync.py with basic sync tests

**Files:**
- Create: `tests/e2e/test_annotation_sync.py`

**Step 1: Create the new test file with initial test class**

```python
"""End-to-end tests for real-time annotation synchronization.

Tests verify that highlights, comments, and presence indicators sync
between independent browser contexts viewing the same workspace.

Uses separate browser contexts (not tabs) to simulate genuinely
independent clients with different cookie jars.
"""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e, pytest.mark.requires_db]


def _select_words(page: Page, start_word: int, end_word: int) -> None:
    """Select a range of words by clicking start and shift-clicking end."""
    word_start = page.locator(f"[data-word-index='{start_word}']")
    word_end = page.locator(f"[data-word-index='{end_word}']")

    word_start.scroll_into_view_if_needed()
    expect(word_start).to_be_visible(timeout=5000)

    word_start.click()
    word_end.click(modifiers=["Shift"])


def _create_highlight(page: Page, start_word: int, end_word: int) -> None:
    """Select words and click the first tag button to create a highlight."""
    _select_words(page, start_word, end_word)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").first
    tag_button.click()


class TestHighlightSync:
    """Tests for highlight creation/deletion syncing between contexts."""

    def test_highlight_created_in_context1_appears_in_context2(
        self, two_annotation_contexts
    ) -> None:
        """Highlight created in one context appears in the other."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        _create_highlight(page1, 0, 1)

        # Verify highlight appears in page1
        word_p1 = page1.locator("[data-word-index='0']")
        expect(word_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=5000
        )

        # Wait for sync and verify in page2
        word_p2 = page2.locator("[data-word-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

    def test_highlight_deleted_in_context1_disappears_in_context2(
        self, two_annotation_contexts
    ) -> None:
        """Highlight deleted in one context disappears from the other."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        _create_highlight(page1, 0, 1)

        # Wait for it to appear in page2
        word_p2 = page2.locator("[data-word-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Delete highlight in page1
        ann_card = page1.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()
        delete_btn = ann_card.locator("button").filter(
            has=page1.locator("[class*='close']")
        )
        if delete_btn.count() == 0:
            delete_btn = (
                ann_card.get_by_role("button")
                .filter(
                    has=page1.locator("i, svg, span").filter(
                        has_text=re.compile("close|delete", re.IGNORECASE)
                    )
                )
                .first
            )
        delete_btn.click()

        # Verify styling removed in page2
        expect(word_p2).not_to_have_css(
            "background-color", re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"), timeout=10000
        )

    def test_highlight_created_in_context2_appears_in_context1(
        self, two_annotation_contexts
    ) -> None:
        """Highlight created in context2 appears in context1 (reverse direction)."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page2
        _create_highlight(page2, 2, 3)

        # Verify in page2
        word_p2 = page2.locator("[data-word-index='2']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=5000
        )

        # Wait for sync and verify in page1
        word_p1 = page1.locator("[data-word-index='2']")
        expect(word_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )
```

**Step 2: Run the tests to verify they work**

```bash
uv run pytest tests/e2e/test_annotation_sync.py -v --tb=short
```

Expected: All 3 tests pass.

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add comment and tag sync tests

**Files:**
- Modify: `tests/e2e/test_annotation_sync.py`

**Step 1: Add TestCommentSync class**

Add after TestHighlightSync:

```python
class TestCommentSync:
    """Tests for comment syncing between contexts."""

    def test_comment_added_in_context1_appears_in_context2(
        self, two_annotation_contexts
    ) -> None:
        """Comment added to highlight in one context appears in the other."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        _create_highlight(page1, 0, 1)

        # Wait for card to appear
        ann_card_p1 = page1.locator("[data-testid='annotation-card']")
        expect(ann_card_p1).to_be_visible()

        # Add comment in page1
        comment_input = ann_card_p1.locator("textarea, input[type='text']").first
        comment_input.fill("Test comment from context 1")
        comment_input.press("Enter")

        # Wait for sync and verify comment in page2's card
        ann_card_p2 = page2.locator("[data-testid='annotation-card']")
        expect(ann_card_p2).to_be_visible(timeout=10000)
        expect(ann_card_p2).to_contain_text("Test comment from context 1", timeout=10000)


class TestTagChangeSync:
    """Tests for tag/color change syncing between contexts."""

    def test_tag_changed_in_context1_updates_in_context2(
        self, two_annotation_contexts
    ) -> None:
        """Tag changed in one context updates highlight color in the other."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight with default tag in page1
        _create_highlight(page1, 0, 1)

        # Wait for sync to page2
        word_p2 = page2.locator("[data-word-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Change tag in page1 to Legal Issues (red)
        ann_card = page1.locator("[data-testid='annotation-card']")
        tag_select = ann_card.locator("select, [role='combobox'], .q-select").first
        tag_select.click()
        page1.get_by_role(
            "option", name=re.compile("legal.?issues", re.IGNORECASE)
        ).click()
        page1.wait_for_timeout(500)

        # Verify color changed in page2 (red = rgb(214, 39, 40))
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\(214,\s*39,\s*40"), timeout=10000
        )
```

**Step 2: Run the new tests**

```bash
uv run pytest tests/e2e/test_annotation_sync.py::TestCommentSync -v
uv run pytest tests/e2e/test_annotation_sync.py::TestTagChangeSync -v
```

Expected: Both test classes pass.

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add concurrent operation and edge case tests

**Files:**
- Modify: `tests/e2e/test_annotation_sync.py`

**Step 1: Add TestConcurrentOperations class**

Add after TestTagChangeSync:

```python
class TestConcurrentOperations:
    """Tests for handling concurrent operations from both contexts."""

    def test_concurrent_highlights_both_appear(
        self, two_annotation_contexts
    ) -> None:
        """Highlights created simultaneously in both contexts both appear."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create different highlights in each context (non-overlapping words)
        _select_words(page1, 0, 1)
        _select_words(page2, 3, 4)

        # Click tag buttons nearly simultaneously
        tag_btn_p1 = page1.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p2 = page2.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p1.click()
        tag_btn_p2.click()

        # Wait for sync
        page1.wait_for_timeout(2000)
        page2.wait_for_timeout(2000)

        # Both contexts should have both highlights
        # Check page1 has both
        word0_p1 = page1.locator("[data-word-index='0']")
        word3_p1 = page1.locator("[data-word-index='3']")
        expect(word0_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )
        expect(word3_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Check page2 has both
        word0_p2 = page2.locator("[data-word-index='0']")
        word3_p2 = page2.locator("[data-word-index='3']")
        expect(word0_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )
        expect(word3_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Both should have 2 annotation cards
        cards_p1 = page1.locator("[data-testid='annotation-card']")
        cards_p2 = page2.locator("[data-testid='annotation-card']")
        assert cards_p1.count() == 2
        assert cards_p2.count() == 2


class TestSyncEdgeCases:
    """Edge case tests for sync behavior."""

    def test_refresh_preserves_highlights(
        self, two_annotation_contexts
    ) -> None:
        """Refreshing one context preserves highlights from the other."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        _create_highlight(page1, 0, 1)

        # Wait for sync
        word_p2 = page2.locator("[data-word-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Refresh page2
        page2.reload()
        page2.wait_for_selector("[data-word-index]", timeout=10000)

        # Highlight should still be visible after reload
        word_p2_after = page2.locator("[data-word-index='0']")
        expect(word_p2_after).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

    def test_late_joiner_sees_existing_highlights(
        self, browser, app_server, two_annotation_contexts
    ) -> None:
        """A third context joining later sees existing highlights."""
        page1, page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        _create_highlight(page1, 0, 1)

        # Wait for save indicator
        saved = page1.locator("[data-testid='save-status']")
        expect(saved).to_contain_text("Saved", timeout=10000)

        # Open third context
        context3 = browser.new_context()
        page3 = context3.new_page()
        url = f"{app_server}/annotation?workspace_id={workspace_id}"
        page3.goto(url)
        page3.wait_for_selector("[data-word-index]", timeout=10000)

        try:
            # Late joiner should see existing highlight
            word_p3 = page3.locator("[data-word-index='0']")
            expect(word_p3).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

            # And see the annotation card
            ann_card_p3 = page3.locator("[data-testid='annotation-card']")
            expect(ann_card_p3).to_be_visible(timeout=5000)
        finally:
            context3.close()
```

**Step 2: Run all sync tests**

```bash
uv run pytest tests/e2e/test_annotation_sync.py -v --tb=short
```

Expected: All tests pass (should be 8+ tests).

**Step 3: Commit the new test file**

```bash
git add tests/e2e/conftest.py tests/e2e/test_annotation_sync.py
git commit -m "$(cat <<'EOF'
test: add annotation sync E2E tests with two-context fixture

Creates test_annotation_sync.py with tests for real-time CRDT
synchronization between independent browser contexts:

- TestHighlightSync: create/delete syncs bidirectionally
- TestCommentSync: comments appear in other context
- TestTagChangeSync: tag color changes sync
- TestConcurrentOperations: simultaneous edits both apply
- TestSyncEdgeCases: refresh preserves state, late joiner sees data

Adds two_annotation_contexts fixture to conftest.py that creates
separate browser contexts (not tabs) for realistic multi-client
simulation with independent cookie jars.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

---

## Phase Completion Checklist

- [ ] `two_annotation_contexts` fixture added to conftest.py
- [ ] `test_annotation_sync.py` created
- [ ] TestHighlightSync: 3 tests (create syncs, delete syncs, reverse direction)
- [ ] TestCommentSync: 1 test (comment appears in other context)
- [ ] TestTagChangeSync: 1 test (tag color syncs)
- [ ] TestConcurrentOperations: 1 test (concurrent highlights both appear)
- [ ] TestSyncEdgeCases: 2 tests (refresh preserves, late joiner)
- [ ] All tests pass: `uv run pytest tests/e2e/test_annotation_sync.py -v`
- [ ] Total sync test count: 8+ scenarios
