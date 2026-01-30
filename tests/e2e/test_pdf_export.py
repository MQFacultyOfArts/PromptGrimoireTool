"""End-to-end tests for PDF export with annotations.

Tests the complete export workflow:
- Multiple users collaborating on annotations
- Adding comments and replies
- Writing general notes
- Exporting to PDF
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Browser, BrowserContext, Locator, Page, expect

from tests.e2e.helpers import click_tag

# Output directory for test artifacts
_OUTPUT_DIR = Path("output/test_output")


def _login_as_user(page: Page, app_server: str, user_email: str) -> None:
    """Login as a specific user.

    Note: This uses explicit emails for multi-user collaboration tests
    where Alice and Bob need deterministic emails to share the same document.
    """
    token = f"mock-token-{user_email}"
    page.goto(f"{app_server}/auth/callback?token={token}")
    page.wait_for_load_state("networkidle", timeout=15000)
    expect(page).to_have_url(f"{app_server}/", timeout=5000)


def _select_words(page: Page, start_word: int, end_word: int) -> None:
    """Select a range of words by dragging from start to end.

    Uses mouse drag for selection to handle overlapping highlights correctly.
    Includes workaround for NiceGUI 3.6 + Playwright issue where selections
    on highlighted text become "sticky" and won't clear with clicks outside
    the document. Clicking on a non-highlighted word inside the document
    container reliably clears the selection.
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

    # Drag from start word to end word to create selection
    start_x = start_box["x"] + 2
    start_y = start_box["y"] + start_box["height"] / 2
    end_x = end_box["x"] + end_box["width"] - 2
    end_y = end_box["y"] + end_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y)
    page.mouse.up()
    page.wait_for_timeout(200)  # Let selection event fire


def _create_highlight(
    page: Page, start_word: int, end_word: int, tag_index: int = 0
) -> None:
    """Select words and apply a tag to create a highlight."""
    _select_words(page, start_word, end_word)
    click_tag(page, tag_index)


def _add_comment_to_card(page: Page, card_index: int, comment_text: str) -> None:
    """Add a comment to an annotation card."""
    cards = page.locator(".ann-card-positioned")
    card = cards.nth(card_index)
    card.scroll_into_view_if_needed()
    expect(card).to_be_visible(timeout=5000)

    comment_input = card.locator("input[placeholder*='comment']")
    expect(comment_input).to_be_visible(timeout=5000)
    comment_input.fill(comment_text)

    post_btn = card.locator("button", has_text="Post")
    post_btn.click()

    expect(card).to_contain_text(comment_text, timeout=5000)


def _scroll_to_word_and_find_card(page: Page, word_idx: int, card_text: str) -> Locator:
    """Scroll to word and find associated annotation card.

    Args:
        page: Playwright page
        word_idx: Word index to scroll to
        card_text: Text to find in the card (e.g. paragraph number like "[48]")

    Returns:
        The located card element
    """
    word = page.locator(f'.doc-container [data-w="{word_idx}"]')
    word.scroll_into_view_if_needed()
    page.wait_for_timeout(500)

    card = page.locator(".ann-card-positioned", has_text=card_text).first
    card.scroll_into_view_if_needed()
    expect(card).to_be_visible(timeout=5000)
    return card


def _add_comment_to_visible_card(page: Page, card: Locator, text: str) -> None:
    """Add comment to a visible/focused card.

    Args:
        page: Playwright page
        card: The card locator to add comment to
        text: Comment text to add
    """
    # Ensure card is visible and expanded
    card.scroll_into_view_if_needed()
    expect(card).to_be_visible(timeout=5000)
    card.click(force=True)  # Force to bypass overlapping cards
    page.wait_for_timeout(500)  # Wait for card expansion animation

    # Find and fill comment input
    comment_input = card.locator("input[placeholder*='comment']")
    # Use force=True to bypass visibility check for Quasar wrapped inputs
    comment_input.fill(text, force=True)
    page.wait_for_timeout(200)

    # Post the comment
    post_btn = card.locator("button", has_text="Post")
    post_btn.click(force=True)

    expect(card).to_contain_text(text, timeout=5000)


