"""End-to-end tests for real-time annotation synchronization.

Tests verify that highlights, comments, and presence indicators sync
between independent browser contexts viewing the same workspace.

Uses separate browser contexts (not tabs) to simulate genuinely
independent clients with different cookie jars.

Uses pytest-subtests to share two-context fixture across related assertions.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/implementation-plans/2026-01-31-test-suite-consolidation/phase_03.md

SKIPPED: Pending #106 HTML input redesign. Reimplement after #106.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.annotation_helpers import create_highlight, select_chars
from tests.e2e.conftest import _authenticate_page

# Skip all tests in this module pending #106 HTML input redesign
pytestmark = pytest.mark.skip(reason="Pending #106 HTML input redesign")

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestHighlightSync:
    """Tests for highlight creation/deletion syncing between contexts.

    Uses subtests to share the expensive two-context fixture across related
    highlight sync assertions.
    """

    @pytestmark_db
    def test_highlight_sync_bidirectional(
        self, subtests, two_annotation_contexts: tuple
    ) -> None:
        """Highlights sync bidirectionally between contexts."""
        page1, page2, _workspace_id = two_annotation_contexts

        # --- Subtest: highlight created in context1 appears in context2 ---
        with subtests.test(msg="context1_to_context2"):
            create_highlight(page1, 0, 1)

            word_p1 = page1.locator("[data-char-index='0']")
            expect(word_p1).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=5000
            )

            word_p2 = page2.locator("[data-char-index='0']")
            expect(word_p2).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

        # --- Subtest: highlight created in context2 appears in context1 ---
        with subtests.test(msg="context2_to_context1"):
            create_highlight(page2, 2, 3)

            word_p2 = page2.locator("[data-char-index='2']")
            expect(word_p2).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=5000
            )

            word_p1 = page1.locator("[data-char-index='2']")
            expect(word_p1).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

    @pytestmark_db
    def test_highlight_deletion_syncs(self, two_annotation_contexts: tuple) -> None:
        """Highlight deleted in one context disappears from the other.

        Separate test because deletion changes state significantly.
        """
        page1, page2, _workspace_id = two_annotation_contexts

        create_highlight(page1, 0, 1)

        word_p2 = page2.locator("[data-char-index='0']")
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

        expect(word_p2).not_to_have_css(
            "background-color",
            re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"),
            timeout=10000,
        )


class TestCommentSync:
    """Tests for comment syncing between contexts."""

    @pytestmark_db
    def test_comment_added_in_context1_appears_in_context2(
        self, two_annotation_contexts: tuple
    ) -> None:
        """Comment added to highlight in one context appears in the other."""
        page1, page2, _workspace_id = two_annotation_contexts

        create_highlight(page1, 0, 1)

        ann_card_p1 = page1.locator("[data-testid='annotation-card']")
        expect(ann_card_p1).to_be_visible()

        comment_input = ann_card_p1.locator("input[placeholder*='comment']")
        expect(comment_input).to_be_visible()
        comment_input.fill("Test comment from context 1")
        post_btn = ann_card_p1.locator("button", has_text="Post")
        post_btn.click()

        expect(ann_card_p1).to_contain_text("Test comment from context 1", timeout=5000)

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

        create_highlight(page1, 0, 1)

        word_p2 = page2.locator("[data-char-index='0']")
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

        select_chars(page1, 0, 1)
        select_chars(page2, 3, 4)

        tag_btn_p1 = page1.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p2 = page2.locator("[data-testid='tag-toolbar'] button").first
        tag_btn_p1.click()
        tag_btn_p2.click()

        page1.wait_for_timeout(2000)

        # Both contexts should have both highlights
        for page in [page1, page2]:
            word0 = page.locator("[data-char-index='0']")
            word3 = page.locator("[data-char-index='3']")
            expect(word0).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )
            expect(word3).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

        # Both should have 2 annotation cards
        cards_p1 = page1.locator("[data-testid='annotation-card']")
        cards_p2 = page2.locator("[data-testid='annotation-card']")
        expect(cards_p1).to_have_count(2, timeout=5000)
        expect(cards_p2).to_have_count(2, timeout=5000)


class TestSyncEdgeCases:
    """Edge case tests for sync behavior.

    Uses subtests to share fixture across edge case assertions.
    """

    @pytestmark_db
    def test_sync_edge_cases(
        self, subtests, browser, app_server: str, two_annotation_contexts: tuple
    ) -> None:
        """Sync edge cases: refresh preserves, late joiner sees highlights."""
        page1, page2, workspace_id = two_annotation_contexts

        create_highlight(page1, 0, 1)

        word_p2 = page2.locator("[data-char-index='0']")
        expect(word_p2).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=10000
        )

        # --- Subtest: refresh preserves highlights ---
        with subtests.test(msg="refresh_preserves"):
            page2.reload()
            page2.wait_for_selector("[data-char-index]", timeout=10000)

            word_p2_after = page2.locator("[data-char-index='0']")
            expect(word_p2_after).to_have_css(
                "background-color", re.compile(r"rgba\("), timeout=10000
            )

        # Wait for save indicator
        saved = page1.locator("[data-testid='save-status']")
        expect(saved).to_contain_text("Saved", timeout=10000)

        # --- Subtest: late joiner sees existing highlights ---
        with subtests.test(msg="late_joiner_sees"):
            context3 = browser.new_context()
            page3 = context3.new_page()

            _authenticate_page(page3, app_server)

            url = f"{app_server}/annotation?workspace_id={workspace_id}"
            page3.goto(url)
            page3.wait_for_selector("[data-char-index]", timeout=10000)

            try:
                word_p3 = page3.locator("[data-char-index='0']")
                expect(word_p3).to_have_css(
                    "background-color", re.compile(r"rgba\("), timeout=10000
                )

                ann_card_p3 = page3.locator("[data-testid='annotation-card']")
                expect(ann_card_p3).to_be_visible(timeout=5000)
            finally:
                context3.close()
