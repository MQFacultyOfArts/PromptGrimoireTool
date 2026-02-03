"""End-to-end tests for multi-user collaboration features.

Tests verify that multiple authenticated users can collaborate on the
same workspace, see each other's contributions, and have proper
presence indicators.

Uses separate authenticated browser contexts with distinct user
identities.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/implementation-plans/2026-01-31-test-suite-consolidation/phase_04.md
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import create_highlight, select_chars

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


class TestMultiUserHighlights:
    """Tests for multi-user highlight visibility."""

    @pytestmark_db
    def test_two_users_see_each_others_highlights(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """Highlights created by each user are visible to both."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # User 1 creates highlight on words 0-1
        create_highlight(page1, 0, 1)

        # Wait for sync to user 2
        word0_p2 = page2.locator("[data-char-index='0']")
        expect(word0_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # User 2 creates highlight on words 3-4
        create_highlight(page2, 3, 4)

        # Wait for sync to user 1
        word3_p1 = page1.locator("[data-char-index='3']")
        expect(word3_p1).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # Both should have 2 cards
        cards_p1 = page1.locator("[data-testid='annotation-card']")
        cards_p2 = page2.locator("[data-testid='annotation-card']")
        expect(cards_p1).to_have_count(2, timeout=5000)
        expect(cards_p2).to_have_count(2, timeout=5000)

    @pytestmark_db
    def test_highlight_deletion_by_creator_syncs(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """User who created highlight can delete it and deletion syncs."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # User 1 creates highlight
        create_highlight(page1, 0, 1)

        # Wait for sync to user 2
        word_p2 = page2.locator("[data-char-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # User 1 deletes highlight
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

        # Deletion should sync to user 2
        expect(word_p2).not_to_have_css(
            "background-color",
            re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"),
            timeout=10000,
        )


class TestUserCountBadge:
    """Tests for user count badge showing connected clients."""

    @pytestmark_db
    def test_user_count_shows_two_when_both_connected(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """User count badge shows 2 when both users are connected."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # Both should see user count of 2
        # WebSocket broadcasts need time to propagate - check both with adequate timeout
        badge_p1 = page1.locator("[data-testid='user-count']")
        badge_p2 = page2.locator("[data-testid='user-count']")

        # Wait for page1 to see both users (page2's join has been broadcast)
        expect(badge_p1).to_contain_text("2", timeout=10000)
        # page2 should also see 2 (its own connection + page1)
        expect(badge_p2).to_contain_text("2", timeout=10000)

    @pytestmark_db
    def test_user_count_updates_when_user_leaves(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """User count decrements when a user disconnects."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # Initially both see 2
        badge_p1 = page1.locator("[data-testid='user-count']")
        expect(badge_p1).to_contain_text("2", timeout=5000)

        # Close page2's context
        page2.context.close()

        # Page1 should eventually show 1
        expect(badge_p1).to_contain_text("1", timeout=10000)


class TestConcurrentCollaboration:
    """Tests for concurrent editing by multiple users."""

    @pytestmark_db
    def test_concurrent_edits_both_preserved(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """Concurrent edits by both users are both preserved."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # Both users select different words simultaneously
        select_chars(page1, 0, 0)
        select_chars(page2, 4, 4)

        # Both click tag buttons
        tag_btn_p1 = page1.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p2 = page2.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p1.click()
        tag_btn_p2.click()

        # Allow sync time
        page1.wait_for_timeout(2000)

        # Both words should be highlighted in both views
        for page in [page1, page2]:
            word0 = page.locator("[data-char-index='0']")
            word4 = page.locator("[data-char-index='4']")
            expect(word0).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )
            expect(word4).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

    @pytestmark_db
    def test_comment_thread_from_both_users(
        self, two_authenticated_contexts: tuple
    ) -> None:
        """Both users can add comments to the same highlight."""
        page1, page2, _workspace_id, _user1, _user2 = two_authenticated_contexts

        # User 1 creates highlight
        create_highlight(page1, 0, 1)

        # Wait for card to appear and get the highlight ID for stable querying
        ann_card_p1 = page1.locator("[data-testid='annotation-card']")
        expect(ann_card_p1).to_be_visible(timeout=10000)

        # Wait for card to sync to user 2
        ann_card_p2 = page2.locator("[data-testid='annotation-card']")
        expect(ann_card_p2).to_be_visible(timeout=10000)

        # User 1 adds comment
        comment_input_p1 = ann_card_p1.locator("input[placeholder*='comment']")
        expect(comment_input_p1).to_be_visible()
        comment_input_p1.fill("Comment from user 1")
        post_btn_p1 = ann_card_p1.locator("button", has_text="Post")
        post_btn_p1.click()

        # Wait for comment to appear in user 1's own view first (confirms post worked)
        expect(ann_card_p1).to_contain_text("Comment from user 1", timeout=10000)

        # Wait for comment to sync to user 2
        expect(ann_card_p2).to_contain_text("Comment from user 1", timeout=10000)

        # User 2 adds reply - re-query to get fresh element
        comment_input_p2 = page2.locator(
            "[data-testid='annotation-card'] input[placeholder*='comment']"
        )
        expect(comment_input_p2).to_be_visible()
        comment_input_p2.fill("Reply from user 2")
        post_btn_p2 = page2.locator(
            "[data-testid='annotation-card'] button", has_text="Post"
        )
        post_btn_p2.click()

        # Wait for user 2's comment to appear in their own view first
        expect(page2.locator("[data-testid='annotation-card']")).to_contain_text(
            "Reply from user 2", timeout=10000
        )

        # Both comments should be visible in user 1's view
        expect(page1.locator("[data-testid='annotation-card']")).to_contain_text(
            "Reply from user 2", timeout=10000
        )
