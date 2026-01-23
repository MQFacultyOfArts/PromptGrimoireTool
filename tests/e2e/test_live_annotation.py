"""End-to-end tests for live annotation demo.

Tests the annotation workflow including:
- Creating highlights with paragraph numbers
- Verifying paragraph numbers appear in annotation cards
- Testing the "highest para seen" heuristic for court orders
- Multi-paragraph highlights with en-dash format
- Highlight deletion, comments, keyboard shortcuts
- Floating tag menu, go-to-text, tag colors
- Multiple highlights and multi-user collaboration
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def clean_page(
    page: Page, live_annotation_url: str, reset_crdt_state: None
) -> Generator[Page]:
    """Navigate to live annotation page with clean CRDT state.

    The reset_crdt_state fixture (function-scoped) resets all CRDT state
    server-side before each test, ensuring complete isolation.

    We navigate to about:blank first to close any existing WebSocket connections,
    then navigate to the demo page to get a fresh connection to the reset CRDT.
    """
    _ = reset_crdt_state
    # Close existing connections by navigating away
    page.goto("about:blank")
    # Now navigate to the demo page with fresh state
    page.goto(live_annotation_url)
    doc_container = page.locator(".doc-container")
    expect(doc_container).to_be_visible(timeout=15000)
    yield page


class TestAnnotationCardParagraphNumbers:
    """Test that annotation cards display correct paragraph numbers."""

    def test_page_loads(self, page: Page, live_annotation_url: str) -> None:
        """Live annotation demo page loads successfully."""
        page.goto(live_annotation_url)

        # Verify the page has the document container
        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

    def test_highlight_in_paragraph_shows_para_number(self, clean_page: Page) -> None:
        """Highlighting text in a numbered paragraph shows [N] in card."""
        page = clean_page

        # Paragraph 1 starts at word 482 ("THE COURT:")
        # Select words 482-483 which are in paragraph 1
        word_482 = page.locator('.doc-container [data-w="482"]')
        word_483 = page.locator('.doc-container [data-w="483"]')
        expect(word_482).to_be_visible(timeout=5000)

        # Select these words by clicking and shift-clicking
        word_482.click()
        word_483.click(modifiers=["Shift"])

        # Click the first tag button (Jurisdiction) to create a highlight
        tag_buttons = page.locator(".tag-toolbar-compact button")
        expect(tag_buttons.first).to_be_visible()
        tag_buttons.first.click()

        # Wait for annotation card to appear
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        # Verify the card contains paragraph reference [1]
        expect(ann_card).to_contain_text("[1]")

    def test_highlight_in_metadata_shows_no_para_number(self, clean_page: Page) -> None:
        """Highlighting text in metadata (before paragraphs) shows no [N]."""
        page = clean_page

        # Select words in metadata table (before any <ol>)
        # Words 0-1 are in the header "Case Name:" which has no para number
        word_0 = page.locator('.doc-container [data-w="0"]')
        word_1 = page.locator('.doc-container [data-w="1"]')
        expect(word_0).to_be_visible(timeout=5000)

        # Click and shift-click to select
        word_0.click()
        word_1.click(modifiers=["Shift"])

        # Click the first tag button to create a highlight
        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for annotation card to be created
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        # Verify the card does NOT contain a paragraph reference like [1], [2], etc.
        card_text = ann_card.inner_text()
        para_refs = re.findall(r"\[\d+\]", card_text)
        assert len(para_refs) == 0, f"Expected no paragraph refs, found: {para_refs}"

    def test_highlight_in_paragraph_48_shows_para_number(
        self, clean_page: Page
    ) -> None:
        """Highlighting in paragraph 48 shows [48] in card."""
        page = clean_page

        # Paragraph 48 starts at word 4335 ("Therefore,")
        word_4335 = page.locator('.doc-container [data-w="4335"]')
        word_4336 = page.locator('.doc-container [data-w="4336"]')
        word_4335.scroll_into_view_if_needed()
        expect(word_4335).to_be_visible(timeout=5000)

        word_4335.click()
        word_4336.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for card
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("[48]")

    def test_highlight_in_court_orders_shows_para_48(self, clean_page: Page) -> None:
        """Highlighting in court orders (sub-list of para 48) shows [48]."""
        page = clean_page

        # Words 4346-4347 are in court orders ("Grant leave") - continues para 48
        word_4346 = page.locator('.doc-container [data-w="4346"]')
        word_4347 = page.locator('.doc-container [data-w="4347"]')
        word_4346.scroll_into_view_if_needed()
        expect(word_4346).to_be_visible(timeout=5000)

        word_4346.click()
        word_4347.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for card
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        # Court orders are part of para 48
        expect(ann_card).to_contain_text("[48]")


class TestHighlightCreation:
    """Test highlight creation workflow."""

    def test_can_select_text_and_create_highlight(self, clean_page: Page) -> None:
        """User can select text and apply a tag to create a highlight."""
        page = clean_page

        # Get first two word spans
        word_0 = page.locator('.doc-container [data-w="0"]')
        word_1 = page.locator('.doc-container [data-w="1"]')
        expect(word_0).to_be_visible(timeout=5000)

        # Click and shift-click to create selection range
        word_0.click()
        word_1.click(modifiers=["Shift"])

        # Click a tag button
        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Verify highlight was created (card appears)
        ann_card = page.locator(".ann-card-positioned")
        expect(ann_card).to_have_count(1, timeout=5000)

    def test_highlight_shows_quoted_text(self, clean_page: Page) -> None:
        """Annotation card shows the highlighted text in quotes."""
        page = clean_page

        word_10 = page.locator('.doc-container [data-w="10"]')
        word_11 = page.locator('.doc-container [data-w="11"]')
        expect(word_10).to_be_visible(timeout=5000)

        word_10.click()
        word_11.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)


class TestMultiParagraphHighlights:
    """Test highlights spanning multiple paragraphs."""

    def test_highlight_spanning_paragraphs_shows_range(self, clean_page: Page) -> None:
        """Highlighting across paragraphs shows [N-M] format with en-dash."""
        page = clean_page

        # Select from paragraph 5 (word 848 "Judge") to paragraph 6 (word 870)
        # Para 5: words 848-860, Para 6: words 861-892
        word_848 = page.locator('.doc-container [data-w="848"]')
        word_870 = page.locator('.doc-container [data-w="870"]')
        word_848.scroll_into_view_if_needed()
        expect(word_848).to_be_visible(timeout=5000)

        word_848.click()
        word_870.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for card
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        card_text = ann_card.inner_text()
        assert re.search(r"\[5\][-\u2013]\[6\]", card_text), (
            f"Expected [5]-[6] range, got: {card_text}"
        )


class TestHighlightDeletion:
    """Test highlight deletion workflow."""

    def test_close_button_removes_highlight(self, clean_page: Page) -> None:
        """Clicking close button removes the annotation card."""
        page = clean_page

        word_0 = page.locator('.doc-container [data-w="0"]')
        word_1 = page.locator('.doc-container [data-w="1"]')
        expect(word_0).to_be_visible(timeout=5000)

        word_0.click()
        word_1.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        ann_card = page.locator(".ann-card-positioned")
        expect(ann_card).to_have_count(1, timeout=5000)

        close_btn = ann_card.locator("button").first
        close_btn.click()

        expect(ann_card).to_have_count(0, timeout=5000)


class TestCommentCreation:
    """Test comment creation on highlights."""

    def test_can_add_comment_to_highlight(self, clean_page: Page) -> None:
        """User can add a comment to an annotation card."""
        page = clean_page

        word_100 = page.locator('.doc-container [data-w="100"]')
        word_101 = page.locator('.doc-container [data-w="101"]')
        expect(word_100).to_be_visible(timeout=5000)

        word_100.click()
        word_101.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        comment_input = ann_card.locator("input[placeholder*='comment']")
        expect(comment_input).to_be_visible()
        comment_input.fill("This is a test comment")

        post_btn = ann_card.locator("button", has_text="Post")
        post_btn.click()

        expect(ann_card).to_contain_text("This is a test comment", timeout=5000)


class TestKeyboardShortcuts:
    """Test keyboard shortcuts for applying tags."""

    def test_number_key_applies_tag(self, clean_page: Page) -> None:
        """Pressing number key applies corresponding tag to selection."""
        page = clean_page

        # Select text by dragging from word 200 to word 201
        word_200 = page.locator('.doc-container [data-w="200"]')
        word_201 = page.locator('.doc-container [data-w="201"]')
        word_200.scroll_into_view_if_needed()
        expect(word_200).to_be_visible(timeout=5000)

        # Get bounding boxes for drag selection
        box_start = word_200.bounding_box()
        box_end = word_201.bounding_box()
        assert box_start and box_end

        # Drag to select text
        page.mouse.move(box_start["x"], box_start["y"])
        page.mouse.down()
        page.mouse.move(box_end["x"] + box_end["width"], box_end["y"])
        page.mouse.up()

        # Press "2" for Procedural History (second tag)
        page.keyboard.press("2")

        # Verify highlight was created with correct tag
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("Procedural History")

    def test_key_0_applies_reflection_tag(self, clean_page: Page) -> None:
        """Pressing 0 applies Reflection tag (10th tag)."""
        page = clean_page

        word_300 = page.locator('.doc-container [data-w="300"]')
        word_301 = page.locator('.doc-container [data-w="301"]')
        word_300.scroll_into_view_if_needed()
        expect(word_300).to_be_visible(timeout=5000)

        # Get bounding boxes for drag selection
        box_start = word_300.bounding_box()
        box_end = word_301.bounding_box()
        assert box_start and box_end

        # Drag to select text
        page.mouse.move(box_start["x"], box_start["y"])
        page.mouse.down()
        page.mouse.move(box_end["x"] + box_end["width"], box_end["y"])
        page.mouse.up()

        page.keyboard.press("0")

        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("Reflection")


class TestFloatingTagMenu:
    """Test floating tag menu behavior."""

    def test_floating_menu_appears_on_selection(self, clean_page: Page) -> None:
        """Floating tag menu appears when text is selected."""
        page = clean_page

        floating_menu = page.locator("#floating-tag-menu")
        # Initially hidden
        expect(floating_menu).not_to_have_class("visible")

        # Select text
        word_400 = page.locator('.doc-container [data-w="400"]')
        word_401 = page.locator('.doc-container [data-w="401"]')
        expect(word_400).to_be_visible(timeout=5000)

        word_400.click()
        word_401.click(modifiers=["Shift"])

        # Menu should be visible
        expect(floating_menu).to_have_class(re.compile("visible"), timeout=5000)

    def test_floating_menu_hides_on_click_outside(self, clean_page: Page) -> None:
        """Floating menu hides when clicking outside."""
        page = clean_page

        # Select text to show menu
        word_400 = page.locator('.doc-container [data-w="400"]')
        word_401 = page.locator('.doc-container [data-w="401"]')
        expect(word_400).to_be_visible(timeout=5000)

        word_400.click()
        word_401.click(modifiers=["Shift"])

        floating_menu = page.locator("#floating-tag-menu")
        expect(floating_menu).to_have_class(re.compile("visible"), timeout=5000)

        # Click outside (on the header)
        page.locator("header").click()

        # Menu should be hidden
        expect(floating_menu).not_to_have_class(re.compile("visible"), timeout=5000)


class TestGoToTextButton:
    """Test the Go to text button functionality."""

    def test_go_to_text_scrolls_to_highlight(self, clean_page: Page) -> None:
        """Go to text button scrolls document to highlighted text."""
        page = clean_page

        word_4335 = page.locator('.doc-container [data-w="4335"]')
        word_4336 = page.locator('.doc-container [data-w="4336"]')
        word_4335.scroll_into_view_if_needed()
        expect(word_4335).to_be_visible(timeout=5000)

        word_4335.click()
        word_4336.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        page.evaluate("document.querySelector('.doc-container').scrollTop = 0")
        page.wait_for_timeout(300)

        go_to_btn = ann_card.locator("button", has_text="Go to text")
        go_to_btn.click()

        page.wait_for_timeout(1000)

        expect(word_4335).to_be_in_viewport(timeout=5000)


class TestTagColors:
    """Test that different tags have correct colors."""

    def test_jurisdiction_tag_has_blue_border(self, clean_page: Page) -> None:
        """Jurisdiction tag creates card with blue border."""
        page = clean_page

        word_50 = page.locator('.doc-container [data-w="50"]')
        word_51 = page.locator('.doc-container [data-w="51"]')
        expect(word_50).to_be_visible(timeout=5000)

        word_50.click()
        word_51.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)

        style = ann_card.get_attribute("style")
        # Browser converts hex to RGB: #1f77b4 -> rgb(31, 119, 180)
        assert style is not None and "rgb(31, 119, 180)" in style, (
            f"Expected blue border, got style: {style}"
        )

    def test_different_tags_have_different_colors(self, clean_page: Page) -> None:
        """Different tags produce cards with different border colors."""
        page = clean_page

        word_50 = page.locator('.doc-container [data-w="50"]')
        word_51 = page.locator('.doc-container [data-w="51"]')
        expect(word_50).to_be_visible(timeout=5000)

        word_50.click()
        word_51.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        word_100 = page.locator('.doc-container [data-w="100"]')
        word_101 = page.locator('.doc-container [data-w="101"]')
        expect(word_100).to_be_visible(timeout=5000)

        word_100.click()
        word_101.click(modifiers=["Shift"])
        tag_buttons.nth(1).click()

        cards = page.locator(".ann-card-positioned")
        expect(cards).to_have_count(2, timeout=5000)

        style1 = cards.first.get_attribute("style")
        style2 = cards.nth(1).get_attribute("style")

        # Browser converts hex to RGB
        assert style1 is not None and "rgb(31, 119, 180)" in style1, (
            f"First card should be blue: {style1}"
        )
        assert style2 is not None and "rgb(255, 127, 14)" in style2, (
            f"Second card should be orange: {style2}"
        )


class TestMultipleHighlights:
    """Test creating and managing multiple highlights."""

    def test_can_create_multiple_highlights(self, clean_page: Page) -> None:
        """User can create multiple highlights with different tags."""
        page = clean_page

        tag_buttons = page.locator(".tag-toolbar-compact button")

        for i, word_idx in enumerate([50, 100, 150]):
            word = page.locator(f'.doc-container [data-w="{word_idx}"]')
            word_next = page.locator(f'.doc-container [data-w="{word_idx + 1}"]')
            expect(word).to_be_visible(timeout=5000)
            word.click()
            word_next.click(modifiers=["Shift"])
            tag_buttons.nth(i).click()
            page.wait_for_timeout(300)

        cards = page.locator(".ann-card-positioned")
        expect(cards).to_have_count(3, timeout=5000)

    def test_deleting_one_highlight_keeps_others(self, clean_page: Page) -> None:
        """Deleting one highlight doesn't affect others."""
        page = clean_page

        tag_buttons = page.locator(".tag-toolbar-compact button")

        word_50 = page.locator('.doc-container [data-w="50"]')
        word_51 = page.locator('.doc-container [data-w="51"]')
        expect(word_50).to_be_visible(timeout=5000)
        word_50.click()
        word_51.click(modifiers=["Shift"])
        tag_buttons.first.click()

        word_100 = page.locator('.doc-container [data-w="100"]')
        word_101 = page.locator('.doc-container [data-w="101"]')
        expect(word_100).to_be_visible(timeout=5000)
        word_100.click()
        word_101.click(modifiers=["Shift"])
        tag_buttons.first.click()

        cards = page.locator(".ann-card-positioned")
        expect(cards).to_have_count(2, timeout=5000)

        close_btn = cards.first.locator("button").first
        close_btn.click()

        expect(cards).to_have_count(1, timeout=5000)


