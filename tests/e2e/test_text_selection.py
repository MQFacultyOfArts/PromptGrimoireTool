"""End-to-end tests for text selection and annotation highlighting.

Acceptance criteria (from GitHub issue #2):
- Display static text in NiceGUI
- Click-drag to select text
- Capture selection range via ui.run_javascript()
- Create visual highlight (CSS class applied to selection)
- Selection data available in Python for creating annotation

Uses Playwright to simulate user text selection in the browser.
All tests use fresh_page fixture for proper isolation.
"""

from playwright.sync_api import Page, expect


def setup_text_selection_page(page: Page, url: str) -> None:
    """Navigate to text selection page and wait for it to be ready.

    Args:
        page: Playwright page object.
        url: URL of the text selection demo page.
    """
    page.goto(url)
    content = page.get_by_test_id("selectable-content")
    expect(content).to_be_visible(timeout=10000)
    # Wait for JS handlers to be set up
    expect(content).to_have_attribute("data-handlers-ready", "true", timeout=5000)


def select_paragraph_text(page: Page, paragraph_index: int = 0) -> None:
    """Select all text in a paragraph using mouse drag.

    Uses Playwright's native mouse APIs to click-drag across a paragraph.
    Assumes page is already set up via setup_text_selection_page().

    Args:
        page: Playwright page object.
        paragraph_index: Which paragraph to select (0-indexed).
    """
    content = page.get_by_test_id("selectable-content")

    # Get the target paragraph
    paragraph = content.locator("p").nth(paragraph_index)
    box = paragraph.bounding_box()
    assert box is not None, f"Paragraph {paragraph_index} not found"

    # Drag from start to end of paragraph to select its text
    # Start just inside the left edge, end just inside the right edge
    start_x = box["x"] + 5
    end_x = box["x"] + box["width"] - 5
    y = box["y"] + box["height"] / 2

    page.mouse.move(start_x, y)
    page.mouse.down()
    page.mouse.move(end_x, y)
    page.mouse.up()


