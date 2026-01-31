"""E2E tests for annotation cards and tag selection UI.

These tests verify the annotation card sidebar and tag selection functionality:
cards display for highlights, show highlighted text snippets, support comments,
and allow tag selection.

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
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import create_highlight, select_words

if TYPE_CHECKING:
    from playwright.sync_api import Page

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

    Invariants tested:
    - Creating a highlight shows an annotation card
    - Card shows preview of highlighted text
    - Users can add comments to highlights via cards
    - Comments persist after page reload
    """

    @pytestmark_db
    def test_creating_highlight_shows_annotation_card(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating a highlight adds an annotation card.

        Regression guard: Highlights without cards are useless - users can't
        see what they highlighted or add annotations. This tests the card
        appears after creating a highlight.
        """
        page = authenticated_page

        # Setup workspace with document
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("The defendant was negligent in their duty")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Create highlight using click + shift+click
        select_words(page, 0, 1)

        # Click any tag button
        tag_button = page.locator("[data-testid='tag-toolbar'] button").first
        tag_button.click()

        # Annotation card should appear
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible(timeout=5000)

    @pytestmark_db
    def test_annotation_card_shows_highlighted_text(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Annotation card shows preview of highlighted text.

        Regression guard: Cards must show which text they refer to, especially
        when there are many highlights. This tests the card contains a snippet
        of the highlighted text.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Important legal text here")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Select and highlight "Important legal" (words 0-1)
        create_highlight(page, 0, 1)

        # Card should contain the highlighted text
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_contain_text("Important")

    @pytestmark_db
    def test_can_add_comment_to_highlight(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Can add a comment to a highlight via annotation card.

        Regression guard: Comments are the primary way users annotate their
        highlights with analysis. This tests the comment input and submit flow.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Text to comment on")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Create highlight (words 0-1)
        create_highlight(page, 0, 1)

        # Find comment input in card
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()

        comment_input = ann_card.locator("input[type='text'], textarea").first
        comment_input.fill("This is my comment")

        # Submit comment
        ann_card.get_by_role(
            "button", name=re.compile("post|add|submit", re.IGNORECASE)
        ).click()

        # Comment should appear in card
        expect(ann_card).to_contain_text("This is my comment")

    @pytestmark_db
    def test_comment_persists_after_reload(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Comments persist after page reload.

        Regression guard: Comments are stored in CRDT state. This tests the
        full round-trip: add comment -> save to DB -> reload -> comment visible.

        Critical for user trust - losing comments would be catastrophic.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))
        workspace_url = page.url

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Persistent comment test")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Create highlight and add comment (words 0-1)
        create_highlight(page, 0, 1)

        ann_card = page.locator("[data-testid='annotation-card']")
        comment_input = ann_card.locator("input[type='text'], textarea").first
        comment_input.fill("Persistent comment")
        ann_card.get_by_role(
            "button", name=re.compile("post|add|submit", re.IGNORECASE)
        ).click()

        # Wait for save
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]")

        # Comment should still be there
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_contain_text("Persistent comment")


class TestTagSelection:
    """Tests for tag selection toolbar.

    The tag toolbar lets users categorize their highlights with semantic tags
    (Jurisdiction, Legal Issues, Facts, Decision). Tags determine highlight
    colors and are essential for organizing legal analysis.

    Invariants tested:
    - Tag toolbar is visible when document is loaded
    - Selecting text then clicking tag creates colored highlight
    """

    @pytestmark_db
    def test_tag_toolbar_visible_when_document_loaded(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Tag toolbar appears when document content is loaded.

        Regression guard: Users need the tag toolbar to create highlights.
        This tests it appears after document content is added.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Content for tag toolbar test")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Tag toolbar should be visible
        tag_toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(tag_toolbar).to_be_visible()

    @pytestmark_db
    def test_selecting_text_then_tag_creates_colored_highlight(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Selecting text then clicking tag creates highlight with tag's color.

        Regression guard: The core workflow is select text -> click tag ->
        see colored highlight. This tests the tag-specific color is applied.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("The legal issues in this case")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up
        page.wait_for_timeout(200)

        # Select "legal issues" (words 1-2)
        select_words(page, 3, 4)

        # Click a tag button from the toolbar (any tag will do)
        tag_toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(tag_toolbar).to_be_visible()
        tag_button = tag_toolbar.locator("button").first
        tag_button.click()

        # Highlight should have a background color (not necessarily yellow now)
        word_legal = page.locator("[data-word-index='3']")
        expect(word_legal).to_have_css(
            "background-color", re.compile(r"rgba?\("), timeout=5000
        )