def _alice_creates_annotations(page: Page) -> int:
    """Alice creates highlights for all 10 tags at specific locations.

    Tag indices:
    - 0: jurisdiction
    - 1: procedural_history
    - 2: legally_relevant_facts
    - 3: legal_issues
    - 4: reasons
    - 5: courts_reasoning
    - 6: decision
    - 7: order
    - 8: domestic_sources
    - 9: reflection

    Returns:
        Initial card count before creating annotations.
    """
    cards = page.locator(".ann-card-positioned")
    initial_count = cards.count()

    # Annotations Alice will create (Bob does procedural_history separately)
    # Each tuple: start_word, end_word, tag_index, description
    # Selection bounds are INCLUSIVE - backend adds +1 for exclusive CRDT storage
    # Testing overlapping highlights as edge cases per spec
    annotations = [
        (4346, 4360, 0, "jurisdiction - para 48 court order item"),
        (789, 840, 2, "legally_relevant_facts - grounds section"),
        (500, 550, 3, "legal_issues - intro section"),
        (893, 905, 4, "reasons - para 7"),
        (1575, 1640, 4, "reasons - para 15 (second instance)"),
        (1640, 1700, 5, "courts_reasoning - para 16 (starts at end of prev)"),
        (4335, 4400, 6, "decision - para 48"),
        (848, 905, 7, "order - overlaps with reasons at 893-905"),
        (2422, 2480, 8, "domestic_sources - para 23"),
        (2480, 2526, 9, "reflection - para 23 (same passage, overlaps)"),
    ]

    for i, (start, end, tag_idx, _desc) in enumerate(annotations):
        _create_highlight(page, start, end, tag_index=tag_idx)
        page.wait_for_timeout(300)  # Let CRDT sync
        expect(cards).to_have_count(initial_count + i + 1, timeout=5000)

    # Comment on jurisdiction card (find by tag name to distinguish from decision card)
    jurisdiction_card = _scroll_to_word_and_find_card(page, 4346, "Jurisdiction")
    _add_comment_to_visible_card(page, jurisdiction_card, "it's excessive")

    return initial_count


def _bob_creates_annotation_and_replies(page: Page, expected_count: int) -> int:
    """Bob adds procedural_history tag to case name and replies to Alice's comment.

    Args:
        page: Bob's browser page
        expected_count: Expected annotation count from Alice

    Returns:
        New total card count after Bob's annotation
    """
    cards = page.locator(".ann-card-positioned")
    expect(cards).to_have_count(expected_count, timeout=10000)

    # Bob annotates case name (words 2-5) with procedural_history tag (index 1)
    _create_highlight(page, 2, 5, tag_index=1)
    page.wait_for_timeout(300)
    new_count = expected_count + 1
    expect(cards).to_have_count(new_count, timeout=5000)

    # Bob comments on Alice's jurisdiction card (find by Alice's comment)
    jurisdiction_card = _scroll_to_word_and_find_card(page, 4346, "it's excessive")
    _add_comment_to_visible_card(page, jurisdiction_card, "no it's not")

    return new_count


def _alice_replies_back(page: Page) -> None:
    """Alice sees Bob's reply and responds."""
    # Find the jurisdiction card with the discussion thread (find by Alice's comment)
    jurisdiction_card = _scroll_to_word_and_find_card(page, 4346, "it's excessive")

    # Wait to see Bob's reply
    expect(jurisdiction_card).to_contain_text("no it's not", timeout=10000)

    # Alice replies
    _add_comment_to_visible_card(page, jurisdiction_card, "yes it is")


def _alice_adds_lipsum_comments(page: Page) -> None:
    """Alice adds multi-paragraph lipsum comments to courts_reasoning annotation."""
    # Find the courts_reasoning card (para 16, around word 1640)
    courts_reasoning_card = _scroll_to_word_and_find_card(page, 1640, "[16]")

    lipsum_paragraphs = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco.",
    ]
    for para in lipsum_paragraphs:
        _add_comment_to_visible_card(page, courts_reasoning_card, para)


def _alice_writes_general_notes(page: Page) -> None:
    """Alice writes acceptance criteria in the general notes editor."""
    notes_section = page.locator("text=General Notes")
    notes_section.scroll_into_view_if_needed()
    expect(notes_section).to_be_visible(timeout=5000)

    # The editor is a Quill WYSIWYG editor
    editor = page.locator(".q-editor__content")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    # Write acceptance criteria so reviewer can verify test proves what it claims
    acceptance_text = """TEST ACCEPTANCE CRITERIA (test_pdf_export.py)

This PDF should demonstrate:

1. ALL 10 TAGS present with distinct highlight colors:
   - Jurisdiction (blue), Procedural History (orange), Legally Relevant Facts,
   - Legal Issues, Reasons (2 instances), Court's Reasoning, Decision,
   - Order, Domestic Sources, Reflection

2. OVERLAPPING HIGHLIGHTS work correctly:
   - Reasons (1575-1640) and Court's Reasoning (1640-1700) share word 1640
   - Domestic Sources (2422-2480) and Reflection (2480-2526) share word 2480
   - Order (848-905) overlaps with Reasons (893-905)

3. MULTI-USER COLLABORATION:
   - Alice's comment "it's excessive" on Jurisdiction
   - Bob's reply "no it's not"
   - Alice's counter "yes it is"

4. MULTI-PARAGRAPH COMMENTS on Court's Reasoning card (3 lipsum paragraphs)

5. MARGIN ANNOTATIONS visible with author names and timestamps

If any of the above is missing or broken, the test has not proven what it claims."""

    page.keyboard.type(acceptance_text)

    expect(editor).to_contain_text("TEST ACCEPTANCE CRITERIA", timeout=5000)


