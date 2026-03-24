"""E2E tests for multi-document tabbed workspace (#186).

Verifies that workspaces with multiple documents render separate
source tabs, that switching tabs shows the correct document content,
and that annotations are isolated per document.

Requires DEV__TEST_DATABASE_URL and a running app server.

Traceability:
- Design: docs/implementation-plans/2026-03-14-multi-doc-tabs-186-plan-a/
- AC: multi-doc-tabs.AC1.1-AC1.6 (tab bar rendering)
- AC: multi-doc-tabs.AC2.1-AC2.5 (per-document isolation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_multi_doc_workspace

if TYPE_CHECKING:
    from playwright.sync_api import Browser


pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.e2e,
]


class TestMultiDocTabRendering:
    """Verify tab bar renders one tab per document plus Organise and Respond."""

    def test_two_documents_show_two_source_tabs(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC1.1: Each document gets its own source tab."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Introduction", "<p>This is the introduction document.</p>"),
                    ("Analysis", "<p>This is the analysis document.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Should have 4 tabs: Source 1, Source 2, Organise, Respond
            tabs = page.locator("[data-testid^='tab-']")
            expect(tabs).to_have_count(4, timeout=5000)

            # Verify source tab labels include titles
            source_1 = page.get_by_test_id("tab-source-1")
            source_2 = page.get_by_test_id("tab-source-2")
            expect(source_1).to_contain_text("Source 1: Introduction")
            expect(source_2).to_contain_text("Source 2: Analysis")

            # Organise and Respond still present
            expect(page.get_by_test_id("tab-organise")).to_be_visible()
            expect(page.get_by_test_id("tab-respond")).to_be_visible()

            # Source 1 is selected by default
            expect(source_1).to_have_attribute("aria-selected", "true")

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocTabSwitching:
    """Verify switching between source tabs shows correct document content."""

    def test_tab_switch_shows_different_content(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC2.1: Switching tabs renders the correct document."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Doc Alpha", "<p>Alpha content unique marker AAAA.</p>"),
                    ("Doc Beta", "<p>Beta content unique marker BBBB.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Source 1 is visible - verify its content
            expect(page.locator("text=Alpha content unique marker AAAA")).to_be_visible(
                timeout=5000
            )

            # Switch to Source 2
            page.get_by_test_id("tab-source-2").click()
            expect(page.locator("text=Beta content unique marker BBBB")).to_be_visible(
                timeout=10000
            )

            # Switch back to Source 1 - content should still be there
            page.get_by_test_id("tab-source-1").click()
            expect(page.locator("text=Alpha content unique marker AAAA")).to_be_visible(
                timeout=5000
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocAnnotationIsolation:
    """Verify annotation cards on one document don't appear on another."""

    def test_card_count_differs_between_tabs(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC2.3: Annotation cards are filtered per document.

        Creates a 2-doc workspace, highlights text on Source 1 via the
        toolbar, then verifies Source 2 shows zero cards.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("First", "<p>First document content here.</p>"),
                    ("Second", "<p>Second document content here.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Select text via mouse drag on Source 1
            doc_text = page.locator(".doc-container p").first
            doc_text.select_text()

            # Click the first tag button in the toolbar to apply highlight
            toolbar_btn = page.locator("[data-tag-id]").first
            toolbar_btn.wait_for(state="visible", timeout=5000)
            toolbar_btn.click()

            # Wait for annotation card to appear on Source 1
            cards = page.locator("[data-testid='annotation-card']")
            expect(cards.first).to_be_visible(timeout=5000)
            assert cards.count() > 0, "Expected at least one annotation card on Doc 1"

            # Switch to Source 2
            page.get_by_test_id("tab-source-2").click()
            wait_for_text_walker(page, timeout=10000)

            # Source 2 should have zero annotation cards
            cards_doc2 = page.locator("[data-testid='annotation-card']")
            expect(cards_doc2).to_have_count(0, timeout=5000)

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
