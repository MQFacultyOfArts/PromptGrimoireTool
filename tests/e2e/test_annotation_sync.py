"""End-to-end tests for real-time annotation synchronization.

Tests verify that highlights, comments, and presence indicators sync
between independent browser contexts viewing the same workspace.

Uses separate browser contexts (not tabs) to simulate genuinely
independent clients with different cookie jars.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/implementation-plans/2026-01-31-test-suite-consolidation/phase_03.md
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import create_highlight, select_words

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


class TestHighlightSync:
    """Tests for highlight creation/deletion syncing between contexts."""

    @pytestmark_db
    def test_highlight_created_in_context1_appears_in_context2(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Highlight created in one context appears in the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight in page1
        create_highlight(page1, 0, 1)

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

    @pytestmark_db
    def test_highlight_deleted_in_context1_disappears_in_context2(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Highlight deleted in one context disappears from the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight in page1
        create_highlight(page1, 0, 1)

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

    @pytestmark_db
    def test_highlight_created_in_context2_appears_in_context1(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Highlight created in context2 appears in context1 (reverse direction)."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight in page2
        create_highlight(page2, 2, 3)

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


class TestCommentSync:
    """Tests for comment syncing between contexts."""

    @pytestmark_db
    def test_comment_added_in_context1_appears_in_context2(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Comment added to highlight in one context appears in the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight in page1
        create_highlight(page1, 0, 1)

        # Wait for card to appear
        ann_card_p1 = page1.locator("[data-testid='annotation-card']")
        expect(ann_card_p1).to_be_visible()

        # Add comment in page1 (find input with placeholder, fill, click Post)
        comment_input = ann_card_p1.locator("input[placeholder*='comment']")
        expect(comment_input).to_be_visible()
        comment_input.fill("Test comment from context 1")
        post_btn = ann_card_p1.locator("button", has_text="Post")
        post_btn.click()

        # Verify comment appears locally first
        expect(ann_card_p1).to_contain_text("Test comment from context 1", timeout=5000)

        # Wait for sync and verify comment in page2's card
        ann_card_p2 = page2.locator("[data-testid='annotation-card']")
        expect(ann_card_p2).to_be_visible(timeout=10000)
        expect(ann_card_p2).to_contain_text(
            "Test comment from context 1", timeout=10000
        )


class TestTagChangeSync:
    """Tests for tag/color change syncing between contexts."""

    @pytestmark_db
    def test_tag_changed_in_context1_updates_in_context2(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Tag changed in one context updates highlight color in the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight with default tag in page1
        create_highlight(page1, 0, 1)

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


class TestConcurrentOperations:
    """Tests for handling concurrent operations from both contexts."""

    @pytestmark_db
    def test_concurrent_highlights_both_appear(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Highlights created simultaneously in both contexts both appear."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create different highlights in each context (non-overlapping words)
        select_words(page1, 0, 1)
        select_words(page2, 3, 4)

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

    @pytestmark_db
    def test_refresh_preserves_highlights(self, two_annotation_contexts: tuple) -> None:
        """Refreshing one context preserves highlights from the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        # Create highlight in page1
        create_highlight(page1, 0, 1)

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

    @pytestmark_db
    def test_late_joiner_sees_existing_highlights(
        self, browser, app_server: str, two_annotation_contexts: tuple
    ) -> None:
        """A third context joining later sees existing highlights."""
        page1, _page2, workspace_id = two_annotation_contexts

        # Create highlight in page1
        create_highlight(page1, 0, 1)

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
