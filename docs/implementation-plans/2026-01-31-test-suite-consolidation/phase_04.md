# Test Suite Consolidation - Phase 4: Create test_annotation_collab.py

**Goal:** Multi-user collaboration tests with separate authenticated users

**Architecture:** New test file extending two-context fixture with distinct user identities

**Tech Stack:** pytest, pytest-subtests, Playwright

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-01-31

---

## Phase Overview

Create `test_annotation_collab.py` for multi-user collaboration scenarios where two distinct authenticated users interact with the same workspace. Unlike Phase 3 (sync tests), these tests verify user identity, presence indicators, and collaboration UX.

**Dependency:** User count badge (Issue #11) should be implemented for full coverage. Tests that require the badge will be marked with `pytest.mark.skip` until that feature exists.

**Key scenarios:**
- Two users see each other's highlights with attribution
- User count badge shows connected users
- Concurrent editing with user attribution
- User presence indicators

---

<!-- START_TASK_1 -->
### Task 1: Add two_authenticated_contexts fixture

**Files:**
- Modify: `tests/e2e/conftest.py`

**Step 1: Add multi-user context fixture**

Add after `two_annotation_contexts` fixture:

```python
@pytest.fixture
def two_authenticated_contexts(browser, app_server, request):
    """Two separate browser contexts with distinct authenticated users.

    Unlike two_annotation_contexts which uses anonymous contexts,
    this fixture creates contexts with different authenticated identities
    to test user-specific features like attribution and presence.

    Yields:
        tuple: (page1, page2, workspace_id, user1_email, user2_email)
    """
    import asyncio

    # Create workspace with test content
    content = "Collaboration test word1 word2 word3 word4 word5"
    loop = asyncio.new_event_loop()
    workspace_id = loop.run_until_complete(_create_test_workspace_with_content(content))
    loop.close()

    user1_email = f"collab_user1_{uuid4().hex[:8]}@test.edu.au"
    user2_email = f"collab_user2_{uuid4().hex[:8]}@test.edu.au"

    # Create contexts with mock auth cookies
    context1 = browser.new_context()
    context2 = browser.new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()

    # Set auth for each user (mock Stytch token)
    # The mock auth middleware reads this cookie
    context1.add_cookies([{
        "name": "stytch_session",
        "value": f"mock_session_{user1_email}",
        "domain": "localhost",
        "path": "/",
    }])
    context2.add_cookies([{
        "name": "stytch_session",
        "value": f"mock_session_{user2_email}",
        "domain": "localhost",
        "path": "/",
    }])

    # Navigate both to the workspace
    url = f"{app_server}/annotation?workspace_id={workspace_id}"
    page1.goto(url)
    page2.goto(url)

    # Wait for both to load word spans
    page1.wait_for_selector("[data-word-index]", timeout=10000)
    page2.wait_for_selector("[data-word-index]", timeout=10000)

    yield page1, page2, workspace_id, user1_email, user2_email

    context1.close()
    context2.close()
```

**Step 2: Verify fixture loads**

```bash
uv run pytest --co tests/e2e/ -q 2>&1 | head -20
```

Expected: Collection succeeds.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create test_annotation_collab.py with user visibility tests

**Files:**
- Create: `tests/e2e/test_annotation_collab.py`

**Step 1: Create the new test file**

```python
"""End-to-end tests for multi-user collaboration features.

Tests verify that multiple authenticated users can collaborate on the
same workspace, see each other's contributions, and have proper
presence indicators.

Uses separate authenticated browser contexts with distinct user
identities.
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


class TestMultiUserHighlights:
    """Tests for multi-user highlight visibility."""

    def test_two_users_see_each_others_highlights(
        self, two_authenticated_contexts
    ) -> None:
        """Highlights created by each user are visible to both."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # User 1 creates highlight on words 0-1
        _create_highlight(page1, 0, 1)

        # Wait for sync
        word0_p2 = page2.locator("[data-word-index='0']")
        expect(word0_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # User 2 creates highlight on words 3-4
        _create_highlight(page2, 3, 4)

        # Wait for sync
        word3_p1 = page1.locator("[data-word-index='3']")
        expect(word3_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Both should have 2 cards
        cards_p1 = page1.locator("[data-testid='annotation-card']")
        cards_p2 = page2.locator("[data-testid='annotation-card']")
        assert cards_p1.count() == 2
        assert cards_p2.count() == 2

    def test_highlight_deletion_by_creator_syncs(
        self, two_authenticated_contexts
    ) -> None:
        """User who created highlight can delete it and deletion syncs."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # User 1 creates highlight
        _create_highlight(page1, 0, 1)

        # Wait for sync to user 2
        word_p2 = page2.locator("[data-word-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # User 1 deletes highlight
        ann_card = page1.locator("[data-testid='annotation-card']")
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

        # Deletion should sync to user 2
        expect(word_p2).not_to_have_css(
            "background-color", re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"), timeout=10000
        )


class TestUserCountBadge:
    """Tests for user count badge showing connected clients.

    These tests require the user count badge feature (Issue #11).
    """

    @pytest.mark.skip(reason="Requires user count badge feature - Issue #11")
    def test_user_count_shows_two_when_both_connected(
        self, two_authenticated_contexts
    ) -> None:
        """User count badge shows 2 when both users are connected."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # Both should see user count of 2
        badge_p1 = page1.locator("[data-testid='user-count-badge']")
        badge_p2 = page2.locator("[data-testid='user-count-badge']")

        expect(badge_p1).to_contain_text("2", timeout=5000)
        expect(badge_p2).to_contain_text("2", timeout=5000)

    @pytest.mark.skip(reason="Requires user count badge feature - Issue #11")
    def test_user_count_updates_when_user_leaves(
        self, browser, app_server, two_authenticated_contexts
    ) -> None:
        """User count decrements when a user disconnects."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # Initially both see 2
        badge_p1 = page1.locator("[data-testid='user-count-badge']")
        expect(badge_p1).to_contain_text("2", timeout=5000)

        # Close page2's context
        page2.context.close()

        # Page1 should eventually show 1
        expect(badge_p1).to_contain_text("1", timeout=10000)


class TestConcurrentCollaboration:
    """Tests for concurrent editing by multiple users."""

    def test_concurrent_edits_both_preserved(
        self, two_authenticated_contexts
    ) -> None:
        """Concurrent edits by both users are both preserved."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # Both users select different words simultaneously
        _select_words(page1, 0, 0)
        _select_words(page2, 4, 4)

        # Both click tag buttons
        tag_btn_p1 = page1.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p2 = page2.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p1.click()
        tag_btn_p2.click()

        # Allow sync time
        page1.wait_for_timeout(2000)

        # Both words should be highlighted in both views
        for page in [page1, page2]:
            word0 = page.locator("[data-word-index='0']")
            word4 = page.locator("[data-word-index='4']")
            expect(word0).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )
            expect(word4).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

    def test_comment_thread_from_both_users(
        self, two_authenticated_contexts
    ) -> None:
        """Both users can add comments to the same highlight."""
        page1, page2, workspace_id, user1, user2 = two_authenticated_contexts

        # User 1 creates highlight
        _create_highlight(page1, 0, 1)

        # Wait for card to sync to user 2
        ann_card_p2 = page2.locator("[data-testid='annotation-card']")
        expect(ann_card_p2).to_be_visible(timeout=10000)

        # User 1 adds comment
        ann_card_p1 = page1.locator("[data-testid='annotation-card']")
        comment_input_p1 = ann_card_p1.locator("textarea, input[type='text']").first
        comment_input_p1.fill("Comment from user 1")
        comment_input_p1.press("Enter")

        # Wait for comment to sync
        expect(ann_card_p2).to_contain_text("Comment from user 1", timeout=10000)

        # User 2 adds comment
        comment_input_p2 = ann_card_p2.locator("textarea, input[type='text']").first
        comment_input_p2.fill("Reply from user 2")
        comment_input_p2.press("Enter")

        # Both comments should be visible in user 1's view
        expect(ann_card_p1).to_contain_text("Reply from user 2", timeout=10000)
```

**Step 2: Run the tests**

```bash
uv run pytest tests/e2e/test_annotation_collab.py -v --tb=short
```

Expected: Tests pass (skipped tests show skip reason).

**Step 3: Commit the collaboration tests**

```bash
git add tests/e2e/conftest.py tests/e2e/test_annotation_collab.py
git commit -m "$(cat <<'EOF'
test: add multi-user collaboration E2E tests

Creates test_annotation_collab.py with tests for multi-user
collaboration scenarios:

- TestMultiUserHighlights: users see each other's highlights, deletion syncs
- TestUserCountBadge: badge tests (skipped until Issue #11)
- TestConcurrentCollaboration: concurrent edits preserved, comment threads

Adds two_authenticated_contexts fixture for testing with distinct
user identities (separate auth cookies per context).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

---

## Phase Completion Checklist

- [ ] `two_authenticated_contexts` fixture added to conftest.py
- [ ] `test_annotation_collab.py` created
- [ ] TestMultiUserHighlights: 2 tests (see each other's highlights, deletion syncs)
- [ ] TestUserCountBadge: 2 tests (skipped, pending Issue #11)
- [ ] TestConcurrentCollaboration: 2 tests (concurrent edits, comment threads)
- [ ] All non-skipped tests pass: `uv run pytest tests/e2e/test_annotation_collab.py -v`
- [ ] Skipped tests documented with Issue #11 reference
