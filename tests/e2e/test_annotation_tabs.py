"""E2E tests for three-tab annotation interface.

Tests verify that the annotation page renders three tabs (Annotate, Organise,
Respond), that deferred rendering works for Tabs 2 and 3, and that switching
tabs preserves Tab 1 state. Phase 3 adds tests for Tag 2 tag columns and
highlight cards.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_01.md
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md
- AC: three-tab-ui.AC1.1 through AC1.4
- AC: three-tab-ui.AC2.1, AC2.2, AC2.6
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight,
    setup_workspace_with_content,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page


# Skip if no database configured
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture
def workspace_page(authenticated_page: Page, app_server: str) -> Generator[Page]:
    """Authenticated page with a workspace containing document content.

    Reuses the authenticated_page fixture and setup_workspace_with_content helper
    to create a workspace with plain text content. Yields a page ready for tab testing.
    """
    setup_workspace_with_content(
        authenticated_page,
        app_server,
        "Tab test content for annotation workspace verification",
    )
    yield authenticated_page


class TestTabHeaders:
    """Verify three tab headers render with correct names and default selection.

    Verifies: three-tab-ui.AC1.1
    """

    @pytestmark_db
    def test_tab_headers(self, workspace_page: Page) -> None:
        """Page renders Annotate, Organise, Respond tabs with Annotate selected."""
        page = workspace_page

        # Assert three tab elements exist
        tabs = page.locator("role=tab")
        expect(tabs).to_have_count(3, timeout=5000)

        # Verify tab names
        expect(tabs.nth(0)).to_contain_text("Annotate")
        expect(tabs.nth(1)).to_contain_text("Organise")
        expect(tabs.nth(2)).to_contain_text("Respond")

        # Verify Annotate is the selected/active tab
        annotate_tab = tabs.nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true")


class TestDeferredRendering:
    """Verify that Tab 2 and Tab 3 use deferred rendering.

    Verifies: three-tab-ui.AC1.3
    """

    @pytestmark_db
    def test_deferred_rendering(self, workspace_page: Page) -> None:
        """Tabs 2 and 3 render content on first visit (deferred rendering).

        Tab 2 (Organise) renders tag columns on first visit.
        Tab 3 (Respond) still shows placeholder until Phase 5.
        """
        page = workspace_page

        # Tab 1 (Annotate) should have document content (char spans)
        expect(page.locator("[data-char-index]").first).to_be_visible()

        # Click Organise tab -- triggers deferred render of tag columns
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Organise panel should show tag columns (Phase 3 replaced placeholder)
        organise_panel = page.locator("[role='tabpanel']").nth(1)
        expect(organise_panel).to_be_visible()
        expect(
            organise_panel.locator('[data-testid="organise-columns"]')
        ).to_be_visible(timeout=3000)

        # Click Respond tab
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(300)

        # Respond panel should be visible with placeholder
        respond_panel = page.locator("[role='tabpanel']").nth(2)
        expect(respond_panel).to_be_visible()
        expect(respond_panel).to_contain_text("Respond tab content will appear here.")


class TestTabStatePreservation:
    """Verify Tab 1 state is preserved when switching tabs.

    Verifies: three-tab-ui.AC1.2, three-tab-ui.AC1.4
    """

    @pytestmark_db
    def test_document_content_preserved_after_tab_switch(
        self, workspace_page: Page
    ) -> None:
        """Document content in Tab 1 survives round-trip to Tab 2 and back."""
        page = workspace_page

        # Verify content is visible in Tab 1
        char_spans = page.locator("[data-char-index]")
        initial_count = char_spans.count()
        assert initial_count > 0, "Expected char spans in Tab 1"

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(300)

        # Switch back to Annotate tab
        page.locator("role=tab").nth(0).click()
        page.wait_for_timeout(300)

        # Verify document content is still there
        char_spans_after = page.locator("[data-char-index]")
        expect(char_spans_after.first).to_be_visible(timeout=3000)
        assert char_spans_after.count() == initial_count, (
            f"Char span count changed: {initial_count} -> {char_spans_after.count()}"
        )


class TestOrganiseTabColumns:
    """Verify Tab 2 shows tag columns with correct structure.

    Verifies: three-tab-ui.AC2.1
    """

    @pytestmark_db
    def test_organise_tab_shows_tag_columns(self, workspace_page: Page) -> None:
        """Navigate to Organise tab and verify tag column headers appear.

        Creates a highlight first to ensure the tab has content, then
        switches to Organise tab and checks for tag column headers.
        """
        page = workspace_page

        # Create a highlight on the first few characters
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Verify the organise columns container exists
        columns = page.locator('[data-testid="organise-columns"]')
        expect(columns).to_be_visible(timeout=3000)

        # Verify at least one tag column exists
        tag_columns = page.locator('[data-testid="tag-column"]')
        expect(tag_columns.first).to_be_visible(timeout=3000)

        # Verify "Jurisdiction" column exists (first tag)
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible()

    @pytestmark_db
    def test_organise_tab_highlight_in_correct_column(
        self, workspace_page: Page
    ) -> None:
        """Create a highlight with a tag, verify it appears in the correct column."""
        page = workspace_page

        # create_highlight clicks first tag button (Jurisdiction)
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # The highlight should appear as a card in the Jurisdiction column
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible(timeout=3000)
        cards_in_col = jurisdiction_col.locator('[data-testid="organise-card"]')
        expect(cards_in_col).to_have_count(1, timeout=3000)

    @pytestmark_db
    def test_organise_tab_card_shows_author_and_text(
        self, workspace_page: Page
    ) -> None:
        """Create a highlight, verify the card shows author and text snippet."""
        page = workspace_page

        # Create a highlight
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Find the organise card
        card = page.locator('[data-testid="organise-card"]').first
        expect(card).to_be_visible(timeout=3000)

        # Card should show "by" author text
        expect(card).to_contain_text("by ")

        # Card should contain a text snippet (quoted text from the highlight)
        # The highlight text is the first few chars of "Tab test content..."
        expect(card.locator(".italic")).to_be_visible()

    @pytestmark_db
    def test_organise_tab_untagged_highlight_in_untagged_column(self) -> None:
        """Create a highlight without a tag, verify it appears in Untagged column.

        Verifies: three-tab-ui.AC2.6
        Note: This test depends on being able to create a highlight with no tag.
        If the UI always assigns a tag, this test will need adjustment.
        The unit test test_untagged_highlights_collected covers the logic path.
        """
        pytest.skip("No UI mechanism to create untagged highlights yet")