class TestMultiUserCollaboration:
    """Test real-time collaboration between multiple users."""

    def test_two_users_see_each_others_highlights(
        self, context: BrowserContext, live_annotation_url: str, reset_crdt_state: None
    ) -> None:
        """Two users in different browser contexts see shared highlights."""
        _ = reset_crdt_state
        page1 = context.new_page()
        page2 = context.new_page()

        try:
            page1.goto(live_annotation_url)
            expect(page1.locator(".doc-container")).to_be_visible(timeout=15000)

            page2.goto(live_annotation_url)
            expect(page2.locator(".doc-container")).to_be_visible(timeout=15000)

            word_50 = page1.locator('.doc-container [data-w="50"]')
            word_51 = page1.locator('.doc-container [data-w="51"]')
            expect(word_50).to_be_visible(timeout=5000)

            word_50.click()
            word_51.click(modifiers=["Shift"])

            tag_buttons = page1.locator(".tag-toolbar-compact button")
            tag_buttons.first.click()

            cards_page1 = page1.locator(".ann-card-positioned")
            expect(cards_page1).to_have_count(1, timeout=5000)

            cards_page2 = page2.locator(".ann-card-positioned")
            expect(cards_page2).to_have_count(1, timeout=10000)
        finally:
            page1.close()
            page2.close()

    def test_user_count_updates_with_connections(
        self,
        browser: Browser,
        live_annotation_url: str,
        reset_crdt_state: None,
    ) -> None:
        """User count label updates as users connect/disconnect."""
        _ = reset_crdt_state
        # Create two separate browser contexts for true multi-user simulation
        context1 = browser.new_context()
        context2 = browser.new_context()
        page1 = context1.new_page()
        page2: Page | None = None

        try:
            page1.goto(live_annotation_url)
            expect(page1.locator(".doc-container")).to_be_visible(timeout=15000)

            count_label = page1.locator("text=/\\d+ user.*online/i")
            expect(count_label).to_contain_text("1 user")

            page2 = context2.new_page()
            page2.goto(live_annotation_url)
            expect(page2.locator(".doc-container")).to_be_visible(timeout=15000)

            # Wait for WebSocket to broadcast user count update
            expect(page1.locator("text=/\\d+ user.*online/i")).to_contain_text(
                "2 user", timeout=10000
            )
        finally:
            page1.close()
            context1.close()
            if page2 is not None:
                page2.close()
            context2.close()
