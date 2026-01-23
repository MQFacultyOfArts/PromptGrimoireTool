"""End-to-end tests for live annotation demo.

Tests the annotation workflow including:
- Creating highlights with paragraph numbers
- Verifying paragraph numbers appear in annotation cards
- Testing the "highest para seen" heuristic for court orders
"""

from playwright.sync_api import Page, expect


class TestAnnotationCardParagraphNumbers:
    """Test that annotation cards display correct paragraph numbers."""

    def test_page_loads(self, page: Page, live_annotation_url: str) -> None:
        """Live annotation demo page loads successfully."""
        page.goto(live_annotation_url)

        # Verify the page has the document container
        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

    def test_highlight_in_paragraph_shows_para_number(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """Highlighting text in a numbered paragraph shows [N] in card."""
        page.goto(live_annotation_url)

        # Wait for document to load
        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

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
        # The paragraph number should be displayed in the card
        expect(ann_card).to_contain_text("[1]")

    def test_highlight_in_metadata_shows_no_para_number(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """Highlighting text in metadata (before paragraphs) shows no [N]."""
        page.goto(live_annotation_url)

        # Wait for document to load
        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

        # Find "Case" in the metadata table - should be before any <ol>
        # This text appears in the header table before numbered paragraphs
        case_span = page.locator(".doc-container [data-w]", has_text="Case").first
        expect(case_span).to_be_visible(timeout=5000)

        # Click to select this word
        case_span.click()

        # Click the first tag button to create a highlight
        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for annotation card to be created
        ann_card = page.locator(".ann-card-positioned").first
        # Scroll sync may hide card - force it visible for testing
        page.wait_for_timeout(500)  # Wait for card to be created
        page.evaluate(
            "document.querySelector('.ann-card-positioned').style.display = ''"
        )
        expect(ann_card).to_be_visible(timeout=5000)

        # Verify the card does NOT contain a paragraph reference like [1], [2], etc.
        # It should just show author without brackets
        card_text = ann_card.inner_text()
        # Check that there's no pattern like [N] where N is a number
        import re

        para_refs = re.findall(r"\[\d+\]", card_text)
        assert len(para_refs) == 0, f"Expected no paragraph refs, found: {para_refs}"

    def test_highlight_in_paragraph_48_shows_para_number(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """Highlighting in paragraph 48 shows [48] in card."""
        page.goto(live_annotation_url)

        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

        # Paragraph 48 starts at word 4335 ("Therefore,")
        # Scroll to it first
        word_4335 = page.locator('.doc-container [data-w="4335"]')
        word_4336 = page.locator('.doc-container [data-w="4336"]')
        word_4335.scroll_into_view_if_needed()
        expect(word_4335).to_be_visible(timeout=5000)

        word_4335.click()
        word_4336.click(modifiers=["Shift"])

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for card and force visible
        ann_card = page.locator(".ann-card-positioned").first
        page.wait_for_timeout(500)
        page.evaluate(
            "document.querySelector('.ann-card-positioned').style.display = ''"
        )
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("[48]")

    def test_highlight_in_court_orders_shows_para_48(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """Highlighting in court orders (sub-list of para 48) shows [48]."""
        page.goto(live_annotation_url)

        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

        # Word 4346 is "Grant" - first word of court orders (continues para 48)
        word_4346 = page.locator('.doc-container [data-w="4346"]')
        word_4346.scroll_into_view_if_needed()
        expect(word_4346).to_be_visible(timeout=5000)

        word_4346.click()

        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Wait for card and force visible
        ann_card = page.locator(".ann-card-positioned").first
        page.wait_for_timeout(500)
        page.evaluate(
            "document.querySelector('.ann-card-positioned').style.display = ''"
        )
        expect(ann_card).to_be_visible(timeout=5000)

        # Court orders are part of para 48
        expect(ann_card).to_contain_text("[48]")


class TestHighlightCreation:
    """Test highlight creation workflow."""

    def test_can_select_text_and_create_highlight(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """User can select text and apply a tag to create a highlight."""
        page.goto(live_annotation_url)

        # Wait for document
        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

        # Get first word span
        first_word = page.locator('.doc-container [data-w="0"]')
        expect(first_word).to_be_visible(timeout=5000)

        # Click to select
        first_word.click()

        # Click a tag button
        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Verify highlight was created (card appears)
        ann_card = page.locator(".ann-card-positioned")
        expect(ann_card).to_have_count(1, timeout=5000)

    def test_highlight_shows_quoted_text(
        self, page: Page, live_annotation_url: str
    ) -> None:
        """Annotation card shows the highlighted text in quotes."""
        page.goto(live_annotation_url)

        doc_container = page.locator(".doc-container")
        expect(doc_container).to_be_visible(timeout=10000)

        # Find and click a specific word
        word = page.locator(".doc-container [data-w]", has_text="Court").first
        expect(word).to_be_visible(timeout=5000)
        word.click()

        # Create highlight
        tag_buttons = page.locator(".tag-toolbar-compact button")
        tag_buttons.first.click()

        # Verify card shows the text
        ann_card = page.locator(".ann-card-positioned").first
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("Court")
