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

        # Select words by clicking and dragging
        first_word = page.locator("[data-word-index='0']")
        third_word = page.locator("[data-word-index='2']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        third_box = third_word.bounding_box()

        # Drag select
        assert first_box is not None and third_box is not None
        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(third_box["x"] + third_box["width"] - 5, third_box["y"] + 5)
        page.mouse.up()

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

        # Select and highlight
        first_word = page.locator("[data-word-index='0']")
        second_word = page.locator("[data-word-index='1']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        second_box = second_word.bounding_box()

        assert first_box is not None and second_box is not None
        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(second_box["x"] + second_box["width"] - 5, second_box["y"] + 5)
        page.mouse.up()

        # Wait for highlight menu and click the highlight button
        page.locator("[data-testid='highlight-menu']").wait_for(
            state="visible", timeout=5000
        )
        page.get_by_role("button", name=re.compile("highlight", re.IGNORECASE)).click()

        # Words should have highlight styling (background color via CSS)
        # Check for yellow background (rgba(255, 235, 59, 0.5))
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(255,\s*235,\s*59")
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

        # Create highlight
        first_word = page.locator("[data-word-index='0']")
        second_word = page.locator("[data-word-index='1']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        second_box = second_word.bounding_box()

        assert first_box is not None and second_box is not None
        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(second_box["x"] + second_box["width"] - 5, second_box["y"] + 5)
        page.mouse.up()

        page.locator("[data-testid='highlight-menu']").wait_for(
            state="visible", timeout=5000
        )
        page.get_by_role("button", name=re.compile("highlight", re.IGNORECASE)).click()

        # Wait for highlight to be applied (check for background color)
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(255,\s*235,\s*59"), timeout=5000
        )

        # Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # Highlight should still be there (check for background color)
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_css(
            "background-color", re.compile(r"rgba\(255,\s*235,\s*59"), timeout=5000
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

        # 4. Select text and create a highlight on "tort law" (word indices 6-7)
        word_tort = page.locator("[data-word-index='6']")
        word_law = page.locator("[data-word-index='7']")

        word_tort.scroll_into_view_if_needed()
        tort_box = word_tort.bounding_box()
        law_box = word_law.bounding_box()

        assert tort_box is not None and law_box is not None
        page.mouse.move(tort_box["x"] + 5, tort_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(law_box["x"] + law_box["width"] - 5, law_box["y"] + 5)
        page.mouse.up()

        # Wait for highlight menu
        highlight_menu = page.locator("[data-testid='highlight-menu']")
        expect(highlight_menu).to_be_visible(timeout=5000)

        # Create highlight
        page.get_by_role("button", name=re.compile("highlight", re.IGNORECASE)).click()

        # Verify highlight is applied (check for background color)
        expect(word_tort).to_have_css(
            "background-color", re.compile(r"rgba\(255,\s*235,\s*59"), timeout=5000
        )

        # 5. Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # 6. Reload the page
        page.goto(workspace_url)

        # Wait for page to fully load
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # 7. Assert: highlight is still visible
        word_tort_after_reload = page.locator("[data-word-index='6']")
        expect(word_tort_after_reload).to_have_css(
            "background-color", re.compile(r"rgba\(255,\s*235,\s*59"), timeout=5000
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

        def create_highlight(start_idx: int, end_idx: int) -> None:
            """Helper to create a highlight between word indices."""
            highlight_menu = page.locator("[data-testid='highlight-menu']")

            # Ensure menu is hidden before we start a new selection
            highlight_menu.wait_for(state="hidden", timeout=5000)

            start_word = page.locator(f"[data-word-index='{start_idx}']")
            end_word = page.locator(f"[data-word-index='{end_idx}']")

            start_word.scroll_into_view_if_needed()
            start_box = start_word.bounding_box()
            end_box = end_word.bounding_box()

            assert start_box is not None and end_box is not None
            page.mouse.move(start_box["x"] + 5, start_box["y"] + 5)
            page.mouse.down()
            page.mouse.move(end_box["x"] + end_box["width"] - 5, end_box["y"] + 5)
            page.mouse.up()

            # Wait for menu to appear
            highlight_menu.wait_for(state="visible", timeout=5000)
            page.get_by_role(
                "button", name=re.compile("highlight", re.IGNORECASE)
            ).click()

            # Verify highlight was applied by checking background color
            expect(start_word).to_have_css(
                "background-color",
                re.compile(r"rgba\(255,\s*235,\s*59"),
                timeout=5000,
            )

        # Create three highlights
        create_highlight(0, 1)  # "First highlight"
        create_highlight(3, 4)  # "Second highlight"
        create_highlight(6, 7)  # "Third highlight"

        # Wait for "Saved" indicator (observable state)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]", timeout=10000)

        # All three highlights should be visible (check words 0,1,3,4,6,7)
        for idx in [0, 1, 3, 4, 6, 7]:
            word = page.locator(f"[data-word-index='{idx}']")
            expect(word).to_have_css(
                "background-color",
                re.compile(r"rgba\(255,\s*235,\s*59"),
                timeout=5000,
            )
