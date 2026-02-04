"""E2E tests for highlight creation, mutation, interaction, and edge cases.

These tests verify the core highlight functionality: creating highlights by
selecting text, modifying highlights (delete, change tag), interacting with
highlights (goto, hover), and edge cases (overlapping, special characters).

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Test consolidation: docs/design-plans/2026-01-31-test-suite-consolidation.md

Why these tests exist:
- TestHighlightCreation: Verifies the fundamental annotation workflow - selecting
  text and creating a highlight. Without this, the entire product is non-functional.
- TestHighlightMutations: Verifies highlights can be modified after creation.
  Users need to correct mistakes or update their analysis.
- TestHighlightInteractions: Verifies UI features that help users navigate between
  highlights and their cards. Essential for usability with many annotations.
- TestEdgeCasesConsolidated: Verifies the system handles unusual inputs gracefully
  (overlapping highlights, special characters, keyboard shortcuts, empty content).

Consolidation note (Phase 2):
TestHighlightMutations, TestHighlightInteractions, and TestEdgeCasesConsolidated
use pytest-subtests to share expensive browser setup across related assertions.
This reduces test runtime while maintaining coverage. See test consolidation design.

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


class TestHighlightCreation:
    """Tests for creating highlights on documents.

    These tests verify the core annotation workflow: selecting text shows a
    highlight menu, clicking a tag creates a highlight with styling, and
    highlights persist after page reload.

    Invariants tested:
    - Selecting text shows highlight creation menu
    - Creating highlight applies background color styling to words
    - Highlights persist in CRDT state and survive page reload
    """

    @pytestmark_db
    def test_select_text_shows_highlight_menu(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Selecting text shows highlight creation menu.

        Regression guard: When users select text, they need a way to create a
        highlight. This tests that the tag toolbar becomes visible/active after
        text selection.
        """
        page = authenticated_page
        # Setup workspace with document
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Select some words here to highlight them")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-char-index]")

        # Wait for JavaScript to set up
        page.wait_for_timeout(200)

        # Select words using click + shift+click
        select_chars(page, 0, 2)

        # Tag toolbar should be visible
        tag_toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(tag_toolbar).to_be_visible()

    @pytestmark_db
    def test_create_highlight_applies_styling(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating highlight applies background color to selected words.

        Regression guard: Highlights must be visually distinguishable from
        unhighlighted text. This tests that clicking a tag button after
        selection applies CSS background-color to the word spans.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Highlight these words")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-char-index]")

        page.wait_for_timeout(200)

        # Select and highlight using click + shift+click
        create_highlight(page, 0, 1)

        # First word should have background color
        word = page.locator("[data-char-index='0']")
        expect(word).to_have_css(
            "background-color", re.compile(r"rgba?\("), timeout=5000
        )

    @pytestmark_db
    def test_highlight_persists_after_reload(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Highlights persist after page reload.

        Regression guard: Highlights are stored in CRDT state which is persisted
        to the database. This tests the full round-trip: create highlight ->
        save to DB -> reload page -> highlight still visible.

        Critical for user trust - losing annotations would be catastrophic.
        """
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))
        workspace_url = page.url

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Persistent highlight test")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-char-index]")

        page.wait_for_timeout(200)

        # Create highlight
        create_highlight(page, 0, 1)

        # Wait for save indicator
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload page
        page.goto(workspace_url)
        page.wait_for_selector("[data-char-index]")

        # Highlight should still be there
        word = page.locator("[data-char-index='0']")
        expect(word).to_have_css(
            "background-color", re.compile(r"rgba?\("), timeout=5000
        )


class TestHighlightMutations:
    """Consolidated tests for highlight mutation operations (delete, change tag).

    Uses subtests to share expensive workspace+document+highlight setup across
    related assertions. Each subtest verifies a different mutation operation.

    Invariants tested:
    - Changing tag via dropdown updates highlight color
    - Deleting highlight removes both the card and the word styling

    Why consolidated (Phase 2):
    Both mutations require the same setup: workspace + document + highlight + card.
    Running them as subtests shares this ~2s setup cost.

    Original tests (pre-consolidation):
    - TestDeleteHighlight.test_delete_highlight_removes_card_and_styling
    - TestChangeTagDropdown.test_change_tag_updates_highlight_color
    """

    @pytestmark_db
    def test_highlight_mutations(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test delete and tag change mutations with shared setup."""
        page = authenticated_page

        # Shared setup: workspace + document + highlight
        setup_workspace_with_content(page, app_server, "Mutation test words here")
        create_highlight(page, 0, 1)

        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()

        word = page.locator("[data-char-index='0']")

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
                "background-color",
                re.compile(r"rgba\(214,\s*39,\s*40"),
                timeout=5000,
            )

        # --- Subtest: delete highlight removes card and styling ---
        with subtests.test(msg="delete_removes_card_and_styling"):
            # Precondition: verify card exists before attempting delete
            expect(ann_card).to_be_visible()

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
                "background-color",
                re.compile(r"rgba\((?!0,\s*0,\s*0,\s*0)"),
                timeout=5000,
            )


