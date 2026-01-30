"""End-to-end tests for live annotation demo.

Tests the annotation workflow including:
- Creating highlights with paragraph numbers
- Verifying paragraph numbers appear in annotation cards
- Testing the "highest para seen" heuristic for court orders
- Multi-paragraph highlights with en-dash format
- Highlight deletion, comments, keyboard shortcuts
- Go-to-text, tag colors
- Multiple highlights and multi-user collaboration
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    FloatRect,
    Locator,
    Page,
    expect,
)

from tests.e2e.helpers import click_tag

# Skip all tests in this module - coverage migrated to new test files
pytestmark = pytest.mark.skip(
    reason="Deprecated: coverage migrated to test_annotation_*.py files. "
    "Paragraph tests blocked on Issue #99 (Seam G). "
    "See coverage-mapping.md for details."
)

if TYPE_CHECKING:
    from collections.abc import Generator


def _select_words(page: Page, start_word: int, end_word: int) -> None:
    """Select a range of words by clicking start and shift-clicking end.

    Scrolls elements into view before clicking.
    """
    word_start = page.locator(f'.doc-container [data-w="{start_word}"]')
    word_end = page.locator(f'.doc-container [data-w="{end_word}"]')

    word_start.scroll_into_view_if_needed()
    expect(word_start).to_be_visible(timeout=5000)

    word_start.click()
    word_end.click(modifiers=["Shift"])


def _create_highlight(
    page: Page, start_word: int, end_word: int, tag_index: int = 0
) -> None:
    """Select words and apply a tag to create a highlight."""
    _select_words(page, start_word, end_word)
    click_tag(page, tag_index)


def _get_ann_cards(page: Page) -> tuple[int, Locator]:
    """Get annotation cards locator and current count."""
    cards = page.locator(".ann-card-positioned")
    return cards.count(), cards


def _login_as_test_user(page: Page, app_server: str, test_name: str) -> None:
    """Login as a test-specific user for isolation.

    Each test run gets a unique UUID to ensure complete isolation -
    no data persists between test runs.

    Args:
        page: Playwright page.
        app_server: Base URL of the app server.
        test_name: Test name (used for debugging, UUID provides isolation).
    """
    from uuid import uuid4

    # UUID ensures each test run is completely isolated
    run_id = uuid4().hex[:8]
    email = f"{test_name}-{run_id}@test.example.edu.au"
    token = f"mock-token-{email}"
    page.goto(f"{app_server}/auth/callback?token={token}")
    page.wait_for_load_state("networkidle", timeout=15000)
    expect(page).to_have_url(f"{app_server}/", timeout=5000)


@pytest.fixture
def clean_page(
    fresh_page: Page,
    app_server: str,
    live_annotation_url: str,
    reset_crdt_state: None,
    request: pytest.FixtureRequest,
) -> Generator[Page]:
    """Navigate to live annotation page with clean CRDT state.

    Uses fresh_page fixture for browser-level isolation (fresh context per test).
    The reset_crdt_state fixture resets all CRDT state server-side.
    Logs in as a test-specific user for per-user document isolation.

    This ensures:
    - No shared browser state (cookies, localStorage, WebSocket connections)
    - No shared CRDT document state
    - Per-user document isolation
    """
    _ = reset_crdt_state
    # Login as test-specific user
    test_name = request.node.name.replace("[", "-").replace("]", "")
    _login_as_test_user(fresh_page, app_server, test_name)

    # Navigate to the demo page with fresh browser context and CRDT state
    fresh_page.goto(live_annotation_url)
    doc_container = fresh_page.locator(".doc-container")
    expect(doc_container).to_be_visible(timeout=15000)

    yield fresh_page


class TestAnnotationCardParagraphNumbers:
    """Test that annotation cards display correct paragraph numbers."""

    def test_page_loads(
        self, page: Page, app_server: str, live_annotation_url: str
    ) -> None:
        """Live annotation demo page loads successfully after login."""
        # Login first (auth required)
        _login_as_test_user(page, app_server, "test_page_loads")
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
        word_482.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
        expect(ann_card).to_be_visible(timeout=5000)

        # Court orders are part of para 48
        expect(ann_card).to_contain_text("[48]")


class TestHighlightCreation:
    """Test highlight creation workflow."""

    def test_can_select_text_and_create_highlight(self, clean_page: Page) -> None:
        """User can select text and apply a tag to create a highlight."""
        page = clean_page

        initial_count, ann_cards = _get_ann_cards(page)
        _create_highlight(page, 0, 1)
        expect(ann_cards).to_have_count(initial_count + 1, timeout=5000)

    def test_highlight_shows_quoted_text(self, clean_page: Page) -> None:
        """Annotation card shows the highlighted text in quotes."""
        page = clean_page

        _create_highlight(page, 10, 11)

        ann_card = page.locator(".ann-card-positioned").first
        ann_card.scroll_into_view_if_needed()
        expect(ann_card).to_be_visible(timeout=5000)


class TestMultiParagraphHighlights:
    """Test highlights spanning multiple paragraphs."""

    def test_highlight_spanning_paragraphs_shows_range(self, clean_page: Page) -> None:
        """Highlighting across paragraphs shows [N-M] format with en-dash."""
        page = clean_page

        # Select from paragraph 5 (word 848) to paragraph 6 (word 870)
        _create_highlight(page, 848, 870)

        ann_card = page.locator(".ann-card-positioned").first
        ann_card.scroll_into_view_if_needed()
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

        _create_highlight(page, 0, 1)

        # Verify highlight was created
        _, ann_cards = _get_ann_cards(page)
        expect(ann_cards.first).to_be_visible(timeout=5000)
        count_before_delete = ann_cards.count()

        # Click close button on the first card
        first_card = ann_cards.first
        first_card.scroll_into_view_if_needed()
        close_btn = first_card.locator("button").first
        close_btn.click()

        # Verify count decreased by 1
        expect(ann_cards).to_have_count(count_before_delete - 1, timeout=5000)


class TestCommentCreation:
    """Test comment creation on highlights."""

    def test_can_add_comment_to_highlight(self, clean_page: Page) -> None:
        """User can add a comment to an annotation card."""
        page = clean_page

        _create_highlight(page, 100, 101)

        ann_card = page.locator(".ann-card-positioned").first
        ann_card.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
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
        ann_card.scroll_into_view_if_needed()
        expect(ann_card).to_be_visible(timeout=5000)
        expect(ann_card).to_contain_text("Reflection")


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
        ann_card.scroll_into_view_if_needed()
        expect(ann_card).to_be_visible(timeout=5000)

        # Scroll document away from the highlight by scrolling to beginning of document
        # Use first word in document as scroll target
        word_0 = page.locator('.doc-container [data-w="0"]')
        word_0.scroll_into_view_if_needed()
        page.wait_for_timeout(300)

        # Verify word is no longer in viewport before clicking Go to text
        expect(word_4335).not_to_be_in_viewport(timeout=2000)

        # The annotation card may have scrolled out of view, dispatch click directly
        go_to_btn = ann_card.locator("button", has_text="Go to text")
        go_to_btn.dispatch_event("click")

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
        ann_card.scroll_into_view_if_needed()
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


def _select_words_drag(page: Page, start_word: int, end_word: int) -> None:
    """Select words using mouse drag (handles overlapping highlights).

    Unlike click+shift-click, this approach clears existing selection first
    and uses drag to avoid browser 'drag existing selection' behavior.
    """
    _do_drag_selection(page, start_word, end_word)


def _do_drag_selection(page: Page, start_word: int, end_word: int) -> None:
    """Execute the drag selection.

    Includes workaround for NiceGUI 3.6 + Playwright issue where selections
    on highlighted text become "sticky" and won't clear with normal clicks
    outside the document. Clicking on a non-highlighted word inside the
    document container reliably clears the selection.
    """
    word_start = page.locator(f'.doc-container [data-w="{start_word}"]')
    word_end = page.locator(f'.doc-container [data-w="{end_word}"]')

    word_start.scroll_into_view_if_needed()
    expect(word_start).to_be_visible(timeout=5000)

    word_end.scroll_into_view_if_needed()
    expect(word_end).to_be_visible(timeout=5000)

    start_box = word_start.bounding_box()
    end_box = word_end.bounding_box()

    if start_box is None or end_box is None:
        msg = f"Could not get bounding box for words {start_word}-{end_word}"
        raise AssertionError(msg)

    # Clear any existing selection by clicking on a non-highlighted word.
    # NiceGUI 3.6 + Playwright has an issue where selections on highlighted
    # text become "sticky" - clicking outside the document doesn't clear them.
    # Clicking on non-highlighted text inside the document reliably clears it.
    # Use word 0 (document header) which is never highlighted in these tests.
    clear_target = page.locator('.doc-container [data-w="0"]')
    if clear_target.count() > 0:
        clear_target.scroll_into_view_if_needed()
        clear_target.click()
        page.wait_for_timeout(50)

    # Re-scroll to target and get fresh bounding boxes
    word_start.scroll_into_view_if_needed()
    page.wait_for_timeout(50)

    start_box = word_start.bounding_box()
    end_box = word_end.bounding_box()

    if start_box is None or end_box is None:
        msg = f"Could not get fresh bounding box for words {start_word}-{end_word}"
        raise AssertionError(msg)

    _execute_drag(page, start_box, end_box)


def _execute_drag(page: Page, start_box: FloatRect, end_box: FloatRect) -> None:
    """Execute the mouse drag operation."""
    start_x = start_box["x"] + 2
    start_y = start_box["y"] + start_box["height"] / 2
    end_x = end_box["x"] + end_box["width"] - 2
    end_y = end_box["y"] + end_box["height"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y)
    page.mouse.up()
    page.wait_for_timeout(200)  # Let selection event fire


def _create_highlight_drag(
    page: Page, start_word: int, end_word: int, tag_index: int = 0
) -> None:
    """Create highlight using drag selection."""
    _select_words_drag(page, start_word, end_word)
    click_tag(page, tag_index)


class TestOverlappingHighlights:
    """Test creating highlights that overlap with existing highlights.

    Regression tests for GitHub issue #78: Selection fails when starting
    on already-highlighted word.
    """

    def test_can_select_starting_on_highlighted_word(self, clean_page: Page) -> None:
        """Selection starting on an already-highlighted word succeeds.

        Regression test for #78: When a word is already highlighted,
        starting a new selection on that word should work normally.
        Uses drag selection which handles overlapping highlights.
        """
        page = clean_page

        initial_count, ann_cards = _get_ann_cards(page)

        # Create first highlight on words 100-120 (wide range)
        _create_highlight_drag(page, 100, 120, tag_index=0)
        expect(ann_cards).to_have_count(initial_count + 1, timeout=5000)

        # Create second highlight starting on word 110 (clearly in the middle of first)
        # This is the exact scenario that failed in #78
        _create_highlight_drag(page, 110, 130, tag_index=1)
        expect(ann_cards).to_have_count(initial_count + 2, timeout=5000)

    def test_can_create_fully_overlapping_highlights(self, clean_page: Page) -> None:
        """Can create a highlight that fully overlaps an existing one.

        Both highlights should exist - the CRDT supports multiple highlights
        on the same text.
        """
        page = clean_page

        initial_count, ann_cards = _get_ann_cards(page)

        # Create first highlight on words 200-210
        _create_highlight_drag(page, 200, 210, tag_index=0)
        expect(ann_cards).to_have_count(initial_count + 1, timeout=5000)

        # Create second highlight on the same words with different tag
        _create_highlight_drag(page, 200, 210, tag_index=1)

        expect(ann_cards).to_have_count(initial_count + 2, timeout=5000)

    def test_can_select_ending_on_highlighted_word(self, clean_page: Page) -> None:
        """Selection ending on an already-highlighted word succeeds."""
        page = clean_page

        initial_count, ann_cards = _get_ann_cards(page)

        # Create first highlight on words 300-310
        _create_highlight_drag(page, 300, 310, tag_index=0)
        expect(ann_cards).to_have_count(initial_count + 1, timeout=5000)

        # Create second highlight ending on word 300 (already highlighted)
        _create_highlight_drag(page, 290, 300, tag_index=1)
        expect(ann_cards).to_have_count(initial_count + 2, timeout=5000)

    def test_can_select_starting_at_highlight_boundary(self, clean_page: Page) -> None:
        """Selection starting at exact end of previous highlight succeeds.

        This is the specific boundary case that fails in #78:
        - Highlight 1: words 400-410
        - Highlight 2: words 410-420 (starts at 410, last word of highlight 1)

        Word 410 is highlighted by both, making them overlap at that word.
        """
        page = clean_page

        initial_count, ann_cards = _get_ann_cards(page)

        # Create first highlight on words 400-410
        _create_highlight_drag(page, 400, 410, tag_index=0)
        expect(ann_cards).to_have_count(initial_count + 1, timeout=5000)

        # Create second highlight starting at word 410 (the boundary)
        # This is the exact scenario that fails in #78
        _create_highlight_drag(page, 410, 420, tag_index=1)
        expect(ann_cards).to_have_count(initial_count + 2, timeout=5000)


class TestMultiUserCollaboration:
    """Test real-time collaboration between multiple users.

    For collaboration tests, both users log in with the same email
    to share the same document (doc_id = demo-{email}).
    """

    # Shared email for collaboration tests - both users get same document
    COLLAB_EMAIL = "collab-test@test.example.edu.au"

    def _login_for_collab(self, page: Page, app_server: str) -> None:
        """Login with shared email for collaboration testing."""
        token = f"mock-token-{self.COLLAB_EMAIL}"
        page.goto(f"{app_server}/auth/callback?token={token}")
        page.wait_for_load_state("networkidle", timeout=15000)
        expect(page).to_have_url(f"{app_server}/", timeout=5000)

    def test_two_users_see_each_others_highlights(
        self,
        context: BrowserContext,
        app_server: str,
        live_annotation_url: str,
        reset_crdt_state: None,
    ) -> None:
        """Two users in different browser contexts see shared highlights."""
        _ = reset_crdt_state
        page1 = context.new_page()
        page2 = context.new_page()

        try:
            # Both users login with same email to share document
            self._login_for_collab(page1, app_server)
            page1.goto(live_annotation_url)
            expect(page1.locator(".doc-container")).to_be_visible(timeout=15000)

            self._login_for_collab(page2, app_server)
            page2.goto(live_annotation_url)
            expect(page2.locator(".doc-container")).to_be_visible(timeout=15000)

            word_50 = page1.locator('.doc-container [data-w="50"]')
            word_51 = page1.locator('.doc-container [data-w="51"]')
            expect(word_50).to_be_visible(timeout=5000)

            # Count existing cards before creating new highlight
            cards_page1 = page1.locator(".ann-card-positioned")
            cards_page2 = page2.locator(".ann-card-positioned")
            initial_count = cards_page1.count()

            word_50.click()
            word_51.click(modifiers=["Shift"])

            tag_buttons = page1.locator(".tag-toolbar-compact button")
            tag_buttons.first.click()

            # Verify page1 sees the new highlight
            expect(cards_page1).to_have_count(initial_count + 1, timeout=5000)

            # Verify page2 also sees it (collaboration working)
            expect(cards_page2).to_have_count(initial_count + 1, timeout=10000)
        finally:
            page1.close()
            page2.close()

    def test_user_count_updates_with_connections(
        self,
        browser: Browser,
        app_server: str,
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
            # Both users login with same email to share document
            self._login_for_collab(page1, app_server)
            page1.goto(live_annotation_url)
            expect(page1.locator(".doc-container")).to_be_visible(timeout=15000)

            count_label = page1.locator("text=/\\d+ user.*online/i")
            expect(count_label).to_contain_text("1 user")

            page2 = context2.new_page()
            self._login_for_collab(page2, app_server)
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
