"""E2E tests for annotation cards and tag selection UI.

These tests verify the annotation card sidebar and tag selection functionality:
cards display for highlights, show highlighted text snippets, support comments,
and allow tag selection.

Uses pytest-subtests to share expensive workspace setup across related assertions.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md

Why these tests exist:
- TestAnnotationCards: Verifies the card UI that lets users view and interact
  with their highlights. Cards show text snippets, allow comments, and persist.
  Without cards, users can't review or annotate their highlights.
- TestTagSelection: Verifies the tag toolbar that lets users categorize their
  highlights. Tags are essential for organizing legal analysis (jurisdiction,
  issues, facts, decisions).

SKIPPED: Pending #106 HTML input redesign. Reimplement after #106.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight,
    select_chars,
    setup_workspace_with_content,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip all tests in this module pending #106 HTML input redesign
pytestmark = pytest.mark.skip(reason="Pending #106 HTML input redesign")

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


class TestAnnotationCards:
    """Tests for annotation card sidebar.

    Annotation cards provide the UI for viewing and interacting with highlights.
    Each highlight gets a card showing the highlighted text snippet and allowing
    users to add comments.

    Uses subtests to share workspace+document setup across card-related tests.

    Invariants tested:
    - Creating a highlight shows an annotation card
    - Card shows preview of highlighted text
    - Users can add comments to highlights via cards
    - Comments persist after page reload
    """

    @pytestmark_db
    def test_annotation_card_behaviour(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Annotation card appearance, content display, and comment functionality."""
        page = authenticated_page

        # Setup workspace with document
        setup_workspace_with_content(page, app_server, "The defendant was negligent")

        # Create highlight on "The" (chars 0-2: T=0, h=1, e=2)
        create_highlight(page, 0, 2)

        ann_card = page.locator("[data-testid='annotation-card']")

        # --- Subtest: creating highlight shows annotation card ---
        with subtests.test(msg="highlight_shows_card"):
            expect(ann_card).to_be_visible(timeout=5000)

        # --- Subtest: card shows highlighted text preview ---
        with subtests.test(msg="card_shows_text_preview"):
            expect(ann_card).to_contain_text("The")

        # --- Subtest: can add comment to highlight ---
        with subtests.test(msg="can_add_comment"):
            comment_input = ann_card.locator("input[placeholder*='comment']")
            expect(comment_input).to_be_visible()
            comment_input.fill("This is my comment")
            ann_card.get_by_role(
                "button", name=re.compile("post", re.IGNORECASE)
            ).click()
            expect(ann_card).to_contain_text("This is my comment", timeout=5000)

    @pytestmark_db
    def test_comment_persistence(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Comments persist after page reload.

        Separate test because it requires reload which would break subtest state.
        """
        page = authenticated_page

        # Setup workspace
        setup_workspace_with_content(page, app_server, "Persistent comment test")
        workspace_url = page.url

        # Create highlight on "Persistent" (chars 0-9)
        create_highlight(page, 0, 9)

        ann_card = page.locator("[data-testid='annotation-card']")
        comment_input = ann_card.locator("input[placeholder*='comment']")
        comment_input.fill("Persistent comment")
        ann_card.get_by_role("button", name=re.compile("post", re.IGNORECASE)).click()

        # Wait for save
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-char-index]")

        # Comment should still be there
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_contain_text("Persistent comment")


class TestTagSelection:
    """Tests for tag selection toolbar.

    The tag toolbar lets users categorize their highlights with semantic tags
    (Jurisdiction, Legal Issues, Facts, Decision). Tags determine highlight
    colors and are essential for organizing legal analysis.

    Uses subtests to share workspace setup across tag-related tests.

    Invariants tested:
    - Tag toolbar is visible when document is loaded
    - Selecting text then clicking tag creates colored highlight
    """

    @pytestmark_db
    def test_tag_toolbar_and_highlight_creation(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Tag toolbar visibility and highlight creation via tags."""
        page = authenticated_page

        # Setup workspace with document
        setup_workspace_with_content(page, app_server, "The legal issues in this case")

        tag_toolbar = page.locator("[data-testid='tag-toolbar']")

        # --- Subtest: tag toolbar visible when document loaded ---
        with subtests.test(msg="tag_toolbar_visible"):
            expect(tag_toolbar).to_be_visible()

        # --- Subtest: selecting text then tag creates colored highlight ---
        with subtests.test(msg="tag_creates_colored_highlight"):
            # Select "legal" (chars 4-8 in "The legal issues in this case")
            select_chars(page, 4, 8)
            tag_toolbar.locator("button").first.click()

            word = page.locator("[data-char-index='4']")
            expect(word).to_have_css(
                "background-color", re.compile(r"rgba?\("), timeout=5000
            )
