"""End-to-end tests for text selection and annotation highlighting.

Acceptance criteria (from GitHub issue #2):
- Display static text in NiceGUI
- Click-drag to select text
- Capture selection range via ui.run_javascript()
- Create visual highlight (CSS class applied to selection)
- Selection data available in Python for creating annotation

Uses Playwright to simulate user text selection in the browser.
"""

from playwright.sync_api import Page, expect


class TestPageLoads:
    """Test that the demo page loads correctly."""

    def test_page_loads_with_sample_text(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Demo page loads and displays sample text."""
        page.goto(text_selection_url)

        # Verify the page title/header is visible
        expect(page.locator("text=Text Selection Demo")).to_be_visible()

        # Verify sample content is present
        content = page.get_by_test_id("selectable-content")
        expect(content).to_be_visible()
        expect(content).to_contain_text("sample")

    def test_selection_info_panel_exists(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Selection info panel is visible."""
        page.goto(text_selection_url)

        # Verify selection display elements exist
        expect(page.get_by_test_id("selected-text")).to_be_visible()
        expect(page.get_by_test_id("start-offset")).to_be_visible()
        expect(page.get_by_test_id("end-offset")).to_be_visible()


class TestTextSelection:
    """Test text selection capture."""

    def test_text_can_be_selected(self, page: Page, text_selection_url: str) -> None:
        """Text can be selected via click-drag."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Select text by triple-clicking a paragraph (selects whole paragraph)
        content.locator("p").first.click(click_count=3)

        # Verify browser has selection
        selection = page.evaluate("window.getSelection().toString()")
        assert len(selection) > 0

    def test_selection_captured_in_python(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Selected text is captured and displayed in selection info panel."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Triple-click to select a paragraph
        content.locator("p").first.click(click_count=3)

        # Wait for Python handler to update UI
        selected_text = page.get_by_test_id("selected-text")
        expect(selected_text).not_to_have_text("No selection", timeout=2000)

    def test_selection_offsets_captured(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Start and end offsets are captured."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Select text
        content.locator("p").first.click(click_count=3)

        # Check offsets are populated
        start_offset = page.get_by_test_id("start-offset")
        end_offset = page.get_by_test_id("end-offset")

        expect(start_offset).not_to_have_text("Start: -", timeout=2000)
        expect(end_offset).not_to_have_text("End: -", timeout=2000)


class TestEmptySelection:
    """Test handling of empty or whitespace selections."""

    def test_click_without_drag_no_selection(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Single click (no drag) does not trigger selection capture."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Single click only
        content.click()

        # Should still show "No selection"
        selected_text = page.get_by_test_id("selected-text")
        expect(selected_text).to_have_text("No selection")


class TestVisualHighlight:
    """Test CSS highlighting of selections."""

    def test_create_highlight_button_exists(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Create Highlight button is present."""
        page.goto(text_selection_url)

        button = page.get_by_test_id("create-highlight-btn")
        expect(button).to_be_visible()

    def test_highlight_applied_to_selection(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Selected text receives highlight CSS class after clicking button."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Select text
        content.locator("p").first.click(click_count=3)

        # Wait for selection to be captured
        expect(page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )

        # Click highlight button
        page.get_by_test_id("create-highlight-btn").click()

        # Verify highlight span was created
        highlight = page.locator(".annotation-highlight")
        expect(highlight).to_be_visible()

    def test_highlight_has_background_color(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Highlighted text has visible background color."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")

        # Select and highlight text
        content.locator("p").first.click(click_count=3)
        expect(page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        page.get_by_test_id("create-highlight-btn").click()

        # Check computed style has background
        highlight = page.locator(".annotation-highlight")
        expect(highlight).to_be_visible()

        # Verify background is not transparent
        bg_color = highlight.evaluate(
            "el => window.getComputedStyle(el).backgroundColor"
        )
        assert bg_color != "rgba(0, 0, 0, 0)", (
            f"Expected background color, got {bg_color}"
        )

    def test_multiple_highlights_supported(
        self, page: Page, text_selection_url: str
    ) -> None:
        """Multiple separate highlights can be created."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")
        paragraphs = content.locator("p")

        # First highlight
        paragraphs.nth(0).click(click_count=3)
        expect(page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        page.get_by_test_id("create-highlight-btn").click()

        # Second highlight (different paragraph)
        paragraphs.nth(1).click(click_count=3)
        expect(page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        page.get_by_test_id("create-highlight-btn").click()

        # Both highlights should exist
        highlights = page.locator(".annotation-highlight")
        expect(highlights).to_have_count(2)


class TestEdgeCases:
    """Edge cases for text selection."""

    def test_multiline_selection(self, page: Page, text_selection_url: str) -> None:
        """Selection spanning multiple lines works."""
        page.goto(text_selection_url)

        content = page.get_by_test_id("selectable-content")
        # Wait for content to be visible and have paragraphs
        expect(content.locator("p").first).to_be_visible()

        # Wait for JavaScript event handlers to be set up
        # The page runs async setup after client.connected()
        page.wait_for_timeout(500)

        # Select across multiple paragraphs using JavaScript
        # (Playwright's click-drag is tricky for multi-line)
        page.evaluate("""
            const selector = '[data-testid="selectable-content"]';
            const container = document.querySelector(selector);
            const range = document.createRange();
            const p1 = container.querySelector('p:first-child');
            const p2 = container.querySelector('p:nth-child(2)');
            range.setStart(p1.firstChild, 0);
            range.setEnd(p2.firstChild, 5);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);

            // Trigger mouseup to fire our handler
            container.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
        """)

        # Verify selection was captured
        selected_text = page.get_by_test_id("selected-text")
        expect(selected_text).not_to_have_text("No selection", timeout=2000)
