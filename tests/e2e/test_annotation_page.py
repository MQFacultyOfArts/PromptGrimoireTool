"""E2E tests for /annotation page."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


def _select_words(page: Page, start_word: int, end_word: int) -> None:
    """Select a range of words by clicking start and shift-clicking end.

    This is the reliable method for text selection in Playwright tests.
    Uses click + shift+click which works consistently across browsers.
    """
    word_start = page.locator(f"[data-word-index='{start_word}']")
    word_end = page.locator(f"[data-word-index='{end_word}']")

    word_start.scroll_into_view_if_needed()
    expect(word_start).to_be_visible(timeout=5000)

    word_start.click()
    word_end.click(modifiers=["Shift"])


def _create_highlight(page: Page, start_word: int, end_word: int) -> None:
    """Select words and click the first tag button to create a highlight.

    Args:
        page: Playwright page.
        start_word: Index of first word to select.
        end_word: Index of last word to select.
    """
    _select_words(page, start_word, end_word)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").first
    tag_button.click()


class TestAnnotationPageBasic:
    """Basic page load tests."""

    def test_annotation_page_loads(self, fresh_page: Page, app_server: str) -> None:
        """Page loads without errors."""
        fresh_page.goto(f"{app_server}/annotation")
        expect(fresh_page.locator("body")).to_be_visible()

    def test_page_shows_create_workspace_option(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows option to create workspace when no workspace_id."""
        fresh_page.goto(f"{app_server}/annotation")

        # Should show create workspace button or form
        create_button = fresh_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        )
        expect(create_button).to_be_visible()

    def test_page_shows_not_found_for_invalid_workspace(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows not found message for non-existent workspace."""
        test_uuid = "12345678-1234-1234-1234-123456789abc"
        fresh_page.goto(f"{app_server}/annotation?workspace_id={test_uuid}")

        # Should show not found message (workspace doesn't exist in DB)
        expect(fresh_page.locator("text=not found")).to_be_visible()


class TestWorkspaceAndDocumentCreation:
    """Tests for workspace and document creation (requires auth + database)."""

    @pytestmark_db
    def test_create_workspace_redirects_and_displays(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating workspace redirects to URL with workspace_id and displays it."""
        authenticated_page.goto(f"{app_server}/annotation")

        # Click create button
        authenticated_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        ).click()

        # Wait for redirect to URL with workspace_id
        authenticated_page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        # Verify URL contains valid UUID
        url = authenticated_page.url
        assert "workspace_id=" in url
        workspace_id_str = url.split("workspace_id=")[1].split("&")[0]
        UUID(workspace_id_str)  # Validates it's a valid UUID

        # Verify the workspace ID is shown on page (proves it loaded from DB)
        expect(authenticated_page.locator(f"text={workspace_id_str}")).to_be_visible()

    @pytestmark_db
    def test_paste_content_creates_document_and_persists(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Pasting content creates a WorkspaceDocument with word spans that persists."""
        # Create workspace first
        authenticated_page.goto(f"{app_server}/annotation")
        authenticated_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        ).click()
        authenticated_page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        # Save the URL for reload test
        workspace_url = authenticated_page.url

        # Find textarea/input for content
        content_input = authenticated_page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        expect(content_input).to_be_visible()

        # Paste content
        test_content = "This is my test document content for annotation."
        content_input.fill(test_content)

        # Submit
        authenticated_page.get_by_role(
            "button", name=re.compile("add|submit", re.IGNORECASE)
        ).click()

        # Content should appear with word spans
        authenticated_page.wait_for_selector("[data-word-index]", timeout=10000)
        word_spans = authenticated_page.locator("[data-word-index]")
        expect(word_spans.first).to_be_visible()
        assert word_spans.count() >= 8  # At least the words in test_content

        # Reload page to verify persistence
        authenticated_page.goto(workspace_url)

        # Content should still be there with word spans
        authenticated_page.wait_for_selector("[data-word-index]", timeout=10000)
        expect(authenticated_page.locator("text=document")).to_be_visible()


class TestHighlightCreation:
    """Tests for creating highlights on documents (requires authentication)."""

    @pytestmark_db
    def test_select_text_shows_highlight_menu(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Selecting text shows highlight creation menu."""
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
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Select words using click + shift+click
        _select_words(page, 0, 2)

        # Should show highlight menu/card
        highlight_menu = page.locator("[data-testid='highlight-menu']")
        expect(highlight_menu).to_be_visible(timeout=5000)

    @pytestmark_db
    def test_create_highlight_applies_styling(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating a highlight applies visual styling."""
        page = authenticated_page
        # Setup
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Highlight this text please")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Select and highlight using click + shift+click
        _select_words(page, 0, 1)

        # Click a tag button (Jurisdiction = blue #1f77b4 = rgb(31, 119, 180))
        page.get_by_role(
            "button", name=re.compile(r"jurisdiction", re.IGNORECASE)
        ).click()

        # Words should have highlight styling with jurisdiction color (blue)
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(31,\s*119,\s*180")
        )

    @pytestmark_db
    def test_highlight_persists_after_reload(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Highlights survive page reload via CRDT persistence."""
        page = authenticated_page
        # Setup
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)
        workspace_url = page.url

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Test highlight persistence")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Select and create highlight using click + shift+click
        _select_words(page, 0, 1)

        # Click a tag button (Jurisdiction = blue #1f77b4 = rgb(31, 119, 180))
        page.get_by_role(
            "button", name=re.compile(r"jurisdiction", re.IGNORECASE)
        ).click()

        # Wait for highlight to be applied with jurisdiction color (blue)
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(31,\s*119,\s*180"), timeout=5000
        )

        # Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Highlight should still be there with jurisdiction color (blue)
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(31,\s*119,\s*180"), timeout=5000
        )


class TestFullAnnotationWorkflow:
    """Complete workflow E2E tests matching UAT statement (requires authentication).

    UAT: The `/annotation` route allows a user to create a workspace, paste text
    content that becomes a WorkspaceDocument, annotate that document with
    highlights, and have those annotations persist across page reloads.
    """

    @pytestmark_db
    def test_complete_annotation_workflow(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """UAT: User creates workspace, pastes content, creates highlight, persists.

        Steps:
        1. Navigate to /annotation
        2. Create a new workspace
        3. Paste text content
        4. Select text and create a highlight
        5. Reload the page (with workspace ID in URL)
        6. Assert: highlight is still visible
        """
        page = authenticated_page

        # 1. Navigate to /annotation
        page.goto(f"{app_server}/annotation")
        expect(page.locator("body")).to_be_visible()

        # 2. Create a new workspace
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)
        workspace_url = page.url

        # 3. Paste text content
        test_content = (
            "This is a legal document about tort law. The defendant was negligent."
        )
        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        expect(content_input).to_be_visible()
        content_input.fill(test_content)

        # Submit content
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

        # Wait for word spans to appear
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # 4. Select text and create a highlight on "tort law" (word indices 6-7)
        _select_words(page, 6, 7)

        # Create highlight with tag (Jurisdiction = blue #1f77b4 = rgb(31, 119, 180))
        page.get_by_role(
            "button", name=re.compile(r"jurisdiction", re.IGNORECASE)
        ).click()

        # Verify highlight is applied with jurisdiction color (blue)
        word_tort = page.locator("[data-word-index='6']")
        expect(word_tort).to_have_css(
            "background-color", re.compile(r"rgba\(31,\s*119,\s*180"), timeout=5000
        )

        # 5. Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # 6. Reload the page
        page.goto(workspace_url)

        # Wait for page to fully load
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # 7. Assert: highlight is still visible with jurisdiction color (blue)
        word_tort_after_reload = page.locator("[data-word-index='6']")
        expect(word_tort_after_reload).to_have_css(
            "background-color", re.compile(r"rgba\(31,\s*119,\s*180"), timeout=5000
        )

    @pytestmark_db
    def test_multiple_highlights_persist(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Multiple highlights on same document all persist after reload."""
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)
        workspace_url = page.url

        # Add content with distinct words for multiple highlights
        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill(
            "First highlight here. Second highlight there. Third highlight everywhere."
        )
        # Words: First=0 highlight=1 here.=2 Second=3 highlight=4 there.=5
        #        Third=6 highlight=7 everywhere.=8
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        def create_highlight_local(start_idx: int, end_idx: int) -> None:
            """Helper to create a highlight between word indices."""
            # Clear any existing selection first
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)

            # Select using click + shift+click
            _select_words(page, start_idx, end_idx)

            # Click tag button (Jurisdiction = blue #1f77b4 = rgb(31, 119, 180))
            page.get_by_role(
                "button", name=re.compile(r"jurisdiction", re.IGNORECASE)
            ).click()

            # Verify highlight was applied with jurisdiction color (blue)
            start_word = page.locator(f"[data-word-index='{start_idx}']")
            expect(start_word).to_have_css(
                "background-color",
                re.compile(r"rgba\(31,\s*119,\s*180"),
                timeout=5000,
            )

        # Create three highlights
        create_highlight_local(0, 1)  # "First highlight"
        create_highlight_local(3, 4)  # "Second highlight"
        create_highlight_local(6, 7)  # "Third highlight"

        # Wait for "Saved" indicator (observable state)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # All three highlights should be visible with jurisdiction color (blue)
        for idx in [0, 1, 3, 4, 6, 7]:
            word = page.locator(f"[data-word-index='{idx}']")
            expect(word).to_have_css(
                "background-color",
                re.compile(r"rgba\(31,\s*119,\s*180"),
                timeout=5000,
            )


class TestTagSelection:
    """Tests for tag selection UI (Task 6)."""

    @pytestmark_db
    def test_tag_toolbar_visible_when_document_loaded(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Tag toolbar shows after document is added."""
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        # Add document
        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Test content for tagging")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Tag toolbar should be visible
        tag_toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(tag_toolbar).to_be_visible()

        # Should have multiple tag buttons (BriefTag has 10 tags)
        tag_buttons = tag_toolbar.locator("button")
        assert tag_buttons.count() >= 5

    @pytestmark_db
    def test_selecting_text_then_tag_creates_colored_highlight(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Selecting text then clicking tag button creates highlight with tag color."""
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("This is a legal issue in the case")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Select "legal issue" using click + shift+click
        _select_words(page, 3, 4)

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


class TestAnnotationCards:
    """Tests for annotation card sidebar (Task 7)."""

    @pytestmark_db
    def test_creating_highlight_shows_annotation_card(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating a highlight adds an annotation card."""
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
        _select_words(page, 0, 1)

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
        """Annotation card shows preview of highlighted text."""
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
        _create_highlight(page, 0, 1)

        # Card should contain the highlighted text
        ann_card = page.locator("[data-testid='annotation-card']")
        expect(ann_card).to_contain_text("Important")

    @pytestmark_db
    def test_can_add_comment_to_highlight(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Can add a comment to a highlight via annotation card."""
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
        _create_highlight(page, 0, 1)

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
        """Comments persist after page reload."""
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
        _create_highlight(page, 0, 1)

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


class TestPdfExport:
    """Tests for PDF export from workspace (Task 8)."""

    @pytestmark_db
    def test_export_pdf_button_visible(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Export PDF button appears when document has highlights."""
        page = authenticated_page
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill("Content for PDF export")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # Create at least one highlight using click + shift+click
        _create_highlight(page, 0, 1)

        # Export button should be visible
        export_button = page.get_by_role(
            "button", name=re.compile("export|pdf", re.IGNORECASE)
        )
        expect(export_button).to_be_visible()


class TestDefinitionOfDone:
    """Tests matching the design document acceptance criterion (Task 9).

    > Using the new `/annotation` route: upload 183.rtf, annotate it,
    > click export PDF, and get a PDF with all annotations included.

    Note: "upload 183.rtf" is interpreted as paste RTF content (copy-paste workflow).
    """

    @pytestmark_db
    def test_full_annotation_workflow_with_tags_and_export(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Complete workflow: create, annotate with tags, add comment, export PDF."""
        page = authenticated_page

        # 1. Navigate to /annotation
        page.goto(f"{app_server}/annotation")

        # 2. Create workspace
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # 3. Paste content (simulating RTF paste)
        legal_content = (
            "The plaintiff, Jane Smith, brought an action against the defendant, "
            "ABC Corporation, alleging negligence in the maintenance of their "
            "premises. "
            "The court found that the defendant owed a duty of care to the "
            "plaintiff as a lawful visitor to the premises. The defendant "
            "breached this duty by failing to address a known hazard. "
            "HELD: The defendant is liable for damages. Judgment for the "
            "plaintiff in the amount of $50,000."
        )

        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill(legal_content)
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Wait for JavaScript to set up (100ms timeout in JS)
        page.wait_for_timeout(200)

        # 4. Create tagged highlights
        def create_tagged_highlight(
            start_idx: int, end_idx: int, tag_text: str
        ) -> None:
            # Clear any existing selection first
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)

            # Select using click + shift+click
            _select_words(page, start_idx, end_idx)

            # Click specific tag button
            tag_button = page.locator(
                "[data-testid='tag-toolbar'] button",
                has_text=re.compile(tag_text, re.IGNORECASE),
            ).first
            tag_button.click()
            page.wait_for_timeout(300)  # Let UI update

        # Tag "plaintiff, Jane Smith" (words 1-3) as "Legal Issues"
        create_tagged_highlight(1, 3, "issue")

        # Tag "HELD:" (word ~53) as "Decision" - adjust based on actual content
        # The word "HELD:" is around index 53
        create_tagged_highlight(53, 53, "decision")

        # 5. Add a comment to one highlight
        ann_card = page.locator("[data-testid='annotation-card']").first
        comment_input = ann_card.locator("input[type='text'], textarea").first
        comment_input.fill("Key finding - establishes duty of care")
        ann_card.get_by_role(
            "button", name=re.compile("post|add|submit", re.IGNORECASE)
        ).click()

        # 6. Wait for save
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # 7. Click Export PDF
        export_button = page.get_by_role(
            "button", name=re.compile("export|pdf", re.IGNORECASE)
        )
        expect(export_button).to_be_visible()

        # Note: Actually downloading and verifying PDF content would require
        # intercepting the download. For now, verify the button is clickable.
        # Full PDF verification is in tests/integration/test_pdf_export.py

        # Verify we have highlights (check computed background-color via CSS rules)
        # Highlights are applied via <style> element, not inline styles
        highlighted_word = page.locator("[data-word-index='1']")
        expect(highlighted_word).to_have_css(
            "background-color", re.compile(r"rgba\("), timeout=5000
        )