class TestHighlightInteractions:
    """Consolidated tests for highlight interaction features (goto, hover).

    Uses subtests to share expensive workspace+document+highlight setup across
    related assertions. Each subtest verifies a different interaction feature.

    Invariants tested:
    - Goto button scrolls viewport to show the highlight
    - Hovering over card adds visual emphasis to highlighted words

    Why consolidated (Phase 2):
    Both interactions require the same setup: workspace + document + highlight +
    card + long content for scroll testing. Running them as subtests shares this
    ~3s setup cost.

    Original tests (pre-consolidation):
    - TestGoToHighlight.test_goto_button_scrolls_to_highlight
    - TestCardHoverEffect.test_hovering_card_highlights_words
    """

    @pytestmark_db
    def test_highlight_interactions(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test goto and hover interactions with shared setup."""
        page = authenticated_page

        # Need long content for scroll testing
        long_content = " ".join([f"word{i}" for i in range(100)])
        setup_workspace_with_content(page, app_server, long_content)

        # Scroll to end and create highlight there (for scroll testing)
        word_90 = page.locator("[data-char-index='90']")
        word_90.scroll_into_view_if_needed()
        select_chars(page, 90, 92)
        page.get_by_role(
            "button", name=re.compile("jurisdiction", re.IGNORECASE)
        ).click()
        page.wait_for_timeout(300)

        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_be_visible()

        # --- Subtest: goto button scrolls to highlight ---
        with subtests.test(msg="goto_scrolls_to_highlight"):
            # Scroll back to top first
            page.locator("[data-char-index='0']").scroll_into_view_if_needed()
            page.wait_for_timeout(200)

            # Click go-to button (icon has text "my_location")
            goto_btn = ann_card.locator("button").filter(has_text="my_location").first
            goto_btn.click()
            page.wait_for_timeout(500)

            # Word 90 should now be visible
            expect(word_90).to_be_in_viewport()

        # --- Subtest: hovering card highlights words ---
        with subtests.test(msg="hover_highlights_words"):
            # Ensure card is visible (scroll required per CLAUDE.md E2E guidelines)
            ann_card.scroll_into_view_if_needed()

            # Hover over card
            ann_card.hover()
            page.wait_for_timeout(100)

            # Words should have hover highlight class
            expect(word_90).to_have_class(
                re.compile("card-hover-highlight"), timeout=2000
            )


class TestEdgeCasesConsolidated:
    """Consolidated tests for edge cases (overlapping, special content, keyboard).

    Uses subtests to share browser context across related edge case assertions.
    Each subtest creates its own workspace since content requirements differ.

    Invariants tested:
    - Keyboard shortcuts (number keys) create highlights
    - Overlapping highlights display combined styling
    - Special characters in content are escaped and don't break highlighting
    - Empty content submission shows validation error

    Why consolidated (Phase 2):
    Edge cases don't share setup (each needs different content), but they share
    the browser context. Consolidating reduces browser startup overhead.

    Original tests (pre-consolidation):
    - TestKeyboardShortcuts.test_number_key_creates_highlight_with_tag
    - TestOverlappingHighlights.test_overlapping_highlights_show_combined_styling
    - TestSpecialContent.test_special_characters_in_content
    - TestSpecialContent.test_empty_content_shows_error
    """

    @pytestmark_db
    def test_edge_cases(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Test various edge cases with shared browser context."""
        page = authenticated_page

        # --- Subtest: keyboard shortcut creates highlight ---
        with subtests.test(msg="keyboard_shortcut_creates_highlight"):
            setup_workspace_with_content(page, app_server, "Keyboard shortcut test")

            # Select words
            select_chars(page, 0, 1)
            page.wait_for_timeout(300)

            # Press "1" key (Jurisdiction - blue)
            page.keyboard.press("1")
            page.wait_for_timeout(500)

            # Verify highlight created with jurisdiction color
            word = page.locator("[data-char-index='0']")
            expect(word).to_have_css(
                "background-color",
                re.compile(r"rgba\(31,\s*119,\s*180"),
                timeout=5000,
            )

            # Card should appear
            ann_card = page.locator("[data-testid='annotation-card']")
            expect(ann_card).to_be_visible()

        # --- Subtest: overlapping highlights show combined styling ---
        with subtests.test(msg="overlapping_highlights_combined_styling"):
            # Setup workspace with content for overlapping test
            setup_workspace_with_content(
                page, app_server, "word1 word2 word3 word4 word5"
            )

            # Create first highlight (words 1-3)
            select_chars(page, 1, 3)
            page.get_by_role(
                "button", name=re.compile("jurisdiction", re.IGNORECASE)
            ).click()

            # Wait for save
            saved_indicator = page.locator("[data-testid='save-status']")
            expect(saved_indicator).to_contain_text("Saved", timeout=10000)

            # Create second overlapping highlight (words 2-4)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            select_chars(page, 2, 4)
            page.get_by_role(
                "button", name=re.compile("legal.?issue", re.IGNORECASE)
            ).click()

            page.wait_for_timeout(500)
            expect(saved_indicator).to_contain_text("Saved", timeout=10000)

            # Middle words should have background color (overlap styling)
            word2 = page.locator("[data-char-index='2']")
            word3 = page.locator("[data-char-index='3']")
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
            special_content = "Test <script> & \"quotes\" 'apostrophe' $100 @email"
            setup_workspace_with_content(page, app_server, special_content)

            # Should have word spans (special chars escaped)
            word_spans = page.locator("[data-char-index]")
            assert word_spans.count() >= 5

            # Can create highlight
            create_highlight(page, 0, 2)
            ann_card = page.locator("[data-testid='annotation-card']")
            expect(ann_card).to_be_visible()

        # --- Subtest: empty content shows validation error ---
        with subtests.test(msg="empty_content_shows_error"):
            page.goto(f"{app_server}/annotation")
            page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
            page.wait_for_url(re.compile(r"workspace_id="))

            # Try to submit without content
            page.get_by_role(
                "button", name=re.compile("add|submit", re.IGNORECASE)
            ).click()

            # Should show error notification
            notification = page.locator(".q-notification, [role='alert']")
            expect(notification).to_be_visible(timeout=3000)