def _alice_exports_pdf(page: Page) -> Path | None:
    """Alice clicks export and captures the downloaded PDF.

    Attempts to intercept the download and save to output/ for inspection.
    Falls back to notification-only verification if download interception fails.

    Returns:
        Path to saved PDF if download was captured, None otherwise.
    """
    export_btn = page.locator("button", has_text="Export PDF")
    export_btn.scroll_into_view_if_needed()
    expect(export_btn).to_be_visible(timeout=5000)

    # Set up download interception BEFORE clicking
    pdf_path: Path | None = None
    try:
        with page.expect_download(timeout=120000) as download_info:
            export_btn.click()
            # Wait for "Generating PDF..." to confirm export started
            expect(page.locator("text=Generating PDF")).to_be_visible(timeout=5000)

        download = download_info.value

        # Save to output directory for inspection
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = _OUTPUT_DIR / "annotated_document.pdf"
        download.save_as(pdf_path)

        # Verify it's a valid PDF
        assert pdf_path.exists(), f"PDF not saved to {pdf_path}"
        with pdf_path.open("rb") as f:
            header = f.read(4)
            assert header == b"%PDF", f"Invalid PDF header: {header!r}"

    except TimeoutError:
        # NiceGUI's ui.download() may not trigger Playwright download in headless mode
        # Fall back to notification-based verification
        pass

    # Always verify via notification (works regardless of download interception)
    page.wait_for_timeout(2000)
    error_locator = page.locator("text=/Export failed/i")
    if error_locator.count() > 0:
        error_text = error_locator.first.text_content()
        raise AssertionError(f"Export failed with error: {error_text}")

    # Wait for success notification (PDF generation can take time with latexmk)
    expect(page.locator("text=PDF generated successfully")).to_be_visible(
        timeout=120000
    )

    return pdf_path


def _setup_user_page(
    context: BrowserContext, app_server: str, doc_url: str, email: str
) -> Page:
    """Create a page, login, and navigate to the shared annotation document."""
    page = context.new_page()
    _login_as_user(page, app_server, email)
    page.goto(doc_url)
    expect(page.locator(".doc-container")).to_be_visible(timeout=15000)
    return page


class TestPdfExportWorkflow:
    """Test the complete PDF export workflow with multi-user collaboration."""

    def test_two_users_collaborate_and_export_pdf(
        self,
        browser: Browser,
        app_server: str,
        live_annotation_url: str,
        reset_crdt_state: None,
    ) -> None:
        """Full workflow: two users annotate with comments, add notes, export PDF.

        Scenario:
        1. Alice creates 10 annotations (all tags) with comment on jurisdiction
        2. Bob joins, adds procedural_history on case name, replies to Alice
        3. Alice replies, adds lipsum to courts_reasoning, writes general notes
        4. Alice exports PDF
        """
        _ = reset_crdt_state

        # Generate unique IDs for test isolation
        test_id = uuid4().hex[:8]
        shared_doc_id = f"test-collab-{test_id}"
        alice_email = f"alice.jones.{test_id}@test.example.edu.au"
        bob_email = f"bob.smith.{test_id}@test.example.edu.au"

        # Both users access the same shared document via URL param
        shared_doc_url = f"{live_annotation_url}?doc={shared_doc_id}"

        context1 = browser.new_context()
        context2 = browser.new_context()

        try:
            # Alice setup and creates 10 annotations (all tags)
            page1 = _setup_user_page(context1, app_server, shared_doc_url, alice_email)
            initial_count = _alice_creates_annotations(page1)
            total_cards = initial_count + 10  # Alice creates 10 annotations

            # Bob joins, adds procedural_history, and replies
            page2 = _setup_user_page(context2, app_server, shared_doc_url, bob_email)
            total_cards = _bob_creates_annotation_and_replies(page2, total_cards)

            # Alice replies back, adds lipsum comments, writes notes, and exports
            _alice_replies_back(page1)
            _alice_adds_lipsum_comments(page1)
            _alice_writes_general_notes(page1)
            pdf_path = _alice_exports_pdf(page1)

            # Report artifact location if captured
            if pdf_path and pdf_path.exists():
                print(f"\nPDF artifact saved to: {pdf_path.absolute()}")

        finally:
            context1.close()
            context2.close()