class TestPageLoads:
    """Test that the demo page loads correctly."""

    def test_page_loads_with_sample_text(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Demo page loads and displays sample text."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Verify the page title/header is visible
        expect(fresh_page.locator("text=Text Selection Demo")).to_be_visible()

        # Verify sample content is present
        content = fresh_page.get_by_test_id("selectable-content")
        expect(content).to_be_visible()
        expect(content).to_contain_text("sample")

    def test_selection_info_panel_exists(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Selection info panel is visible."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Verify selection display elements exist
        expect(fresh_page.get_by_test_id("selected-text")).to_be_visible()
        expect(fresh_page.get_by_test_id("start-offset")).to_be_visible()
        expect(fresh_page.get_by_test_id("end-offset")).to_be_visible()


class TestTextSelection:
    """Test text selection capture."""

    def test_text_can_be_selected(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Text can be selected and captured by the app."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Select text using mouse drag
        select_paragraph_text(fresh_page, 0)

        # Verify selection was captured (UI shows selected text)
        selected_text = fresh_page.get_by_test_id("selected-text")
        expect(selected_text).not_to_have_text("No selection", timeout=2000)

    def test_selection_captured_in_python(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Selected text is captured and displayed in selection info panel."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Select text using mouse drag
        select_paragraph_text(fresh_page, 0)

        # Wait for Python handler to update UI
        selected_text = fresh_page.get_by_test_id("selected-text")
        expect(selected_text).not_to_have_text("No selection", timeout=2000)

    def test_selection_offsets_captured(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Start and end offsets are captured."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Select text using mouse drag
        select_paragraph_text(fresh_page, 0)

        # Check offsets are populated
        start_offset = fresh_page.get_by_test_id("start-offset")
        end_offset = fresh_page.get_by_test_id("end-offset")

        expect(start_offset).not_to_have_text("Start: -", timeout=2000)
        expect(end_offset).not_to_have_text("End: -", timeout=2000)


class TestEmptySelection:
    """Test handling of empty or whitespace selections."""

    def test_click_without_drag_no_selection(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Single click (no drag) does not trigger selection capture."""
        setup_text_selection_page(fresh_page, text_selection_url)

        content = fresh_page.get_by_test_id("selectable-content")

        # Single click only
        content.click()

        # Should still show "No selection"
        selected_text = fresh_page.get_by_test_id("selected-text")
        expect(selected_text).to_have_text("No selection")


class TestVisualHighlight:
    """Test CSS highlighting of selections."""

    def test_create_highlight_button_exists(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Create Highlight button is present."""
        setup_text_selection_page(fresh_page, text_selection_url)

        button = fresh_page.get_by_test_id("create-highlight-btn")
        expect(button).to_be_visible()

    def test_highlight_applied_to_selection(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Selected text receives highlight CSS class after clicking button."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Select text using mouse drag
        select_paragraph_text(fresh_page, 0)

        # Wait for selection to be captured
        expect(fresh_page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )

        # Click highlight button
        fresh_page.get_by_test_id("create-highlight-btn").click()

        # Verify highlight span was created
        highlight = fresh_page.locator(".annotation-highlight")
        expect(highlight).to_be_visible()

    def test_highlight_has_background_color(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Highlighted text has visible background color."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # Select and highlight text using mouse drag
        select_paragraph_text(fresh_page, 0)
        expect(fresh_page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        fresh_page.get_by_test_id("create-highlight-btn").click()

        # Check computed style has background
        highlight = fresh_page.locator(".annotation-highlight")
        expect(highlight).to_be_visible()

        # Verify background is not transparent using Playwright's to_have_css
        # The annotation-highlight class should apply a yellow background
        expect(highlight).not_to_have_css("background-color", "rgba(0, 0, 0, 0)")

    def test_multiple_highlights_supported(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Multiple separate highlights can be created."""
        setup_text_selection_page(fresh_page, text_selection_url)

        # First highlight using mouse drag
        select_paragraph_text(fresh_page, 0)
        expect(fresh_page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        fresh_page.get_by_test_id("create-highlight-btn").click()

        # Second highlight (different paragraph)
        select_paragraph_text(fresh_page, 1)
        expect(fresh_page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )
        fresh_page.get_by_test_id("create-highlight-btn").click()

        # Both highlights should exist
        highlights = fresh_page.locator(".annotation-highlight")
        expect(highlights).to_have_count(2)


class TestClickDragSelection:
    """Test actual click-drag selection (primary use case)."""

    def test_click_drag_selection(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """User can click-drag to select partial text within a paragraph."""
        setup_text_selection_page(fresh_page, text_selection_url)

        content = fresh_page.get_by_test_id("selectable-content")
        p = content.locator("p").first

        # Get bounding box and drag within it to select partial text
        box = p.bounding_box()
        assert box is not None

        # Drag from near left to middle of the paragraph
        fresh_page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
        fresh_page.mouse.down()
        fresh_page.mouse.move(box["x"] + 150, box["y"] + box["height"] / 2)
        fresh_page.mouse.up()

        # Verify selection was captured
        expect(fresh_page.get_by_test_id("selected-text")).not_to_have_text(
            "No selection", timeout=2000
        )


class TestEdgeCases:
    """Edge cases for text selection."""

    def test_multiline_selection(
        self, fresh_page: Page, text_selection_url: str
    ) -> None:
        """Selection spanning multiple lines works."""
        setup_text_selection_page(fresh_page, text_selection_url)

        content = fresh_page.get_by_test_id("selectable-content")

        # Select across multiple paragraphs using mouse drag
        p1 = content.locator("p").first
        p2 = content.locator("p").nth(1)
        box1 = p1.bounding_box()
        box2 = p2.bounding_box()
        assert box1 is not None and box2 is not None

        # Drag from start of first paragraph to partway into second paragraph
        start_x = box1["x"] + 5
        start_y = box1["y"] + box1["height"] / 2
        end_x = box2["x"] + 50  # A bit into second paragraph
        end_y = box2["y"] + box2["height"] / 2

        fresh_page.mouse.move(start_x, start_y)
        fresh_page.mouse.down()
        fresh_page.mouse.move(end_x, end_y)
        fresh_page.mouse.up()

        # Verify selection was captured and spans both paragraphs
        selected_text = fresh_page.get_by_test_id("selected-text")
        expect(selected_text).not_to_have_text("No selection", timeout=2000)

        # Verify the selection spans a significant range (multiline = longer selection)
        # The display is truncated at 50 chars, so check offsets for span verification
        start_offset = fresh_page.get_by_test_id("start-offset")
        end_offset = fresh_page.get_by_test_id("end-offset")
        expect(start_offset).not_to_have_text("Start: -")
        expect(end_offset).not_to_have_text("End: -")

        # Parse the offset values to verify the selection spans multiple paragraphs
        start_text = start_offset.text_content()
        end_text = end_offset.text_content()
        assert start_text is not None and end_text is not None
        start_value = int(start_text.replace("Start: ", ""))
        end_value = int(end_text.replace("End: ", ""))
        selection_length = end_value - start_value
        # First paragraph alone is ~55 chars; multiline selection should be longer
        assert selection_length > 55, (
            f"Selection should span into second paragraph, length={selection_length}"
        )
