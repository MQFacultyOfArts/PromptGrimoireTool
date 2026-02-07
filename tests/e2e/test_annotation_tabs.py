"""E2E tests for three-tab annotation interface.

Tests verify that the annotation page renders three tabs (Annotate, Organise,
Respond), that deferred rendering works for Tabs 2 and 3, and that switching
tabs preserves Tab 1 state.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_01.md
- AC: three-tab-ui.AC1.1 through AC1.4
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import setup_workspace_with_content

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
        """Tabs 2 and 3 show placeholder content until first visit."""
        page = workspace_page

        # Tab 1 (Annotate) should have document content (char spans)
        expect(page.locator("[data-char-index]").first).to_be_visible()

        # Click Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(300)

        # Organise panel should be visible with placeholder
        organise_panel = page.locator("[role='tabpanel']").nth(1)
        expect(organise_panel).to_be_visible()
        expect(organise_panel).to_contain_text("Organise tab content will appear here.")

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
